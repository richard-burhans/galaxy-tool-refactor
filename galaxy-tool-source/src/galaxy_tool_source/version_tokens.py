"""Tier-1 version tokenization: the shared decision, gate, and offset planner.

The IUC "Tool versions" practice factors a literal
``version="<base>+galaxy<suffix>"`` into ``@TOOL_VERSION@+galaxy@VERSION_SUFFIX@``,
rewrites the matching package ``<requirement>`` to ``@TOOL_VERSION@``, and defines
the two tokens (inline, or in an imported ``macros.xml``). This module owns the
*decision* (``tokenization_skip_reason``), the *soundness gate*
(``expansion_equality_holds``, proof by execution: tokenizing must not change the
macro expansion), the *tree mutation* (``tokenize_tree``, reused by the GTR094
codemod), and the *offset rendering* (``tokenize_version_plan``).

``tokenize_version_plan`` is the editor-and-CLI-shared sibling of the codemod: it
returns minimal ``(start, end, replacement)`` edits over the original tool source
plus, in separate-file mode, the full content of a new ``macros.xml``. This mirrors
``cheetah_rename.rename_param_plan`` (offset edits, not a full re-serialisation), so
the galaxy-language-server turns it into a minimal-diff LSP ``WorkspaceEdit`` (the
tool edits as ``TextEdit``s, the new file as a ``CreateFile`` resource operation),
and the CLI applies the same plan. Tier 1 has no serializer; the planner emits only
minimal text edits and one fixed four-line ``macros.xml`` template, never a general
document serialization.

Every successful plan is validated by execution: the rendered bytes are re-parsed
and macro-expanded, and the plan bails unless that expansion is byte-identical to
the original tool's. An imperfect offset anchor therefore yields a *bail*, never
wrong output. See ``galaxy-tool-codemod/docs/decisions.md`` §43 (the codemod) and
``galaxy-tool-source/docs/decisions.md`` §29 for the offset-planner extraction.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree

from galaxy_tool_source.binding import parse_tool
from galaxy_tool_source.macros import expand_from_tree, token_definitions

if TYPE_CHECKING:
    from galaxy_tool_source.document import ToolDocument

# The extraction precondition (shared shape with `scripts.measure
# version-tokenization`'s _GALAXY_SUFFIX and the GTR094 codemod): a literal base +
# the IUC `+galaxy` revision suffix. `@` excluded so an already-tokenized version
# never matches.
GALAXY_SUFFIX_VERSION = re.compile(r"^(?P<base>[^@]+)\+galaxy(?P<suffix>[^@]*)$")

_TOKEN_NAMES = ("@TOOL_VERSION@", "@VERSION_SUFFIX@")
_TOKENIZED_VERSION = "@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"


# --------------------------------------------------------------------------- #
# Decision + soundness gate (shared with the GTR094 codemod)                   #
# --------------------------------------------------------------------------- #


def package_requirements(root: etree._Element, /) -> list[etree._Element]:
    """The ``<requirement type="package">`` elements of *root*."""
    return [
        requirement
        for requirement in root.findall("requirements/requirement")
        if requirement.get("type") == "package"
    ]


def tokenization_skip_reason(document: ToolDocument, /) -> str | None:
    """Why version tokenization would skip *document*, or ``None`` when it applies."""
    root = document.root
    version = root.get("version")
    if version is None:
        return "no version= attribute to tokenize"
    match = GALAXY_SUFFIX_VERSION.fullmatch(version)
    if match is None:
        return (
            'version is not a literal "<base>+galaxy<suffix>" (already tokenized, '
            "or not using the IUC suffix convention)"
        )
    base = match["base"]
    if not any(
        requirement.get("version") == base
        for requirement in package_requirements(root)
    ):
        return (
            f"no package <requirement> pins version {base!r}, the extraction "
            "precondition (the tokens exist to share the tool/package version)"
        )
    macros = root.find("macros")
    if (
        macros is not None
        and macros.find("import") is not None
        and document.source_path is None
    ):
        return (
            "<macros> imports files but the tool was parsed from bytes, so the "
            "expansion-equality gate cannot resolve imports (fail closed)"
        )
    defined = {definition.name for definition in token_definitions(document)}
    clashes = sorted(set(_TOKEN_NAMES) & defined)
    if clashes:
        return f"token(s) already defined: {', '.join(clashes)}"
    return None


def append_version_tokens(parent: etree._Element, *, base: str, suffix: str) -> None:
    """Append the two ``<token>`` definitions to *parent* (a ``<macros>`` element)."""
    for name, value in (("@TOOL_VERSION@", base), ("@VERSION_SUFFIX@", suffix)):
        token = etree.SubElement(parent, "token")
        token.set("name", name)
        token.text = value


def build_version_macros_root(*, base: str, suffix: str) -> etree._Element:
    """A fresh ``<macros>`` root holding the two version ``<token>`` definitions.

    The content of a separate ``macros.xml`` (the ``--macros-file`` mode): a caller
    wraps it in a ``MacroDocument`` and serialises it through fmt
    (``format_macro_document``), so fmt stays the only serializer.
    """
    macros = etree.Element("macros")
    append_version_tokens(macros, base=base, suffix=suffix)
    return macros


def retarget_version(root: etree._Element, *, base: str) -> None:
    """Rewrite ``version=`` to the tokenized form and matching requirements.

    The token-reference half of the tokenization (no ``<macros>`` change): the
    ``<tool version>`` becomes ``@TOOL_VERSION@+galaxy@VERSION_SUFFIX@`` and each
    package ``<requirement>`` pinning *base* becomes ``@TOOL_VERSION@``. Used on its
    own when the token *definitions* live in an already-imported macros file the
    caller edits separately (the merge-into-existing path).
    """
    root.set("version", _TOKENIZED_VERSION)
    for requirement in package_requirements(root):
        if requirement.get("version") == base:
            requirement.set("version", "@TOOL_VERSION@")


def tokenize_tree(
    root: etree._Element, *, base: str, suffix: str, macros_file: str | None = None
) -> None:
    """Apply the tokenization to *root* in place (preconditions already held).

    With ``macros_file=None`` the two ``<token>`` definitions go in the tool's inline
    ``<macros>`` (created when absent). With a ``macros_file`` name the tool instead
    gains a ``<macros><import>macros_file</import></macros>`` and the tokens live in
    that separate file (built by ``build_version_macros_root``); the macro expansion
    is identical either way, so the expansion-equality gate (run on the inline form)
    proves both.
    """
    retarget_version(root, base=base)
    macros = root.find("macros")
    if macros is None:
        macros = etree.Element("macros")
        root.insert(0, macros)
    if macros_file is not None:
        importer = etree.SubElement(macros, "import")
        importer.text = macros_file
    else:
        append_version_tokens(macros, base=base, suffix=suffix)


def _expanded_root(
    root: etree._Element, *, source_dir: Path | None
) -> etree._Element | None:
    """*root*'s macro expansion with every ``<macros>`` block dropped, or None."""
    expanded, errors = expand_from_tree(copy.deepcopy(root), source_dir=source_dir)
    if expanded is None or errors:
        return None
    expanded_root = expanded.getroot()
    for macros in expanded_root.findall("macros"):
        expanded_root.remove(macros)
    return expanded_root


