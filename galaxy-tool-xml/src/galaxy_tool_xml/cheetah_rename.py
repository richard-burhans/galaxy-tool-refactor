"""Rename a parameter across a tool's Cheetah sections — the first Cheetah *mutator*.

The mutating sibling of ``cheetah_refs`` / ``find-references``: rewrite every reference
to a parameter ``old`` so it reads ``new`` instead — in ``<command>`` / inline
``<configfile>`` bodies (via the faithful ``cheetah_cdm`` lexer, so a ``$old`` inside a
``#raw`` block, a ``##`` comment, or an escaped ``\\$old`` is left untouched), in the
attribute-Cheetah sections (output ``label``, dynamic ``<options>``, ``<entry_point>``,
``<environment_variable>``, ``data_source``), in the by-name cross-reference attributes
(``data_ref``, ``format_source``, …), and the parameter's own definition.

**Rename is atomic.** A half-applied rename — definition renamed but a reference left
dangling, or vice versa — is a broken tool, so the whole operation either rewrites
every live occurrence or changes nothing. It **bails** (returns ``RenameOutcome.bailed``
with a reason, leaving the tree unmutated) when it cannot prove the rewrite safe:

- ``shadowed`` — ``old`` is bound as a ``#set`` / ``#for`` / ``#def`` local, so a bare
  ``$old`` may not be the parameter;
- ``mixed-content`` — a ``<command>`` / ``<configfile>`` with child elements splits the
  Cheetah text across nodes, which the section lexer cannot span;
- ``lexer-bail`` — CT3 cannot faithfully parse a body that references ``old`` (the
  ``cheetah_cdm`` extra is absent, or the body is one of the ~0.4% it can't compile);
- ``filter-bare-ref`` — an output ``<filter>`` references ``old`` by **bare** name (a
  Python expression, not ``$old``), which a safe rewrite would need a Python tokenizer.
  This is the single largest residual bail (~5.6% of corpus rename attempts); closing
  it with an ``ast``/``tokenize``-based ``<filter>`` rewrite is tracked as the next
  coverage win in ``../../docs/upgrade_research/cheetah_section_editing.md`` (M5.3);
- ``cross-ref-residual`` — after rewriting, some attribute value still equals ``old``
  (a by-name cross-reference this version does not model), so a reference would dangle;
- ``not-found`` / ``invalid-name`` / ``no-op`` — nothing named ``old`` occurs, ``new``
  is not an identifier, or ``old == new``.

The tree is the source of truth (tier 1 has no serializer); the caller serialises. The
facade deep-copies before calling, so even a post-apply bail leaves the original intact.

Two renderings of the same plan share one planner (``_plan_rename``) so they never
diverge on which sites to touch or when to bail:

- ``rename_param`` mutates the lxml tree in place (the tree-mutating sibling used by the
  facade / CLI; serialised by fmt);
- ``rename_param_plan`` returns minimal ``RenameEdit`` offsets over the *original*
  source — the editor-oriented rendering (an LSP ``WorkspaceEdit`` touches only the
  renamed tokens, no document reflow). It adds further bails, all sound (they refuse to
  emit an offset rather than emit a wrong one):

  - ``entity-content`` — a text body contains an entity the offset walker cannot decode
    (an unknown named entity). Ordinary references — ``&amp;`` for shell ``&&``,
    ``&lt;`` — and ``<![CDATA[`` sections (including whitespace before one) are handled:
    the body walker decodes/skips them and relocates each span, so they do *not* bail.
  - ``locator-failed`` — an element / attribute value could not be anchored in the raw
    source (no ``sourceline``, an ambiguous start tag, or a body that won't reconcile).

  ``rename_param_plan`` also bails ``parse-error`` when the source is not well-formed,
  and ``encoding`` when ``bytes`` input is not UTF-8 (the LSP path passes an
  already-decoded ``str``; the bytes convenience only supports UTF-8 character offsets).
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterator
from dataclasses import dataclass

from lxml import etree

from galaxy_tool_xml.binding import parse_tool
from galaxy_tool_xml.cdata import is_cdata_wrapped
from galaxy_tool_xml.cheetah_cdm import CheetahSpan, SpanKind, cheetah_spans

# A whole ``$var`` reference, including a dotted/indexed access (``$cond.old``,
# ``${cond.old}``, ``$old.ext``) — the lexer keeps these whole, so one token per ref.
_REF_TOKEN = re.compile(r"\$\{?[A-Za-z_][\w.\[\]]*\}?")
# A bare identifier segment within a reference (``cond``, ``old``, ``ext``).
_IDENT = re.compile(r"[A-Za-z_]\w*")
# The root identifier of a ``$var`` (the binding target in ``#set $x`` / ``#for $i``).
_REF_TOKEN_ROOT = re.compile(r"\$\{?([A-Za-z_]\w*)")
# A fully-formed identifier (the validity gate on ``old`` / ``new``).
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*\Z")

# Directives that introduce a local binding able to shadow a parameter.
_BINDING_DIRECTIVES = frozenset({"set", "for", "def", "import", "from"})

# Single-valued attributes that name a parameter by bare name (rewrite when ``== old``).
_CROSS_REF_ATTRS = (
    "data_ref",  # <param type="data_column" data_ref="X">
    "format_source",  # output format inherited from input X
    "metadata_source",  # output metadata inherited from input X
    "structured_like",  # <collection structured_like="X">
    "collection_type_source",  # <collection collection_type_source="X">
    "default_identifier_source",  # <collection default_identifier_source="X">
    "input",  # <change_format><when input="X"> / <actions>
    "ref",  # dynamic <options><filter ref="X">
    "from_dataset",  # dynamic <options from_dataset="X">
    "split_inputs",  # <parallelism split_inputs="X">
)

# Attributes whose value is literal / display / datatype text, so a value equal to *old*
# is a coincidence, not a missed reference — the completeness net ignores these.
# (``name`` is modelled and rewritten, so it never lingers as a residual.)
_LITERAL_ATTRS = frozenset({
    "label", "value", "type", "format", "ftype", "help", "argument", "truevalue",
    "falsevalue", "checked", "selected", "optional", "multiple", "text", "title",
    "min", "max", "size", "separator", "key", "column", "macro", "from_data_table",
    "token", "value_json", "hidden", "display", "default", "name",
})  # fmt: skip

# Tags whose ``name`` attribute *defines* the referent of a ``$name`` reference.
_INPUT_DEFINITION_TAGS = frozenset({"param", "conditional", "repeat", "section"})
_OUTPUT_DEFINITION_TAGS = frozenset({"data", "collection"})
# Tags in ``<tests>`` that reference a parameter / output by name (the test tree mirrors
# the input/output tree), so a rename must follow them too.
_TEST_REFERENCE_TAGS = frozenset(
    {"param", "conditional", "repeat", "section", "output", "output_collection"}
)


@dataclass(frozen=True)
class RenameOutcome:
    """The result of a parameter rename over one tool tree.

    Attributes:
        renamed: How many sites were rewritten (each reference segment plus each
            definition / cross-reference attribute), or ``0`` on a bail.
        bailed: True when the rename changed nothing because it could not be proven
            safe (or there was nothing to do).
        reason: The bail reason (see the module docstring), or ``None`` on success.
    """

    renamed: int
    bailed: bool
    reason: str | None


@dataclass(frozen=True)
class RenameEdit:
    """One minimal text replacement over the original source document.

    Attributes:
        start: Character offset into the original (decoded) document where the edit
            begins.
        end: Character offset where the edit ends (exclusive).
        replacement: The replacement text for ``[start:end]`` — the new identifier
            segment (e.g. ``"aligned_reads"``), never the whole reference.
    """

    start: int
    end: int
    replacement: str


@dataclass(frozen=True)
class RenamePlan:
    """A minimal-diff parameter rename rendered as offsets over the original source.

    The editor-oriented sibling of ``RenameOutcome``: applying ``edits`` (each a
    disjoint, document-ordered span replacement) to the original source yields the same
    rename ``rename_param`` would produce on the tree, touching only the renamed tokens.

    Attributes:
        edits: The replacements, disjoint and document-ordered; empty on a bail.
        renamed: How many sites were rewritten (matches ``RenameOutcome.renamed``), or
            ``0`` on a bail.
        bailed: True when the rename changed nothing (could not be proven safe, or there
            was nothing to do).
        reason: The bail reason (see the module docstring), or ``None`` on success.
    """

    edits: tuple[RenameEdit, ...]
    renamed: int
    bailed: bool
    reason: str | None


def is_identifier(name: str, /) -> bool:
    """Whether *name* is a single Cheetah/Python identifier (the rename name gate)."""
    return bool(_IDENTIFIER.match(name))


def _segment_edits(text: str, base: int, old: str, /) -> list[tuple[int, int]]:
    """Absolute ``(start, end)`` spans of each ``$``-reference segment equal to *old*.

    Scans only the identifier portion of each ``$var`` token, so a bare ``old`` in
    surrounding shell text is never matched and ``$old_other`` (a different name) is
    not a partial hit. Both the root (``$old``) and a dotted leaf (``$cond.old``) match.
    """
    edits: list[tuple[int, int]] = []
    for token in _REF_TOKEN.finditer(text):
        start = token.start() + 1  # past the ``$``
        if text[start : start + 1] == "{":
            start += 1
        for ident in _IDENT.finditer(text, start, token.end()):
            if ident.group() == old:
                edits.append((base + ident.start(), base + ident.end()))
    return edits


def _apply_edits(text: str, edits: list[tuple[int, int]], new: str, /) -> str:
    """Replace each ``(start, end)`` span of *text* with *new*, highest offset first."""
    for start, end in sorted(set(edits), reverse=True):
        text = f"{text[:start]}{new}{text[end:]}"
    return text


def _references_old(text: str, old: str, /) -> bool:
    """Whether *text* contains a ``$``-reference one of whose segments is *old*."""
    return bool(_segment_edits(text, 0, old))


def _has_bare_reference(text: str, name: str, /) -> bool:
    """Whether *name* appears as a bare identifier (not part of a ``$``-reference).

    A ``$name`` / ``cond.name`` access is preceded by ``$`` / ``.`` and excluded; a
    standalone ``name`` token (an output ``<filter>`` Python reference) matches.
    """
    return re.search(rf"(?<![\w$.]){re.escape(name)}(?![\w])", text) is not None


def local_binding_names(spans: list[CheetahSpan], /) -> set[str]:
    """Identifiers bound as locals by ``#set`` / ``#for`` / ``#def`` / ``#import``.

    Over-approximates in the safe direction (a name flagged here only makes rename bail,
    never mis-rewrite): the targets of ``#set`` / ``#for`` (the ``$vars`` left of ``=``
    / ``in``), a ``#def`` name and its parameters, and ``#import`` / ``#from`` names.
    """
    names: set[str] = set()
    for span in spans:
        if (
            span.kind is not SpanKind.DIRECTIVE
            or span.directive not in _BINDING_DIRECTIVES
        ):
            continue
        text = span.text
        if span.directive == "set":
            left = text.split("=", 1)[0]
            names.update(match.group(1) for match in _REF_TOKEN_ROOT.finditer(left))
        elif span.directive == "for":
            head = re.split(r"\bin\b", text, maxsplit=1)[0]
            names.update(match.group(1) for match in _REF_TOKEN_ROOT.finditer(head))
        elif span.directive == "def":
            match = re.match(r"#def\s+(\w+)\s*(?:\(([^)]*)\))?", text)
            if match is not None:
                names.add(match.group(1))
                if match.group(2):
                    names.update(_IDENT.findall(match.group(2)))
        else:  # import / from — bind the bare module / imported names
            body = re.sub(r"\b(import|from|as)\b", " ", text[1:])
            names.update(_IDENT.findall(body))
    return names


@dataclass(frozen=True)
class _LogicalEdit:
    """One planned rewrite, expressed against an element's text or an attribute value.

    The shared currency of both renderings: ``rename_param`` applies it to the tree,
    ``rename_param_plan`` resolves its ``spans`` to source offsets. ``spans`` are local
    ``(start, end)`` offsets into the target string (``element.text`` when ``attr`` is
    ``None``, else ``element.get(attr)``); each span is replaced by the new name, so an
    exact-match attribute carries a single whole-value span ``(0, len(old))``.
    """

    element: etree._Element
    attr: str | None  # None => the element's text body; else this attribute's value
    spans: tuple[tuple[int, int], ...]
    cdata: bool  # text body was CDATA-wrapped (re-wrap on apply); False for attrs


@dataclass
class _BodyPlan:
    """The planned spans (or a bail) for one faithful-lexer body."""

    bail_reason: str | None = None
    spans: tuple[tuple[int, int], ...] = ()
    cdata: bool = False


def _plan_lexer_body(element: etree._Element, old: str, /) -> _BodyPlan:
    """Plan the rewrite of a faithful-lexer body (``<command>`` / ``<configfile>``)."""
    if len(element) > 0:  # mixed content: the lexer cannot span text split by children
        if _references_old("".join(element.itertext()), old):
            return _BodyPlan(bail_reason="mixed-content")
        return _BodyPlan()
    text = element.text or ""
    spans = cheetah_spans(text)
    if spans is None:
        if _references_old(text, old):
            return _BodyPlan(bail_reason="lexer-bail")
        return _BodyPlan()
    if old in local_binding_names(spans):
        return _BodyPlan(bail_reason="shadowed")
    edits: list[tuple[int, int]] = []
    for span in spans:
        if span.kind is SpanKind.COMMENT:
            continue
        if span.kind is SpanKind.DIRECTIVE and span.directive == "raw":
            continue
        edits.extend(_segment_edits(span.text, span.start, old))
    if not edits:
        return _BodyPlan()
    return _BodyPlan(spans=tuple(edits), cdata=is_cdata_wrapped(element))


def _lexer_bodies(root: etree._Element, /) -> Iterator[etree._Element]:
    """The faithful-lexer bodies: ``<command>`` and every inline ``<configfile>``."""
    command = root.find("command")
    if command is not None:
        yield command
    yield from root.iter("configfile")


def _attr_cheetah_sites(
    root: etree._Element, /
) -> Iterator[tuple[etree._Element, str]]:
    """``(element, attr)`` for every attribute-Cheetah site (a ``$var`` in an attr)."""
    for tag in ("data", "collection"):
        for element in root.iter(tag):
            if element.get("label") is not None:
                yield element, "label"
    for element in root.iter("option"):
        for attr in ("from_url", "request_body", "request_headers"):
            if element.get(attr) is not None:
                yield element, attr
    for element in root.iter("entry_point"):
        for attr in ("url", "label", "port"):
            if element.get(attr) is not None:
                yield element, attr
    data_source = root.find("data_source")
    if data_source is not None and data_source.get("redirect_url_params") is not None:
        yield data_source, "redirect_url_params"


def _named_reference_elements(
    root: etree._Element, old: str, /
) -> Iterator[etree._Element]:
    """Elements whose ``name`` is *old*: the definition (``<inputs>`` / ``<outputs>``)
    and every ``<tests>`` element that mirrors it (a test references params by name)."""
    inputs = root.find("inputs")
    if inputs is not None:
        for element in inputs.iter():
            if element.tag in _INPUT_DEFINITION_TAGS and element.get("name") == old:
                yield element
    outputs = root.find("outputs")
    if outputs is not None:
        for element in outputs.iter():
            if element.tag in _OUTPUT_DEFINITION_TAGS and element.get("name") == old:
                yield element
    tests = root.find("tests")
    if tests is not None:
        for element in tests.iter():
            if element.tag in _TEST_REFERENCE_TAGS and element.get("name") == old:
                yield element


def _plan_rename(
    root: etree._Element, old: str, /
) -> tuple[list[_LogicalEdit], str | None]:
    """Plan every site to rewrite for ``old`` over *root*, or return a bail reason.

    The single source of truth for *which* sites a rename touches and *when* it bails;
    both ``rename_param`` (tree mutation) and ``rename_param_plan`` (source offsets)
    consume the returned edits, so the two renderings never diverge. Pure: inspects
    *root* but does not mutate it. Does **not** run the post-apply completeness net
    (that needs the rewritten tree) or the ``invalid-name`` / ``no-op`` gate (caller).
    """
    edits: list[_LogicalEdit] = []

    # Faithful-lexer bodies first — they own the bail checks (shadow / mixed / lexer).
    for element in _lexer_bodies(root):
        body = _plan_lexer_body(element, old)
        if body.bail_reason is not None:
            return [], body.bail_reason
        if body.spans:
            edits.append(_LogicalEdit(element, None, body.spans, body.cdata))

    # Environment-variable bodies are Cheetah text (no #raw/comments) — regex-rewrite.
    for env_element in root.iter("environment_variable"):
        spans = _segment_edits(env_element.text or "", 0, old)
        if spans:
            edits.append(_LogicalEdit(env_element, None, tuple(spans), False))

    # Output filters reference params by bare Python name — unsafe to rewrite here.
    for filter_element in root.iter("filter"):
        text = filter_element.text or ""
        if _has_bare_reference(text, old):
            return [], "filter-bare-ref"
        spans = _segment_edits(text, 0, old)
        if spans:
            edits.append(_LogicalEdit(filter_element, None, tuple(spans), False))

    # Attribute-Cheetah sites: rewrite the ``$old`` references in the attribute value.
    for element, attr in _attr_cheetah_sites(root):
        spans = _segment_edits(element.get(attr) or "", 0, old)
        if spans:
            edits.append(_LogicalEdit(element, attr, tuple(spans), False))

    # By-name cross-reference attributes (exact value match → whole-value span).
    whole = ((0, len(old)),)
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        for attr in _CROSS_REF_ATTRS:
            if element.get(attr) == old:
                edits.append(_LogicalEdit(element, attr, whole, False))

    # The definition of the parameter plus its by-name mirrors in <inputs> / <outputs>
    # / <tests>.
    for element in _named_reference_elements(root, old):
        edits.append(_LogicalEdit(element, "name", whole, False))

    if not edits:
        return [], "not-found"
    return edits, None


def _edit_count(edits: list[_LogicalEdit], /) -> int:
    """Total rewritten sites across *edits* (one per span)."""
    return sum(len(edit.spans) for edit in edits)


def _apply_logical_edits(edits: list[_LogicalEdit], new: str, /) -> None:
    """Apply each logical edit to its element's text / attribute value in place."""
    for edit in edits:
        if edit.attr is None:
            text = _apply_edits(edit.element.text or "", list(edit.spans), new)
            edit.element.text = etree.CDATA(text) if edit.cdata else text
        else:
            current = edit.element.get(edit.attr) or ""
            edit.element.set(edit.attr, _apply_edits(current, list(edit.spans), new))


