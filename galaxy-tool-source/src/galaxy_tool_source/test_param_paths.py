"""Qualified ``parent|...|child`` paths for ``<inputs>`` params and ``<test>`` params.

From profile 24.2 Galaxy requires a ``<test>`` parameter targeting a nested input
(inside a ``<conditional>``, ``<section>`` or ``<repeat>``) to be written with its
fully-qualified path; an unqualified leaf name resolves to nothing and the test
silently runs with the tool's **defaults** instead
(``24_2_fix_test_case_validation``). Galaxy's own
``verify.parse.ParamContext.param_names`` yields only ``for_state()`` — the
qualified name — once ``allow_unqualified_access`` is off, which it is for any
profile above 24.1.

This module is the single analysis of that condition, and it lives in tier 1
because **both** consumers need it and they sit in sibling tiers that cannot
import each other:

* ``galaxy_tool_codemod.codemods.FixTestParamQualification`` (GTR096) rewrites the
  name, but only on the ``upgrade`` path, and only for a tool whose profile walk
  *crosses* 24.2 — a tool authored at 24.2 or later is never visited.
* ``galaxy_tool_lint.checks.tests.TestParamQualified`` (GTR103) reports the same
  condition on the ``check`` path, for any profile above 24.1, which is the gap
  the codemod structurally cannot cover.

Sharing the resolution is what keeps the report and the fix from disagreeing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from galaxy_tool_source.param_names import resolved_param_name

if TYPE_CHECKING:
    from collections.abc import Iterator

    from lxml import etree

# Grouping elements whose ``name`` joins the qualified path (Galaxy's
# ``flat_state_path`` uses ``|`` between each). ``<when>`` is transparent: a
# conditional's child params live under the conditional name, not the when value.
_GROUPING_TAGS = frozenset({"conditional", "section", "repeat"})


def input_leaf_paths(root: etree._Element, /) -> dict[str, list[tuple[str, ...]]]:
    """Map each input leaf parameter name to the ancestor paths it appears at.

    Each value is a list of ancestor tuples (the ``section`` / ``conditional`` /
    ``repeat`` names between ``<inputs>`` and the parameter, outermost first);
    an empty tuple means a top-level parameter. A name appearing more than once
    yields multiple entries (the ambiguous case the caller must reject).
    """
    paths: dict[str, list[tuple[str, ...]]] = {}

    def walk(element: etree._Element, prefix: tuple[str, ...]) -> None:
        for child in element:
            if not isinstance(child.tag, str):
                continue
            if child.tag == "param":
                name = _declared_name(child)
                if name is not None:
                    paths.setdefault(name, []).append(prefix)
            elif child.tag == "when":
                walk(child, prefix)  # transparent: keep the conditional's prefix
            elif child.tag in _GROUPING_TAGS:
                name = child.get("name")
                if name is not None:
                    walk(child, (*prefix, name))

    inputs = root.find("inputs")
    if inputs is not None:
        walk(inputs, ())
    return paths


def _declared_name(param: etree._Element, /) -> str | None:
    """*param*'s resolved name, via the shared tier-1 ``resolved_param_name``.

    Galaxy derives the name from ``argument`` when ``name`` is absent, and reading
    ``name`` alone made a sibling declared with only ``argument=`` invisible: a
    *top-level* ``argument="--threshold"`` beside a nested ``name="threshold"`` looked
    like a single nested leaf, so the planner "qualified" a test param that was already
    binding correctly to the top-level one. Delegated rather than re-derived so this
    agrees with GTR034/GTR037, which resolve the same way.
    """
    return resolved_param_name(param)


def crosses_a_repeat(ancestors: tuple[str, ...], root: etree._Element, /) -> bool:
    """Whether *ancestors* passes through a ``<repeat>``, which is not qualifiable.

    Galaxy's test flattening appends an **instance index** to a repeat segment
    (``__prefix_join`` in ``parser/xml.py``: ``rep`` \u2192 ``rep_0``), so the
    qualified name of a param inside a repeat is ``rep_0|x``, not ``rep|x``. The
    planner used to emit ``rep|x`` \u2014 measured against Galaxy: ``x`` and ``rep|x``
    are *both* rejected with ``Invalid parameter name found`` while ``rep_0|x`` binds.
    So the rewrite replaced one hard error with another, and silenced the report that
    had found it.

    Choosing an index is a guess at intent (one declared ``<repeat>`` may legitimately
    want several instances), and this module's contract is to act **only when
    unambiguous**. So a path through a repeat is declined rather than indexed.
    """
    element = root.find("inputs")
    for segment in ancestors:
        if element is None:
            return False
        for child in element.iter():
            if (
                isinstance(child.tag, str)
                and child.tag in _GROUPING_TAGS
                and child.get("name") == segment
            ):
                if child.tag == "repeat":
                    return True
                element = child
                break
        else:
            return False
    return False


def plan_test_param_qualifications(
    root: etree._Element, /
) -> list[tuple[etree._Element, str]]:
    """Return ``(test_param_element, qualified_name)`` rewrites for *root*.

    A ``<test>`` ``<param>`` is rewritten only when its name has no ``|`` (it is
    flat), is not already a valid input name, and its leaf resolves to exactly
    one **nested** input parameter. Test params nested under a ``<conditional>``
    or ``<section>`` element in the test itself carry their own ancestor prefix,
    so the resolution accounts for where the test already places them.
    """
    leaf_paths = input_leaf_paths(root)
    rewrites: list[tuple[etree._Element, str]] = []
    for test in root.findall("tests/test"):
        for param, prefix in _iter_test_params(test, ()):
            name = param.get("name")
            if name is None or "|" in name:
                continue
            written = (*prefix, name)
            if _is_valid_path(written, leaf_paths):
                continue  # already a valid (possibly nested-by-element) path
            candidates = leaf_paths.get(name)
            if candidates is None or len(candidates) != 1:
                continue  # no candidate (typo/builtin) or ambiguous
            ancestors = candidates[0]
            if not ancestors:
                continue  # a top-level input: the flat name is already correct
            if crosses_a_repeat(ancestors, root):
                continue  # needs an instance index; choosing one is a guess
            rewrites.append((param, "|".join((*ancestors, name))))
    return rewrites


def _iter_test_params(
    element: etree._Element, prefix: tuple[str, ...], /
) -> Iterator[tuple[etree._Element, tuple[str, ...]]]:
    """Yield each ``<param>`` under a test with the element-nesting prefix."""
    for child in element:
        if not isinstance(child.tag, str):
            continue
        if child.tag == "param":
            yield child, prefix
        elif child.tag in {"conditional", "section", "repeat"}:
            name = child.get("name")
            if name is not None:
                yield from _iter_test_params(child, (*prefix, name))


def _is_valid_path(
    written: tuple[str, ...], leaf_paths: dict[str, list[tuple[str, ...]]], /
) -> bool:
    """Whether *written* (element-prefix + leaf) is an existing input path."""
    leaf = written[-1]
    ancestors = written[:-1]
    return ancestors in leaf_paths.get(leaf, [])


def qualify_test_params(root: etree._Element, /) -> int:
    """Apply every unambiguous qualification in place; return the count."""
    rewrites = plan_test_param_qualifications(root)
    for param, qualified in rewrites:
        param.set("name", qualified)
    return len(rewrites)
