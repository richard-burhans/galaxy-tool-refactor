#!/usr/bin/env python3
"""Measure our tooling's impact against the open-PR corpus built by ``fetch_iuc_prs``.

For every snapshotted PR (see ``scripts/fetch_iuc_prs.py``) this answers: how
often is a change a human made in the PR one our ``format`` / ``upgrade`` /
``check`` tooling would have made or flagged automatically? Two metrics, both
computed in **canonical space** (every file run through the cosmetic formatter
first) so pure indentation / quote / shorthand churn never registers as a
difference:

* **DETECT ("would-have-flagged")** — a rule code our ``check`` reports on the
  *before* ref but not on *head*: the human fixed something we detect.
* **FIX ("would-have-auto-fixed")** — a structural change our fixable rules
  *produce* that coincides with what the human did. Attributed to a concrete
  GTR code by isolating each rule's effect (``cosmetic | {code}``) and asking
  whether its diff hunks are a subset of the human's diff hunks. A
  ``full_reproduce`` is the strongest form: our ``format`` (or ``upgrade``)
  output on *before* equals *head*.

Both metrics are reported for **both baselines**: ``base`` (the PR's
target-branch ref → the full PR contribution) and ``first`` (the PR's
first-commit ref → ``first``→``head`` is the review-driven delta, the most
faithful "suggested by a maintainer" signal).

**Reading the numbers — DETECT is largely an artifact; trust FIX.** A code can stop
firing between *before* and *head* for reasons unrelated to the human fixing what we
detect — a macro edit shifting a ``$var``'s provability, a positional change moving an
occurrence — so the DETECT / "would-have-flagged" share is inflated (sampling put it
~90% artifact). The execution-grounded signal is FIX: the lines our *isolated* fix would
add/remove are a subset of the lines the human added/removed. FIX is low (≈1-2%) and that
is the honest headline — IUC tools are already clean, and PR edits are mostly substantive
logic/version changes outside our mechanical scope. FIX's blind spot is a pure element
reorder (GTR013 moves identical lines → empty multiset delta); within-line fixes
(GTR002/GTR005) are captured.

Writes ``docs/pr_impact_stats.md`` and a ranked example list
``docs/corpus_data/pr_impact_examples.json`` (the source of the real before/after
examples folded into the audience guide).

Usage::

    uv run python -m scripts.pr_impact [--repo OWNER/NAME] [--limit N] \
        [--baseline {base,first,both}] [--no-stats] [--examples-only]
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
from galaxy_tool_refactor_registry.facade import run as facade_run
from galaxy_tool_refactor_registry.facade import upgrade as facade_upgrade
from galaxy_tool_refactor_registry.registry import registry
from galaxy_tool_refactor_registry.resolve import resolve_codes, resolve_upgrade_codes

logger = logging.getLogger("pr_impact")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PR_CORPUS_ROOT = _REPO_ROOT / ".local" / "pr-corpus"
_DEFAULT_REPO = "galaxyproject/tools-iuc"
_STATS_PAGE = _REPO_ROOT / "docs" / "pr_impact_stats.md"
_EXAMPLES_JSON = _REPO_ROOT / "docs" / "corpus_data" / "pr_impact_examples.json"
_BASELINES = ("base", "first")


@cache
def _cosmetic_codes() -> frozenset[str]:
    """The cosmetic-only fmt rule set — the canonical-space noise-canceller."""
    return resolve_codes(rulesets=["cosmetic"])


@cache
def _strict_codes() -> frozenset[str]:
    """The widest detect net: canonical codemods + cosmetic + advisory checks."""
    return resolve_codes(rulesets=["strict"])


@cache
def _iuc_fixable_codes() -> tuple[str, ...]:
    """The fixable rule codes in the default ruleset, sorted (for isolation runs)."""
    reg = registry()
    return tuple(
        sorted(code for code in resolve_codes(rulesets=["default"]) if reg[code].fixable)
    )


def _canonical_bytes(path: Path, /) -> bytes:
    """Return *path* run through the cosmetic formatter — canonical whitespace.

    This is the single canonicalizer: two files that differ only in formatting
    canonicalize to identical bytes, so structural diffs are isolated downstream.
    """
    return facade_run(path, codes=_cosmetic_codes()).formatted


def _canonical_lines(path: Path, /) -> list[str]:
    """Canonical bytes of *path* as decoded lines (for difflib)."""
    return _canonical_bytes(path).decode("utf-8").splitlines()


def _detect_codes(path: Path, /, *, codes: frozenset[str]) -> dict[str, str]:
    """Map each rule code that fires on *path* to one of its messages.

    Keyed by **code only** (not line / xpath): a coincidence means the human
    eliminated every instance of that code, which is robust to the positional
    churn that contaminates per-location keys when surrounding content shifts.
    """
    result = facade_detect(path, codes=codes)
    found: dict[str, str] = {}
    for violation in result.violations:
        found.setdefault(violation.code, violation.message)
    return found


@dataclass(frozen=True)
class DetectCoincidence:
    """A code our ``check`` reports somewhere on *before* but nowhere on *head*."""

    pr: int
    relpath: str
    baseline: str
    code: str
    message: str


@dataclass(frozen=True)
class FixCoincidence:
    """A structural change our fixable rules produce that the human also made."""

    pr: int
    relpath: str
    baseline: str
    code: str
    kind: str  # "full_reproduce" | "hunk_subset"
    before_snippet: str
    after_snippet: str


@dataclass
class PrImpactResult:
    """Aggregated impact across the swept PR corpus."""

    pr_count: int = 0
    prs_with_before: dict[str, set[int]] = field(default_factory=dict)
    detect: list[DetectCoincidence] = field(default_factory=list)
    fix: list[FixCoincidence] = field(default_factory=list)
    prs_with_detect: dict[str, set[int]] = field(default_factory=dict)
    prs_with_fix: dict[str, set[int]] = field(default_factory=dict)
    per_code_detect: Counter[tuple[str, str]] = field(default_factory=Counter)
    per_code_fix: Counter[tuple[str, str]] = field(default_factory=Counter)


def _detect_coincidences(
    before_path: Path, head_path: Path, /, *, codes: frozenset[str]
) -> list[tuple[str, str]]:
    """Return ``(code, message)`` for codes that fire on *before* but not *head*.

    By-code (not by-location): the human eliminated every instance of a class of
    issue our ``check`` reports. Robust to positional churn from surrounding edits.
    """
    before_codes = _detect_codes(before_path, codes=codes)
    head_codes = _detect_codes(head_path, codes=codes)
    gone = before_codes.keys() - head_codes.keys()
    return [(code, before_codes[code]) for code in sorted(gone)]


def _snippet(lines: list[str], /) -> str:
    """Render lines as a stripped, joined snippet for the doc example."""
    return "\n".join(line.strip() for line in lines if line.strip())


def _line_delta(before_lines: list[str], after_lines: list[str], /) -> tuple[Counter[str], Counter[str]]:
    """Return ``(added, removed)`` line multisets between two canonical line lists."""
    before = Counter(before_lines)
    after = Counter(after_lines)
    return after - before, before - after


def _fix_coincidences(
    before_path: Path,
    head_path: Path,
    /,
    *,
    candidate_codes: list[str],
) -> list[tuple[str, str, str, str]]:
    """Return ``(code, kind, before_snippet, after_snippet)`` coincidences.

    A code coincides when every canonical line its isolated fix *adds* (and
    every line it *removes*) is also a line the human added (removed) between
    *before* and *head*. Position-independent line-multiset containment, so it
    survives hunk coalescing; exact-line in canonical space, so formatting churn
    is cancelled. *candidate_codes* are the fixable codes our detector already
    reports on *before* (a rule cannot fix what it does not detect). A vacuous PR
    (before == head once canonicalized) yields nothing.
    """
    before_lines = _canonical_lines(before_path)
    head_canon = _canonical_bytes(head_path)
    if _canonical_bytes(before_path) == head_canon:
        return []
    head_lines = head_canon.decode("utf-8").splitlines()
    human_added, human_removed = _line_delta(before_lines, head_lines)
    if not human_added and not human_removed:
        return []

    cosmetic = _cosmetic_codes()
    our_iuc = facade_run(before_path, codes=resolve_codes(rulesets=["default"])).formatted
    our_upgrade = facade_upgrade(before_path, codes=resolve_upgrade_codes()).formatted
    full_reproduce = our_iuc == head_canon or our_upgrade == head_canon

    coincidences: list[tuple[str, str, str, str]] = []
    for code in candidate_codes:
        our_lines = facade_run(before_path, codes=cosmetic | {code}).formatted.decode("utf-8").splitlines()
        our_added, our_removed = _line_delta(before_lines, our_lines)
        if not our_added and not our_removed:
            continue  # code is a no-op here (e.g. already covered by cosmetic)
        if our_added <= human_added and our_removed <= human_removed:
            kind = "full_reproduce" if full_reproduce else "hunk_subset"
            coincidences.append(
                (
                    code,
                    kind,
                    _snippet(sorted(our_removed.elements())),
                    _snippet(sorted(our_added.elements())),
                )
            )
    return coincidences


def _baseline_ok(entry: dict[str, object], baseline: str, /) -> bool:
    """Return True when *baseline*'s before-ref is usable for *entry*."""
    snapshot = entry.get("snapshot")
    if not isinstance(snapshot, dict):
        return False
    ref = snapshot.get(baseline)
    if not isinstance(ref, dict) or not ref.get("present"):
        return False
    if baseline == "first" and entry.get("single_commit") is True:
        return False  # first == head: no review delta
    return True


