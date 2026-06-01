"""Tests for the vendored Galaxy tool-profile upgrade-code catalogue."""

from __future__ import annotations

from packaging.version import Version

from galaxy_tool_xml_codemod.profile_semantics import (
    PROFILE_UPGRADE_CODES,
    upgrade_codes_crossed,
)


def test_catalogue_shape() -> None:
    codes = [change.code for change in PROFILE_UPGRADE_CODES]
    assert len(codes) == len(set(codes))  # unique code names
    for change in PROFILE_UPGRADE_CODES:
        Version(change.profile)  # every profile is a valid version
        assert change.level in {"must_fix", "consider"}  # the `ready` note is omitted
    # Galaxy's `ready` note and the two changes it doesn't catalogue are absent.
    assert "16_04_ready_interpreter" not in codes
    profiles = {change.profile for change in PROFILE_UPGRADE_CODES}
    assert "19.05" not in profiles and "25.1" not in profiles


def test_crossed_is_open_below_closed_above() -> None:
    """from < profile <= to: the from-profile isn't re-crossed; the target is."""
    crossed = {
        c.code
        for c in upgrade_codes_crossed(from_profile="20.05", to_profile="20.09")
    }
    assert "20_09_consider_set_e" in crossed  # closed at the top
    assert "20_09_consider_output_collection_order" in crossed
    assert not any(c.startswith("20_05") for c in crossed)  # open at the bottom


def test_full_span_from_no_profile_baseline_crosses_all() -> None:
    """A 16.01 (no-profile) tool bumped to latest crosses every catalogued code."""
    crossed = upgrade_codes_crossed(from_profile="16.01", to_profile="26.1")
    assert len(crossed) == len(PROFILE_UPGRADE_CODES)
    codes = {c.code for c in crossed}
    assert {"16_04_exit_code", "20_09_consider_set_e"} <= codes
    assert "24_2_fix_test_case_validation" in codes


def test_no_change_when_not_upward() -> None:
    assert upgrade_codes_crossed(from_profile="24.2", to_profile="24.2") == []
    assert upgrade_codes_crossed(from_profile="26.0", to_profile="24.0") == []


def test_additive_only_span_crosses_nothing() -> None:
    """24.2 -> 25.0 has no catalogued code (25.0 is additive)."""
    assert upgrade_codes_crossed(from_profile="24.2", to_profile="25.0") == []


def test_unparseable_profile_yields_no_codes() -> None:
    """A macro-token profile can't be placed, so it crosses nothing (no false alarm)."""
    assert upgrade_codes_crossed(from_profile="@PROFILE@", to_profile="26.1") == []
    assert upgrade_codes_crossed(from_profile="16.01", to_profile="@TOKEN@") == []
