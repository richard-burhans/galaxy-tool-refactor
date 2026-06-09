"""Tests for the shared ``RuleMeta`` descriptor."""

from __future__ import annotations

import dataclasses

import pytest

from galaxy_tool_refactor_rules.meta import RuleMeta


def test_rule_meta_is_frozen() -> None:
    meta = RuleMeta(code="GTR001", summary="Do a thing.", since="0.1.0")
    with pytest.raises(dataclasses.FrozenInstanceError):
        meta.code = "GTR999"  # type: ignore[misc]


def test_rule_meta_defaults() -> None:
    meta = RuleMeta(code="GTR001", summary="Do a thing.", since="0.1.0")
    assert meta.until is None
    assert meta.cite is None
    assert meta.order == 100
    assert meta.detect_only is False
    assert meta.applies_to == frozenset({"tool"})
    assert meta.parent is None
    assert meta.rulesets == frozenset()
    assert meta.planemo_linters == frozenset()


def test_rule_meta_partition_child_carries_parent() -> None:
    meta = RuleMeta(
        code="GTR020.1", summary="Fix the provable part.", since="0.1.0",
        parent="GTR020",
    )
    assert meta.code == "GTR020.1"
    assert meta.parent == "GTR020"


def test_rule_meta_applies_to_can_widen_to_macro() -> None:
    meta = RuleMeta(
        code="GTR001",
        summary="Generic XML rule.",
        since="0.1.0",
        applies_to=frozenset({"tool", "macro"}),
    )
    assert meta.applies_to == frozenset({"tool", "macro"})


def test_rule_meta_carries_supplied_values() -> None:
    meta = RuleMeta(
        code="GTR021",
        summary="Do a thing.",
        since="0.1.0",
        until="0.4.0",
        cite="https://example.invalid/spec",
        order=10,
        detect_only=True,
    )
    assert meta.until == "0.4.0"
    assert meta.cite == "https://example.invalid/spec"
    assert meta.order == 10
    assert meta.detect_only is True
