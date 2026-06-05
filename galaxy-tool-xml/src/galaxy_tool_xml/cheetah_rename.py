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
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from lxml import etree

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


def _set_text_edit(element: etree._Element, value: str, /) -> Callable[[], None]:
    """A thunk that replaces *element*'s text with *value* (a plain-text body)."""

    def edit() -> None:
        element.text = value

    return edit


def _set_attr_edit(
    element: etree._Element, attr: str, value: str, /
) -> Callable[[], None]:
    """A thunk that sets *element*'s *attr* attribute to *value*."""

    def edit() -> None:
        element.set(attr, value)

    return edit


@dataclass
class _Plan:
    """A planned (not yet applied) edit, or a bail, for one section."""

    bail_reason: str | None = None
    edit: Callable[[], None] | None = None
    count: int = 0


def _plan_lexer_body(element: etree._Element, old: str, new: str, /) -> _Plan:
    """Plan the rewrite of a faithful-lexer body (``<command>`` / ``<configfile>``)."""
    if len(element) > 0:  # mixed content: the lexer cannot span text split by children
        if _references_old("".join(element.itertext()), old):
            return _Plan(bail_reason="mixed-content")
        return _Plan()
    text = element.text or ""
    spans = cheetah_spans(text)
    if spans is None:
        if _references_old(text, old):
            return _Plan(bail_reason="lexer-bail")
        return _Plan()
    if old in local_binding_names(spans):
        return _Plan(bail_reason="shadowed")
    edits: list[tuple[int, int]] = []
    for span in spans:
        if span.kind is SpanKind.COMMENT:
            continue
        if span.kind is SpanKind.DIRECTIVE and span.directive == "raw":
            continue
        edits.extend(_segment_edits(span.text, span.start, old))
    if not edits:
        return _Plan()
    new_text = _apply_edits(text, edits, new)
    cdata = is_cdata_wrapped(element)

    def do_edit() -> None:
        element.text = etree.CDATA(new_text) if cdata else new_text

    return _Plan(edit=do_edit, count=len(edits))


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

    edits: list[Callable[[], None]] = []
    count = 0

    # Faithful-lexer bodies first — they own the bail checks (shadow / mixed / lexer).
    for element in _lexer_bodies(root):
        plan = _plan_lexer_body(element, old, new)
        if plan.bail_reason is not None:
            return RenameOutcome(0, True, plan.bail_reason)
        if plan.edit is not None:
            edits.append(plan.edit)
            count += plan.count

    # Environment-variable bodies are Cheetah text (no #raw/comments) — regex-rewrite.
    for env_element in root.iter("environment_variable"):
        text = env_element.text or ""
        segment_edits = _segment_edits(text, 0, old)
        if segment_edits:
            new_text = _apply_edits(text, segment_edits, new)
            edits.append(_set_text_edit(env_element, new_text))
            count += len(segment_edits)

    # Output filters reference params by bare Python name — unsafe to rewrite here.
    for filter_element in root.iter("filter"):
        text = filter_element.text or ""
        if _has_bare_reference(text, old):
            return RenameOutcome(0, True, "filter-bare-ref")
        segment_edits = _segment_edits(text, 0, old)
        if segment_edits:
            new_text = _apply_edits(text, segment_edits, new)
            edits.append(_set_text_edit(filter_element, new_text))
            count += len(segment_edits)

    # Attribute-Cheetah sites: rewrite the ``$old`` references in the attribute value.
    for element, attr in _attr_cheetah_sites(root):
        value = element.get(attr) or ""
        segment_edits = _segment_edits(value, 0, old)
        if segment_edits:
            new_value = _apply_edits(value, segment_edits, new)
            edits.append(_set_attr_edit(element, attr, new_value))
            count += len(segment_edits)

    # By-name cross-reference attributes (exact value match).
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        for attr in _CROSS_REF_ATTRS:
            if element.get(attr) == old:
                edits.append(_set_attr_edit(element, attr, new))
                count += 1

    # The definition of the parameter plus its by-name mirrors in <inputs> / <outputs>
    # / <tests>.
    for element in _named_reference_elements(root, old):
        edits.append(_set_attr_edit(element, "name", new))
        count += 1

    if count == 0:
        return RenameOutcome(0, True, "not-found")

    for edit in edits:
        edit()

    # Completeness net: a non-literal attribute value still exactly ``old`` is a by-name
    # cross-reference this version does not model — bail rather than leave a dangler. A
    # ``label`` / ``value`` / ``type`` / … that merely equals ``old`` is a coincidence,
    # not a reference, so those literal attributes are exempt.
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        for attr, value in element.attrib.items():
            if value == old and attr not in _LITERAL_ATTRS:
                return RenameOutcome(count, True, "cross-ref-residual")

    return RenameOutcome(count, False, None)
