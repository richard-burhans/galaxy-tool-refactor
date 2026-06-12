"""The deployment-ceiling constants and their drift guard.

The ceiling is vendored (the facade must not read a repo doc at runtime), so
this module pins the constants to the committed snapshot
``docs/galaxy_server_versions.json``: when a re-poll moves the snapshot, the
guard fails naming both the snapshot and the constant to update.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from galaxy_tool_source.profiles import available_profiles, latest_profile

from galaxy_tool_refactor_registry import deployment

_SNAPSHOT = (
    Path(__file__).resolve().parents[2] / "docs" / "galaxy_server_versions.json"
)


def test_ceiling_matches_the_committed_snapshot() -> None:
    """DEPLOYMENT_CEILING is vendored from the committed server-poll snapshot."""
    snapshot = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    assert snapshot["profile_ceiling"] == deployment.DEPLOYMENT_CEILING, (
        f"deployment.DEPLOYMENT_CEILING ({deployment.DEPLOYMENT_CEILING!r}) no"
        f" longer matches docs/galaxy_server_versions.json"
        f" ({snapshot['profile_ceiling']!r}); after re-running"
        f" `uv run python -m scripts.poll_galaxy_servers`, update"
        f" DEPLOYMENT_CEILING and DEPLOYMENT_SNAPSHOT_DATE in"
        f" galaxy_tool_refactor_registry/deployment.py to match."
    )


def test_snapshot_date_matches_the_committed_snapshot() -> None:
    """DEPLOYMENT_SNAPSHOT_DATE is the snapshot's polled_on date."""
    snapshot = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    assert (
        deployment.DEPLOYMENT_SNAPSHOT_DATE.isoformat() == snapshot["polled_on"]
    ), (
        f"deployment.DEPLOYMENT_SNAPSHOT_DATE"
        f" ({deployment.DEPLOYMENT_SNAPSHOT_DATE.isoformat()}) no longer"
        f" matches docs/galaxy_server_versions.json polled_on"
        f" ({snapshot['polled_on']!r}); update deployment.py alongside the"
        f" snapshot."
    )


def test_ceiling_is_a_vendored_profile_below_or_at_latest() -> None:
    """The ceiling must be a profile the toolchain can actually declare."""
    profiles = available_profiles()
    assert deployment.DEPLOYMENT_CEILING in profiles
    assert profiles.index(deployment.DEPLOYMENT_CEILING) <= profiles.index(
        latest_profile()
    )


def test_snapshot_is_stale_after_the_threshold() -> None:
    """Staleness flips exactly past the threshold, never before."""
    fresh = deployment.DEPLOYMENT_SNAPSHOT_DATE + timedelta(days=30)
    at_threshold = (
        deployment.DEPLOYMENT_SNAPSHOT_DATE + deployment.SNAPSHOT_STALE_AFTER
    )
    past = at_threshold + timedelta(days=1)
    assert not deployment.snapshot_is_stale(today=fresh)
    assert not deployment.snapshot_is_stale(today=at_threshold)
    assert deployment.snapshot_is_stale(today=past)


def test_snapshot_is_stale_takes_a_date() -> None:
    """The probe is injectable (no hidden today()) so callers stay testable."""
    assert deployment.snapshot_is_stale(today=date(2030, 1, 1))
