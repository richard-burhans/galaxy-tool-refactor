"""The provably-clean 24.2 test-case checker (our own validator, gated).

Galaxy validates test cases strictly from profile 24.2: it re-parses the tool,
builds a parameter-model tree, and generates a pydantic model class per tool
(``galaxy.tool_util.parameters``). This module is the toolchain's own
implementation of the same decision as a direct structural query over the
already-parsed (macro-expanded) tree: no re-parse, no model tree, no class
generation, no dependency (``docs/galaxy_reimplementations.md`` touchpoint 3).

**The contract is one-directional.** ``all_test_cases_provably_clean`` may return
``True`` only when every test input is provably valid under rules justified
from Galaxy's model code (cited per rule below); every construct it cannot
model returns ``False``, which leaves the ``24_2_fix_test_case_validation``
detector firing and the behavior gate stopping below 24.2 — never wider than
Galaxy, by construction. The standing parity oracle
(``scripts.measure test-case-validation-truth``) runs Galaxy's real validator
beside this checker over every test-shipping corpus tool and must report zero
unsound suppressions; ``tests/test_test_case_check.py`` pins the same
agreement on synthetic fixtures in CI.

Rule sources (galaxy-tool-util-models ``parameters.py`` / ``case.py`` at the
dev-pinned version): per-type ``py_type`` for the ``test_case_xml``
representation, per-type ``requires_value`` (a required field missing from the
test fails validation), ``legacy_from_string`` coercions at profile >= 24.2
(``int()`` / ``float()`` / ``asbool`` / the ``^(\\d+)$`` column-index pattern),
the strict-``Literal`` membership rule for static selects, and the
``extra="forbid"`` model config that makes any unknown test input an error.
``<repeat>`` is modeled (``RepeatParameterModel``): a min/max-bounded list of
instances, each validated as an inner scope, with Galaxy's pad-to-``min``
empty-instance rule; ``min``/``max`` are proven only when they are clean
non-negative integers (a strict subset of Galaxy's ``int()`` parse).
Constructs deliberately out of scope (always unclean): data collections,
drill-downs, directory URIs, any ``<validator>`` (an ``expression`` validator
runs ``eval`` at validation time), un-expanded ``<expand>`` in ``<inputs>``,
and any parameter type not modeled here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lxml import etree

# galaxy.util.asbool's exact vocabulary (truthy | falsy, after strip().lower()).
_TRUTHY = frozenset({"true", "yes", "on", "y", "t", "1"})
_FALSY = frozenset({"false", "no", "off", "n", "f", "0"})
_BOOL_WORDS = _TRUTHY | _FALSY

# Strict SUBSETS of what Python's int()/float() accept (no underscores, no
# inf/nan, no surrounding whitespace): if our grammar matches, Galaxy's
# coercion succeeds; the converse may not hold, which is the sound direction.
_INT_LITERAL = re.compile(r"^[+-]?\d+$")
_FLOAT_LITERAL = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
# Galaxy's INTEGER_STR_PATTERN for data_column values: ^(\d+)$ (unsigned).
_COLUMN_INDEX = re.compile(r"^\d+$")
# Galaxy's ensure_color_valid: exactly "#" + six LOWERCASE hex digits (it tests
# membership in "0123456789abcdef" — uppercase is rejected as "Invalid color").
_COLOR = re.compile(r"^#[0-9a-f]{6}$")

# Test-XML child tags that describe OUTPUT expectations. The 24.2 validation
# covers test INPUTS only, but Galaxy's test PARSER runs first and raises on
# an <output> with nothing to check, so outputs still gate provability:
# an <output> is provably parseable with a file= or an <assert_contents>;
# anything else (including <output_collection>) bails to unclean.
_TEST_ASSERT_TAGS = frozenset(
    {
        "assert_command",
        "assert_command_version",
        "assert_stdout",
        "assert_stderr",
    }
)


@dataclass(frozen=True)
class _Param:
    """One modeled leaf parameter, reduced to the facts the rules need."""

    kind: str
    optional: bool
    has_default: bool
    multiple: bool
    # Static select option values; None for dynamic options (any string passes).
    option_values: frozenset[str] | None = None
    minimum: float | None = None
    maximum: float | None = None

    @property
    def requires_test_value(self) -> bool:
        """Whether the test-case model makes this field required (per type).

        Mirrors each model's ``request_requires_value`` as used for the
        ``test_case_xml`` representation: integer and hidden require a value
        when non-optional with no default; data when non-optional; group_tag
        when non-optional; data_column only when ``multiple`` and neither
        optional nor defaulted; every other modeled type is never required.
        """
        if self.kind in {"integer", "hidden"}:
            return not self.optional and not self.has_default
        if self.kind == "data":
            return not self.optional
        if self.kind == "group_tag":
            return not self.optional
        if self.kind == "data_column":
            return self.multiple and not (self.optional or self.has_default)
        return False


@dataclass(frozen=True)
class _Conditional:
    """A conditional: a select/boolean test parameter switching `when` scopes."""

    test_name: str
    test_param: _Param
    whens: dict[str, _Scope]
    default_discriminator: str | None  # provable default branch, or None


@dataclass(frozen=True)
class _Repeat:
    """A repeat: a min/max-bounded list of instances, each one inner ``_Scope``."""

    scope: _Scope
    minimum: int | None
    maximum: int | None


@dataclass(frozen=True)
class _Scope:
    """One nesting level of the input model (top level, a when, a section)."""

    params: dict[str, _Param] = field(default_factory=dict)
    conditionals: dict[str, _Conditional] = field(default_factory=dict)
    sections: dict[str, _Scope] = field(default_factory=dict)
    repeats: dict[str, _Repeat] = field(default_factory=dict)

    def member_names(self) -> frozenset[str]:
        return (
            frozenset(self.params)
            | frozenset(self.conditionals)
            | frozenset(self.sections)
            | frozenset(self.repeats)
        )


_LEAF_KINDS = frozenset(
    {
        "text",
        "integer",
        "float",
        "boolean",
        "select",
        "data",
        "data_column",
        "hidden",
        "genomebuild",
        "group_tag",
        "color",
    }
)


def _parse_bound(value: str | None, /) -> tuple[bool, float | None]:
    """``(ok, bound)`` for a min/max attribute; not-ok bails the param."""
    if value is None:
        return True, None
    if _FLOAT_LITERAL.match(value) is None:
        return False, None
    return True, float(value)


def _model_safe_name(name: str | None, /) -> bool:
    """Whether *name* is a name Galaxy's pydantic model builder accepts.

    Pydantic reserves leading-underscore names for private attributes, so a
    parameter, conditional, or section whose name starts with ``_`` makes
    ``create_model`` raise ("Decorators defined with incorrect fields") rather
    than return a clean verdict. We cannot prove Galaxy validates such a tool
    cleanly, so any leading-underscore name bails the whole tool to unclean.
    """
    return name is not None and not name.startswith("_")


def _build_param(element: etree._Element, /) -> _Param | None:
    """Model one ``<param>``; ``None`` when it is not provably modelable."""
    kind = element.get("type")
    name = element.get("name") or element.get("argument")
    if kind not in _LEAF_KINDS or not _model_safe_name(name):
        return None
    if element.find("validator") is not None:
        return None  # regex/length/expression validators run at validation time
    optional = (element.get("optional") or "").strip().lower() in _TRUTHY
    has_default = element.get("value") is not None
    multiple = (element.get("multiple") or "").strip().lower() in _TRUTHY
    option_values: frozenset[str] | None = None
    if kind == "select":
        if element.find("options") is not None:
            option_values = None  # dynamic: validates as a plain string
        else:
            options = element.findall("option")
            values = [option.get("value") for option in options]
            if any(value is None for value in values):
                return None
            option_values = frozenset(value for value in values if value is not None)
            if not option_values:
                return None  # empty static select: nothing provable about it
            # A static select with a selected option (or any option, the API
            # default) counts as defaulted; membership is the real rule.
            has_default = True
    min_ok, minimum = _parse_bound(element.get("min"))
    max_ok, maximum = _parse_bound(element.get("max"))
    if not (min_ok and max_ok):
        return None
    return _Param(
        kind=kind,
        optional=optional,
        has_default=has_default,
        multiple=multiple,
        option_values=option_values,
        minimum=minimum,
        maximum=maximum,
    )


def _select_default(element: etree._Element, /) -> str | None:
    """The provable default value of a conditional's select test param."""
    selected = [
        option.get("value")
        for option in element.findall("option")
        if (option.get("selected") or "").strip().lower() in _TRUTHY
    ]
    if len(selected) == 1 and selected[0] is not None:
        return str(selected[0])
    return None


