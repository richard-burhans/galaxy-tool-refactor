"""Render the GTR coverage table of ``docs/planemo_linter_parity.md`` from metadata.

The table's content is **derived** from the registry — each rule's planemo linter
coverage (``RuleMeta.planemo_linters``), detect/fix status, tier, narrowest ruleset,
and summary. Only the prose preamble and the HAVE/SKIP/n-a accounting in that doc are
hand-written (they cover planemo linters we *don't* implement, which aren't in our
metadata). ``scripts/gen_planemo_parity.py`` writes the rendered table between the
doc's ``BEGIN/END`` markers; a freshness test pins the committed block to this output.
"""

from __future__ import annotations

import re

from galaxy_tool_refactor_registry.adapters import upgrade_only_codemods
from galaxy_tool_refactor_registry.registry import all_handles

# A rule summary like "declare <requirements>" carries bare XML tags; in a markdown
# table cell the renderer treats ``<requirements>`` as an (unknown) HTML tag and drops
# it. Backtick-quote each ``<…>`` run so it renders literally. (Summaries are plain
# text — none contain backticks — so this is unambiguous; pinned by a test.)
_TAG = re.compile(r"<[^>]+>")


def _quote_tags(text: str, /) -> str:
    """Wrap each bare ``<…>`` XML tag in *text* in backticks for markdown."""
    return _TAG.sub(lambda m: f"`{m.group(0)}`", text)

# The narrowest-first ruleset order (the sets nest: cosmetic ⊂ default = iuc ⊂ strict).
_NARROW_ORDER = ("cosmetic", "default", "iuc", "strict")

# The opt-in conversion codemod: rulesets are empty (so it is not selectable, like
# the upgrade-only codemods) but it is applied by the dedicated ``convert-help``
# command, NOT ``upgrade`` — so its tier column stays its real family ("codemod").
# Hand-known exception, mirroring _NO_OP_DETECT (codemod ``docs/decisions.md`` §38).
_OPT_IN_COMMAND_CODES = frozenset({"GTR092"})

# The one reserved no-op detector — documented in check ``docs/decisions.md`` D3.
# It carries a ``detect`` method (uniform interface) but never fires, so the table
# shows ``—``. The single hand-known exception; everything else detects.
_NO_OP_DETECT = frozenset({"GTR032"})

_HEADER = "| GTR | planemo linter(s) covered | detect | fix | tier | ruleset | description |"  # noqa: E501
_SEPARATOR = "|---|---|:--:|:--:|---|---|---|"

# Markers bounding the generated table block in the doc (shared by the writer script
# ``scripts/gen_planemo_parity.py`` and the freshness test).
BEGIN_MARKER = "<!-- BEGIN GENERATED: GTR coverage table (scripts/gen_planemo_parity.py) -->"  # noqa: E501
END_MARKER = "<!-- END GENERATED -->"


def render_parity_table() -> str:
    """Return the GTR coverage table as markdown (header + separator + rows)."""
    upgrade_codes = {cls.meta.code for cls in upgrade_only_codemods()}
    handles = all_handles()
    rows = [_HEADER, _SEPARATOR]
    for code in sorted(handles):
        meta = handles[code].meta
        names = sorted(meta.planemo_linters)
        planemo = ", ".join(names) if names else "—"
        detect = "—" if code in _NO_OP_DETECT else "✓"
        fix = "✗" if meta.detect_only else "✓"
        tier = (
            "upgrade"
            if code in upgrade_codes - _OPT_IN_COMMAND_CODES
            else handles[code].family
        )
        ruleset = next((name for name in _NARROW_ORDER if name in meta.rulesets), "—")
        rows.append(
            f"| {code} | {planemo} | {detect} | {fix} | {tier} | {ruleset} "
            f"| {_quote_tags(meta.summary)} |"
        )
    return "\n".join(rows)
