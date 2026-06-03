"""Tests for the markdown rule-reference table renderer."""

from __future__ import annotations

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.reference import render_rule_reference_table


def test_header_and_separator() -> None:
    lines = render_rule_reference_table([])
    assert lines == ["| Rule | Tier | What it does |", "|---|---|---|"]


def test_rows_are_sorted_by_code() -> None:
    entries = [
        (RuleMeta(code="GTR003", summary="Three.", since="0.1.0"), "fmt"),
        (RuleMeta(code="GTR001", summary="One.", since="0.1.0"), "fmt"),
        (RuleMeta(code="GTR002", summary="Two.", since="0.0.1"), "codemod"),
    ]
    rows = render_rule_reference_table(entries)[2:]
    codes = [line.split("|")[1].strip() for line in rows]
    assert codes == ["GTR001", "GTR002", "GTR003"]


def test_tier_label_is_emitted() -> None:
    entries = [(RuleMeta(code="GTR002", summary="Two.", since="0.0.1"), "codemod")]
    assert render_rule_reference_table(entries)[2] == "| GTR002 | codemod | Two. |"


def test_angle_bracket_tokens_are_backtick_wrapped() -> None:
    entries = [
        (
            RuleMeta(
                code="GTR004",
                summary="Collapse empty leaves to <foo/> form for <tool> children.",
                since="0.1.0",
            ),
            "fmt",
        ),
    ]
    row = render_rule_reference_table(entries)[2]
    assert "`<foo/>`" in row
    assert "`<tool>`" in row
    assert "<foo/> " not in row.replace("`<foo/>`", "")