def _build_conditional(element: etree._Element, /) -> _Conditional | None:
    """Model one ``<conditional>``; ``None`` when not provably modelable."""
    name = element.get("name")
    test_element = element.find("param")
    if name is None or test_element is None:
        return None
    test_param = _build_param(test_element)
    if test_param is None or test_param.kind not in {"select", "boolean"}:
        return None
    if test_param.kind == "select" and test_param.option_values is None:
        return None  # a dynamic-options conditional switch is not provable
    default: str | None = None
    if test_param.kind == "select":
        default = _select_default(test_element)
    else:
        checked = (test_element.get("checked") or "false").strip().lower()
        if checked in _BOOL_WORDS:
            default = "true" if checked in _TRUTHY else "false"
    whens: dict[str, _Scope] = {}
    for when in element.findall("when"):
        discriminator = when.get("value")
        if discriminator is None:
            return None
        scope = _build_scope(when)
        if scope is None:
            return None
        whens[discriminator] = scope
    if not whens:
        return None
    if default is not None and default not in whens:
        default = None
    return _Conditional(
        test_name=test_element.get("name") or "",
        test_param=test_param,
        whens=whens,
        default_discriminator=default,
    )


def _build_scope(container: etree._Element, /) -> _Scope | None:
    """Model the params directly under *container*; ``None`` bails the tool."""
    params: dict[str, _Param] = {}
    conditionals: dict[str, _Conditional] = {}
    sections: dict[str, _Scope] = {}
    repeats: dict[str, _Repeat] = {}
    for child in container:
        if not isinstance(child.tag, str):
            continue  # comments / processing instructions
        if child.tag == "param":
            if child.get("name") is None and child.get("argument") is None:
                return None
            name = child.get("name") or _argument_name(child)
            param = _build_param(child)
            if name is None or param is None:
                return None
            params[name] = param
        elif child.tag == "conditional":
            conditional = _build_conditional(child)
            if conditional is None or not _model_safe_name(child.get("name")):
                return None
            conditionals[str(child.get("name"))] = conditional
        elif child.tag == "section":
            scope = _build_scope(child)
            if scope is None or not _model_safe_name(child.get("name")):
                return None
            sections[str(child.get("name"))] = scope
        elif child.tag == "repeat":
            repeat = _build_repeat(child)
            if repeat is None or not _model_safe_name(child.get("name")):
                return None
            repeats[str(child.get("name"))] = repeat
        elif child.tag == "when" and container.tag == "conditional":
            continue  # handled by _build_conditional
        else:
            # expand, upload_dataset, display, or anything novel: the model is not
            # fully visible, so nothing is provable.
            return None
    return _Scope(
        params=params,
        conditionals=conditionals,
        sections=sections,
        repeats=repeats,
    )