def _cross_ref_residual(root: etree._Element, old: str, /) -> bool:
    """Whether a non-literal attribute value still equals *old* after a rewrite.

    The completeness net: such a value is a by-name cross-reference this version does
    not model, so a reference would dangle — bail rather than leave it. A ``label`` /
    ``value`` / ``type`` / … that merely equals *old* is a coincidence, not a reference,
    so those literal attributes are exempt.
    """
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        for attr, value in element.attrib.items():
            if value == old and attr not in _LITERAL_ATTRS:
                return True
    return False


def rename_param(root: etree._Element, /, *, old: str, new: str) -> RenameOutcome:
    """Rename parameter *old* to *new* across *root*, atomically (see module docstring).

    Mutates *root* in place on success. On a bail, *root* is unchanged when the bail
    is detected during planning (the common case); the facade deep-copies regardless, so
    callers never observe a partial rewrite.
    """
    if not is_identifier(old) or not is_identifier(new):
        return RenameOutcome(0, True, "invalid-name")
    if old == new:
        return RenameOutcome(0, True, "no-op")

    edits, reason = _plan_rename(root, old)
    if reason is not None:
        return RenameOutcome(0, True, reason)
    count = _edit_count(edits)
    _apply_logical_edits(edits, new)
    if _cross_ref_residual(root, old):
        return RenameOutcome(count, True, "cross-ref-residual")
    return RenameOutcome(count, False, None)


