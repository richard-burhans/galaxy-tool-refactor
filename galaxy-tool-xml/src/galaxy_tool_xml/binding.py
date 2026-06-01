"""Parse and validate entry points, plus the result and error types.

Parsing and validation live together because validation parses first and both
share the ``XmlError`` type. The result-returning functions (``parse_tool``,
``validate_tool``) are the preferred API and never raise on malformed XML —
they collect every error into their result. ``load_tool`` is the strict
variant, raising ``ToolXmlSyntaxError`` instead.

XML is always read into ``bytes`` once and parsed once, never decoded to ``str``
first, so lxml honours the document's own encoding declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from lxml import etree

from galaxy_tool_xml.document import MacroDocument, ToolDocument
from galaxy_tool_xml.macros import (
    MacroError,
    expand_from_path,
    expand_from_tree,
    has_macros,
    strip_macros,
)
from galaxy_tool_xml.profiles import (
    available_profiles,
    compiled_schema,
    resolve_profile,
)

Source = str | Path | bytes | BinaryIO

_MACRO_MODES = frozenset({"off", "skip", "strip", "expand"})
_STRING_SOURCE = "<string>"


@dataclass(frozen=True)
class XmlError:
    """A single XML well-formedness or XSD-validation error."""

    line: int
    column: int
    message: str
    source: str

    def __str__(self) -> str:
        return f"{self.source}:{self.line}:{self.column}: {self.message}"


@dataclass(frozen=True)
class ParseResult:
    """The outcome of a lenient parse."""

    document: ToolDocument | None
    syntax_errors: list[XmlError]

    @property
    def well_formed(self) -> bool:
        """Whether the source parsed with no well-formedness errors."""
        return not self.syntax_errors


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of a profile-aware validation."""

    validated: bool
    schema_version: str
    declared_profile: str | None
    macro_handling: str
    macros_present: bool
    syntax_errors: list[XmlError]
    errors: list[XmlError]
    macro_errors: list[MacroError]

    @property
    def valid(self) -> bool:
        """Whether validation ran and found no errors of any kind."""
        return (
            self.validated
            and not self.syntax_errors
            and not self.errors
            and not self.macro_errors
        )


class ToolXmlSyntaxError(Exception):
    """Raised by ``load_tool`` when the source XML is not well-formed."""

    def __init__(self, errors: list[XmlError]) -> None:
        self.errors = errors
        detail = "; ".join(str(error) for error in errors) or "malformed tool XML"
        super().__init__(detail)


def _read_source(source: Source) -> tuple[bytes, Path | None, str]:
    """Read a source into ``(xml_bytes, source_path, source_label)``."""
    if isinstance(source, bytes):
        return source, None, _STRING_SOURCE
    if isinstance(source, str | Path):
        path = Path(source)
        return path.read_bytes(), path, str(path)
    return source.read(), None, _STRING_SOURCE


def _to_xml_error(entry: etree._LogEntry, source: str) -> XmlError:
    """Convert one lxml error-log entry to an ``XmlError``."""
    return XmlError(
        line=entry.line,
        column=entry.column,
        message=entry.message,
        source=source,
    )


def _parse_bytes(
    xml_bytes: bytes, source: str
) -> tuple[etree._ElementTree | None, list[XmlError]]:
    """Parse XML bytes leniently, collecting every well-formedness error.

    CDATA and comments are preserved (``strip_cdata=False``). The parser's error
    log is snapshotted immediately, before anything else touches the parser.
    """
    parser = etree.XMLParser(recover=True, strip_cdata=False)
    # third-party API: no LBYL form — lxml's recover=True parser still raises
    # XMLSyntaxError on pathological input that the recovery path cannot
    # salvage (e.g., a completely binary file with no XML structure).
    try:
        root = etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError:
        root = None
    syntax_errors = [_to_xml_error(entry, source) for entry in parser.error_log]
    if root is None:
        if not syntax_errors:
            syntax_errors = [XmlError(0, 0, "document could not be parsed", source)]
        return None, syntax_errors
    return root.getroottree(), syntax_errors


def load_tool(source: Source) -> ToolDocument:
    """Parse a tool strictly; raise ``ToolXmlSyntaxError`` if it is malformed."""
    xml_bytes, source_path, label = _read_source(source)
    tree, syntax_errors = _parse_bytes(xml_bytes, label)
    if tree is None or syntax_errors:
        raise ToolXmlSyntaxError(syntax_errors)
    return ToolDocument(tree, source_path=source_path)


def parse_tool(source: Source) -> ParseResult:
    """Parse a tool leniently, collecting every well-formedness error.

    A ``ToolDocument`` is still built from the recovered tree whenever recovery
    yields a usable root.
    """
    xml_bytes, source_path, label = _read_source(source)
    tree, syntax_errors = _parse_bytes(xml_bytes, label)
    document = None if tree is None else ToolDocument(tree, source_path=source_path)
    return ParseResult(document=document, syntax_errors=syntax_errors)


def load_macros(source: Source) -> MacroDocument:
    """Parse a macro-library file strictly; raise ``ToolXmlSyntaxError`` if malformed.

    The macro-file counterpart to ``load_tool``. A macro library (a ``<macros>``
    root holding ``<token>`` / ``<xml>`` / ``<macro>`` / ``<import>``) has no
    standalone XSD, so this only parses — there is no ``validate`` for macro
    files. The returned ``MacroDocument`` carries the mutable tree (CDATA,
    comments, and attribute order preserved) and ``source_path``. The root tag
    is not enforced; callers that need to distinguish a macro file from a tool
    inspect ``document.root.tag``.
    """
    xml_bytes, source_path, label = _read_source(source)
    tree, syntax_errors = _parse_bytes(xml_bytes, label)
    if tree is None or syntax_errors:
        raise ToolXmlSyntaxError(syntax_errors)
    return MacroDocument(tree, source_path=source_path)


