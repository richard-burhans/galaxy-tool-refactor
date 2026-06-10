"""Galaxy macro detection, stripping, and expansion.

This is the **only** module that imports ``galaxy.util.xml_macros``, isolating
the coupling to Galaxy's internal API behind a single adapter. Every exception
raised by that internal API is caught here and converted to a ``MacroError`` —
a Galaxy exception never escapes this module.

The Galaxy tool XSD is a *post-macro-expansion* schema, so ``validate_tool``
transforms a tool through these functions into a throwaway copy before
validating. The throwaway tree's loss of comments and whitespace (Galaxy's
parser strips them) does not matter — it is used only for validation.
"""

from __future__ import annotations

import copy
import logging
import shutil
import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from galaxy.util.xml_macros import load_with_references
from lxml import etree

from galaxy_tool_source.document import ToolDocument

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MacroError:
    """A single macro-expansion failure (cycle, missing macro, bad ``<import>``)."""

    message: str
    source: str | None = None

    def __str__(self) -> str:
        message = " ".join(self.message.split())
        if self.source:
            return f"{self.source}: {message}"
        return message


def has_macros(root: etree._Element) -> bool:
    """Return whether the tree uses macros — any ``<expand>`` or a ``<macros>``."""
    if root.find("macros") is not None:
        return True
    return root.find(".//expand") is not None


def strip_macros(tree: etree._ElementTree) -> etree._ElementTree:
    """Return a deep copy with every ``<expand>`` and ``<macros>`` removed.

    The input tree is never modified.
    """
    copied = copy.deepcopy(tree)
    root = copied.getroot()
    for tag in ("expand", "macros"):
        for element in list(root.iter(tag)):
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
    return copied


@dataclass(frozen=True)
class TokenDefinition:
    """A ``<token name="@X@">value</token>`` defined for a tool.

    Attributes:
        name: The token name as written, including the ``@`` delimiters
            (e.g. ``"@TOOL_VERSION@"``).
        value: The token's text value, whitespace-stripped.
        source: The macro file the token is defined in, or ``None`` when it is
            defined inline in the tool's own ``<macros>`` block.
        sourceline: 1-based line of the ``<token>`` element in its file, or
            ``0`` if unknown.
    """

    name: str
    value: str
    source: Path | None
    sourceline: int


def _parse_root(path: Path, /) -> etree._Element | None:
    """Parse *path* leniently and return its root element, or ``None``.

    Shared by the macro-file resolution helpers. ``recover=True`` matches the
    lenient parse used elsewhere; a missing file, I/O error, or unrecoverable
    XML yields ``None``.
    """
    if not path.is_file():
        return None
    parser = etree.XMLParser(recover=True, strip_cdata=False)
    try:
        with path.open("rb") as handle:
            tree = etree.parse(handle, parser)
    except (etree.XMLSyntaxError, OSError):
        return None
    return tree.getroot()


def _root_and_dir(
    target: ToolDocument | Path, /
) -> tuple[etree._Element | None, Path | None]:
    """Resolve *target* to ``(root element, base directory)`` for import walks.

    A ``ToolDocument`` contributes its root and ``source_path``'s directory (or
    ``None`` when it was parsed from bytes/stream and has no origin); a ``Path``
    is parsed leniently and contributes its own parent directory.
    """
    if isinstance(target, ToolDocument):
        source_path = target.source_path
        return target.root, source_path.parent if source_path is not None else None
    return _parse_root(target), target.parent


