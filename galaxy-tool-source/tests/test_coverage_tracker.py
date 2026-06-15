"""Tests for the canonical-form coverage tracker (scripts/coverage_tracker.py, N6).

Synthetic only. A ragged-indentation tool is non-canonical (GTR001); running it
through the gate-eligible rule set yields a canonical sibling. So a two-tool repo
has 50% coverage, which the tracker should report, record, and render.
"""

from __future__ import annotations

import json
from pathlib import Path

from galaxy_tool_refactor_registry.facade import run as facade_run
from scripts.coverage_tracker import (
    CoverageSnapshot,
    gate_codes,
    measure_coverage,
    record_snapshot,
    render_trend,
)

_DIRTY = b"""<tool id="t" name="T" version="1.0" profile="24.0">
  <description>d</description>
        <command><![CDATA[echo x]]></command>
  <inputs/>
</tool>
"""

_MACROS = b"""<macros>
    <token name="@TOOL_VERSION@">1.0</token>
</macros>
"""


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "tools" / "foo").mkdir(parents=True)
    (tmp_path / "tools" / "bar").mkdir(parents=True)
    (tmp_path / "tools" / "foo" / "foo.xml").write_bytes(_DIRTY)
    (tmp_path / "tools" / "foo" / "macros.xml").write_bytes(_MACROS)  # not counted
    (tmp_path / "tools" / "bar" / "bar.xml").write_bytes(
        facade_run(tmp_path / "tools" / "foo" / "foo.xml", codes=gate_codes()).formatted
    )
    return tmp_path


def test_measure_coverage_counts_clean_over_tools(tmp_path: Path) -> None:
    snap = measure_coverage(
        _repo(tmp_path), repo="demo", snapshot_date="2026-06-15", codes=gate_codes()
    )
    assert snap.total_tools == 2  # the two <tool> files; macros.xml excluded
    assert snap.clean == 1  # the canonical one
    assert snap.pct == 50.0
    assert snap.per_code_flagged["GTR001"] == 1  # the dirty one


def test_record_snapshot_appends_and_replaces_same_day(tmp_path: Path) -> None:
    history = tmp_path / "history.json"
    record_snapshot(
        CoverageSnapshot(date="2026-06-14", repo="demo", total_tools=10, clean=2),
        history_path=history,
    )
    record_snapshot(
        CoverageSnapshot(date="2026-06-15", repo="demo", total_tools=10, clean=9),
        history_path=history,
    )
    # Re-recording the same (date, repo) replaces, not duplicates.
    record_snapshot(
        CoverageSnapshot(date="2026-06-15", repo="demo", total_tools=10, clean=10),
        history_path=history,
    )
    snaps = json.loads(history.read_text(encoding="utf-8"))["snapshots"]
    assert len(snaps) == 2
    latest = [s for s in snaps if s["date"] == "2026-06-15"][0]
    assert latest["clean"] == 10 and latest["pct"] == 100.0


def test_render_trend_tabulates_per_repo() -> None:
    history = [
        {"date": "2026-06-14", "repo": "demo", "total_tools": 10, "clean": 2,
         "pct": 20.0, "per_code_flagged": {"GTR001": 8}},
        {"date": "2026-06-15", "repo": "demo", "total_tools": 10, "clean": 9,
         "pct": 90.0, "per_code_flagged": {"GTR001": 1}},
    ]
    out = render_trend(history)
    assert "## `demo`" in out
    assert "20.0%" in out and "90.0%" in out
    assert "GTR001 (1)" in out  # latest top blocking rule
