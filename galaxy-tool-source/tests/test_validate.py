"""Tests for profile-aware validation."""

from pathlib import Path

import pytest

from galaxy_tool_source.binding import (
    load_tool,
    newest_valid_profile,
    oldest_valid_profile,
    validate_tool,
)
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


def test_newest_valid_profile_honors_a_ceiling(data_dir: Path) -> None:
    # The minimal tool validates everywhere, so the capped scan returns the
    # ceiling itself (a vendored profile); the default scan is unchanged.
    unbounded = newest_valid_profile(data_dir / "minimal_tool.xml")
    assert newest_valid_profile(data_dir / "minimal_tool.xml", ceiling="24.1") == "24.1"
    assert (
        newest_valid_profile(data_dir / "minimal_tool.xml", ceiling=None) == unbounded
    )


def test_newest_valid_profile_ceiling_below_all_profiles_is_none(
    data_dir: Path,
) -> None:
    # No vendored profile lies at or below 16.04, so a capped scan has nothing
    # to validate against.
    assert newest_valid_profile(data_dir / "minimal_tool.xml", ceiling="16.04") is None


# <required_files> entered the schema at 21.09, so this tool is invalid at
# every older vendored profile — it exercises the ascending scan's skip past
# invalid profiles (the minimal-bump case).
_REQUIRED_FILES_TOOL = (
    b'<tool id="t" name="t" version="1">'
    b'<required_files><include path="x.py"/></required_files>'
    b"<command>echo</command><inputs/><outputs/></tool>"
)


def test_oldest_valid_profile_returns_the_floor_when_valid_there(
    data_dir: Path,
) -> None:
    # The minimal tool validates everywhere, so the oldest profile at or above
    # the floor is the floor itself.
    assert oldest_valid_profile(data_dir / "minimal_tool.xml", floor="16.10") == "16.10"
    assert oldest_valid_profile(data_dir / "minimal_tool.xml", floor="24.1") == "24.1"


def test_oldest_valid_profile_non_vendored_floor_admits_the_next_profile(
    data_dir: Path,
) -> None:
    # Galaxy's 16.01 legacy default is below every vendored XSD; the scan
    # starts at the oldest vendored profile at or above the floor.
    assert oldest_valid_profile(data_dir / "minimal_tool.xml", floor="16.01") == "16.10"


def test_oldest_valid_profile_skips_profiles_the_tool_is_invalid_at() -> None:
    assert oldest_valid_profile(_REQUIRED_FILES_TOOL, floor="16.01") == "21.09"


def test_oldest_valid_profile_none_when_never_valid() -> None:
    assert (
        oldest_valid_profile(b"<tool><not_a_real_element/></tool>", floor="16.01")
        is None
    )


def test_oldest_valid_profile_none_when_floor_above_all_profiles(
    data_dir: Path,
) -> None:
    assert oldest_valid_profile(data_dir / "minimal_tool.xml", floor="99.9") is None


def test_oldest_valid_profile_honors_a_ceiling(data_dir: Path) -> None:
    # No vendored profile lies in [16.01, 16.04]; with the ceiling lifted to a
    # vendored release the scan lands on it.
    minimal = data_dir / "minimal_tool.xml"
    assert oldest_valid_profile(minimal, floor="16.01", ceiling="16.04") is None
    assert oldest_valid_profile(minimal, floor="16.10", ceiling="16.10") == "16.10"


def test_oldest_valid_profile_ceiling_excludes_the_only_valid_profiles() -> None:
    # The required-files tool first validates at 21.09; a ceiling below that
    # leaves nothing to return even though the floor admits older profiles.
    assert (
        oldest_valid_profile(_REQUIRED_FILES_TOOL, floor="16.01", ceiling="21.05")
        is None
    )


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