def imported_macro_paths(target: ToolDocument | Path, /) -> list[Path]:
    """Return the macro files *target* imports, transitively, in import order.

    Resolves every ``<macros><import>`` of the tool — and, recursively, the
    ``<import>``s of each imported macro file (each resolved against *its own*
    directory, matching Galaxy) — to existing, de-duplicated, absolute paths.
    LBYL: an ``<import>`` that is absolute, escapes its directory with ``..``,
    or points at a missing file is skipped. Returns ``[]`` when *target* has no
    source directory (in-memory ``ToolDocument``) or imports nothing.

    *target* is a ``ToolDocument`` or a filesystem ``Path`` — resolution needs a
    location on disk, so raw bytes/streams are out of scope.
    """
    root, base_dir = _root_and_dir(target)
    if root is None or base_dir is None:
        return []
    resolved: list[Path] = []
    seen: set[Path] = set()
    frontier: deque[tuple[etree._Element, Path]] = deque([(root, base_dir)])
    while frontier:
        element, current_dir = frontier.popleft()
        for relative in _import_targets(element):
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                continue
            macro_path = (current_dir / relative_path).resolve()
            if macro_path in seen or not macro_path.is_file():
                continue
            seen.add(macro_path)
            resolved.append(macro_path)
            imported_root = _parse_root(macro_path)
            if imported_root is not None:
                frontier.append((imported_root, macro_path.parent))
    return resolved


def _tokens_in(
    root: etree._Element, *, source: Path | None
) -> list[TokenDefinition]:
    """Collect the top-level ``<token>`` definitions of a tool or macro root."""
    elements = (
        root.findall("token")
        if root.tag == "macros"
        else root.findall("macros/token")
    )
    definitions: list[TokenDefinition] = []
    for element in elements:
        name = element.get("name")
        if name is None:
            continue
        value = element.text.strip() if element.text else ""
        definitions.append(
            TokenDefinition(name, value, source, element.sourceline or 0)
        )
    return definitions


def token_definitions(target: ToolDocument | Path, /) -> list[TokenDefinition]:
    """Return every ``<token>`` defined for *target*, inline then imported.

    Collects the tool's own inline ``<macros><token>`` definitions (``source``
    ``None``) followed by the ``<token>``s of each transitively-imported macro
    file (``source`` the file's path), in import order. This is the lookup a
    token-aware codemod uses to find where a ``@TOKEN@`` reference — e.g. a
    ``profile="@PROFILE@"`` — is actually defined. Token *precedence* when a name
    is defined more than once is left to the caller (the common case is a single
    definition).
    """
    root, _base_dir = _root_and_dir(target)
    definitions: list[TokenDefinition] = []
    if root is not None:
        definitions.extend(_tokens_in(root, source=None))
    for macro_path in imported_macro_paths(target):
        imported_root = _parse_root(macro_path)
        if imported_root is not None:
            definitions.extend(_tokens_in(imported_root, source=macro_path))
    return definitions


def _load_with_references(
    file_path: Path, *, error_source: str | None, log_label: str
) -> tuple[etree._ElementTree | None, list[MacroError]]:
    """Call ``galaxy.util.xml_macros.load_with_references`` and catch anything.

    Both ``expand_from_path`` and ``expand_from_tree`` need the same
    "call the adapter, log a warning on failure, wrap the failure as a
    ``MacroError``" sequence; this helper carries the only sanctioned
    broad-except in the module so the caller sites stay one-liners.
    """
    # third-party API: no LBYL form — galaxy.util.xml_macros raises a wide
    # variety of internal exceptions (cycle, missing macro, malformed XML)
    # and isolating that here is the whole point of the macros.py adapter.
    try:
        expanded, _imported = load_with_references(str(file_path))
    except Exception as error:  # noqa: BLE001 — galaxy.util adapter boundary
        logger.warning("macro expansion failed for %s: %s", log_label, error)
        failure = MacroError(f"macro expansion failed: {error}", source=error_source)
        return None, [failure]
    return expanded, []


def expand_from_path(
    path: Path,
) -> tuple[etree._ElementTree | None, list[MacroError]]:
    """Expand a tool's macros, reading it and its ``<import>``s from disk.

    ``<import>``s resolve against the file's own directory. Returns the expanded
    tree (or ``None`` on failure) and any errors.
    """
    return _load_with_references(path, error_source=str(path), log_label=str(path))


