"""Render a cross-tier GTX rule glossary as GitHub-flavored markdown.

A pure, dependency-free helper: it turns ``(RuleMeta, tier)`` pairs into the
rows of a ``| Rule | Tier | What it does |`` table, sorted by code. It emits the
table only — the caller owns any surrounding heading and intro prose, which is
context-specific (the fmt stat page frames it differently than a standalone rule
registry would).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from galaxy_tool_refactor_rules.meta import RuleMeta

# Element names in a summary (``<param>``, ``<foo/>``) would be parsed as HTML
# tags inside a markdown table cell and rendered as nothing; wrap them in
# backticks so they survive as literal text.
_ANGLE_TOKEN = re.compile(r"(<[^>]+>)")


def _backtick_xml_tokens(text: str) -> str:
    """Backtick-wrap angle-bracket tokens so GitHub renders them literally."""
    return _ANGLE_TOKEN.sub(r"`\1`", text)


def render_rule_reference_table(entries: Iterable[tuple[RuleMeta, str]]) -> list[str]:
    """Render ``(meta, tier)`` pairs as a markdown reference table.

    Args:
        entries: ``(RuleMeta, tier_label)`` pairs, where ``tier_label`` names the
            owning tier (e.g. ``"fmt"`` or ``"codemod"``).

    Returns:
        Markdown lines: a header row, the separator, then one row per rule
        ordered by ``meta.code``.
    """
    rows = sorted(entries, key=lambda entry: entry[0].code)
    lines = [
        "| Rule | Tier | What it does |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {meta.code} | {tier} | {_backtick_xml_tokens(meta.summary)} |"
        for meta, tier in rows
    )
    return lines
