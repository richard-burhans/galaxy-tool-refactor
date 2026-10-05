#!/usr/bin/env python3
"""Certify every FIXABLE GTR rule against the render-equality oracle, corpus-wide.

Each fixable rule ships a ``docs/proofs/<code>.md`` asserting it is
behaviour-preserving. ``corpus_check codemod`` already checks post-edit **validity**
and **idempotence**; neither can see an edit that leaves the XML valid and stable while
changing the **rendered command**. This sweep applies each rule in isolation to every
corpus tool and asks the oracle (``galaxy_tool_source.render_oracle``) what it can
prove, converting those prose claims into a measurement.

Both tiers are covered uniformly, which is why this is one script rather than a flag on
two subcommands:

* **codemods** (tier 2) apply through ``CodemodCommand.apply``;
* **fmt rules** (tier 3) yield ``Edit``\\ s applied with ``galaxy_tool_fmt.apply_edits``.

Per rule it reports, over the tools the rule actually MODIFIED:

``text-equal``   the rendered command is byte-identical — the strong proof.
``argv-equal``   the bytes differ but the shell reads the line identically (same argv
                 partition and fd topology, after POSIX quote removal). This is the
                 verdict a quoting rule needs: GTR020.1 changes bytes on purpose.
``NOT PROVEN``   neither held. **Not the same as unsafe** — it means this instrument
                 could not establish preservation, and the tool is named so a human
                 can judge.
``unknown``      a side would not render (Python-2 Cheetah, a construct CT3 rejects, an
                 unresolvable macro) or would not parse as bash. Nothing measured.

Usage::

    uv run python -m scripts.certify_render_sweep [--limit N] [--rule GTR020.1 ...]
                                                  [--source toolshed|github|combined]
"""

from __future__ import annotations

import argparse
import copy
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from galaxy_tool_codemod.catalog import coded_codemods  # noqa: E402
from galaxy_tool_codemod.parse import parse_module  # noqa: E402
from galaxy_tool_fmt.edits import apply_edits  # noqa: E402
from galaxy_tool_fmt.format import all_rules  # noqa: E402
from galaxy_tool_refactor_registry import facade  # noqa: E402
from galaxy_tool_source.binding import parse_tool  # noqa: E402
from galaxy_tool_source.render_oracle import render_equality_holds  # noqa: E402

from scripts._shared import iter_tool_xmls  # noqa: E402
from scripts.corpus_check import _iter_sources  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger("certify_render_sweep")


def _fixable_appliers() -> dict[str, object]:
    """Map every fixable rule code to something that applies it in isolation.

    Derived from the registry and the two tiers' own catalogues, never hardcoded, so a
    rule added or retired cannot leave this sweep silently incomplete.
    """
    fixable = {rule.code for rule in facade.list_rules() if rule.fixable}
    appliers: dict[str, object] = {}
    for codemod_cls in coded_codemods():
        if codemod_cls.meta.code in fixable:
            appliers[codemod_cls.meta.code] = codemod_cls
    for fmt_cls in all_rules():
        if fmt_cls.meta.code in fixable:
            appliers[fmt_cls.meta.code] = fmt_cls
    missing = sorted(fixable - set(appliers))
    if missing:
        logger.warning(
            "no isolated applier for fixable rule(s) %s -- they are NOT certified here",
            ", ".join(missing),
        )
    return appliers


def _apply_in_isolation(applier: object, path: Path) -> etree._Element | None:
    """Apply one rule to *path* alone; return the mutated root, or ``None`` on error."""
    try:
        if hasattr(applier, "edits"):  # a tier-3 fmt rule
            parsed = parse_tool(path)
            if parsed.document is None:
                return None
            tree = parsed.document.tree
            apply_edits(applier().edits(tree))  # type: ignore[operator]
            return tree.getroot()
        module = parse_module(path)  # a tier-2 codemod
        applier().apply(module)  # type: ignore[operator]
        return module.document.root
    except Exception:  # noqa: BLE001 - a crash is the sweep's finding, not a stop
        return None


def _tools(source: str, limit: int) -> Iterator[tuple[str, Path]]:
    """Yield ``(display_name, path)`` for every corpus tool XML, in repo order."""
    yielded = 0
    for _label, display_name, repo_dir, _version in _iter_sources(
        (source,), repo_filter=None
    ):
        for path in sorted(iter_tool_xmls(repo_dir)):
            yield display_name, path
            yielded += 1
            if limit and yielded >= limit:
                return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.certify_render_sweep")
    parser.add_argument("--source", default="toolshed",
                        choices=("github", "toolshed", "combined"))
    parser.add_argument("--limit", type=int, default=0,
                        help="stop after N tools per rule (0 = the whole corpus)")
    parser.add_argument("--rule", action="append", default=None,
                        help="certify only this rule code (repeatable)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    appliers = _fixable_appliers()
    codes = sorted(args.rule) if args.rule else sorted(appliers)
    unknown = [c for c in codes if c not in appliers]
    if unknown:
        parser.error(f"not a fixable rule with an isolated applier: {unknown}")

    overall: dict[str, Counter[str]] = {}
    for code in codes:
        applier = appliers[code]
        counts: Counter[str] = Counter()
        not_proven: list[str] = []
        for display_name, path in _tools(args.source, args.limit):
            parsed = parse_tool(path)
            if parsed.document is None or parsed.document.root.tag != "tool":
                continue
            counts["tools"] += 1
            pristine = copy.deepcopy(parsed.document.root)
            after = _apply_in_isolation(applier, path)
            if after is None:
                counts["crash-or-unparseable"] += 1
                continue
            if etree.tostring(pristine) == etree.tostring(after):
                continue  # the rule did not touch this tool
            counts["modified"] += 1
            verdict = render_equality_holds(pristine, after, source_dir=path.parent)
            if verdict.equal is None:
                counts["unknown"] += 1
            elif verdict.equal:
                counts["text-equal"] += 1
            elif verdict.boundary_equal:
                counts["argv-equal"] += 1
            elif verdict.boundary_equal is None:
                counts["unknown"] += 1
            else:
                counts["not-proven"] += 1
                detail = ""
                if verdict.divergence is not None:
                    world, section, before_text, after_text = verdict.divergence
                    detail = (
                        f"\n    world={world} section={section}"
                        f"\n    before: {' '.join(before_text.split())[:300]}"
                        f"\n    after:  {' '.join(after_text.split())[:300]}"
                    )
                not_proven.append(f"{display_name}: {path.name}{detail}")
        overall[code] = counts
        logger.info(
            "%-10s %5d modified of %5d tools -> %4d text-equal, %4d argv-equal, "
            "%3d NOT PROVEN, %4d unknown",
            code, counts["modified"], counts["tools"], counts["text-equal"],
            counts["argv-equal"], counts["not-proven"], counts["unknown"],
        )
        for entry in not_proven:
            logger.warning("  NOT PROVEN  %s", entry)

    certified = sum(c["text-equal"] + c["argv-equal"] for c in overall.values())
    modified = sum(c["modified"] for c in overall.values())
    unproven = sum(c["not-proven"] for c in overall.values())
    logger.info(
        "TOTAL across %d rule(s): %d modifications, %d certified, %d NOT PROVEN, "
        "%d unknown",
        len(overall), modified, certified, unproven,
        sum(c["unknown"] for c in overall.values()),
    )
    return 1 if unproven else 0


if __name__ == "__main__":
    sys.exit(main())