def _source_label(document: ToolDocument) -> str:
    """Return the error-message source label for a document."""
    return str(document.source_path) if document.source_path else _STRING_SOURCE


def _schema_errors(
    schema: etree.XMLSchema, tree: etree._ElementTree, source: str
) -> list[XmlError]:
    """Validate a tree against a compiled schema; return any schema errors."""
    if schema.validate(tree):
        return []
    return [_to_xml_error(entry, source) for entry in schema.error_log]


def _tree_to_validate(
    document: ToolDocument,
    *,
    macro_handling: str,
    macros_present: bool,
    path_target: Path | None,
) -> tuple[etree._ElementTree | None, list[MacroError]]:
    """Select the tree to validate per ``macro_handling``.

    Returns ``(tree, macro_errors)``; a ``None`` tree means XSD validation must
    be skipped (``skip`` mode with macros, or expansion produced no tree).
    """
    if not macros_present or macro_handling == "off":
        return document.tree, []
    if macro_handling == "skip":
        return None, []
    if macro_handling == "strip":
        return strip_macros(document.tree), []
    if path_target is not None:
        return expand_from_path(path_target)
    source_dir = document.source_path.parent if document.source_path else None
    return expand_from_tree(document.root, source_dir=source_dir)


def validate_tool(
    target: Source | ToolDocument,
    *,
    profile: str | None = None,
    on_missing: str = "nearest",
    macro_handling: str = "expand",
) -> ValidationResult:
    """Validate a tool against the profile-appropriate vendored XSD.

    ``target`` is a source (path, ``bytes``, or binary stream) or an already
    parsed ``ToolDocument``. The profile is resolved from ``profile``, then the
    tool's own ``profile`` attribute, then — when neither is set — Galaxy's
    ``16.01`` legacy default, which resolves to the nearest vendored XSD (``16.10``,
    the oldest). See ``profiles.resolve_profile`` / ``docs/decisions.md`` §1.5.

    Because the Galaxy XSD is a post-macro-expansion schema, ``macro_handling``
    controls how macros are dealt with before validation: ``off`` validates the
    tree as-is, ``skip`` skips validation when macros are present, ``strip``
    validates the tree with ``<expand>``/``<macros>`` removed, and ``expand``
    (the default) validates the fully expanded tool. The ``ToolDocument``'s tree
    is never mutated. Raises ``UnknownProfileError`` only when
    ``on_missing="exact"``.
    """
    if macro_handling not in _MACRO_MODES:
        raise ValueError(f"macro_handling must be one of {sorted(_MACRO_MODES)}")

    if isinstance(target, ToolDocument):
        document: ToolDocument | None = target
        syntax_errors: list[XmlError] = []
        path_target = None
    else:
        result = parse_tool(target)
        document = result.document
        syntax_errors = result.syntax_errors
        path_target = Path(target) if isinstance(target, str | Path) else None

    if document is None:
        return ValidationResult(
            validated=False,
            schema_version="",
            declared_profile=None,
            macro_handling=macro_handling,
            macros_present=False,
            syntax_errors=syntax_errors,
            errors=[],
            macro_errors=[],
        )

    declared_profile = document.profile
    macros_present = has_macros(document.root)
    schema_version = resolve_profile(
        profile if profile is not None else declared_profile, on_missing=on_missing
    )
    tree, macro_errors = _tree_to_validate(
        document,
        macro_handling=macro_handling,
        macros_present=macros_present,
        path_target=path_target,
    )

    if tree is None:
        return ValidationResult(
            validated=False,
            schema_version=schema_version,
            declared_profile=declared_profile,
            macro_handling=macro_handling,
            macros_present=macros_present,
            syntax_errors=syntax_errors,
            errors=[],
            macro_errors=macro_errors,
        )

    errors = _schema_errors(
        compiled_schema(schema_version), tree, _source_label(document)
    )
    return ValidationResult(
        validated=True,
        schema_version=schema_version,
        declared_profile=declared_profile,
        macro_handling=macro_handling,
        macros_present=macros_present,
        syntax_errors=syntax_errors,
        errors=errors,
        macro_errors=macro_errors,
    )


def newest_valid_profile(target: Source | ToolDocument) -> str | None:
    """Return the newest vendored profile whose XSD the tool satisfies.

    The tool is validated — with macros expanded — against each vendored profile
    from newest to oldest, and the first profile that validates cleanly is
    returned. ``None`` means no vendored profile validates, including when the
    tool is malformed or its macros cannot be expanded.

    The scan stops at the first (newest) profile that validates and assumes
    nothing about the older ones — a tool's valid profiles are often *not* a
    contiguous range of releases (2.58% have gaps; see
    ``docs/decisions.md`` §10.3). It is O(1) when the tool validates at the
    latest profile, which is the case for 90.1% of unique tools in the
    2026-05-27 combined sweep (§10.5).
    """
    # Prefer a filesystem path: validate_tool then resolves macros via
    # expand_from_path, which follows transitive <import>s. A ToolDocument may
    # carry a mutated tree, so it is validated as-is.
    if isinstance(target, str | Path):
        probe: Source | ToolDocument = Path(target)
    elif isinstance(target, ToolDocument):
        probe = target
    else:
        parsed = parse_tool(target).document
        if parsed is None:
            return None
        probe = parsed
    for version in reversed(available_profiles()):
        if validate_tool(probe, profile=version).valid:
            return version
    return None
