"""Tests for ``test_param_paths`` -- the qualified-name analysis two tiers share.

This module moved into tier 1 so GTR096 (the fixer) and its reporters could not drift.
Its unit tests had stayed behind in the codemod package, which left tier 1 owning an
untested module; these are that gap closed, and every case below is a defect a
red-team pass found in the shipped behaviour.
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_source.test_param_paths import (
    crosses_a_repeat,
    input_leaf_paths,
    plan_test_param_qualifications,
)


def _root(inputs: str, tests: str) -> etree._Element:
    return etree.fromstring(
        f'<tool id="t" name="T" version="1.0.0" profile="24.2">'
        f"<inputs>{inputs}</inputs><outputs/>"
        f"<tests><test>{tests}</test></tests></tool>".encode()
    )


def test_qualifies_a_section_leaf() -> None:
    root = _root(
        '<section name="adv" title="A"><param name="cutoff" type="integer" '
        'value="5"/></section>',
        '<param name="cutoff" value="9"/>',
    )
    assert [(e.get("name"), q) for e, q in plan_test_param_qualifications(root)] == [
        ("cutoff", "adv|cutoff")
    ]


def test_declines_a_path_through_a_repeat() -> None:
    """⛔ Galaxy's qualified name for a repeat carries an INSTANCE INDEX.

    ``parser/xml.py::__prefix_join`` makes it ``rep_0|x``, not ``rep|x``. Measured
    against Galaxy: ``x`` and ``rep|x`` are *both* rejected with ``Invalid parameter
    name found`` while ``rep_0|x`` binds. The planner used to emit ``rep|x``, so the
    fix replaced one hard error with another **and silenced the report that found
    it**. Choosing an index is a guess (one ``<repeat>`` may want several instances),
    so the path is declined instead.
    """
    root = _root(
        '<repeat name="rep" title="R"><param name="x" type="integer" value="1"/>'
        "</repeat>",
        '<param name="x" value="7"/>',
    )
    assert plan_test_param_qualifications(root) == []
    assert crosses_a_repeat(("rep",), root) is True
    assert crosses_a_repeat(("adv",), root) is False


def test_declines_when_an_argument_sibling_shares_the_derived_name() -> None:
    """⛔ Galaxy derives a param's name from ``argument`` when ``name`` is absent.

    A top-level ``argument="--threshold"`` beside a nested ``name="threshold"`` means
    there are *two* ``threshold`` leaves after resolution, and an unqualified test
    param legitimately binds to the top-level one. Reading only ``name`` saw one
    nested leaf, called it unambiguous, and "qualified" a test that was already
    correct -- which silently moved the value into the section and reverted the
    top-level param to its default, with nothing reporting it afterwards.
    """
    root = _root(
        '<param argument="--threshold" type="integer" value="5"/>'
        '<section name="adv" title="A"><param name="threshold" type="integer" '
        'value="9"/></section>',
        '<param name="threshold" value="3"/>',
    )
    assert plan_test_param_qualifications(root) == []
    assert sorted(input_leaf_paths(root)["threshold"]) == [(), ("adv",)]


def test_leaves_a_top_level_param_alone() -> None:
    root = _root(
        '<param name="cutoff" type="integer" value="5"/>',
        '<param name="cutoff" value="9"/>',
    )
    assert plan_test_param_qualifications(root) == []


def test_leaves_an_ambiguous_leaf_alone() -> None:
    root = _root(
        '<section name="a" title="A"><param name="x" type="integer" value="1"/>'
        '</section><section name="b" title="B"><param name="x" type="integer" '
        'value="2"/></section>',
        '<param name="x" value="9"/>',
    )
    assert plan_test_param_qualifications(root) == []


def test_leaves_an_already_qualified_name_alone() -> None:
    root = _root(
        '<section name="adv" title="A"><param name="cutoff" type="integer" '
        'value="5"/></section>',
        '<param name="adv|cutoff" value="9"/>',
    )
    assert plan_test_param_qualifications(root) == []


def test_a_when_is_transparent_to_the_conditional_prefix() -> None:
    root = _root(
        '<conditional name="mode"><param name="sel" type="select">'
        '<option value="a">a</option></param>'
        '<when value="a"><param name="deep" type="integer" value="1"/></when>'
        "</conditional>",
        '<param name="deep" value="9"/>',
    )
    assert [q for _, q in plan_test_param_qualifications(root)] == ["mode|deep"]