def _expansion_bytes(
    root: etree._Element, *, source_dir: Path | None
) -> bytes | None:
    """Canonical bytes of *root*'s macro expansion (macros block dropped), or None."""
    expanded_root = _expanded_root(root, source_dir=source_dir)
    return None if expanded_root is None else bytes(etree.tostring(expanded_root))


def expansion_equality_holds(
    document: ToolDocument, *, base: str, suffix: str
) -> bool:
    """The proof-by-execution gate: tokenizing must not change the expansion."""
    source_path = document.source_path
    source_dir = source_path.parent if source_path is not None else None
    before = _expansion_bytes(document.root, source_dir=source_dir)
    if before is None:
        return False
    trial = copy.deepcopy(document.root)
    tokenize_tree(trial, base=base, suffix=suffix)
    after = _expansion_bytes(trial, source_dir=source_dir)
    return after is not None and after == before


# --------------------------------------------------------------------------- #
# Adopt-suffix: the opt-in, identity-changing authoring action                 #
# --------------------------------------------------------------------------- #


def adopt_suffix_skip_reason(document: ToolDocument, /) -> str | None:
    """Why ``--adopt-suffix`` would skip *document*, or ``None`` when it applies.

    Unlike ``tokenization_skip_reason`` (which requires a literal
    ``<base>+galaxy<suffix>``), this targets a tool whose **bare** ``version`` equals a
    package ``<requirement>`` but does not yet carry the IUC ``+galaxy`` revision
    suffix. Adopting it *adds* ``+galaxy0`` and tokenizes, which changes the published
    version, so this is an authoring action, never a behaviour-preserving fix.
    """
    root = document.root
    version = root.get("version")
    if version is None:
        return "no version= attribute to adopt a suffix for"
    if "+" in version or "@" in version:
        return (
            "version is not a bare version (already has a +local segment or a token); "
            "plain tokenize-version handles the +galaxy case"
        )
    if not any(
        requirement.get("version") == version
        for requirement in package_requirements(root)
    ):
        return (
            f"no package <requirement> pins version {version!r}; @TOOL_VERSION@ would "
            "not name the wrapped tool's version"
        )
    macros = root.find("macros")
    if (
        macros is not None
        and macros.find("import") is not None
        and document.source_path is None
    ):
        return (
            "<macros> imports files but the tool was parsed from bytes, so the "
            "controlled-change gate cannot resolve imports (fail closed)"
        )
    defined = {definition.name for definition in token_definitions(document)}
    clashes = sorted(set(_TOKEN_NAMES) & defined)
    if clashes:
        return f"token(s) already defined: {', '.join(clashes)}"
    return None


