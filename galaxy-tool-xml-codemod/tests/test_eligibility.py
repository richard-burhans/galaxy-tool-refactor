"""Tests for ``corpus_test_profile_for`` — the codemod sweep eligibility policy."""

from __future__ import annotations

from galaxy_tool_xml_codemod.eligibility import corpus_test_profile_for

_PROFILES = ("20.01", "20.05", "21.05", "23.0", "26.1")


def _valid_at(*allowed: str) -> object:
    """Build a ``validates_at`` callable that returns True for the given profiles."""
    allowed_set = set(allowed)
    return lambda profile: profile in allowed_set


def test_returns_none_when_no_profile_validates() -> None:
    """No valid profile at all → ineligible."""
    result = corpus_test_profile_for(
        "20.05", validates_at=_valid_at(), profiles=_PROFILES  # type: ignore[arg-type]
    )
    assert result is None


def test_returns_newest_valid_when_no_declared() -> None:
    """No declared profile → newest valid wins."""
    result = corpus_test_profile_for(
        None,
        validates_at=_valid_at("20.05", "21.05", "23.0"),  # type: ignore[arg-type]
        profiles=_PROFILES,
    )
    assert result == "23.0"


def test_returns_declared_when_declared_is_valid() -> None:
    """Declared profile validates → honour the maintainer's contract."""
    result = corpus_test_profile_for(
        "20.05",
        validates_at=_valid_at("20.05", "21.05", "23.0"),  # type: ignore[arg-type]
        profiles=_PROFILES,
    )
    assert result == "20.05"


def test_picks_oldest_newer_profile_when_declared_invalid() -> None:
    """Declared invalid → use the oldest strictly-newer profile that validates."""
    result = corpus_test_profile_for(
        "20.01",
        validates_at=_valid_at("21.05", "23.0", "26.1"),  # type: ignore[arg-type]
        profiles=_PROFILES,
    )
    assert result == "21.05"


def test_does_not_fall_back_to_older_profiles() -> None:
    """Declared invalid + only older profiles valid → ineligible.

    The user policy is to try strictly *newer* profiles. Falling back to
    an older valid profile would let a tool author silently use an
    older-than-declared profile, which would mask a real maintainer
    bug.
    """
    result = corpus_test_profile_for(
        "23.0",
        validates_at=_valid_at("20.05", "21.05"),  # type: ignore[arg-type]
        profiles=_PROFILES,
    )
    assert result is None


def test_falls_back_to_newest_valid_when_declared_not_in_profiles() -> None:
    """Declared profile not on the vendored list (e.g. ``@PROFILE@``) → newest valid."""
    result = corpus_test_profile_for(
        "@PROFILE@",
        validates_at=_valid_at("20.05", "21.05"),  # type: ignore[arg-type]
        profiles=_PROFILES,
    )
    assert result == "21.05"


def test_skips_declared_invalid_with_no_newer_anything() -> None:
    """Declared is the newest profile but invalid → no newer to try → ineligible."""
    result = corpus_test_profile_for(
        "26.1",
        validates_at=_valid_at("20.05"),  # type: ignore[arg-type]
        profiles=_PROFILES,
    )
    assert result is None


def test_short_circuits_when_declared_is_valid() -> None:
    """Common case: declared profile validates → exactly one probe.

    The codemod sweep runs over thousands of tools; if a typical
    well-authored tool triggers ``validates_at`` for every vendored
    profile, the dominant cost balloons unnecessarily.
    """
    probed: list[str] = []

    def validates_at(profile: str) -> bool:
        probed.append(profile)
        return profile == "20.05"

    result = corpus_test_profile_for(
        "20.05", validates_at=validates_at, profiles=_PROFILES
    )
    assert result == "20.05"
    assert probed == ["20.05"]


def test_short_circuits_when_no_declared_at_newest_valid() -> None:
    """No declared → scan newest-first; stop at the first valid match."""
    probed: list[str] = []

    def validates_at(profile: str) -> bool:
        probed.append(profile)
        return profile in {"20.05", "23.0"}

    result = corpus_test_profile_for(
        None, validates_at=validates_at, profiles=_PROFILES
    )
    assert result == "23.0"
    # Reverse scan: probed 26.1, 23.0 (stop). Should NOT probe older
    # profiles once a valid one is found.
    assert probed == ["26.1", "23.0"]
