"""Tests for the runtime-gated-fix family + profile-conditioned selection."""

from __future__ import annotations

from galaxy_tool_xml_codemod.codemods.fix_from_work_dir_whitespace import (
    FixFromWorkDirWhitespace,
)
from galaxy_tool_xml_codemod.runtime_fixes import (
    RUNTIME_GATED_FIXES,
    runtime_fixes_for,
)


def test_registry_contains_the_from_work_dir_fix() -> None:
    assert FixFromWorkDirWhitespace in RUNTIME_GATED_FIXES
    # every registered fix declares an introduction profile
    assert all(fix.introduced_profile for fix in RUNTIME_GATED_FIXES)


def test_selection_is_profile_conditioned() -> None:
    # A tool that reaches >= 21.09 gets the from_work_dir fix...
    assert FixFromWorkDirWhitespace in runtime_fixes_for("26.1")
    assert FixFromWorkDirWhitespace in runtime_fixes_for("21.09")
    # ...one that stalls below it does not (Galaxy <21.09 stripped anyway).
    assert FixFromWorkDirWhitespace not in runtime_fixes_for("20.09")
