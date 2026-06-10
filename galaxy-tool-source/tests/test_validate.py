"""Tests for profile-aware validation."""

from pathlib import Path

import pytest

from galaxy_tool_source.binding import load_tool, newest_valid_profile, validate_tool
from galaxy_tool_source.profiles import (
    UnknownProfileError,
    available_profiles,
    latest_profile,
)


def test_declared_profile_selects_matching_schema(data_dir: Path) -> None:
    result = validate_tool(data_dir / "minimal_tool.xml")
    assert result.valid
    assert result.validated
    assert result.schema_version == "24.0"
    assert result.declared_profile == "24.0"


def test_no_profile_tool_uses_galaxy_default(data_dir: Path) -> None:
    # Galaxy runs a no-profile tool as its 16.01 legacy default; we validate
    # against the nearest vendored XSD (the oldest, 16.10) — not the latest.
    result = validate_tool(data_dir / "tool_no_profile.xml")
    assert result.schema_version == available_profiles()[0]
    assert result.schema_version != latest_profile()
    assert result.declared_profile is None
    assert result.valid


def test_old_profile_resolves_to_nearest(data_dir: Path) -> None:
    result = validate_tool(data_dir / "tool_old_profile.xml")
    assert result.declared_profile == "16.04"
    assert result.schema_version == "16.10"
    assert result.valid


def test_profile_argument_overrides(data_dir: Path) -> None:
    result = validate_tool(data_dir / "minimal_tool.xml", profile="26.0")
    assert result.schema_version == "26.0"


def test_on_missing_exact_raises(data_dir: Path) -> None:
    with pytest.raises(UnknownProfileError):
        validate_tool(data_dir / "minimal_tool.xml", profile="99.9", on_missing="exact")


def test_invalid_tool_reports_schema_errors(data_dir: Path) -> None:
    result = validate_tool(data_dir / "invalid_tool.xml")
    assert not result.valid
    assert result.validated
    assert result.errors


def test_validate_accepts_mutated_document(data_dir: Path) -> None:
    document = load_tool(data_dir / "minimal_tool.xml")
    document.root.set("name", "Renamed Tool")
    result = validate_tool(document)
    assert result.valid


def test_validate_rejects_bad_macro_handling(data_dir: Path) -> None:
    with pytest.raises(ValueError, match="macro_handling"):
        validate_tool(data_dir / "minimal_tool.xml", macro_handling="bogus")


def test_macro_handling_expand_is_valid(data_dir: Path) -> None:
    result = validate_tool(data_dir / "tool_with_macros.xml")
    assert result.macro_handling == "expand"
    assert result.macros_present
    assert result.validated
    assert result.valid


def test_macro_handling_off_reports_expand_errors(data_dir: Path) -> None:
    result = validate_tool(data_dir / "tool_with_macros.xml", macro_handling="off")
    assert result.validated
    assert not result.valid
    assert result.errors


def test_macro_handling_skip_does_not_validate(data_dir: Path) -> None:
    result = validate_tool(data_dir / "tool_with_macros.xml", macro_handling="skip")
    assert result.macros_present
    assert not result.validated


def test_macro_handling_strip_validates(data_dir: Path) -> None:
    result = validate_tool(data_dir / "tool_with_macros.xml", macro_handling="strip")
    assert result.validated


def test_macro_free_tool_has_macros_present_false(data_dir: Path) -> None:
    result = validate_tool(data_dir / "minimal_tool.xml")
    assert not result.macros_present


def test_transitive_macro_imports_expand_via_document(data_dir: Path) -> None:
    """A chain of <import>ed macro files resolves when validating a document."""
    document = load_tool(data_dir / "tool_nested_macros.xml")
    result = validate_tool(document)  # ToolDocument -> expand_from_tree
    assert result.valid
    assert not result.macro_errors


def test_newest_valid_profile_returns_a_vendored_ceiling(data_dir: Path) -> None:
    result = newest_valid_profile(data_dir / "minimal_tool.xml")
    assert result in available_profiles()


def test_newest_valid_profile_none_when_never_valid() -> None:
    assert newest_valid_profile(b"<tool><not_a_real_element/></tool>") is None


_PROFILE_SWEEP_FIXTURES = [
    "minimal_tool.xml",
    "representative_tool.xml",
    "tool_no_profile.xml",
    "tool_old_profile.xml",
    "tool_with_macros.xml",
]


@pytest.mark.slow
@pytest.mark.parametrize("fixture", _PROFILE_SWEEP_FIXTURES)
def test_newest_valid_profile_matches_validity_vector(
    data_dir: Path, fixture: str
) -> None:
    """newest_valid_profile returns the newest profile in the full validity vector.

    Validity is *not* assumed contiguous — the corpus sweep finds real tools
    whose valid profiles have gaps — so newest_valid_profile is a plain
    newest-first scan and must match the vector's newest ``True`` regardless.
    """
    profiles = available_profiles()
    valid = [
        validate_tool(data_dir / fixture, profile=profile).valid for profile in profiles
    ]
    expected = next(
        (
            profile
            for profile, ok in zip(reversed(profiles), reversed(valid), strict=True)
            if ok
        ),
        None,
    )
    assert newest_valid_profile(data_dir / fixture) == expected
