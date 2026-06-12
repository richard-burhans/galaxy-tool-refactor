"""Tests for ``behavior_gate``: the behavior-preserving upgrade ceiling.

The gate decides how far an upgrade can walk while provably preserving runtime
behaviour: every Galaxy behaviour code the bump would cross must be either not
applicable to the tool, or cleared by its mapped auto-fix (proven by execution:
apply the fix to a copy and re-detect), or the walk stops below it. The ceiling
is the newest vendored profile strictly below the first surviving blocker.
"""

from __future__ import annotations

from galaxy_tool_source.profiles import available_profiles, latest_profile
from packaging.version import Version

from galaxy_tool_codemod.behavior_gate import (
    auto_fixes_by_code,
    behavior_ceiling,
    blocked_below_baseline,
    blocking_codes,
    code_cleared_by_autofix,
    placeable_baseline,
    resolved_baseline,
)
from galaxy_tool_codemod.codemods.fix_interpreter import FixInterpreter
from galaxy_tool_codemod.parse import parse_module
from galaxy_tool_codemod.profile_semantics import (
    PROFILE_UPGRADE_CODES,
    ProfileUpgradeCode,
)
from galaxy_tool_codemod.runtime_fixes import RUNTIME_GATED_FIXES

_HEAD = b'<tool id="t" name="T" version="1.0.0">'


def _blocker(profile: str, *, level: str = "must_fix") -> ProfileUpgradeCode:
    """A synthetic catalogue entry for ceiling-math tests (pure, no document)."""
    return ProfileUpgradeCode(
        code=f"synthetic_{profile.replace('.', '_')}",
        profile=profile,
        level=level,
        niche=False,
        message="synthetic",
        url=None,
    )


# --- the fix -> Galaxy-code mapping ---------------------------------------------


def test_every_fix_declares_its_galaxy_upgrade_code() -> None:
    catalogue = {change.code: change for change in PROFILE_UPGRADE_CODES}
    for fix in RUNTIME_GATED_FIXES:
        assert fix.upgrade_code in catalogue
        entry = catalogue[fix.upgrade_code]
        # The fix clears the behaviour change introduced at its own profile...
        assert entry.profile == fix.introduced_profile
        # ...and every runtime-gated fix mirrors a must_fix code (module contract).
        assert entry.level == "must_fix"


def test_auto_fixes_by_code_maps_every_runtime_gated_fix() -> None:
    mapping = auto_fixes_by_code()
    assert set(mapping) == {fix.upgrade_code for fix in RUNTIME_GATED_FIXES}
    for fix in RUNTIME_GATED_FIXES:
        assert mapping[fix.upgrade_code] is fix


# --- the auto-fix probe (proof by execution) -------------------------------------


def test_probe_clears_a_fixable_interpreter_tool() -> None:
    module = parse_module(
        _HEAD + b'<command interpreter="python">myscript.py $input</command></tool>'
    )
    assert code_cleared_by_autofix(
        module.document, fix=FixInterpreter, code="16_04_fix_interpreter"
    )
    # The probe works on a copy: the caller's tree is untouched.
    command = module.document.root.find("command")
    assert command is not None and command.get("interpreter") == "python"


def test_probe_blocks_an_unfixable_interpreter_tool() -> None:
    # Bucket B: the command's first token is Cheetah, so FixInterpreter soundly
    # declines and the detector still fires on the probe result.
    module = parse_module(
        _HEAD + b'<command interpreter="python">$script $input</command></tool>'
    )
    assert not code_cleared_by_autofix(
        module.document, fix=FixInterpreter, code="16_04_fix_interpreter"
    )


# --- blocking_codes (the policy filter) ------------------------------------------


def test_blocking_codes_default_policy_keeps_unfixable_must_fix_only() -> None:
    # Trips: 16_04_fix_interpreter (auto-fixable here), 24_2_fix_test_case_validation
    # (no auto-fix), and several consider-level codes (implicit extra-file
    # collection, exit_code, home directory). Default policy keeps only the
    # surviving must_fix blocker.
    module = parse_module(
        _HEAD
        + b'<command interpreter="python">myscript.py</command>'
        + b"<tests><test/></tests></tool>"
    )
    blockers = blocking_codes(module.document, baseline="16.01")
    assert [change.code for change in blockers] == ["24_2_fix_test_case_validation"]


