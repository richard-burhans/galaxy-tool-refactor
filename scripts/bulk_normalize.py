#!/usr/bin/env python3
"""Bulk normalizer: Half A of the repository-scale auto-fix system.

Plan: ``~/.claude/plans/tools-iuc-autofix-system.md``. The one-shot pass that
clears a tool repository's backlog by applying the blessed, behaviour-preserving
rule subset to every tool. Its sibling, the forward-enforcement gate
(``scripts/forward_gate.py``, Half B), keeps the repository clean afterward. Both
read the same classification (``galaxy_tool_refactor_registry.gate_eligibility``)
so they can never disagree.

Rule set: the **gate-eligible** rules PLUS the **bulk-only** rules (uncited house
conventions the bulk pass offers but the gate does not hard-enforce). It never
applies the blocked-pending-IUC rules (attribute reordering, GTR002/GTR005) or the
advisory checks.

By default this is a **dry run** (reports what would change, writes nothing).
``--write`` applies the normalization in place and, per changed tool, asserts the
two invariants that make the pass safe: it **preserves validity** (a tool valid at
its profile before stays valid after) and is **idempotent** (re-normalizing the
written file is a no-op). A tool that breaks either invariant is **reverted to its
original** (never left written) and retained in the report, so the written tree is
safe by construction; an errored tool is likewise retained.

Run it against a throwaway working copy (e.g. a fork clone), never the canonical
repo. Usage::

    uv run python -m scripts.bulk_normalize .local/tools-iuc            # dry run
    uv run python -m scripts.bulk_normalize .local/tools-iuc --write    # apply
    uv run python -m scripts.bulk_normalize .local/tools-iuc --limit 50 # sample
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from galaxy_tool_refactor_registry.facade import run as facade_run
from galaxy_tool_refactor_registry.gate_eligibility import bulk_codes
from galaxy_tool_source.binding import validate_tool

from scripts._shared import is_tool_document, iter_tool_xmls

logger = logging.getLogger("bulk_normalize")


@dataclass
class NormalizeResult:
    """Aggregate outcome of a bulk-normalization sweep over a repository."""

    total_tools: int = 0
    already_canonical: int = 0
    normalized: int = 0
    written: int = 0
    reverted: int = 0
    validity_regressions: list[str] = field(default_factory=list)
    idempotence_failures: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _normalize_one(
    path: Path,
    relpath: str,
    result: NormalizeResult,
    /,
    *,
    codes: frozenset[str],
    write: bool,
) -> None:
    """Normalize a single tool, folding the outcome into *result*.

    Path-based throughout so imported macros resolve and the GTR013 ``<expand>``
    resolution layer is active. Validity is checked against the ORIGINAL on disk
    before any write; idempotence and post-write validity are checked against the
    written file.
    """
    try:
        original = path.read_bytes()
        normalized = facade_run(path, codes=codes).formatted
    except Exception as error:  # noqa: BLE001 — bulk sweep: a bad tool is retained, not fatal
        result.errors.append(f"{relpath}: {error}")
        return
    if normalized == original:
        result.already_canonical += 1
        return
    result.normalized += 1
    before_valid = validate_tool(path).valid  # path still holds the original here
    if not write:
        return
    wrote = False
    try:
        path.write_bytes(normalized)
        wrote = True
        regressed = before_valid and not validate_tool(path).valid
        not_idempotent = facade_run(path, codes=codes).formatted != normalized
        if regressed or not_idempotent:
            # Never leave an unsafe tool written: restore the original and retain
            # the failure for the report (safe-by-construction bulk pass).
            path.write_bytes(original)
            result.reverted += 1
            if regressed:
                result.validity_regressions.append(relpath)
            if not_idempotent:
                result.idempotence_failures.append(relpath)
        else:
            result.written += 1
    except Exception as error:  # noqa: BLE001 — retain a write/re-check failure
        # If the re-check raised *after* the write, never leave the unverified bytes
        # on disk: restore the original (the same safe-by-construction guarantee).
        if wrote:
            path.write_bytes(original)
            result.reverted += 1
        result.errors.append(f"{relpath}: {error}")


def normalize_repo(
    root: Path, /, *, codes: frozenset[str], write: bool, limit: int = 0
) -> NormalizeResult:
    """Sweep every ``<tool>`` under *root*, normalizing each. Pure of printing."""
    result = NormalizeResult()
    for path in sorted(iter_tool_xmls(root)):
        if not is_tool_document(path):
            continue
        if limit and result.total_tools >= limit:
            break
        result.total_tools += 1
        relpath = str(path.relative_to(root))
        _normalize_one(path, relpath, result, codes=codes, write=write)
    return result


def _report(result: NormalizeResult, /, *, write: bool) -> None:
    """Print the coverage summary + any retained failures."""
    total = result.total_tools
    canon_pct = (100.0 * result.already_canonical / total) if total else 0.0
    mode = "WRITE" if write else "dry-run"
    print(f"\n=== bulk-normalize ({mode}; {total} tools) ===")
    print(f"  already canonical: {result.already_canonical} ({canon_pct:.1f}%)")
    written_note = f" (wrote {result.written}, reverted {result.reverted})" if write else ""
    print(f"  would-normalize:   {result.normalized}{written_note}")
    print(f"  validity regressions: {len(result.validity_regressions)}")
    print(f"  idempotence failures: {len(result.idempotence_failures)}")
    print(f"  errors: {len(result.errors)}")
    for label, items in (
        ("validity regression", result.validity_regressions),
        ("idempotence failure", result.idempotence_failures),
        ("error", result.errors),
    ):
        for item in items[:20]:
            print(f"    [{label}] {item}")


def main(argv: list[str]) -> int:
    """Run the bulk normalizer; return 0 unless an invariant broke."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Apply the blessed rule subset across a repo.")
    parser.add_argument("root", type=Path, help="repository root (use a throwaway working copy)")
    parser.add_argument("--write", action="store_true", help="apply in place (default: dry run)")
    parser.add_argument("--limit", type=int, default=0, help="cap tools processed (0 = all)")
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        logger.error("not a directory: %s", args.root)
        return 2

    result = normalize_repo(args.root, codes=bulk_codes(), write=args.write, limit=args.limit)
    _report(result, write=args.write)
    # A broken invariant is a failure exit; a clean sweep (even with normalizations) is 0.
    broke = bool(result.validity_regressions or result.idempotence_failures)
    return 1 if broke else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
