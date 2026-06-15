#!/usr/bin/env python3
"""Measure how fast the canonical-form backlog rebuilds in a target repository.

Backs §7 of ``docs/iuc_conference_questions.md`` (the forward-enforcement gate)
and the auto-fix-system plan (``~/.claude/plans/tools-iuc-autofix-system.md``).

The argument for a pre-merge normalization gate is that a one-shot bulk reformat
decays: new PRs land in the author's own style, so the toolchain would re-fix the
same files forever. This script quantifies that decay. It takes a corpus of
**recently merged** PRs (built by ``scripts.fetch_iuc_prs --state closed
--merged-only``) and, for each PR's **merged (`head`) state**, asks whether the
gate's blessed rule subset would *still* flag the tool the human just touched. A
flagged merged PR is one the gate would have caught — direct evidence the backlog
re-accumulates without forward enforcement.

This is the inverse of ``scripts.pr_impact``: that script asks "did the human's
edit coincide with one of our fixes?" (a before→head delta); this one asks "is
the post-merge result already non-canonical?" (a head-only property). No
canonical-space noise-cancellation here — we want the raw merged bytes, because a
gate runs on exactly those bytes.

Three gate variants are reported, since "which rule subset belongs in the gate"
is itself the open IUC question:

* **cosmetic** — ``GTR001``/``GTR004`` only (the most conservative gate);
* **full** — every behaviour-preserving fixable rule in the ``default`` ruleset
  (the widest gate);
* **full minus attribute order** — ``full`` without ``GTR002``, which is blocked
  pending an IUC canonical-order decision (conference §3).

Plus a per-code table (so any candidate subset's flag rate can be read off) and
the count of PRs flagged **only** by attribute order (the cost of leaving §3
unresolved).

Writes ``docs/gate_reaccumulation_stats.md``. Needs the merged-PR corpus on disk
(network + ``gh`` to build), so it is not run in CI.

Usage::

    uv run python -m scripts.fetch_iuc_prs --state closed --merged-only \
        --corpus-name galaxyproject__tools-iuc__merged --limit 200
    uv run python -m scripts.gate_reaccumulation \
        --corpus-name galaxyproject__tools-iuc__merged
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

from lxml import etree

from galaxy_tool_refactor_registry.facade import detect as facade_detect
from galaxy_tool_refactor_registry.registry import registry
from galaxy_tool_refactor_registry.resolve import resolve_codes

logger = logging.getLogger("gate_reaccumulation")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PR_CORPUS_ROOT = _REPO_ROOT / ".local" / "pr-corpus"
_DEFAULT_REPO = "galaxyproject/tools-iuc"
_DEFAULT_CORPUS = "galaxyproject__tools-iuc__merged"
_STATS_PAGE = _REPO_ROOT / "docs" / "gate_reaccumulation_stats.md"

# GTR002 (ReorderParamAttributes) is behaviour-preserving but its canonical order
# is contested upstream (conference §3), so it cannot enter the gate until IUC
# decides. We split it out to size exactly that decision.
_ATTRIBUTE_ORDER_CODE = "GTR002"


@cache
def _gate_candidate_codes() -> frozenset[str]:
    """Every behaviour-preserving *fixable* rule in the ``default`` ruleset.

    The widest gate a forward-enforcement check could run — the set a bulk
    normalizer would also apply. Cosmetic codes are a subset of this.
    """
    reg = registry()
    return frozenset(
        code for code in resolve_codes(rulesets=["default"]) if reg[code].fixable
    )


@cache
def _cosmetic_codes() -> frozenset[str]:
    """The conservative gate: cosmetic whitespace/shorthand only."""
    return resolve_codes(rulesets=["cosmetic"])


def _is_tool_document(path: Path, /) -> bool:
    """Return True when *path* parses as XML with a ``<tool>`` root.

    The changed-file list can include ``macros.xml`` / other non-tool XML, which
    the gate does not lint as a tool; those are excluded from the denominator
    rather than miscounted as clean.
    """
    try:
        tree = etree.parse(str(path))
    except etree.LxmlError:
        return False
    return bool(tree.getroot().tag == "tool")


def _firing_codes(path: Path, /, *, codes: frozenset[str]) -> set[str] | None:
    """Return the set of *codes* that fire on *path*, or ``None`` on failure.

    LBYL boundary: the facade is the one thing that can raise on a malformed
    snapshot; a failure is logged and folded into ``None`` so the sweep skips the
    file rather than aborting.
    """
    try:
        result = facade_detect(path, codes=codes)
    except Exception as error:  # noqa: BLE001 — corpus sweep: a bad snapshot is skipped, not fatal
        logger.warning("skipping %s: %s", path, error)
        return None
    return {violation.code for violation in result.violations}


@dataclass
class GateReaccumulationResult:
    """How often a merged PR's result is still non-canonical under the gate."""

    pr_count: int = 0  # every ``ok`` PR in the manifest
    prs_with_tool: set[int] = field(default_factory=set)  # PRs with >=1 evaluable tool
    tool_files_evaluated: int = 0
    tool_files_flagged: int = 0
    skipped_files: int = 0
    # PR number -> union of codes that fire across its merged tool files.
    per_pr_codes: dict[int, set[str]] = field(default_factory=dict)
    per_code_prs: Counter[str] = field(default_factory=Counter)
    per_code_files: Counter[str] = field(default_factory=Counter)


