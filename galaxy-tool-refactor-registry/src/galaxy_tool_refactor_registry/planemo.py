"""The planemo-linter alias index — derived from per-rule membership.

Each rule declares the planemo (``galaxy.tool_util.lint``) linter class names it
covers (``RuleMeta.planemo_linters``); this module derives a ``planemo name → GTR
codes`` index so a planemo user can select or find a rule by its planemo name
(``--select HelpMissing``). The lookup is **case-insensitive** (keys are
lower-cased). One GTR rule may cover several planemo linters, so a name resolves
to whichever GTR code(s) carry it — and a *bundled* rule is reached by any of its
names (selecting one planemo name of a bundle selects the whole covering GTR).
"""

from __future__ import annotations

from functools import cache

from galaxy_tool_refactor_registry.registry import all_handles


@cache
def planemo_index() -> dict[str, frozenset[str]]:
    """Return ``planemo linter name (lower-cased) → frozenset of GTR codes``."""
    index: dict[str, set[str]] = {}
    for handle in all_handles().values():
        for name in handle.meta.planemo_linters:
            index.setdefault(name.lower(), set()).add(handle.meta.code)
    return {name: frozenset(codes) for name, codes in index.items()}
