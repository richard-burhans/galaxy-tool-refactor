"""The deployment profile ceiling: the newest profile major public servers run.

The modernize walk targets the latest vendored profile, but the newest
vendored profile can be a pre-release no public server runs yet (26.1 at the
time of the current snapshot): a tool declaring it cannot install on the
lagging servers, however behaviour-safe the walk was. The deployment ceiling
is the second, orthogonal cap on the walk: the newest vendored profile at or
below the deployment floor, the lowest release across the major public Galaxy
servers (usegalaxy.org, .eu, .org.au, .fr, and .ca).

The value is vendored here rather than read from disk at runtime (the
installed package must not depend on a repo doc). Its source of truth is the
committed snapshot ``docs/galaxy_server_versions.json``, written by
``uv run python -m scripts.poll_galaxy_servers``; the drift guard
(``tests/test_deployment.py``) fails when the snapshot and these constants
disagree, naming both.

Scope (registry ``docs/decisions.md`` D23): the ceiling caps only the walk
modes without an explicit target. ``target_profile`` expresses deliberate
intent and may exceed it (a note still mentions the ceiling), and the
minimal-bump default ignores it entirely; a bump the tool strictly needs for
validity always wins (zero corpus tools need one above the ceiling,
``docs/upgrade_minimal_need_stats.md``).
"""

from datetime import date, timedelta

DEPLOYMENT_CEILING = "25.1"
"""The newest vendored profile every major public Galaxy server can run."""

DEPLOYMENT_SNAPSHOT_DATE = date(2026, 6, 12)
"""The ``polled_on`` date of the snapshot the ceiling was vendored from."""

SNAPSHOT_STALE_AFTER = timedelta(days=180)
"""Galaxy releases land roughly twice a year, so a snapshot older than this
may lag a release (and with it, the true deployment floor)."""


def snapshot_is_stale(*, today: date) -> bool:
    """Whether the vendored snapshot is old enough that the ceiling may lag.

    *today* is injected (no hidden clock) so callers and tests stay
    deterministic; the facade passes ``date.today()`` and appends a
    re-poll suggestion to the upgrade notes when this returns ``True``.
    """
    return today - DEPLOYMENT_SNAPSHOT_DATE > SNAPSHOT_STALE_AFTER