def _parse_count(value: str | None, /) -> tuple[bool, int | None]:
    """``(ok, count)`` for a repeat ``min``/``max``; not-ok bails the repeat.

    Galaxy parses these with ``int()`` (which would also accept ``"-1"`` / ``"1_0"``
    / surrounding whitespace). We prove clean only for a clean non-negative integer
    literal — a strict subset — and bail (declining to prove) on anything else.
    """
    if value is None:
        return True, None
    if _COLUMN_INDEX.match(value) is None:  # ^\d+$ — non-negative, no underscores/ws
        return False, None
    return True, int(value)


def _build_repeat(element: etree._Element, /) -> _Repeat | None:
    """Model one ``<repeat>``; ``None`` when it is not provably modelable."""
    inner = _build_scope(element)
    if inner is None:
        return None
    min_ok, minimum = _parse_count(element.get("min"))
    max_ok, maximum = _parse_count(element.get("max"))
    if not (min_ok and max_ok):
        return None
    return _Repeat(scope=inner, minimum=minimum, maximum=maximum)


def _argument_name(element: etree._Element, /) -> str | None:
    argument = element.get("argument")
    if argument is None:
        return None
    return str(argument).lstrip("-").replace("-", "_")


# --- the test side -----------------------------------------------------------------

# A parsed test entry tree: leaf values are the <param> value strings, interior
# nodes are dicts (from nested <conditional>/<section> elements or pipe paths), and
# a repeat is a list of per-instance dicts (one entry per <repeat name="r"> element).
_TestNode = str | dict[str, "_TestNode"] | list[dict[str, "_TestNode"]]


