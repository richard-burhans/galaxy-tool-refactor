"""Resolve a flat ``<test>`` parameter name to its qualified input path.

From profile 24.2, Galaxy requires test parameters that target a nested input
(inside a ``<conditional>``, ``<section>``, or ``<repeat>``) to be written with
the fully-qualified ``parent|...|child`` path; an unqualified leaf name is
rejected (``24_2_fix_test_case_validation``; the migration's own prescribed
fix). This module computes that qualification **only when it is unambiguous**:
the flat name must resolve to exactly one input parameter, and that parameter
must be nested. A flat name that matches no input (a typo, a removed
parameter, or a Galaxy built-in like ``chromInfo``), matches a top-level
input (already correct), or matches more than one input (ambiguous) is left
untouched.

The qualification edits only ``<tests>``, never a tool runtime element, and the
unique-leaf precondition means the unqualified name already referred to exactly
that one parameter, so the tool's behaviour and the test's intent are both
preserved. The codemod ``FixTestParamQualification`` (GTR096) applies it on the
``upgrade`` path; ``scripts.measure test-param-qualification`` sizes it. Both
share ``plan_test_param_qualifications`` so they cannot drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
                name = child.get("name")
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
