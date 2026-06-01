"""Tests for profile resolution and the vendored-schema registry."""

import pytest
from packaging.version import Version

from galaxy_tool_xml.profiles import (
    UnknownProfileError,
    available_profiles,
    compiled_schema,
    is_newer_profile,
    latest_profile,
    resolve_profile,
)


def test_available_profiles_sorted_ascending() -> None:
    profiles = available_profiles()
    assert profiles == sorted(profiles, key=Version)
    assert "26.0" in profiles


def test_latest_profile_is_last() -> None:
    assert latest_profile() == available_profiles()[-1]


def test_resolve_exact_match() -> None:
    assert resolve_profile("21.09") == "21.09"


def test_resolve_none_is_galaxy_default() -> None:
    # No profile= -> Galaxy's 16.01 legacy default -> nearest vendored (oldest).
    assert resolve_profile(None) == available_profiles()[0]
    assert resolve_profile(None) != latest_profile()


def test_resolve_nearest_not_newer() -> None:
    assert resolve_profile("20.06") == "20.05"


def test_resolve_nearest_older_than_all_is_oldest() -> None:
    assert resolve_profile("16.04") == available_profiles()[0]


def test_resolve_nearest_newer_than_all_is_latest() -> None:
    assert resolve_profile("99.9") == latest_profile()


def test_resolve_unparseable_profile_is_latest() -> None:
    assert resolve_profile("not-a-version") == latest_profile()


def test_resolve_exact_mode_raises() -> None:
    with pytest.raises(UnknownProfileError):
        resolve_profile("99.9", on_missing="exact")


def test_is_newer_profile() -> None:
    assert is_newer_profile("24.2", "24.1") is True
    assert is_newer_profile("24.1", "24.1") is False  # strictly newer only
    assert is_newer_profile("24.0", "24.2") is False
    # an unparseable baseline (e.g. a macro token) is never treated as older
    assert is_newer_profile("26.1", "@PROFILE@") is False


def test_resolve_latest_mode() -> None:
    assert resolve_profile("99.9", on_missing="latest") == latest_profile()


def test_resolve_invalid_on_missing() -> None:
    with pytest.raises(ValueError, match="on_missing"):
        resolve_profile("99.9", on_missing="bogus")


def test_compiled_schema_for_latest() -> None:
    schema = compiled_schema(latest_profile())
    assert schema is compiled_schema(latest_profile())  # cached


def test_compiled_schema_for_uncompilable_release() -> None:
    # release 21.09 ships a non-deterministic content model; it must still
    # compile after the in-memory Output-group fix.
    assert compiled_schema("21.09") is not None