def adopt_suffix_equality_holds(document: ToolDocument, *, base: str) -> bool:
    """The controlled-change gate: adopting ``+galaxy0`` changes *only* the version.

    Proves by execution that tokenizing the bare ``base`` (to ``base+galaxy0``) leaves
    the macro expansion byte-identical to the original *except* the root ``version``
    attribute, which gains ``+galaxy0``. Any other divergence (a requirement that should
    not have moved, a token leaking elsewhere) fails the gate, so the only effect is the
    intended version-identity bump.
    """
    source_path = document.source_path
    source_dir = source_path.parent if source_path is not None else None
    before = _expanded_root(document.root, source_dir=source_dir)
    if before is None:
        return False
    trial = copy.deepcopy(document.root)
    tokenize_tree(trial, base=base, suffix="0")
    after = _expanded_root(trial, source_dir=source_dir)
    if after is None:
        return False
    before.set("version", f"{base}+galaxy0")  # the one intended change
    return bytes(etree.tostring(before)) == bytes(etree.tostring(after))


# --------------------------------------------------------------------------- #
# Offset planner (the galaxy-language-server / CLI shared rendering)           #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VersionEdit:
    """One minimal text replacement over the original tool source.

    Attributes:
        start: Character offset into the source where the edit begins.
        end: Character offset where the edit ends (exclusive); ``start == end``
            for a pure insertion (the inserted ``<macros>``/``<import>``).
        replacement: The text for ``source[start:end]``.
    """

    start: int
    end: int
    replacement: str


@dataclass(frozen=True)
class NewMacroFile:
    """A macros file the plan would create (separate-file mode).

    Attributes:
        path: The import path, relative to the tool (e.g. ``"macros.xml"``).
        content: The full UTF-8 content of the new file.
    """

    path: str
    content: str