# --- offset-returning rename (the editor-oriented rendering) --------------------


def _line_starts(text: str, /) -> list[int]:
    """Character offset of the start of each 1-based source line (``[line - 1]``)."""
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _start_tag_open(
    text: str, line_starts: list[int], element: etree._Element, /
) -> int | None:
    """Character offset of the ``<`` opening *element*'s start tag, or ``None``.

    Anchored on lxml's ``sourceline``, which is the line of the start tag's **closing**
    ``>`` (the same as the opening line for a single-line tag, but a *later* line when
    the tag spans lines — ``<param name="x"\\n  type="data"/>``). So this finds ``<tag``
    occurrences whose start tag *closes* on ``sourceline`` and takes the document-order
    ordinal (which disambiguates several same-tag elements closing on the same line).
    """
    line = element.sourceline
    if line is None or not (1 <= line <= len(line_starts)):
        return None
    tag = element.tag
    if not isinstance(tag, str):
        return None
    root = element.getroottree().getroot()
    siblings = [e for e in root.iter(tag) if e.sourceline == line]
    ordinal = siblings.index(element)
    # A start tag closing on `line` must open at or before the end of `line`.
    scan_end = line_starts[line] if line < len(line_starts) else len(text)
    pattern = re.compile(r"<" + re.escape(tag) + r"(?=[\s/>])")
    found = 0
    for match in pattern.finditer(text, 0, scan_end):
        close = _start_tag_close(text, match.start())
        if close is None or bisect.bisect_right(line_starts, close) != line:
            continue
        if found == ordinal:
            return match.start()
        found += 1
    return None