def expand_from_tree(
    root: etree._Element, *, source_dir: Path | None
) -> tuple[etree._ElementTree | None, list[MacroError]]:
    """Expand the macros of an in-memory (possibly mutated) tool tree.

    The tree is serialised to a temp directory; each ``<import>``ed macro file
    is copied in beside it, resolved against ``source_dir``. With
    ``source_dir=None`` external ``<import>``s cannot be resolved — inline
    macros still expand and a ``MacroError`` records the limitation.
    """
    errors: list[MacroError] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        tool_path = tmp_dir / "tool.xml"
        tool_path.write_bytes(etree.tostring(root))
        errors.extend(_stage_imports(root, source_dir=source_dir, tmp_dir=tmp_dir))
        expanded, expand_errors = _load_with_references(
            tool_path, error_source=None, log_label="in-memory tree"
        )
        errors.extend(expand_errors)
        if expanded is None:
            return None, errors
    return expanded, errors


def expanded_detection_root(document: ToolDocument) -> etree._Element:
    """The root to run **read-only** detection/advisory queries on.

    Galaxy's own tool advisors parse the tool *post-macro-expansion*, so a
    construct supplied only by an ``<expand>`` (e.g. a ``<stdio>`` from a shared
    macro) is part of what they see. This returns the macro-expanded root when the
    tool's macros expand cleanly (mirroring Galaxy), and otherwise falls back to
    the raw ``document.root`` — the conservative direction (it over-reports rather
    than going silent when expansion fails). It never mutates the document: the
    expanded tree is a throwaway copy.

    Macro-free tools return ``document.root`` unchanged. Imports resolve against
    the document's ``source_path`` directory; an in-memory document with no source
    path cannot resolve external ``<import>``s and so falls back to raw.
    """
    root = document.root
    if not has_macros(root):
        return root
    source_dir = document.source_path.parent if document.source_path else None
    expanded, errors = expand_from_tree(root, source_dir=source_dir)
    if expanded is not None and not errors:
        return expanded.getroot()
    return root


def _import_targets(root: etree._Element) -> list[str]:
    """Return the macro-file paths a tool or macro-file element ``<import>``s.

    A tool nests imports under ``<tool><macros>``; a macro file lists them as
    direct children of its root ``<macros>``.
    """
    elements = (
        root.findall("import")
        if root.tag == "macros"
        else root.findall("macros/import")
    )
    return [
        element.text.strip()
        for element in elements
        if element.text and element.text.strip()
    ]


def _stage_imports(
    root: etree._Element, *, source_dir: Path | None, tmp_dir: Path
) -> list[MacroError]:
    """Copy every macro file the tree imports — directly or transitively.

    Each staged macro file is itself scanned for further ``<import>``s, so a
    whole chain of macro files (a tool importing ``macros.xml`` that imports
    ``read_group_macros.xml``, say) all reach the temp directory.
    """
    errors: list[MacroError] = []
    staged: set[str] = set()
    pending = _import_targets(root)
    while pending:
        relative = pending.pop()
        if relative in staged:
            continue
        staged.add(relative)
        imported_root, stage_errors = _stage_import(
            relative, source_dir=source_dir, tmp_dir=tmp_dir
        )
        errors.extend(stage_errors)
        if imported_root is not None:
            pending.extend(_import_targets(imported_root))
    return errors


def _stage_import(
    relative: str, *, source_dir: Path | None, tmp_dir: Path
) -> tuple[etree._Element | None, list[MacroError]]:
    """Copy one ``<import>``ed macro file into the temp directory.

    Returns the staged file's parsed root — so the caller can stage that file's
    own ``<import>``s — or ``None`` when the file could not be staged or parsed.
    """
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None, [
            MacroError(
                f"cannot stage <import> {relative!r}: path escapes the tool directory"
            )
        ]
    if source_dir is None:
        return None, [
            MacroError(
                f"cannot resolve <import> {relative!r}: "
                "in-memory input has no source directory"
            )
        ]
    source = source_dir / relative_path
    if not source.exists():
        return None, [MacroError(f"imported macro file not found: {source}")]
    destination = tmp_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, destination)
    # third-party API: no LBYL form — recover=True handles most malformed
    # XML, but pathological inputs (an empty file with nothing to recover)
    # still raise; treat as un-stageable. The missing root just suppresses
    # transitive <import> staging.
    try:
        staged_root = etree.parse(
            str(destination), etree.XMLParser(recover=True)
        ).getroot()
    except etree.XMLSyntaxError:
        staged_root = None
    return staged_root, []
