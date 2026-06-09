"""Tests for the unified ``code -> RuleHandle`` registry."""

from __future__ import annotations

import pytest
from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_xml.document import ToolDocument

from galaxy_tool_refactor_registry.errors import UnknownRuleCode
from galaxy_tool_refactor_registry.handle import RuleHandle
from galaxy_tool_refactor_registry.registry import (
    _build_index,
    _index,
    _validate_partitions,
    advisory_codes,
    all_handles,
    by_code,
    known_codes,
    registry,
)


def _fake_handle(
    code: str, *, parent: str | None = None, fixable: bool = True
) -> RuleHandle:
    """A synthetic RuleHandle for exercising the partition guard in isolation."""

    def _detect(_document: ToolDocument) -> list:
        return []

    def _apply(_document: ToolDocument) -> None:
        return None

    return RuleHandle(
        meta=RuleMeta(
            code=code, summary="x", since="0.0.1", parent=parent,
            detect_only=not fixable,
        ),
        family="codemod" if fixable else "check",
        fixable=fixable,
        detect=_detect,
        apply=_apply if fixable else None,
    )


def _index_of(*handles: RuleHandle) -> dict[str, tuple[RuleHandle, bool]]:
    return {h.meta.code: (h, True) for h in handles}


def test_known_codes_are_the_selectable_set() -> None:
    """Selectable = canonical codemods + cosmetic fmt + advisory checks (derived)."""
    from galaxy_tool_xml_codemod.canonical import canonical_codemods

    codes = known_codes()
    # canonical codemods are selectable (derived from ruleset membership)...
    assert {cls.meta.code for cls in canonical_codemods()} <= codes
    assert {"GTR001", "GTR021"} <= codes  # a cosmetic fmt rule + an advisory check
    # ...upgrade-only codemods are NOT selectable (derived: all_handles − selectable).
    upgrade_only = set(all_handles()) - codes
    assert upgrade_only and upgrade_only.isdisjoint(codes)


def test_upgrade_only_set_matches_the_codemod_catalog() -> None:
    """Registry's non-selectable codemod codes == coded_codemods − canonical.

    Both sides are *derived* (no hardcoded list that can go stale), so a new
    codemod wrongly tagged with a ruleset (and thus selectable) or one omitted
    from the catalog would be caught — incl. the runtime-gated GTR014/015.
    """
    from galaxy_tool_xml_codemod.canonical import canonical_codemods
    from galaxy_tool_xml_codemod.catalog import coded_codemods

    catalog_upgrade_only = {cls.meta.code for cls in coded_codemods()} - {
        cls.meta.code for cls in canonical_codemods()
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
    # Iterate real rule handles, not known_codes() — the latter now also includes
    # partition *parent* group codes (e.g. GTR020), which are not themselves rules.
    for handle in registry().values():
        if handle.fixable:
            assert handle.apply is not None
        else:
            assert handle.apply is None


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


def test_real_registry_passes_the_partition_guard() -> None:
    """The baked-in registry satisfies the partition invariants (it builds, so the
    guard in _index() already ran; this asserts it explicitly)."""
    _validate_partitions(_index())  # must not raise


def test_partition_guard_accepts_a_well_formed_partition() -> None:
    _validate_partitions(
        _index_of(
            _fake_handle("GTR900.1", parent="GTR900", fixable=True),
            _fake_handle("GTR900.2", parent="GTR900", fixable=False),
        )
    )


def test_partition_guard_rejects_a_non_dotted_child_code() -> None:
    with pytest.raises(ValueError, match="must be coded '<parent>"):
        _validate_partitions(
            _index_of(
                _fake_handle("GTR901X", parent="GTR901", fixable=True),
                _fake_handle("GTR901.2", parent="GTR901", fixable=False),
            )
        )


def test_partition_guard_rejects_parent_colliding_with_a_rule() -> None:
    with pytest.raises(ValueError, match="collides with a real rule"):
        _validate_partitions(
            _index_of(
                _fake_handle("GTR902", fixable=True),  # a real rule named like a parent
                _fake_handle("GTR902.1", parent="GTR902", fixable=True),
                _fake_handle("GTR902.2", parent="GTR902", fixable=False),
            )
        )


def test_partition_guard_requires_both_a_fix_and_an_advisory_child() -> None:
    with pytest.raises(ValueError, match="no advisory sub-rule"):
        _validate_partitions(
            _index_of(
                _fake_handle("GTR903.1", parent="GTR903", fixable=True),
                _fake_handle("GTR903.2", parent="GTR903", fixable=True),  # both fixable
            )
        )
    with pytest.raises(ValueError, match="no fixable sub-rule"):
        _validate_partitions(
            _index_of(
                _fake_handle("GTR904.1", parent="GTR904", fixable=False),
                _fake_handle("GTR904.2", parent="GTR904", fixable=False),  # no fix
            )
        )