def _measure_gate_reaccumulation(
    repo_root: Path,
    manifest: dict[str, dict[str, object]],
    /,
    *,
    candidate_codes: frozenset[str],
) -> GateReaccumulationResult:
    """Sweep the merged-PR corpus; tally which merged results the gate would flag.

    Pure: no printing, no file writes. *repo_root* is the per-repo corpus dir
    (holding the ``pr-<N>/`` snapshots). Only the ``head`` ref is read — the
    merged state. Per-file facade failures are skipped (counted in
    ``skipped_files``) so one bad tool never aborts the sweep.
    """
    result = GateReaccumulationResult()
    for key, entry in sorted(manifest.items(), key=lambda item: int(item[0])):
        if entry.get("status") != "ok":
            continue
        result.pr_count += 1
        number = int(key)
        changed = entry.get("changed_xml_files")
        if not isinstance(changed, list):
            continue
        head_dir = repo_root / f"pr-{number}" / "head"
        pr_codes: set[str] = set()
        saw_tool = False
        for relpath in changed:
            if not isinstance(relpath, str):
                continue
            head_path = head_dir / relpath
            if not head_path.is_file() or not _is_tool_document(head_path):
                continue
            firing = _firing_codes(head_path, codes=candidate_codes)
            if firing is None:
                result.skipped_files += 1
                continue
            saw_tool = True
            result.tool_files_evaluated += 1
            if firing:
                result.tool_files_flagged += 1
            for code in firing:
                result.per_code_files[code] += 1
            pr_codes |= firing
        if saw_tool:
            result.prs_with_tool.add(number)
            result.per_pr_codes[number] = pr_codes
            for code in pr_codes:
                result.per_code_prs[code] += 1
    return result


@dataclass(frozen=True)
class GateVariantShare:
    """A named gate subset and how many merged PRs it would have flagged."""

    name: str
    flagged: int
    total: int

    @property
    def pct(self) -> float:
        """Flagged share as a percentage (0 when no PRs)."""
        return (100.0 * self.flagged / self.total) if self.total else 0.0


def _variant_shares(result: GateReaccumulationResult, /) -> list[GateVariantShare]:
    """Compute the cosmetic / full / full-minus-GTR002 flagged shares.

    Derived from ``per_pr_codes`` by set arithmetic, so all three variants come
    from one detect pass over the corpus.
    """
    cosmetic = _cosmetic_codes()
    total = len(result.prs_with_tool)
    cosmetic_flagged = 0
    full_flagged = 0
    minus_attr_flagged = 0
    for codes in result.per_pr_codes.values():
        if codes & cosmetic:
            cosmetic_flagged += 1
        if codes:
            full_flagged += 1
        if codes - {_ATTRIBUTE_ORDER_CODE}:
            minus_attr_flagged += 1
    return [
        GateVariantShare("cosmetic (GTR001, GTR004)", cosmetic_flagged, total),
        GateVariantShare("full (all default fixable rules)", full_flagged, total),
        GateVariantShare(
            f"full minus attribute order ({_ATTRIBUTE_ORDER_CODE})",
            minus_attr_flagged,
            total,
        ),
    ]


def _attribute_order_only(result: GateReaccumulationResult, /) -> int:
    """Count merged PRs flagged ONLY by the contested attribute-order rule.

    These are PRs the full gate would catch but a gate excluding GTR002 would
    pass — the exact population blocked behind the IUC canonical-order decision.
    """
    return sum(
        1
        for codes in result.per_pr_codes.values()
        if codes == {_ATTRIBUTE_ORDER_CODE}
    )