def _start_tag_close(text: str, tag_open: int, /) -> int | None:
    """Offset of the ``>`` closing the start tag at *tag_open*, or ``None``."""
    quote: str | None = None
    for index in range(tag_open, len(text)):
        char = text[index]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == ">":
            return index
    return None


def _attr_value_base(
    text: str, tag_open: int, attr: str, /
) -> int | None:
    """Offset where *attr*'s value begins (just past the opening quote), or ``None``."""
    close = _start_tag_close(text, tag_open)
    if close is None:
        return None
    region = text[tag_open : close + 1]
    match = re.search(r"(?<![\w-])" + re.escape(attr) + r"\s*=\s*[\"']", region)
    if match is None:
        return None
    return tag_open + match.end()


# The five XML predefined entities; XML (no DTD) decodes only these plus numeric refs.
_PREDEFINED_ENTITIES = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
}


def _decode_entity(entity: str, /) -> str | None:
    """Decode one ``&…;`` reference to its single character, or ``None`` if unknown."""
    predefined = _PREDEFINED_ENTITIES.get(entity)
    if predefined is not None:
        return predefined
    if entity.startswith(("&#x", "&#X")) and entity.endswith(";"):
        digits = entity[3:-1]
        if digits and all(c in "0123456789abcdefABCDEF" for c in digits):
            return chr(int(digits, 16))
    elif entity.startswith("&#") and entity.endswith(";"):
        digits = entity[2:-1]
        if digits.isdigit():
            return chr(int(digits))
    return None


