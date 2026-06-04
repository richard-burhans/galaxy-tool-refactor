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
    """Selectable = canonical codemods + cosmetic fmt + advisory checks (derived)."""
    from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS

    codes = known_codes()
    # canonical codemods are selectable (derived from the source-of-truth tuple)...
    assert {cls.meta.code for cls in CANONICAL_CODEMODS} <= codes
    assert {"GTR001", "GTR021"} <= codes  # a cosmetic fmt rule + an advisory check
    # ...upgrade-only codemods are NOT selectable (derived: all_handles − selectable).
    upgrade_only = set(all_handles()) - codes
    assert upgrade_only and upgrade_only.isdisjoint(codes)


def test_upgrade_only_set_matches_the_codemod_catalog() -> None:
    """Registry's non-selectable codemod codes == coded_codemods − CANONICAL.

    Both sides are *derived* (no hardcoded list that can go stale), so a new
    codemod wrongly placed in ``CANONICAL_CODEMODS`` (and thus selectable) or one
    omitted from the catalog would be caught — incl. the runtime-gated GTR014/015.
    """
    from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS
    from galaxy_tool_xml_codemod.catalog import coded_codemods

    catalog_upgrade_only = {cls.meta.code for cls in coded_codemods()} - {
        cls.meta.code for cls in CANONICAL_CODEMODS
    }
    registry_upgrade_only = set(all_handles()) - set(known_codes())
    assert registry_upgrade_only == catalog_upgrade_only
    assert registry_upgrade_only.isdisjoint(registry())
    assert {"GTR014", "GTR015"} <= registry_upgrade_only  # runtime-gated wiring guard


def test_by_code_returns_the_handle() -> None:
    handle = by_code("GTR002")
    assert handle.meta.code == "GTR002"
    assert handle.family == "codemod"
    assert handle.fixable is True
    assert handle.apply is not None


def test_by_code_unknown_raises() -> None:
    with pytest.raises(UnknownRuleCode):
        by_code("GTR999")
    # Upgrade-only codes are not selectable, so they are "unknown" to by_code —
    # incl. the runtime-gated pair.
    for code in ("GTR012", "GTR014", "GTR015"):
        with pytest.raises(UnknownRuleCode):
            by_code(code)


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
    handle = by_code("GTR002")
    with pytest.raises(ValueError, match="duplicate rule code 'GTR002'"):
        _build_index([(handle, True), (handle, True)])