def _measure_pr_impact(
    repo_root: Path,
    manifest: dict[str, dict[str, object]],
    /,
    *,
    detect_codes: frozenset[str],
    fix_codes: tuple[str, ...],
    baselines: tuple[str, ...] = _BASELINES,
) -> PrImpactResult:
    """Sweep the on-disk PR corpus and aggregate detect + fix coincidences.

    Pure: no printing, no file writes. *repo_root* is the per-repo corpus dir
    (the one holding the ``pr-<N>/`` snapshots). Per-file facade failures are
    logged and skipped so one bad tool never aborts the sweep.
    """
    result = PrImpactResult()
    fix_code_set = frozenset(fix_codes)
    for baseline in baselines:
        result.prs_with_before[baseline] = set()
        result.prs_with_detect[baseline] = set()
        result.prs_with_fix[baseline] = set()

    for key, entry in sorted(manifest.items(), key=lambda item: int(item[0])):
        if entry.get("status") != "ok":
            continue
        result.pr_count += 1
        number = int(key)
        changed = entry.get("changed_xml_files")
        if not isinstance(changed, list):
            continue
        pr_dir = repo_root / f"pr-{number}"
        for baseline in baselines:
            if not _baseline_ok(entry, baseline):
                continue
            head_dir = pr_dir / "head"
            before_dir = pr_dir / baseline
            saw_before_file = False
            for relpath in changed:
                if not isinstance(relpath, str):
                    continue
                before_path = before_dir / relpath
                head_path = head_dir / relpath
                if not before_path.is_file() or not head_path.is_file():
                    continue
                saw_before_file = True
                _accumulate(
                    result,
                    number=number,
                    relpath=relpath,
                    baseline=baseline,
                    before_path=before_path,
                    head_path=head_path,
                    detect_codes=detect_codes,
                    fix_code_set=fix_code_set,
                )
            if saw_before_file:
                result.prs_with_before[baseline].add(number)
    return result


