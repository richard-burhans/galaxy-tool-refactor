"""Tests for the unified ``code -> RuleHandle`` registry."""

from __future__ import annotations

import pytest

from galaxy_tool_refactor_registry.errors import UnknownRuleCode
from galaxy_tool_refactor_registry.registry import (
    _build_index,
    advisory_codes,
    all_handles,
    by_code,
    known_codes,
    registry,
)


def test_known_codes_are_the_selectable_set() -> None:
    """Selectable = canonical codemods + cosmetic fmt + advisory checks."""
    codes = known_codes()
    canonical = {"GTX001", "GTX002", "GTX003", "GTX004", "GTX005", "GTX006", "GTX013"}
    assert canonical <= codes
    assert {"IUC001", "IUC010"} <= codes
    # Upgrade-only codemods are NOT selectable.
    upgrade_only = {"GTX007", "GTX008", "GTX009", "GTX010", "GTX011", "GTX012"}
    assert upgrade_only.isdisjoint(codes)


def test_upgrade_only_codes_appear_only_in_all_handles() -> None:
    """``all_handles`` includes the upgrade-only codemods; ``registry`` does not."""
    full = set(all_handles())
    assert {"GTX007", "GTX012"} <= full
    assert {"GTX007", "GTX012"}.isdisjoint(registry())


def test_by_code_returns_the_handle() -> None:
    handle = by_code("GTX002")
    assert handle.meta.code == "GTX002"
    assert handle.family == "codemod"
    assert handle.fixable is True
    assert handle.apply is not None


def test_by_code_unknown_raises() -> None:
    with pytest.raises(UnknownRuleCode):
        by_code("GTX999")
    # Upgrade-only codes are not selectable, so they are "unknown" to by_code.
    with pytest.raises(UnknownRuleCode):
        by_code("GTX012")


def test_advisory_handles_have_no_apply() -> None:
    for code in advisory_codes():
        handle = by_code(code)
        assert handle.fixable is False
        assert handle.apply is None
        assert handle.family == "check"


def test_fixable_handles_have_apply() -> None:
    for code in known_codes() - advisory_codes():
        handle = by_code(code)
        assert handle.fixable is True
        assert handle.apply is not None


def test_every_code_unique_across_families() -> None:
    """The build-time guard means one handle per code; sizes line up."""
    assert len(all_handles()) == len({h.meta.code for h in all_handles().values()})


def test_duplicate_code_raises() -> None:
    """The collision guard fires when two handles share one code.

    ``test_every_code_unique_across_families`` proves the *real* registry has no
    duplicate; this proves the guard that keeps it that way actually raises —
    feeding ``_build_index`` the same handle twice (so its ``meta.code`` collides).
    """
    handle = by_code("GTX002")
    with pytest.raises(ValueError, match="duplicate rule code 'GTX002'"):
        _build_index([(handle, True), (handle, True)])
