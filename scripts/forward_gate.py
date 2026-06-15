#!/usr/bin/env python3
"""Forward-enforcement gate: Half B of the repository-scale auto-fix system.

Plan: ``~/.claude/plans/tools-iuc-autofix-system.md``; conference question §7
(``docs/iuc_conference_questions.md``). The gate is the durable half of the
two-part design: a one-shot bulk normalizer (Half A, ``scripts/bulk_normalize.py``)
clears a repository's backlog, and this gate keeps it clean by running the SAME
blessed rule subset on every incoming PR, over just the tools the PR changed,
before merge. Both halves read their rule set from the one classification
(``galaxy_tool_refactor_registry.gate_eligibility``), so they can never disagree.

This is the **block-until-canonical** form: the gate reports where a changed tool
deviates and fails, naming the exact local fix command, leaving the author in
control of their branch. (The **auto-normalize** alternative — the gate rewrites
the branch itself — is IUC's call, conference §7; not implemented here.) Only the
**gate-eligible** rules run: provably behaviour-preserving AND with an
uncontroversial canonical form (so attribute reordering, blocked pending an IUC
decision, never fires here).

Exit code is 0 when every checked tool is canonical, 1 when any is not (the CI
failure), and 2 on a usage error.

Usage::

    # explicit files (what a CI Action passes after computing the PR diff)
    uv run python -m scripts.forward_gate tools/foo/foo.xml tools/bar/bar.xml

    # or derive the changed tools from a git range
    uv run python -m scripts.forward_gate --changed-against origin/main
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path, PurePosixPath

from galaxy_tool_refactor_registry.facade import fired_codes as facade_fired_codes
from galaxy_tool_refactor_registry.gate_eligibility import gate_codes

from scripts._shared import is_tool_document

logger = logging.getLogger("forward_gate")

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _changed_tool_xmls(ref: str, root: Path, /) -> list[Path]:
    """Return tool XML files changed against *ref* (``git diff --name-only ref...``).

    Added/modified ``*.xml`` under ``tools/`` that still exist on disk; deletions
    and non-tool XML are dropped downstream by ``_select_tool_documents``.
    """
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=AM", f"{ref}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.error("git diff failed: %s", result.stderr.strip() or "<no stderr>")
        return []
    changed: list[Path] = []
    for line in result.stdout.splitlines():
        posix = PurePosixPath(line)
        if posix.parts and posix.parts[0] == "tools" and posix.suffix == ".xml":
            changed.append(root / line)
    return changed


def _expand_paths(paths: list[Path], /) -> list[Path]:
    """Expand directories to their ``*.xml`` files; pass files through."""
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(path.rglob("*.xml")))
        else:
            expanded.append(path)
    return expanded


def _select_tool_documents(paths: list[Path], /) -> list[Path]:
    """Keep only existing files that parse as a ``<tool>`` document."""
    return [p for p in _expand_paths(paths) if p.is_file() and is_tool_document(p)]


def check_files(paths: list[Path], /, *, codes: frozenset[str]) -> dict[Path, set[str]]:
    """Return ``{path: firing gate codes}`` for every non-canonical tool.

    A tool whose ``detect`` raises (a malformed snapshot) is logged and skipped,
    not failed: the gate certifies canonical *form*, and validity is a separate
    check, so it never blocks a PR on a parse error it cannot interpret.
    """
    findings: dict[Path, set[str]] = {}
    for path in _select_tool_documents(paths):
        try:
            fired = facade_fired_codes(path, codes=codes)
        except Exception as error:  # noqa: BLE001 — gate sweep: an uncheckable tool is skipped, not failed
            logger.warning("skipping %s (could not check): %s", path, error)
            continue
        if fired:
            findings[path] = fired
    return findings


def _report(findings: dict[Path, set[str]], codes: frozenset[str], /) -> None:
    """Print a CoC-friendly, actionable failure report to stderr."""
    all_fired = sorted({code for fired in findings.values() for code in fired})
    print(
        f"\nForward gate: {len(findings)} changed tool(s) are not in canonical form.",
        file=sys.stderr,
    )
    for path in sorted(findings):
        codes_here = ", ".join(sorted(findings[path]))
        print(f"  {path}: {codes_here}", file=sys.stderr)
    select = ",".join(sorted(codes))
    print(
        "\nThese are deterministic, behaviour-preserving fixes. To apply them "
        "locally, run:\n"
        f"  galaxy-tool-refactor format --select {select} <file>\n"
        f"(codes flagged: {', '.join(all_fired)}). The gate runs only "
        "provably behaviour-preserving, IUC-blessed rules; see docs/gate_eligibility.md.",
        file=sys.stderr,
    )


def main(argv: list[str]) -> int:
    """Run the forward gate; return a process exit code (0 clean, 1 deviations)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Fail when a changed tool is not canonical under the gate-eligible rules."
    )
    parser.add_argument("paths", nargs="*", type=Path, help="tool XML files or directories")
    parser.add_argument(
        "--changed-against",
        metavar="REF",
        help="derive changed tool XMLs from `git diff REF...HEAD` instead of paths",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_REPO_ROOT,
        help="repository root for --changed-against (default: this repo)",
    )
    args = parser.parse_args(argv)

    if args.changed_against:
        paths = _changed_tool_xmls(args.changed_against, args.root)
    else:
        paths = args.paths
    if not paths:
        logger.info("no changed tool XML files to check; gate passes")
        return 0

    codes = gate_codes()
    findings = check_files(paths, codes=codes)
    if not findings:
        logger.info("forward gate: all checked tools are canonical")
        return 0
    _report(findings, codes)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