def _accumulate(
    result: PrImpactResult,
    /,
    *,
    number: int,
    relpath: str,
    baseline: str,
    before_path: Path,
    head_path: Path,
    detect_codes: frozenset[str],
    fix_code_set: frozenset[str],
) -> None:
    """Compute one (PR, file, baseline) cell and fold it into *result*.

    LBYL boundary: the facade is the one place that can raise on a malformed
    snapshot; a failure here is logged and the cell skipped (per-tool isolation).
    """
    try:
        detected = _detect_coincidences(before_path, head_path, codes=detect_codes)
        before_codes = _detect_codes(before_path, codes=detect_codes)
        candidates = sorted(before_codes.keys() & fix_code_set)
        fixed = _fix_coincidences(before_path, head_path, candidate_codes=candidates)
    except Exception as error:  # noqa: BLE001 — corpus sweep: a malformed snapshot is skipped, not fatal
        logger.warning("skipping PR #%d %s (%s): %s", number, relpath, baseline, error)
        return

    for code, message in detected:
        result.detect.append(
            DetectCoincidence(number, relpath, baseline, code, message)
        )
        result.per_code_detect[(baseline, code)] += 1
        result.prs_with_detect[baseline].add(number)
    for code, kind, before_snippet, after_snippet in fixed:
        result.fix.append(
            FixCoincidence(
                number, relpath, baseline, code, kind, before_snippet, after_snippet
            )
        )
        result.per_code_fix[(baseline, code)] += 1
        result.prs_with_fix[baseline].add(number)