def _insert(tree: dict[str, _TestNode], path: list[str], value: str, /) -> bool:
    """Insert *value* at *path*; ``False`` on conflict (not provable)."""
    node = tree
    for segment in path[:-1]:
        nested = node.setdefault(segment, {})
        if not isinstance(nested, dict):
            return False
        node = nested
    leaf = path[-1]
    if leaf in node:
        return False  # duplicate input for one path: undefined, bail
    node[leaf] = value
    return True


def _collect_test_inputs(
    element: etree._Element, tree: dict[str, _TestNode], prefix: list[str], /
) -> bool:
    """Walk one test (or nested grouping) element into *tree*; ``False`` bails."""
    for child in element:
        if not isinstance(child.tag, str):
            continue
        if child.tag in _TEST_ASSERT_TAGS:
            continue
        if child.tag == "output":
            # Galaxy's test parser raises on an output with nothing to check.
            if child.get("file") is None and child.find("assert_contents") is None:
                return False
            continue
        if child.tag == "param":
            name = child.get("name")
            value = child.get("value")
            if name is None or value is None:
                return False  # value-less / nameless test params: not provable
            if not _insert(tree, [*prefix, *name.split("|")], value):
                return False
        elif child.tag in {"conditional", "section"}:
            name = child.get("name")
            if name is None:
                return False
            if not _collect_test_inputs(child, tree, [*prefix, *name.split("|")]):
                return False
        elif child.tag == "repeat":
            if not _collect_repeat_instance(child, tree, prefix):
                return False
        else:
            return False  # anything novel: not provable
    return True


def _collect_repeat_instance(
    element: etree._Element, tree: dict[str, _TestNode], prefix: list[str], /
) -> bool:
    """Append one ``<repeat name=…>`` element's inputs to its instance list.

    Each ``<repeat name="r">`` element is one instance (Galaxy indexes repeated
    same-named blocks ``r_0`` / ``r_1`` / …); the instance's own inputs are collected
    into a fresh sub-tree. The list is anchored under the same prefixed path the
    other grouping constructs use, so a repeat nested in a conditional/section lands
    in the right scope.
    """
    name = element.get("name")
    if name is None:
        return False
    instance: dict[str, _TestNode] = {}
    if not _collect_test_inputs(element, instance, []):
        return False
    node: dict[str, _TestNode] = tree
    for segment in prefix:
        nested = node.setdefault(segment, {})
        if not isinstance(nested, dict):
            return False
        node = nested
    bucket = node.setdefault(name, [])
    if not isinstance(bucket, list):
        return False  # name reused as a non-repeat input: undefined, bail
    bucket.append(instance)
    return True


def _value_provably_valid(param: _Param, value: str, /) -> bool:
    """Whether *value* provably passes coercion + strict validation for *param*."""
    if param.kind in {"text", "hidden", "genomebuild", "group_tag"}:
        return True
    if param.kind == "integer":
        if _INT_LITERAL.match(value) is None:
            return False
        return _within_bounds(param, float(value))
    if param.kind == "float":
        if _FLOAT_LITERAL.match(value) is None:
            return False
        return _within_bounds(param, float(value))
    if param.kind == "boolean":
        return value.strip().lower() in _BOOL_WORDS
    if param.kind == "select":
        if param.option_values is None:
            return True  # dynamic options: a provided value is a plain string
        pieces = value.split(",") if param.multiple else [value]
        return all(piece in param.option_values for piece in pieces)
    if param.kind == "data":
        pieces = value.split(",") if param.multiple else [value]
        return all(piece != "" for piece in pieces)
    if param.kind == "data_column":
        pieces = value.split(",") if param.multiple else [value]
        return all(_COLUMN_INDEX.match(piece) is not None for piece in pieces)
    if param.kind == "color":
        return _COLOR.match(value) is not None
    return False


def _within_bounds(param: _Param, value: float, /) -> bool:
    if param.minimum is not None and value < param.minimum:
        return False
    return not (param.maximum is not None and value > param.maximum)


