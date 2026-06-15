#!/usr/bin/env python3
"""Durable canonical-form coverage tracker (auto-fix system N6).

Plan: ``~/.claude/plans/tools-iuc-autofix-system.md``. The forward gate (Half B)
and the bulk normalizer (Half A) act on a repository; this tracks, over time, how
canonical that repository *is*: the fraction of its tools that already pass the
gate (need no behaviour-preserving fix). It is the project's analog of Carta's
type-coverage curve (14% climbing to 67%): a one-time bulk pass plus a forward gate
should drive this toward 100% and hold it there.

Each run measures one repository against the **gate-eligible** rule subset (the
exact set the forward gate enforces, read from
``galaxy_tool_refactor_registry.gate_eligibility``), appends a dated snapshot to
``docs/corpus_data/coverage_history.json``, and renders the trend to
``docs/coverage_tracker.md``. Re-running on the same date for the same repo
replaces that day's snapshot (idempotent). Needs a repository clone, so it is not
run in CI.

Usage::

    uv run python -m scripts.coverage_tracker --repo-root .local/tools-iuc --repo-name tools-iuc
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from pathlib import Path

from galaxy_tool_refactor_registry.facade import detect as facade_detect
from galaxy_tool_refactor_registry.gate_eligibility import (
    GATE_ELIGIBLE,
    eligibility_groups,
)

from scripts._shared import is_tool_document, iter_tool_xmls

logger = logging.getLogger("coverage_tracker")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HISTORY = _REPO_ROOT / "docs" / "corpus_data" / "coverage_history.json"
_DOC = _REPO_ROOT / "docs" / "coverage_tracker.md"
_BEGIN = "<!-- BEGIN generated coverage trend -->"
_END = "<!-- END generated coverage trend -->"


@cache
def gate_codes() -> frozenset[str]:
    """The gate-eligible rule set — what 'canonical' means for coverage."""
    return frozenset(eligibility_groups()[GATE_ELIGIBLE])


@dataclass
class CoverageSnapshot:
    """A repository's canonical-form coverage at one point in time."""

    date: str
    repo: str
    total_tools: int = 0
    clean: int = 0
    per_code_flagged: Counter[str] = field(default_factory=Counter)
    skipped: int = 0

    @property
    def pct(self) -> float:
        """Canonical coverage as a percentage (clean / total)."""
        return (100.0 * self.clean / self.total_tools) if self.total_tools else 0.0


def measure_coverage(
    root: Path, /, *, repo: str, snapshot_date: str, codes: frozenset[str]
) -> CoverageSnapshot:
    """Measure *root*'s canonical coverage under *codes*. Pure (no I/O writes).

    A tool is *clean* when no gate-eligible rule fires on it; a tool whose detect
    raises is skipped (counted) rather than scored, so a malformed tool never
    silently inflates or deflates coverage.
    """
    snapshot = CoverageSnapshot(date=snapshot_date, repo=repo)
    for path in sorted(iter_tool_xmls(root)):
        if not is_tool_document(path):
            continue
        try:
            result = facade_detect(path, codes=codes)
        except Exception as error:  # noqa: BLE001 — coverage sweep: an uncheckable tool is skipped
            logger.warning("skipping %s: %s", path, error)
            snapshot.skipped += 1
            continue
        snapshot.total_tools += 1
        fired = {violation.code for violation in result.violations}
        if fired:
            for code in fired:
                snapshot.per_code_flagged[code] += 1
        else:
            snapshot.clean += 1
    return snapshot