def test_blocking_codes_keeps_an_unfixable_interpreter_in_profile_order() -> None:
    module = parse_module(
        _HEAD
        + b'<command interpreter="python">$script</command>'
        + b"<tests><test/></tests></tool>"
    )
    blockers = blocking_codes(module.document, baseline="16.01")
    assert [change.code for change in blockers] == [
        "16_04_fix_interpreter",
        "24_2_fix_test_case_validation",
    ]


def test_blocking_codes_levels_seam_includes_consider() -> None:
    module = parse_module(_HEAD + b"<command>cat in > out</command></tool>")
    blockers = blocking_codes(
        module.document,
        baseline="16.01",
        levels=frozenset({"must_fix", "consider"}),
    )
    # Galaxy emits this consider code unconditionally within the 16.04 migration.
    assert "16_04_consider_implicit_extra_file_collection" in {
        change.code for change in blockers
    }


def test_blocking_codes_respects_the_baseline_range() -> None:
    # A tool already at 25.0 crosses nothing above it that applies here.
    module = parse_module(
        _HEAD + b"<command>cat in > out</command><tests><test/></tests></tool>"
    )
    assert blocking_codes(module.document, baseline="25.0") == ()


def test_blocking_codes_unparseable_baseline_blocks_nothing() -> None:
    # An unplaceable baseline cannot range the bump; the caller (the facade)
    # must fail closed separately. The gate itself reports no blockers.
    module = parse_module(_HEAD + b"<tests><test/></tests></tool>")
    assert blocking_codes(module.document, baseline="@PROFILE@") == ()


# --- behavior_ceiling (the cap math) ----------------------------------------------


def test_no_blockers_means_the_latest_profile() -> None:
    assert behavior_ceiling(()) == latest_profile()


def test_ceiling_is_the_newest_vendored_profile_below_the_first_blocker() -> None:
    below = [
        profile
        for profile in available_profiles()
        if Version(profile) < Version("24.2")
    ]
    expected = max(below, key=Version)
    assert behavior_ceiling((_blocker("24.2"),)) == expected


def test_ceiling_uses_the_lowest_blocker_regardless_of_order() -> None:
    expected = behavior_ceiling((_blocker("24.2"),))
    assert behavior_ceiling((_blocker("25.1"), _blocker("24.2"))) == expected


def test_no_vendored_profile_below_the_blocker_means_none() -> None:
    # The oldest vendored profile is 16.10, so a 16.04 blocker on a legacy-default
    # baseline leaves no safe profile to declare at all.
    assert min(available_profiles(), key=Version) == "16.10"
    assert behavior_ceiling((_blocker("16.04"),)) is None


def test_placeable_baseline_rejects_tokens_and_none() -> None:
    assert placeable_baseline("16.01")
    assert placeable_baseline("24.2")
    assert not placeable_baseline(None)
    assert not placeable_baseline("@PROFILE@")


def test_resolved_baseline_defaults_declares_and_resolves_tokens() -> None:
    assert (
        resolved_baseline(parse_module(_HEAD + b"<inputs/></tool>").document)
        == "16.01"
    )
    declared = parse_module(
        b'<tool id="t" name="T" version="1" profile="21.09"><inputs/></tool>'
    )
    assert resolved_baseline(declared.document) == "21.09"
    tokenised = parse_module(
        b'<tool id="t" name="T" version="1" profile="@PROFILE@">'
        b'<macros><token name="@PROFILE@">24.1</token></macros><inputs/></tool>'
    )
    assert resolved_baseline(tokenised.document) == "24.1"
    unresolved = parse_module(
        b'<tool id="t" name="T" version="1" profile="@PROFILE@"><inputs/></tool>'
    )
    assert resolved_baseline(unresolved.document) is None


def test_gate_never_lowers_a_declared_profile() -> None:
    # A tool already declaring a profile at or above the ceiling keeps its
    # declaration: the blockers were crossed by its author's declaration, not by
    # this upgrade. A None ceiling always reads as blocked.
    assert blocked_below_baseline(ceiling=None, baseline="16.01")
    assert blocked_below_baseline(ceiling="24.1", baseline="25.0")
    assert not blocked_below_baseline(ceiling="24.1", baseline="24.1")
    assert not blocked_below_baseline(ceiling="24.1", baseline="16.01")
    # An unparseable baseline cannot be compared; that case fails closed earlier
    # (the facade's unplaceable-baseline path), so the predicate stays False.
    assert not blocked_below_baseline(ceiling="24.1", baseline="@PROFILE@")