def _rank_examples(result: PrImpactResult, /) -> list[FixCoincidence]:
    """Rank fix coincidences for the doc: full_reproduce first, then by recency."""
    return sorted(
        result.fix,
        key=lambda coincidence: (
            coincidence.kind != "full_reproduce",
            -coincidence.pr,
        ),
    )


def _share(numerator: set[int], denominator: set[int], /) -> str:
    """Render ``len(numerator)/len(denominator)`` as ``N/D (P%)``."""
    total = len(denominator)
    hit = len(numerator & denominator)
    pct = (100.0 * hit / total) if total else 0.0
    return f"{hit}/{total} ({pct:.1f}%)"


@dataclass
class PrSetComposition:
    """How the scanned PRs split into qualifying vs dropped (and why)."""

    scanned: int = 0
    qualifying: int = 0
    drop_reasons: Counter[str] = field(default_factory=Counter)
    new_tool: int = 0
    modify: int = 0
    single_commit: int = 0
    other_status: Counter[str] = field(default_factory=Counter)


def _pr_set_composition(manifest: dict[str, dict[str, object]], /) -> PrSetComposition:
    """Tally the scanned PR set: qualifying vs dropped (by reason) and shape.

    Pure. ``scanned`` is every manifest entry; ``qualifying`` is the ``ok`` ones,
    split into new-tool (no ``base`` ref), modify (has a ``base`` ref), and the
    single-commit subset (no ``first``→``head`` review delta).
    """
    comp = PrSetComposition()
    for entry in manifest.values():
        comp.scanned += 1
        status = entry.get("status")
        if status == "dropped":
            reason = entry.get("drop_reason")
            comp.drop_reasons[str(reason).split(":", 1)[0] if reason else "unknown"] += 1
            continue
        if status != "ok":
            comp.other_status[str(status)] += 1
            continue
        comp.qualifying += 1
        if entry.get("new_tool") is True:
            comp.new_tool += 1
        else:
            comp.modify += 1
        if entry.get("single_commit") is True:
            comp.single_commit += 1
    return comp