def _load_history(path: Path, /) -> list[dict[str, object]]:
    """Return the recorded snapshots (newest-appended list), or empty."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    snapshots = raw.get("snapshots") if isinstance(raw, dict) else None
    return [s for s in snapshots if isinstance(s, dict)] if isinstance(snapshots, list) else []


def record_snapshot(snapshot: CoverageSnapshot, /, *, history_path: Path = _HISTORY) -> None:
    """Append *snapshot* to the history, replacing any same-(date, repo) entry."""
    history = [
        s
        for s in _load_history(history_path)
        if not (s.get("date") == snapshot.date and s.get("repo") == snapshot.repo)
    ]
    history.append(
        {
            "date": snapshot.date,
            "repo": snapshot.repo,
            "total_tools": snapshot.total_tools,
            "clean": snapshot.clean,
            "pct": round(snapshot.pct, 1),
            "skipped": snapshot.skipped,
            "per_code_flagged": dict(snapshot.per_code_flagged.most_common()),
        }
    )
    history.sort(key=lambda s: (str(s.get("repo")), str(s.get("date"))))
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps({"snapshots": history}, indent=2) + "\n", encoding="utf-8"
    )


def render_trend(history: list[dict[str, object]], /) -> str:
    """Render the per-repository coverage trend as the generated doc body."""
    if not history:
        return "_No coverage snapshots recorded yet._"
    by_repo: dict[str, list[dict[str, object]]] = {}
    for snap in history:
        by_repo.setdefault(str(snap.get("repo", "?")), []).append(snap)
    lines: list[str] = []
    for repo in sorted(by_repo):
        snaps = sorted(by_repo[repo], key=lambda s: str(s.get("date")))
        latest = snaps[-1]
        lines.append(f"## `{repo}`")
        lines.append("")
        lines.append("| Date | Tools | Canonical | Coverage |")
        lines.append("|---|---:|---:|---:|")
        for snap in snaps:
            lines.append(
                f"| {snap.get('date')} | {snap.get('total_tools')} | "
                f"{snap.get('clean')} | {snap.get('pct')}% |"
            )
        per_code = latest.get("per_code_flagged")
        if isinstance(per_code, dict) and per_code:
            top = ", ".join(f"{code} ({n})" for code, n in list(per_code.items())[:8])
            lines.append("")
            lines.append(f"Latest ({latest.get('date')}) top blocking rules: {top}.")
        lines.append("")
    return "\n".join(lines).rstrip()


def _write_doc(history: list[dict[str, object]], /, *, out: Path = _DOC) -> None:
    """Rewrite the generated trend block in the coverage doc."""
    codes = ", ".join(sorted(gate_codes()))
    preamble = (
        "# Canonical-form coverage over time\n\n"
        "> Generated by `python -m scripts.coverage_tracker`. Tracks the share of a\n"
        "> repository's tools that are already **canonical** under the gate-eligible\n"
        "> rule subset (what the forward gate enforces), over time. The auto-fix\n"
        "> system's goal is to drive this toward 100% (a one-time bulk pass) and hold\n"
        "> it there (the forward gate). Carta's type-coverage-curve analog.\n\n"
        f"Gate-eligible rules scored: {codes}. See "
        "[`gate_eligibility.md`](gate_eligibility.md) and "
        "[`forward_gate.md`](forward_gate.md).\n\n"
    )
    if out.exists():
        text = out.read_text(encoding="utf-8")
        before = text.split(_BEGIN)[0] if _BEGIN in text else preamble
    else:
        before = preamble
    block = f"{_BEGIN}\n{render_trend(history)}\n{_END}"
    out.write_text(f"{before}{block}\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    """Measure coverage, record a dated snapshot, render the trend."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Track canonical-form coverage over time.")
    parser.add_argument("--repo-root", type=Path, required=True, help="a repository clone")
    parser.add_argument("--repo-name", required=True, help="label for the repo in the history")
    parser.add_argument("--no-record", action="store_true", help="measure + print only")
    args = parser.parse_args(argv)

    if not args.repo_root.is_dir():
        logger.error("not a directory: %s", args.repo_root)
        return 2

    snapshot = measure_coverage(
        args.repo_root,
        repo=args.repo_name,
        snapshot_date=date.today().isoformat(),
        codes=gate_codes(),
    )
    print(
        f"\n{args.repo_name} @ {snapshot.date}: {snapshot.clean}/{snapshot.total_tools} "
        f"canonical ({snapshot.pct:.1f}%); {snapshot.skipped} skipped"
    )
    for code, count in snapshot.per_code_flagged.most_common(8):
        print(f"  {code}: {count} tools flagged")
    if not args.no_record:
        record_snapshot(snapshot)
        _write_doc(_load_history(_HISTORY))
        logger.info("recorded snapshot -> %s; rendered %s", _HISTORY.name, _DOC.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
