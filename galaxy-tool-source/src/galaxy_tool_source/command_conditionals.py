"""Boolean-controlled Cheetah conditionals in ``<command>`` (the IUC Booleans rule).

The IUC ``tool_xml`` standard says a ``type="boolean"`` parameter "should not be used
as a conditional for other options" — for options shown or hidden by a choice, use a
``<conditional>`` with a ``select`` instead. That is mechanically visible in
``<command>`` as a Cheetah ``#if`` / ``#elif`` / ``#unless`` whose condition tests a
boolean parameter. A bare ``#if $bool`` is common and perfectly fine (it usually just
adds the parameter's own flag), so each boolean-controlled conditional is classified by
what its body does:

* :data:`GATES_OTHER_PARAMS` — the body references a *different* input parameter, i.e.
  the boolean is gating other options (the genuine anti-pattern; the fix is a
  ``<conditional>`` / ``select``, an authoring change).
* :data:`CONSTANT_ONLY` — the body references no parameter at all (a literal-flag
  block; the IUC idiom is ``truevalue`` / ``falsevalue`` + a bare ``$bool``).
* :data:`OTHER` — the body references only the controlling boolean or Galaxy built-ins.

Read-only: parses the pure-text ``<command>`` body with the faithful CT3 lexer
(:func:`galaxy_tool_source.cheetah_cdm.cheetah_spans`) and resolves a reference to its
``<param>`` by leaf name (the same sizing-grade resolution as ``find-references``).
Returns ``[]`` when there is no pure-text ``<command>``, it declares no boolean
parameter, or the lexer cannot parse the body. The advisory check tier flags only
:data:`GATES_OTHER_PARAMS`; the sizing measure consumes the full classification.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from galaxy_tool_source.cheetah_cdm import CHEETAH_VAR_RE, SpanKind, cheetah_spans

GATES_OTHER_PARAMS = "gates-other-params"
CONSTANT_ONLY = "constant-only"
OTHER = "other"
_OPENER_DIRECTIVES = frozenset(
    {"if", "unless", "for", "while", "def", "block", "with", "closure"}
)


@dataclass(frozen=True)
class BooleanConditional:
    """One boolean-controlled ``#if`` / ``#elif`` / ``#unless`` in ``<command>``.

    Attributes:
        param: The controlling boolean parameter's leaf name (the first, when a
            condition tests more than one boolean).
        klass: One of :data:`GATES_OTHER_PARAMS` / :data:`CONSTANT_ONLY` /
            :data:`OTHER`.
        line: Best-effort 1-based source line of the directive (``0`` if unknown).
    """

    param: str
    klass: str
    line: int


def _ref_components(text: str) -> set[str]:
    """Every path component of every Cheetah ``$ref`` in *text* (``$a.b`` → a, b)."""
    components: set[str] = set()
    for raw in CHEETAH_VAR_RE.findall(text):
        bare = raw.lstrip("$").strip("{}")
        for part in bare.replace("[", ".").split("."):
            cleaned = part.strip("] ")
            if cleaned:
                components.add(cleaned)
    return components


def _input_param_names(root: etree._Element, /) -> tuple[set[str], set[str]]:
    """``(all input param leaf names, boolean param leaf names)``.

    A param with no ``name`` derives one from ``argument`` the way Galaxy does
    (strip leading dashes, internal dashes → underscores), mirroring the IUC note.
    """
    inputs = root.find("inputs")
    params: set[str] = set()
    booleans: set[str] = set()
    if inputs is None:
        return params, booleans
    for param in inputs.iter("param"):
        name = param.get("name")
        if not name:
            argument = param.get("argument")
            if argument:
                name = argument.lstrip("-").replace("-", "_")
        if not name:
            continue
        params.add(name)
        if param.get("type") == "boolean":
            booleans.add(name)
    return params, booleans


@dataclass
class _Frame:
    is_bool: bool
    ctrl: set[str]
    line: int
    body: set[str] = field(default_factory=set)


def command_boolean_conditionals(root: etree._Element, /) -> list[BooleanConditional]:
    """Classify each boolean-controlled conditional in ``<command>``.

    See the module docstring for the classes. One result per controlling conditional,
    in source order; ``[]`` when there is nothing to classify or the lexer bails.
    """
    command = root.find("command")
    if command is None or len(command):  # missing or mixed-content (a macro <expand>)
        return []
    text = "".join(command.itertext())
    if not any(token in text for token in ("#if", "#elif", "#unless")):
        return []
    param_names, boolean_names = _input_param_names(root)
    if not boolean_names:
        return []
    spans = cheetah_spans(text)
    if spans is None:  # CT3 could not compile the body — no faithful classification
        return []

    base_line = command.sourceline or 0

    def line_at(offset: int) -> int:
        return base_line + text[:offset].count("\n")

    findings: list[BooleanConditional] = []
    stack: list[_Frame] = []

    def finalize(frame: _Frame) -> None:
        if not frame.is_bool:
            return
        param = sorted(frame.ctrl)[0]
        other_params = {ref for ref in frame.body if ref in param_names} - frame.ctrl
        if other_params:
            klass = GATES_OTHER_PARAMS
        elif not frame.body:
            klass = CONSTANT_ONLY
        else:
            klass = OTHER
        findings.append(BooleanConditional(param=param, klass=klass, line=frame.line))

    for span in spans:
        if span.kind is SpanKind.PLACEHOLDER:
            refs = _ref_components(span.text)
            for frame in stack:
                frame.body |= refs
            continue
        if span.kind is not SpanKind.DIRECTIVE:
            continue
        directive = span.directive or ""
        refs = _ref_components(span.text)
        if directive in ("elif", "else"):
            if stack:
                finalize(stack[-1])
                for frame in stack[:-1]:  # the condition lives in the enclosing blocks
                    frame.body |= refs
                ctrl = refs & boolean_names
                stack[-1] = _Frame(
                    is_bool=(directive == "elif" and bool(ctrl)),
                    ctrl=ctrl,
                    line=line_at(span.start),
                )
            continue
        if directive == "end":
            if stack:
                finalize(stack.pop())
            continue
        for frame in stack:  # a condition / #set ref is seen within enclosing blocks
            frame.body |= refs
        if directive in _OPENER_DIRECTIVES:
            ctrl = refs & boolean_names
            stack.append(
                _Frame(
                    is_bool=(directive in ("if", "unless") and bool(ctrl)),
                    ctrl=ctrl,
                    line=line_at(span.start),
                )
            )
    while stack:  # CT3 balances on a clean parse; be defensive anyway
        finalize(stack.pop())
    return findings