@dataclass(frozen=True)
class VersionTokenPlan:
    """An offset-based plan to define the IUC version tokens for one tool.

    Applying ``edits`` (disjoint, document-ordered) to the original tool source
    tokenizes ``version=`` and the matching ``<requirement>`` and inserts the token
    definitions (inline) or an ``<import>`` (separate-file); ``new_file`` is the
    ``macros.xml`` to create in separate-file mode (``None`` inline). One plan is
    shared by the CLI (apply + write) and the galaxy-language-server (``WorkspaceEdit``
    + ``CreateFile``), mirroring ``rename_param`` / ``rename_param_plan``.

    Attributes:
        edits: The replacements, disjoint and document-ordered; empty on a bail.
        new_file: The macros.xml to create (separate-file mode), else ``None``.
        base: The ``@TOOL_VERSION@`` value, or ``None`` on a bail.
        suffix: The ``@VERSION_SUFFIX@`` value, or ``None`` on a bail.
        bailed: True when the plan changed nothing (not a candidate, or unproven).
        reason: The bail reason, or ``None`` on success.
    """

    edits: tuple[VersionEdit, ...]
    new_file: NewMacroFile | None
    base: str | None
    suffix: str | None
    bailed: bool
    reason: str | None

    def apply(self, source: str, /) -> str:
        """Apply ``edits`` to *source*, highest offset first (disjoint spans)."""
        result = source
        for edit in sorted(self.edits, key=lambda item: item.start, reverse=True):
            result = f"{result[: edit.start]}{edit.replacement}{result[edit.end :]}"
        return result


def _bail(reason: str) -> VersionTokenPlan:
    return VersionTokenPlan(
        edits=(), new_file=None, base=None, suffix=None, bailed=True, reason=reason
    )


def _line_starts(text: str) -> list[int]:
    """Character offset of the start of each line (index ``i`` => line ``i + 1``)."""
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _start_tag_span(
    text: str, line_starts: list[int], element: etree._Element
) -> tuple[int, int] | None:
    """``(open, close)`` source offsets of *element*'s start tag, or ``None``.

    ``open`` is the ``<`` of the start tag; ``close`` is just past its ``>``. The
    scan honours quoted attribute values so a ``>`` inside a value is not mistaken
    for the tag terminator. Returns ``None`` (a locator bail) when the tag cannot be
    anchored; the expansion gate guarantees this only suppresses output.

    libxml2 reports ``sourceline`` as the line of the start tag's closing ``>`` (so
    a multi-line ``<tool …>`` tag whose ``<tool`` is on line 1 can report a later
    line). The opening ``<localname`` is therefore found by scanning *backward* from
    the end of that line, the last boundary-delimited occurrence at or before it.
    """
    line = element.sourceline
    tag = element.tag
    if not line or not isinstance(tag, str) or line > len(line_starts):
        return None
    localname = tag.rsplit("}", 1)[-1]
    needle = f"<{localname}"
    line_end = line_starts[line] if line < len(line_starts) else len(text)
    open_at = text.rfind(needle, 0, line_end)
    while open_at != -1:
        after = open_at + len(needle)
        if after < len(text) and (text[after].isspace() or text[after] in ">/"):
            break
        open_at = text.rfind(needle, 0, open_at)
    if open_at == -1:
        return None
    index = open_at + len(needle)
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == ">":
            return open_at, index + 1
        index += 1
    return None


def _attr_value_span(
    text: str, open_at: int, close_at: int, attr: str
) -> tuple[int, int] | None:
    """Span of *attr*'s quoted value inside the start tag ``text[open_at:close_at]``."""
    pattern = re.compile(
        r"(?<![\w:.-])" + re.escape(attr) + r"\s*=\s*([\"'])(.*?)\1", re.DOTALL
    )
    match = pattern.search(text, open_at, close_at)
    if match is None:
        return None
    return match.start(2), match.end(2)


def _detect_indent(text: str, line_starts: list[int]) -> str:
    """The leading-whitespace unit of the first indented element line."""
    for start in line_starts:
        newline = text.find("\n", start)
        line = text[start : newline if newline != -1 else len(text)]
        stripped = line.lstrip(" \t")
        if stripped.startswith("<") and stripped != line:
            return line[: len(line) - len(stripped)]
    return "    "


