"""Tests for ``FixTestParamQualification`` (GTR096), the runtime-gated 24.2 fix.

Rewrites a flat ``<test>`` parameter name to its fully-qualified
``parent|...|child`` path when (and only when) the leaf resolves to exactly one
nested input parameter, which is the migration Galaxy prescribes for
``24_2_fix_test_case_validation``. Behaviour-preserving: it edits only
``<tests>``, and the unique-leaf precondition means the unqualified name already
referred to that one parameter.
"""

from __future__ import annotations

from galaxy_tool_codemod.codemods.fix_test_param_qualification import (
    FixTestParamQualification,
)
from galaxy_tool_codemod.parse import parse_module

_HEAD = b'<tool id="m" name="M" version="1.0.0" profile="24.1">'


def _names(root: object) -> list[str]:
    return [p.get("name") for p in root.iter("param")]  # type: ignore[attr-defined]


def test_qualifies_a_unique_nested_conditional_param() -> None:
    module = parse_module(
        _HEAD
        + b"<command>echo</command>"
        + b'<inputs><conditional name="c"><param name="mode" type="select">'
        + b'<option value="x">X</option></param>'
        + b'<when value="x"><param name="depth" type="integer" value="1"/></when>'
        + b"</conditional></inputs>"
        + b'<outputs><data name="o"/></outputs>'
        + b'<tests><test><param name="c|mode" value="x"/>'
        + b'<param name="depth" value="3"/></test></tests></tool>'
    )
    changes = list(FixTestParamQualification().detect(module))
    assert len(changes) == 1 and changes[0].code == "GTR096"
    FixTestParamQualification().apply(module)
    test_param = module.document.root.find('tests/test/param[@value="3"]')
    assert test_param is not None
    assert test_param.get("name") == "c|depth"


def test_qualifies_through_a_section() -> None:
    module = parse_module(
        _HEAD
        + b"<command>echo</command>"
        + b'<inputs><section name="adv" title="A">'
        + b'<param name="k" type="integer" value="1"/></section></inputs>'
        + b'<outputs><data name="o"/></outputs>'
        + b'<tests><test><param name="k" value="9"/></test></tests></tool>'
    )
    FixTestParamQualification().apply(module)
    assert module.document.root.find("tests/test/param").get("name") == "adv|k"


def test_leaves_a_top_level_name_alone() -> None:
    module = parse_module(
        _HEAD
        + b"<command>echo</command>"
        + b'<inputs><param name="t" type="integer" value="1"/></inputs>'
        + b'<outputs><data name="o"/></outputs>'
        + b'<tests><test><param name="t" value="2"/></test></tests></tool>'
    )
    assert not list(FixTestParamQualification().detect(module))


def test_leaves_an_unknown_name_alone() -> None:
    # No input named 'nosuch' anywhere: a typo / removed param / builtin, not a
    # qualification candidate.
    module = parse_module(
        _HEAD
        + b"<command>echo</command>"
        + b'<inputs><section name="adv" title="A">'
        + b'<param name="k" type="integer" value="1"/></section></inputs>'
        + b'<outputs><data name="o"/></outputs>'
        + b'<tests><test><param name="nosuch" value="2"/></test></tests></tool>'
    )
    assert not list(FixTestParamQualification().detect(module))


def test_leaves_an_ambiguous_leaf_alone() -> None:
    # 'k' appears under two different sections: qualification is ambiguous.
    module = parse_module(
        _HEAD
        + b"<command>echo</command>"
        + b'<inputs><section name="a" title="A">'
        + b'<param name="k" type="integer" value="1"/></section>'
        + b'<section name="b" title="B">'
        + b'<param name="k" type="integer" value="1"/></section></inputs>'
        + b'<outputs><data name="o"/></outputs>'
        + b'<tests><test><param name="k" value="2"/></test></tests></tool>'
    )
    assert not list(FixTestParamQualification().detect(module))


def test_is_idempotent() -> None:
    from lxml import etree

    module = parse_module(
        _HEAD
        + b"<command>echo</command>"
        + b'<inputs><section name="adv" title="A">'
        + b'<param name="k" type="integer" value="1"/></section></inputs>'
        + b'<outputs><data name="o"/></outputs>'
        + b'<tests><test><param name="k" value="9"/></test></tests></tool>'
    )
    FixTestParamQualification().apply(module)
    once = etree.tostring(module.document.root)
    FixTestParamQualification().apply(module)
    assert etree.tostring(module.document.root) == once


def test_clears_the_24_2_detector_for_a_qualifiable_tool() -> None:
    # End-to-end with the gate's auto-fix machinery: a tool blocked only by an
    # unqualified nested test name becomes provably clean after the fix.
    from galaxy_tool_codemod.behavior_gate import (
        auto_fixes_by_code,
        code_cleared_by_autofix,
    )

    module = parse_module(
        _HEAD
        + b"<command>echo</command>"
        + b'<inputs><section name="adv" title="A">'
        + b'<param name="k" type="integer" value="1"/></section></inputs>'
        + b'<outputs><data name="o"/></outputs>'
        + b'<tests><test><param name="k" value="9"/>'
        + b'<output name="o"><assert_contents><has_text text="x"/>'
        + b"</assert_contents></output></test></tests></tool>"
    )
    fixes = auto_fixes_by_code()
    assert fixes["24_2_fix_test_case_validation"] is FixTestParamQualification
    assert code_cleared_by_autofix(
        module.document,
        fix=FixTestParamQualification,
        code="24_2_fix_test_case_validation",
    )