def _conditional_clean(
    conditional: _Conditional, state: dict[str, _TestNode] | None, /
) -> bool:
    """Whether a conditional's test inputs (or its absence) are provably valid."""
    if state is None:
        # The whole conditional is absent: Galaxy selects the default when; a
        # missing or unprovable default raises, and required params inside the
        # default branch would be missing.
        if conditional.default_discriminator is None:
            return False
        branch = conditional.whens[conditional.default_discriminator]
        return _scope_clean(branch, None)
    provided = state.get(conditional.test_name)
    if provided is None or not isinstance(provided, str):
        # Touched without an explicit test-param value: branch selection rests
        # on the default; provable only when the default is, and the provided
        # inputs must then belong to that branch.
        discriminator = conditional.default_discriminator
    else:
        if not _value_provably_valid(conditional.test_param, provided):
            return False
        if conditional.test_param.kind == "boolean":
            discriminator = (
                "true" if provided.strip().lower() in _TRUTHY else "false"
            )
        else:
            discriminator = provided
    if discriminator is None or discriminator not in conditional.whens:
        return False
    rest = {
        key: node for key, node in state.items() if key != conditional.test_name
    }
    return _scope_clean(conditional.whens[discriminator], rest)


def _scope_clean(scope: _Scope, state: dict[str, _TestNode] | None, /) -> bool:
    """Whether *state* (one nesting level of test inputs) is provably valid."""
    provided = state if state is not None else {}
    known = scope.member_names()
    if any(key not in known for key in provided):
        return False  # an unknown input name: Galaxy raises, never suppress
    for name, param in scope.params.items():
        node = provided.get(name)
        if node is None:
            if param.requires_test_value:
                return False
            if param.kind == "select" and param.option_values is None:
                # An omitted dynamic-options select: the no-options validator
                # can reject the resulting None, so absence is not provable.
                return False
            continue
        if not isinstance(node, str):
            return False
        if not _value_provably_valid(param, node):
            return False
    for name, conditional in scope.conditionals.items():
        node = provided.get(name)
        if node is not None and not isinstance(node, dict):
            return False
        if not _conditional_clean(conditional, node):
            return False
    for name, section in scope.sections.items():
        node = provided.get(name)
        if node is not None and not isinstance(node, dict):
            return False
        if not _scope_clean(section, node if isinstance(node, dict) else None):
            return False
    for name, repeat in scope.repeats.items():
        node = provided.get(name)
        if node is not None and not isinstance(node, list):
            return False
        if not _repeat_clean(repeat, node):
            return False
    return True


def _repeat_clean(
    repeat: _Repeat, instances: list[dict[str, _TestNode]] | None, /
) -> bool:
    """Whether a repeat's test instances (or its absence) are provably valid.

    Mirrors Galaxy: the instances validate as inner scopes, Galaxy pads the list to
    ``min`` with empty instances (each must still validate), and the final length must
    satisfy the ``min_length`` / ``max_length`` the ``RepeatParameterModel`` imposes.
    An absent repeat with no ``min`` is an empty list — valid, nothing to check.
    """
    supplied = instances or []
    count = len(supplied)
    # After Galaxy pads to `min`, the validated length is max(count, min); it must not
    # exceed max (catches both too-many instances and a malformed min > max).
    effective = max(count, repeat.minimum or 0)
    if repeat.maximum is not None and effective > repeat.maximum:
        return False
    for instance in supplied:
        if not isinstance(instance, dict):
            return False
        if not _scope_clean(repeat.scope, instance):
            return False
    if repeat.minimum is None or count >= repeat.minimum:
        return True
    # count < min: Galaxy pads to `min` with empty instances; each is clean iff the
    # inner scope needs nothing (no required field). One empty check covers them all.
    return _scope_clean(repeat.scope, {})


def all_test_cases_provably_clean(root: etree._Element, /) -> bool:
    """Whether every ``<test>`` of *root* provably passes 24.2 validation.

    Run this on the macro-expanded view (the detector does); an un-expanded
    ``<expand>`` under ``<inputs>`` bails to ``False``. A tool with no tests
    is vacuously clean (the caller's detector handles the has-tests gate).
    """
    tests = root.findall("tests/test")
    if not tests:
        return True
    inputs = root.find("inputs")
    scope = _build_scope(inputs) if inputs is not None else _Scope()
    if scope is None:
        return False
    for test in tests:
        tree: dict[str, _TestNode] = {}
        if not _collect_test_inputs(test, tree, []):
            return False
        if not _scope_clean(scope, tree):
            return False
    return True
