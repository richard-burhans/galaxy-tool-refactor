"""Tests for the ``Change`` descriptor and ``apply_changes`` dispatcher."""

from __future__ import annotations

import dataclasses

import pytest
from galaxy_tool_refactor_rules.violation import Violation

from galaxy_tool_codemod.change import Change, apply_changes


def _noop() -> None:
    return None


def test_change_is_frozen() -> None:
    change = Change(
        code="GTR002", sourceline=4, xpath="/tool", message="m", mutate=_noop
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        change.code = "GTR999"  # type: ignore[misc]


def test_change_to_violation_projects_diagnostic_fields() -> None:
    change = Change(
        code="GTR002",
        sourceline=4,
        xpath="/tool/inputs/param[1]",
        message="<param> attributes are not in IUC order",
        mutate=_noop,
    )
    assert change.to_violation() == Violation(
        code="GTR002",
        sourceline=4,
        xpath="/tool/inputs/param[1]",
        message="<param> attributes are not in IUC order",
    )


def test_change_equality_ignores_the_thunk() -> None:
    """Two changes with identical data but different thunks compare equal."""
    one = Change(code="GTR002", sourceline=4, xpath="/tool", message="m", mutate=_noop)
    two = Change(
        code="GTR002", sourceline=4, xpath="/tool", message="m", mutate=lambda: None
    )
    assert one == two


def test_apply_changes_runs_each_thunk_in_order() -> None:
    calls: list[str] = []
    changes = [
        Change(
            code="GTR002",
            sourceline=1,
            xpath="/tool",
            message="first",
            mutate=lambda: calls.append("first"),
        ),
        Change(
            code="GTR002",
            sourceline=2,
            xpath="/tool",
            message="second",
            mutate=lambda: calls.append("second"),
        ),
    ]
    apply_changes(changes)
    assert calls == ["first", "second"]


def test_apply_changes_on_empty_iterable_is_a_noop() -> None:
    apply_changes([])  # must not raise