def _leading_whitespace(text: str, pos: int) -> str:
    """The maximal run of whitespace in *text* starting at *pos*."""
    end = pos
    while end < len(text) and text[end] in " \t\r\n":
        end += 1
    return text[pos:end]


def _payload_lines(*, base: str, suffix: str, macros_file: str | None) -> list[str]:
    """The child lines of the tool's ``<macros>`` block (import, or token defs)."""
    if macros_file is not None:
        return [f"<import>{macros_file}</import>"]
    return [
        f'<token name="@TOOL_VERSION@">{base}</token>',
        f'<token name="@VERSION_SUFFIX@">{suffix}</token>',
    ]


def _new_file_content(*, base: str, suffix: str) -> str:
    """The fixed four-line macros.xml template (a template, not a serializer)."""
    return (
        "<macros>\n"
        f'    <token name="@TOOL_VERSION@">{base}</token>\n'
        f'    <token name="@VERSION_SUFFIX@">{suffix}</token>\n'
        "</macros>\n"
    )


def _insertion_edit(
    text: str,
    line_starts: list[int],
    root: etree._Element,
    *,
    base: str,
    suffix: str,
    macros_file: str | None,
) -> VersionEdit | None:
    """The edit that puts the tokens (or import) into the tool's ``<macros>``.

    The inserted block reuses the *original* leading whitespace as its prefix, so the
    expansion gate's ``remove(<macros>)`` leaves the surrounding inter-element
    whitespace byte-identical, matching the GTR094 tree codemod (whose fresh element
    carries no tail). A pure offset insertion that swallowed that whitespace into the
    new element's tail would otherwise drop a blank line and fail the gate.
    """
    payload = _payload_lines(base=base, suffix=suffix, macros_file=macros_file)
    macros = root.find("macros")
    if macros is not None:
        span = _start_tag_span(text, line_starts, macros)
        if span is None:
            return None
        _open, close = span
        if text[close - 2 : close] == "/>":  # <macros/>, cannot inject children
            return None
        whitespace = _leading_whitespace(text, close)
        child_indent = whitespace.rsplit("\n", 1)[-1]
        body = f"\n{child_indent}".join(payload)
        return VersionEdit(close, close, f"{whitespace}{body}")
    root_span = _start_tag_span(text, line_starts, root)
    if root_span is None:
        return None
    _open, close = root_span
    whitespace = _leading_whitespace(text, close)
    base_indent = whitespace.rsplit("\n", 1)[-1]
    child_indent = base_indent + _detect_indent(text, line_starts)
    body = f"\n{child_indent}".join(payload)
    block = f"<macros>\n{child_indent}{body}\n{base_indent}</macros>"
    return VersionEdit(close, close, f"{whitespace}{block}")


def _effective_root(
    rendered: str, *, base: str, suffix: str, macros_file: str | None
) -> etree._Element | None:
    """The rendered tool's root, with the *new* file's import simulated inline.

    Lets the gate execute the *real* rendered structure. In inline mode the tokens
    are already present, so the tree is returned unchanged. In separate-file mode the
    not-yet-written ``macros_file`` cannot be resolved from disk, so its ``<import>``
    is replaced by the tokens it would contain, exactly what Galaxy's ``<import>``
    resolution does once the file is written. Any *other* (pre-existing) ``<import>``
    is left for the real expander to resolve against the tool's source directory.
    """
    result = parse_tool(rendered.encode("utf-8"))
    if result.document is None or result.syntax_errors:
        return None
    root = result.document.root
    if macros_file is None:
        return root
    macros = root.find("macros")
    if macros is not None:
        for importer in list(macros.findall("import")):
            if (importer.text or "").strip() == macros_file:
                macros.remove(importer)
        for name, value in (("@TOOL_VERSION@", base), ("@VERSION_SUFFIX@", suffix)):
            if macros.find(f"token[@name='{name}']") is None:
                token = etree.SubElement(macros, "token")
                token.set("name", name)
                token.text = value
    return root