def _report_gate_reaccumulation(result: GateReaccumulationResult, /) -> None:
    """Print the headline shares + per-code table to stdout."""
    total = len(result.prs_with_tool)
    print(f"\n=== gate re-accumulation ({result.pr_count} merged PRs swept) ===")
    print(
        f"evaluable: {total} PRs with >=1 merged tool file "
        f"({result.tool_files_evaluated} tool files, "
        f"{result.skipped_files} skipped)"
    )
    for share in _variant_shares(result):
        print(f"  flagged under {share.name}: {share.flagged}/{share.total} ({share.pct:.1f}%)")
    print(f"  flagged ONLY by attribute order ({_ATTRIBUTE_ORDER_CODE}): {_attribute_order_only(result)}")
    print("\nper-code (merged PRs in which the code still fires):")
    for code, count in result.per_code_prs.most_common():
        print(f"  {code}: {count} PRs / {result.per_code_files[code]} files")


def _write_gate_reaccumulation_stats(
    result: GateReaccumulationResult,
    repo: str,
    /,
    *,
    retrieved: str,
    out: Path = _STATS_PAGE,
) -> None:
    """Write ``docs/gate_reaccumulation_stats.md`` from *result*."""
    total = len(result.prs_with_tool)
    lines = [
        "# Gate re-accumulation statistics",
        "",
        f"_Generated by `python -m scripts.gate_reaccumulation` on "
        f"{date.today().isoformat()}; swept {result.pr_count} merged PRs from "
        f"`{repo}` (PR corpus retrieved {retrieved})._",
        "",
        "Reproduced by: `python -m scripts.fetch_iuc_prs --state closed "
        "--merged-only --corpus-name "
        f"{_DEFAULT_CORPUS} --limit 0` then `python -m scripts.gate_reaccumulation`",
        "",
        "## What this measures",
        "",
        "For every **recently merged** PR, we evaluate the tool in its **merged "
        "(`head`) state** — the bytes that actually landed — and ask whether a "
        "pre-merge normalization gate (conference §7) would *still* flag it. A "
        "flagged merged PR is one whose author left the tool non-canonical even "
        "after a full human review cycle: direct evidence the canonical-form "
        "backlog re-accumulates without forward enforcement.",
        "",
        f"Of **{result.pr_count}** merged PRs swept, **{total}** changed at least "
        "one file that parses as a `<tool>` (PRs touching only `macros.xml` or "
        "non-tool XML are excluded from the denominator; "
        f"{result.skipped_files} tool files were skipped on a parse/detect error).",
        "",
        "## Headline — share of merged PRs the gate would have flagged",
        "",
        "| Gate variant | Flagged merged PRs |",
        "|---|---|",
    ]
    for share in _variant_shares(result):
        lines.append(f"| {share.name} | {share.flagged}/{share.total} ({share.pct:.1f}%) |")
    attr_only = _attribute_order_only(result)
    lines += [
        "",
        f"**{attr_only}** of the flagged PRs are flagged *only* by attribute order "
        f"(`{_ATTRIBUTE_ORDER_CODE}`) — the population that stays blocked until IUC "
        "blesses a canonical order (conference §3). Every other flagged PR would be "
        "caught by a gate we could ship today.",
        "",
        "## Per-code re-accumulation",
        "",
        "How many merged PRs still carry each rule's finding in their merged state:",
        "",
        "| Code | Merged PRs | Tool files |",
        "|---|---|---|",
    ]
    for code, count in result.per_code_prs.most_common():
        lines.append(f"| {code} | {count} | {result.per_code_files[code]} |")
    out.parent.mkdir(parents=True, exist_ok=True)
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
    """Run the gate re-accumulation analysis; return a process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Measure how often a merged PR's result is still non-canonical."
    )
    parser.add_argument("--repo", default=_DEFAULT_REPO, metavar="OWNER/NAME")
    parser.add_argument(
        "--corpus-name",
        default=_DEFAULT_CORPUS,
        metavar="NAME",
        help=f"corpus subdir under .local/pr-corpus (default {_DEFAULT_CORPUS})",
    )
    parser.add_argument("--no-stats", action="store_true", help="skip writing the stats page")
    args = parser.parse_args(argv)

    repo_root = _PR_CORPUS_ROOT / args.corpus_name
    manifest = _load_manifest(args.corpus_name)
    if not manifest:
        logger.error(
            "no PR-corpus manifest for %s (run scripts.fetch_iuc_prs --state closed "
            "--merged-only --corpus-name %s first)",
            args.corpus_name,
            args.corpus_name,
        )
        return 1

    result = _measure_gate_reaccumulation(
        repo_root, manifest, candidate_codes=_gate_candidate_codes()
    )
    _report_gate_reaccumulation(result)

    if not args.no_stats:
        _write_gate_reaccumulation_stats(
            result, args.repo, retrieved=_manifest_retrieved(args.corpus_name)
        )
        logger.info("wrote %s", _STATS_PAGE.relative_to(_REPO_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
