"""Tests for the shared ``RuleMeta`` descriptor."""

from __future__ import annotations

import dataclasses

import pytest

from galaxy_tool_refactor_rules.meta import RuleMeta


def test_rule_meta_is_frozen() -> None:
    meta = RuleMeta(code="GTX001", summary="Do a thing.", since="0.1.0")
    with pytest.raises(dataclasses.FrozenInstanceError):
        meta.code = "GTX999"  # type: ignore[misc]


def test_rule_meta_defaults() -> None:
    meta = RuleMeta(code="GTX001", summary="Do a thing.", since="0.1.0")
    assert meta.until is None
    assert meta.cite is None
    assert meta.order == 100


def test_rule_meta_carries_supplied_values() -> None:
    meta = RuleMeta(
        code="GTX001",
        summary="Do a thing.",
        since="0.1.0",
        until="0.4.0",
        cite="https://example.invalid/spec",
        order=10,
    )
    assert meta.until == "0.4.0"
    assert meta.cite == "https://example.invalid/spec"
    assert meta.order == 10