def _raw_offset_map(text: str, base: int, decoded: str, /) -> list[int] | str:
    """Absolute raw offset of each *decoded* character, or a bail reason string.

    Reconciles a decoded value with its raw source so a span can be relocated. Used for
    both a childless element's text body (*base* just past the start tag's ``>``) and an
    attribute value (*base* just past the opening quote). Consumes ``<![CDATA[`` /
    ``]]>`` markers (content verbatim — ``&`` / ``<`` literal in a section; attr values
    never contain them) and decodes entity references outside a section (``&amp;`` for
    shell ``&&``, ``&lt;``). Returns one absolute offset per decoded character, or
    ``"entity-content"`` (an unknown entity) / ``"locator-failed"`` (the raw text won't
    reconcile — a mis-anchored start tag or mixed content).
    """
    mapping: list[int] = []
    raw_i = base
    raw_len = len(text)
    in_cdata = False
    for decoded_char in decoded:
        while True:  # consume any CDATA section markers at the current position
            if not in_cdata and text.startswith("<![CDATA[", raw_i):
                raw_i += len("<![CDATA[")
                in_cdata = True
            elif in_cdata and text.startswith("]]>", raw_i):
                raw_i += len("]]>")
                in_cdata = False
            else:
                break
        if raw_i >= raw_len:
            return "locator-failed"
        char = text[raw_i]
        if not in_cdata and char == "&":
            semi = text.find(";", raw_i)
            if semi == -1:
                return "locator-failed"
            if _decode_entity(text[raw_i : semi + 1]) != decoded_char:
                return "entity-content"
            mapping.append(raw_i)
            raw_i = semi + 1
        elif not in_cdata and char == "<":
            return "locator-failed"  # closing tag reached before the body was consumed
        elif char != decoded_char:
            return "locator-failed"
        else:
            mapping.append(raw_i)
            raw_i += 1
    return mapping


