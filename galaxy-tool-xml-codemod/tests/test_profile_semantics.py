"""Tests for the profile runtime-behaviour (semantic) change map."""

from __future__ import annotations

from packaging.version import Version

from galaxy_tool_xml_codemod.profile_semantics import (
    SEMANTIC_PROFILE_CHANGES,
    semantic_changes_crossed,
)


def test_every_key_is_a_valid_version() -> None:
    for version in SEMANTIC_PROFILE_CHANGES:
        Version(version)  # raises if not a valid version


def test_crossed_is_open_below_closed_above() -> None:
    """from < V <= to: the from-profile itself is not re-crossed; the target is."""
    crossed = dict(semantic_changes_crossed(from_profile="20.05", to_profile="20.09"))
    assert "20.09" in crossed  # closed at the top
    assert "20.05" not in crossed  # open at the bottom


def test_full_span_from_no_profile_baseline_crosses_many() -> None:
    """A 16.01 (no-profile) tool bumped to latest crosses every documented change."""
    crossed = semantic_changes_crossed(from_profile="16.01", to_profile="26.1")
    versions = [v for v, _ in crossed]
    assert versions == sorted(versions, key=Version)
    # the high-impact boundaries are all present
    assert {"16.04", "19.05", "20.05", "20.09", "23.0"} <= set(versions)


def test_no_change_when_not_upward() -> None:
    assert semantic_changes_crossed(from_profile="24.2", to_profile="24.2") == []
    assert semantic_changes_crossed(from_profile="26.0", to_profile="24.0") == []


def test_additive_only_span_crosses_nothing() -> None:
    """A bump between two adjacent additive profiles crosses no semantic boundary."""
    # 24.2 -> 25.0 is additive (no documented runtime change at 25.0).
    assert semantic_changes_crossed(from_profile="24.2", to_profile="25.0") == []


def test_unparseable_profile_yields_no_changes() -> None:
    """A macro-token profile can't be placed, so it crosses nothing (no false alarm)."""
    assert semantic_changes_crossed(from_profile="@PROFILE@", to_profile="26.1") == []
    assert semantic_changes_crossed(from_profile="16.01", to_profile="@TOKEN@") == []