def tokenize_version_plan(
    source: bytes | str,
    *,
    source_path: Path | None = None,
    macros_file: str | None = None,
) -> VersionTokenPlan:
    """Plan the IUC version tokenization of *source* as minimal offset edits.

    Args:
        source: The tool XML, as bytes (UTF-8) or already-decoded text (the LSP
            path passes ``str``).
        source_path: The tool's path, when known, so the gate can resolve the
            tool's own existing ``<import>``s.
        macros_file: When set, the tokens go in a new file at this relative path
            (separate-file mode) and ``new_file`` is populated; ``None`` inline.

    Returns:
        A ``VersionTokenPlan``; ``bailed`` with a ``reason`` when *source* is not a
        sound candidate or the rendered bytes do not macro-expand identically.
    """
    if isinstance(source, bytes):
        # LBYL: tier-1 offsets are character offsets; non-UTF-8 bytes have no
        # well-defined character mapping for the editor path, so fail closed.
        try:
            text = source.decode("utf-8")
        except UnicodeDecodeError:
            return _bail("source bytes are not valid UTF-8")
    else:
        text = source

    result = parse_tool(text.encode("utf-8"))
    if result.document is None or result.syntax_errors:
        return _bail("source is not well-formed XML")
    document = result.document
    if source_path is not None:
        document = type(document)(document.root.getroottree(), source_path=source_path)

    reason = tokenization_skip_reason(document)
    if reason is not None:
        return _bail(reason)

    match = GALAXY_SUFFIX_VERSION.fullmatch(document.root.get("version") or "")
    if match is None:  # defensive: skip_reason already vetted this
        return _bail("version is not a literal <base>+galaxy<suffix>")
    base, suffix = match["base"], match["suffix"]

    root = document.root
    line_starts = _line_starts(text)

    edits: list[VersionEdit] = []
    root_tag = _start_tag_span(text, line_starts, root)
    if root_tag is None:
        return _bail("could not anchor the <tool> start tag in the source")
    version_span = _attr_value_span(text, root_tag[0], root_tag[1], "version")
    if version_span is None:
        return _bail("could not anchor the version= attribute in the source")
    edits.append(VersionEdit(version_span[0], version_span[1], _TOKENIZED_VERSION))

    for requirement in package_requirements(root):
        if requirement.get("version") != base:
            continue
        span = _start_tag_span(text, line_starts, requirement)
        if span is None:
            return _bail("could not anchor a <requirement> start tag in the source")
        value = _attr_value_span(text, span[0], span[1], "version")
        if value is None:
            return _bail("could not anchor a <requirement> version= in the source")
        edits.append(VersionEdit(value[0], value[1], "@TOOL_VERSION@"))

    insertion = _insertion_edit(
        text, line_starts, root, base=base, suffix=suffix, macros_file=macros_file
    )
    if insertion is None:
        return _bail("could not anchor the <macros> insertion point in the source")
    edits.append(insertion)

    new_file = (
        NewMacroFile(macros_file, _new_file_content(base=base, suffix=suffix))
        if macros_file is not None
        else None
    )
    plan = VersionTokenPlan(
        edits=tuple(edits),
        new_file=new_file,
        base=base,
        suffix=suffix,
        bailed=False,
        reason=None,
    )

    # Proof by execution over the *rendered* bytes: the offset edits must produce a
    # tool whose macro expansion is byte-identical to the original's.
    source_dir = source_path.parent if source_path is not None else None
    before = _expansion_bytes(root, source_dir=source_dir)
    if before is None:
        return _bail("the original tool's macros could not be expanded")
    effective = _effective_root(
        plan.apply(text), base=base, suffix=suffix, macros_file=macros_file
    )
    if effective is None:
        return _bail("the rendered tool is not well-formed")
    after = _expansion_bytes(effective, source_dir=source_dir)
    if after is None or after != before:
        return _bail("tokenization would change the macro expansion (unproven)")
    return plan