def _report_pr_impact(result: PrImpactResult, comp: PrSetComposition, /) -> None:
    """Print the composition + headline shares to stdout."""
    print(f"\n=== pr-impact ({result.pr_count} PRs swept) ===")
    print(
        f"scanned {comp.scanned}: {comp.qualifying} qualifying "
        f"({comp.new_tool} new-tool, {comp.modify} modify, "
        f"{comp.single_commit} single-commit); dropped "
        + ", ".join(f"{n} {r}" for r, n in sorted(comp.drop_reasons.items(), key=lambda kv: -kv[1]))
    )
    for baseline in _BASELINES:
        before = result.prs_with_before.get(baseline, set())
        if not before:
            continue
        print(f"baseline {baseline!r} (PRs with a usable before-ref: {len(before)})")
        print(f"  would-have-flagged (detect): {_share(result.prs_with_detect[baseline], before)}")
        print(f"  would-have-auto-fixed (fix): {_share(result.prs_with_fix[baseline], before)}")


def _write_examples(result: PrImpactResult, repo: str, /, *, out: Path = _EXAMPLES_JSON) -> None:
    """Write the ranked example candidates as machine-readable JSON."""
    examples = [
        {
            "pr": coincidence.pr,
            "html_url": f"https://github.com/{repo}/pull/{coincidence.pr}",
            "relpath": coincidence.relpath,
            "baseline": coincidence.baseline,
            "code": coincidence.code,
            "kind": coincidence.kind,
            "before": coincidence.before_snippet,
            "after": coincidence.after_snippet,
        }
        for coincidence in _rank_examples(result)[:20]
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"repo": repo, "examples": examples}, indent=2) + "\n", encoding="utf-8")


def _composition_lines(comp: PrSetComposition, /) -> list[str]:
    """Render the PR-set composition as markdown table rows."""
    lines = [
        "## PR set composition",
        "",
        f"Of **{comp.scanned}** pull requests scanned, **{comp.qualifying}** "
        "qualified (open/merged · non-draft · touches a tool XML · not a bot or "
        "version-bump-only). The rest were dropped:",
        "",
        "| Outcome | Count |",
        "|---|---|",
        f"| qualifying | {comp.qualifying} |",
    ]
    for reason, count in sorted(comp.drop_reasons.items(), key=lambda kv: -kv[1]):
        lines.append(f"| dropped: {reason} | {count} |")
    for status, count in sorted(comp.other_status.items()):
        lines.append(f"| {status} | {count} |")
    lines += [
        "",
        "Among the qualifying PRs:",
        "",
        "| Shape | Count |",
        "|---|---|",
        f"| new tool (no `base` version) | {comp.new_tool} |",
        f"| modifies an existing tool | {comp.modify} |",
        f"| single-commit (no `first`→`head` review delta) | {comp.single_commit} |",
        "",
    ]
    return lines


