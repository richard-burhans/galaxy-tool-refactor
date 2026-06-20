#!/usr/bin/env python3
"""Poll major public Galaxy servers for the Galaxy release they run.

A tool's ``profile`` is a forward-compatibility contract: a server can only
install a tool whose ``profile`` is at most the server's own Galaxy release. So
the newest profile a tool can declare and still run *everywhere people actually
use* is bounded by the **lowest** release among the major servers, not by the
newest profile Galaxy has ever shipped (which may be an unreleased pre-release).
This script gathers that data: it queries each curated server's public
``/api/version`` endpoint (no auth) and reports the per-server release, the
deployment floor (the lowest ``version_major`` across the set), and the newest
*vendored* profile at or below that floor (the deployment ceiling).

It writes a dated snapshot to ``docs/galaxy_server_versions.json``, the source
of truth for the vendored ``DEPLOYMENT_CEILING`` that caps
``upgrade --modernize`` (``galaxy_tool_refactor_registry/deployment.py``,
registry decisions D23). After a re-poll moves the snapshot, update
``deployment.py`` to match; the drift-guard test
(``galaxy-tool-refactor-registry/tests/test_deployment.py``) fails naming both
files until they agree. Network failures degrade gracefully: an unreachable
server is reported as such and excluded from the floor, and the run still
exits 0 as long as at least one server answered.

Run from the workspace root::

    uv run python -m scripts.poll_galaxy_servers
    uv run python -m scripts.poll_galaxy_servers --no-write   # report only
"""

from __future__ import annotations

import argparse
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from packaging.version import InvalidVersion, Version

logger = logging.getLogger("poll_galaxy_servers")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SNAPSHOT_PATH = _REPO_ROOT / "docs" / "galaxy_server_versions.json"

# The curated set of major public Galaxy servers. Deliberately small and
# federation-flagship: these are the deployments most tools must run on. Edit
# this list to change the policy population.
MAJOR_SERVERS: dict[str, str] = {
    "usegalaxy.org": "https://usegalaxy.org",
    "usegalaxy.eu": "https://usegalaxy.eu",
    "usegalaxy.org.au": "https://usegalaxy.org.au",
    "usegalaxy.fr": "https://usegalaxy.fr",
    "usegalaxy.ca": "https://usegalaxy.ca",
}

_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class ServerVersion:
    """One server's reported Galaxy release."""

    name: str
    version_major: str  # the release, e.g. "25.1" (the profile-relevant part)
    version_minor: str  # the point/build, e.g. "3.dev0", "rc1", "2"
    reachable: bool

    @property
    def prerelease(self) -> bool:
        """Whether the running build is a dev or release-candidate, not a final point release."""
        minor = self.version_minor.lower()
        return "dev" in minor or "rc" in minor


def parse_version_payload(name: str, payload: dict[str, object]) -> ServerVersion:
    """Build a ``ServerVersion`` from a ``/api/version`` JSON body (pure)."""
    major = str(payload.get("version_major", "")).strip()
    minor = str(payload.get("version_minor", "")).strip()
    return ServerVersion(
        name=name, version_major=major, version_minor=minor, reachable=True
    )


def deployment_floor(versions: list[ServerVersion], /) -> str | None:
    """The lowest parseable ``version_major`` among reachable servers, or ``None``.

    This is the highest profile every server in the set can install (pure).
    """
    parseable: list[tuple[Version, str]] = []
    for version in versions:
        if not version.reachable:
            continue
        parsed = _version_or_none(version.version_major)
        if parsed is not None:
            parseable.append((parsed, version.version_major))
    if not parseable:
        return None
    return min(parseable, key=lambda item: item[0])[1]


def profile_ceiling_for_floor(
    floor: str | None, available_profiles: list[str], /
) -> str | None:
    """The newest vendored profile at or below *floor* (pure).

    ``None`` when there is no floor or no vendored profile is low enough. A
    server release with no exactly-matching vendored XSD still resolves to the
    newest vendored profile it can run (the next one down).
    """
    if floor is None:
        return None
    cap = _version_or_none(floor)
    if cap is None:
        return None
    candidates = [
        profile
        for profile in available_profiles
        if (parsed := _version_or_none(profile)) is not None and parsed <= cap
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda profile: Version(profile))


def _version_or_none(value: str, /) -> Version | None:
    try:
        return Version(value)
    except InvalidVersion:
        return None


def poll_server(name: str, base_url: str, /) -> ServerVersion:
    """Query one server's ``/api/version`` (network boundary; never raises)."""
    url = f"{base_url.rstrip('/')}/api/version"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        logger.warning("%s: unreachable (%s)", name, error)
        return ServerVersion(
            name=name, version_major="", version_minor="", reachable=False
        )
    return parse_version_payload(name, payload)


def _available_profiles() -> list[str]:
    """The vendored profiles, or ``[]`` if the package is not importable."""
    try:
        from galaxy_tool_source.profiles import available_profiles
    except ImportError:
        logger.warning("galaxy_tool_source not importable; skipping profile mapping")
        return []
    return available_profiles()


def _snapshot(versions: list[ServerVersion], today: str) -> dict[str, object]:
    profiles = _available_profiles()
    floor = deployment_floor(versions)
    return {
        "polled_on": today,
        "servers": [
            {
                "name": v.name,
                "version_major": v.version_major,
                "version_minor": v.version_minor,
                "reachable": v.reachable,
                "prerelease": v.prerelease if v.reachable else None,
            }
            for v in versions
        ],
        "deployment_floor": floor,
        "profile_ceiling": profile_ceiling_for_floor(floor, profiles),
    }


def _report(snapshot: dict[str, object]) -> None:
    print("\n=== major Galaxy server versions ===")
    for server in cast("list[dict[str, object]]", snapshot["servers"]):
        if server["reachable"]:
            flag = " (pre-release)" if server["prerelease"] else ""
            print(
                f"  {server['name']:18} {server['version_major']}"
                f".{server['version_minor']}{flag}"
            )
        else:
            print(f"  {server['name']:18} unreachable")
    floor = snapshot["deployment_floor"]
    ceiling = snapshot["profile_ceiling"]
    print(f"\nDeployment floor (lowest server release): {floor or '(none reachable)'}")
    print(f"Newest vendored profile at or below the floor: {ceiling or '(none)'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.poll_galaxy_servers",
        description=(
            "Poll major public Galaxy servers for their Galaxy release and "
            "report the deployment floor + candidate profile ceiling."
        ),
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="report only; do not write docs/galaxy_server_versions.json",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    versions = [poll_server(name, url) for name, url in MAJOR_SERVERS.items()]
    today = date.today().isoformat()
    snapshot = _snapshot(versions, today)
    _report(snapshot)

    if not any(v.reachable for v in versions):
        logger.error("no server was reachable; not writing a snapshot")
        return 1
    if not args.no_write:
        _SNAPSHOT_PATH.write_text(
            json.dumps(snapshot, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {_SNAPSHOT_PATH.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
