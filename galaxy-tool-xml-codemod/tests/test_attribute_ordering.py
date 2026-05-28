"""Tests for the ``canonical_order`` helper used by attribute-reorder codemods."""

from __future__ import annotations

from galaxy_tool_xml_codemod.codemods._attribute_ordering import canonical_order


def test_known_attrs_sort_by_priority() -> None:
    """Attributes listed in the priority map appear in ascending priority order."""
    priority = {"name": 0, "type": 1, "value": 2}
    assert canonical_order(["value", "name", "type"], priority) == (
        "name",
        "type",
        "value",
    )


def test_unknown_attrs_sort_alphabetical_after_known() -> None:
    """Attributes not in the priority map sort alphabetically after the known ones."""
    priority = {"name": 0}
    assert canonical_order(["zz", "aa", "name", "bb"], priority) == (
        "name",
        "aa",
        "bb",
        "zz",
    )


def test_mutually_exclusive_slots_keep_alphabetical_tie_break() -> None:
    """Attributes sharing a priority slot fall back to alphabetical ordering."""
    priority = {"min": 4, "truevalue": 4, "max": 5, "falsevalue": 5}
    assert canonical_order(["max", "min", "truevalue", "falsevalue"], priority) == (
        "min",
        "truevalue",
        "falsevalue",
        "max",
    )


def test_empty_input_returns_empty_tuple() -> None:
    """No attributes → no output."""
    assert canonical_order([], {"name": 0}) == ()
