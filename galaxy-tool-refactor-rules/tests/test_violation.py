"""Tests for the shared ``Violation`` diagnostic descriptor."""

from __future__ import annotations

import dataclasses

import pytest

from galaxy_tool_refactor_rules.violation import Violation


def test_violation_is_frozen() -> None:
    violation = Violation(
        code="GTX001", sourceline=12, xpath="/tool", message="needs a fix"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        violation.code = "GTX999"  # type: ignore[misc]


def test_violation_carries_supplied_values() -> None:
    violation = Violation(
        code="GTX002",
        sourceline=7,
        xpath="/tool/inputs/param[1]",
        message="<param> attributes are not in IUC order",
    )
    assert violation.code == "GTX002"
    assert violation.sourceline == 7
    assert violation.xpath == "/tool/inputs/param[1]"
    assert violation.message == "<param> attributes are not in IUC order"


def test_violation_equality_is_by_value() -> None:
    one = Violation(code="GTX001", sourceline=1, xpath="/tool", message="m")
    two = Violation(code="GTX001", sourceline=1, xpath="/tool", message="m")
    assert one == two