def rename_param_plan(source: bytes | str, *, old: str, new: str) -> RenamePlan:
    """Rename *old* to *new*, returned as minimal offset edits over *source*.

    The editor-oriented sibling of ``rename_param``: parses *source*, plans the rename
    with the shared planner, and resolves every planned site to a ``RenameEdit`` span
    into the original document, so an LSP ``WorkspaceEdit`` touches only the renamed
    tokens (no reflow). Character offsets are into the decoded ``str`` (bytes are
    decoded UTF-8). Bails — empty ``edits`` — on every reason ``rename_param`` would,
    plus ``parse-error`` / ``entity-content`` / ``locator-failed`` (see docstring).
    """
    if not is_identifier(old) or not is_identifier(new):
        return RenamePlan((), 0, True, "invalid-name")
    if old == new:
        return RenamePlan((), 0, True, "no-op")

    if isinstance(source, bytes):
        # The LSP path always passes the editor's already-decoded ``str``; the bytes
        # convenience can only place faithful UTF-8 character offsets, so a non-UTF-8
        # document (e.g. a legacy CP1252 tool) bails rather than mis-offset.
        try:
            document_text = source.decode("utf-8")
        except UnicodeDecodeError:
            return RenamePlan((), 0, True, "encoding")
        xml_bytes = source
    else:
        document_text = source
        xml_bytes = source.encode("utf-8")
    parsed = parse_tool(xml_bytes)
    if parsed.document is None:
        return RenamePlan((), 0, True, "parse-error")
    root = parsed.document.root

    edits, reason = _plan_rename(root, old)
    if reason is not None:
        return RenamePlan((), 0, True, reason)
    count = _edit_count(edits)

    line_starts = _line_starts(document_text)
    rename_edits: list[RenameEdit] = []
    for edit in edits:
        # Anchor the edit's text body / attribute value, then relocate each decoded span
        # to the raw source via the walker (handles CDATA sections, whitespace before a
        # section, and entity refs — the same for a body and an attribute value).
        tag_open = _start_tag_open(document_text, line_starts, edit.element)
        if tag_open is None:
            return RenamePlan((), 0, True, "locator-failed")
        if edit.attr is None:
            close = _start_tag_close(document_text, tag_open)
            base = None if close is None else close + 1
            target = edit.element.text or ""
        else:
            base = _attr_value_base(document_text, tag_open, edit.attr)
            target = edit.element.get(edit.attr) or ""
        if base is None:
            return RenamePlan((), 0, True, "locator-failed")
        mapping = _raw_offset_map(document_text, base, target)
        if isinstance(mapping, str):
            return RenamePlan((), 0, True, mapping)
        for start, end in edit.spans:
            raw_start = mapping[start]
            raw_end = raw_start + (end - start)
            if document_text[raw_start:raw_end] != target[start:end]:
                # A CDATA/entity boundary split the matched identifier (very rare).
                return RenamePlan((), 0, True, "locator-failed")
            rename_edits.append(RenameEdit(raw_start, raw_end, new))

    # Completeness net runs on the parsed tree (our copy; *source* is untouched).
    _apply_logical_edits(edits, new)
    if _cross_ref_residual(root, old):
        return RenamePlan((), 0, True, "cross-ref-residual")

    rename_edits.sort(key=lambda e: e.start)
    for previous, current in zip(rename_edits, rename_edits[1:], strict=False):
        if current.start < previous.end:  # overlap => a mis-anchored span; refuse it
            return RenamePlan((), 0, True, "locator-failed")
    return RenamePlan(tuple(rename_edits), count, False, None)
