"""Tests for the runtime-gated-fix family + profile-conditioned selection."""

from __future__ import annotations

from galaxy_tool_codemod.codemods.fix_from_work_dir_whitespace import (
    FixFromWorkDirWhitespace,
)
from galaxy_tool_codemod.runtime_fixes import (
    RUNTIME_GATED_FIXES,
    runtime_fixes_for,
)


def test_registry_contains_the_from_work_dir_fix() -> None:
    assert FixFromWorkDirWhitespace in RUNTIME_GATED_FIXES
    # every registered fix declares an introduction profile
    assert all(fix.introduced_profile for fix in RUNTIME_GATED_FIXES)


def test_selection_is_crossing_conditioned() -> None:
    # A tool crossing UP through 21.09 (baseline below, reached at/above) gets the fix.
    assert FixFromWorkDirWhitespace in runtime_fixes_for(
        "26.1", baseline_profile="16.01"
    )
    assert FixFromWorkDirWhitespace in runtime_fixes_for(
        "21.09", baseline_profile="20.09"
    )
    # ...one that stalls below it does not (Galaxy <21.09 stripped anyway).
    assert FixFromWorkDirWhitespace not in runtime_fixes_for(
        "20.09", baseline_profile="16.01"
    )


def test_crossing_gate_skips_tools_already_past_the_boundary() -> None:
    # A tool ALREADY declaring >= the fix's introduction is left untouched — Galaxy
    # already applies the new behaviour, so rewriting would change current behaviour.
    assert FixFromWorkDirWhitespace not in runtime_fixes_for(
        "26.1", baseline_profile="21.09"
    )
    assert FixFromWorkDirWhitespace not in runtime_fixes_for(
        "26.1", baseline_profile="22.01"
    )


def test_unplaceable_baseline_applies_no_runtime_fixes() -> None:
    # A None / unparseable (macro-token) baseline can't be placed, so we apply
    # nothing and let the §23 semantic warning report instead.
    assert runtime_fixes_for("26.1", baseline_profile=None) == ()
    assert runtime_fixes_for("26.1", baseline_profile="@PROFILE@") == ()