def _write_pr_impact_stats(
    result: PrImpactResult,
    comp: PrSetComposition,
    repo: str,
    /,
    *,
    retrieved: str,
    out: Path = _STATS_PAGE,
) -> None:
    """Write ``docs/pr_impact_stats.md`` from *result* and *comp*."""
    lines = [
        "# PR-impact statistics",
        "",
        f"_Generated by `python -m scripts.pr_impact` on {date.today().isoformat()}; "
        f"swept {result.pr_count} qualifying PRs from `{repo}` "
        f"(PR corpus retrieved {retrieved})._",
        "",
        "Reproduced by: `python -m scripts.fetch_iuc_prs` then `python -m scripts.pr_impact`",
        "",
        *_composition_lines(comp),
        "## Headline",
        "",
        "Share of qualifying PRs where our tooling would have made or flagged "
        "at least one of the human's changes:",
        "",
        "| Baseline | PRs w/ before-ref | Would-have-flagged | Would-have-auto-fixed |",
        "|---|---|---|---|",
    ]
    for baseline in _BASELINES:
        before = result.prs_with_before.get(baseline, set())
        if not before:
            continue
        lines.append(
            f"| `{baseline}` | {len(before)} | "
            f"{_share(result.prs_with_detect[baseline], before)} | "
            f"{_share(result.prs_with_fix[baseline], before)} |"
        )
    lines += [
        "",
        "> **Reading these numbers.** The **Detect** / *would-have-flagged* column is "
        "largely an artifact — a code can stop firing between *before* and *head* "
        "because of a macro-provability or positional shift, not because the human "
        "fixed what we detect (sampling put this ~90% artifact). The trustworthy, "
        "execution-grounded signal is **Fix** / *would-have-auto-fixed* (our isolated "
        "fix's added/removed lines are a subset of the human's). Fix is low because IUC "
        "tools are already clean and PR edits are mostly substantive logic/version "
        "changes outside our mechanical scope.",
    ]
    lines += ["", "## Per-code coincidences", "", "| Baseline | Code | Detect | Fix |", "|---|---|---|---|"]
    codes = sorted(
        {code for (_b, code) in result.per_code_detect}
        | {code for (_b, code) in result.per_code_fix}
    )
    for baseline in _BASELINES:
        for code in codes:
            det = result.per_code_detect.get((baseline, code), 0)
            fix = result.per_code_fix.get((baseline, code), 0)
            if det or fix:
                lines.append(f"| `{baseline}` | {code} | {det} | {fix} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_manifest(corpus_name: str, /) -> dict[str, dict[str, object]]:
    """Load the PR-corpus manifest's ``pull_requests`` map for *corpus_name*."""
    path = _PR_CORPUS_ROOT / corpus_name / "manifest.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    prs = raw.get("pull_requests")
    if not isinstance(prs, dict):
        return {}
    return {key: entry for key, entry in prs.items() if isinstance(entry, dict)}


def _manifest_retrieved(corpus_name: str, /) -> str:
    """Return the manifest's ``retrieved`` date, or ``unknown``."""
    path = _PR_CORPUS_ROOT / corpus_name / "manifest.json"
    if not path.exists():
        return "unknown"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("retrieved"), str):
        return str(raw["retrieved"])
    return "unknown"


def main(argv: list[str]) -> int:
    """Run the PR-impact analysis; return a process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Measure tooling impact over the PR corpus.")
    parser.add_argument("--repo", default=_DEFAULT_REPO, metavar="OWNER/NAME")
    parser.add_argument(
        "--corpus-name",
        default="",
        metavar="NAME",
        help="corpus subdir under .local/pr-corpus (default: the repo slug)",
    )
    parser.add_argument("--limit", type=int, default=0, help="cap PRs swept (0 = all on disk)")
    parser.add_argument("--baseline", choices=("base", "first", "both"), default="both")
    parser.add_argument("--no-stats", action="store_true", help="skip writing the stats page")
    parser.add_argument("--examples-only", action="store_true", help="write only the examples JSON")
    args = parser.parse_args(argv)

    corpus_name = args.corpus_name or args.repo.replace("/", "__")
    repo_root = _PR_CORPUS_ROOT / corpus_name
    manifest = _load_manifest(corpus_name)
    if not manifest:
        logger.error("no PR-corpus manifest for %s (run scripts.fetch_iuc_prs first)", corpus_name)
        return 1
    if args.limit:
        ok_keys = [k for k, e in sorted(manifest.items(), key=lambda i: int(i[0])) if e.get("status") == "ok"]
        keep = set(ok_keys[: args.limit])
        manifest = {k: e for k, e in manifest.items() if e.get("status") != "ok" or k in keep}

    baselines = _BASELINES if args.baseline == "both" else (args.baseline,)
    composition = _pr_set_composition(manifest)
    result = _measure_pr_impact(
        repo_root,
        manifest,
        detect_codes=_strict_codes(),
        fix_codes=_iuc_fixable_codes(),
        baselines=baselines,
    )
    _report_pr_impact(result, composition)

    retrieved = _manifest_retrieved(corpus_name)
    _write_examples(result, args.repo)
    if not args.no_stats and not args.examples_only:
        _write_pr_impact_stats(result, composition, args.repo, retrieved=retrieved)
        logger.info("wrote %s", _STATS_PAGE.relative_to(_REPO_ROOT))
    logger.info("wrote %s", _EXAMPLES_JSON.relative_to(_REPO_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
