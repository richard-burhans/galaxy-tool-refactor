"""Tests for the pure logic of ``scripts.poll_galaxy_servers``.

Only the network-free helpers are tested (parsing a version payload, the
deployment floor, the profile-ceiling mapping, the pre-release flag); the actual
HTTP poll is exercised by running the script against the live servers.
"""

from __future__ import annotations

from scripts.poll_galaxy_servers import (
    ServerVersion,
    deployment_floor,
    parse_version_payload,
    profile_ceiling_for_floor,
)


def _v(name: str, major: str, minor: str, *, reachable: bool = True) -> ServerVersion:
    return ServerVersion(
        name=name, version_major=major, version_minor=minor, reachable=reachable
    )


def test_parse_version_payload_reads_major_and_minor() -> None:
    version = parse_version_payload(
        "usegalaxy.org", {"version_major": "26.1", "version_minor": "rc1"}
    )
    assert version.version_major == "26.1"
    assert version.version_minor == "rc1"
    assert version.reachable


def test_prerelease_flag() -> None:
    assert _v("a", "26.1", "rc1").prerelease
    assert _v("b", "26.0", "1.dev1").prerelease
    assert not _v("c", "25.1", "2").prerelease


def test_deployment_floor_is_the_lowest_reachable_major() -> None:
    versions = [
        _v("org", "26.1", "rc1"),
        _v("eu", "26.0", "1.dev1"),
        _v("fr", "25.1", "3.dev0"),
    ]
    assert deployment_floor(versions) == "25.1"


def test_deployment_floor_ignores_unreachable_servers() -> None:
    versions = [
        _v("org", "26.1", "rc1"),
        _v("down", "", "", reachable=False),
    ]
    assert deployment_floor(versions) == "26.1"


def test_deployment_floor_none_when_nothing_reachable() -> None:
    assert deployment_floor([_v("down", "", "", reachable=False)]) is None


def test_profile_ceiling_maps_floor_to_newest_vendored_at_or_below() -> None:
    available = ["24.0", "24.1", "24.2", "25.0", "25.1", "26.0", "26.1"]
    # An exact match resolves to itself.
    assert profile_ceiling_for_floor("25.1", available) == "25.1"
    # A floor with no exact vendored profile drops to the next one down.
    assert profile_ceiling_for_floor("25.2", available) == "25.1"
    # No floor, or no vendored profile low enough, yields None.
    assert profile_ceiling_for_floor(None, available) is None
    assert profile_ceiling_for_floor("16.01", available) is None
