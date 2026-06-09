"""Named rule-sets — derived from per-rule membership (the single source).

A *ruleset* is a named, described bucket of rules. **Membership is declared on
each rule** (``RuleMeta.rulesets``); this module derives ``name -> {codes}`` by
grouping the live registry by that membership, so the mapping never drifts from
the rules that actually exist. The ruleset *names and descriptions* live in the
tier-0.5 catalog (``galaxy_tool_refactor_rules.rulesets``); selection unions the
named sets, and the set applied when the user names none is ``DEFAULT_RULESET``.

Adding or retagging a ruleset is a developer task — there are no user-defined
rulesets, by design.
"""

from __future__ import annotations

from functools import cache

from galaxy_tool_refactor_rules.rulesets import ruleset_names

from galaxy_tool_refactor_registry.registry import all_handles


@cache
def ruleset_codes() -> dict[str, frozenset[str]]:
    """Return ``ruleset name -> frozenset of rule codes`` (derived from membership).

    Built by grouping every registered rule by the names in its ``meta.rulesets``,
    keyed and ordered by the tier-0.5 catalog. A membership name outside the
    catalog is ignored here (and caught by the registry validation test), so the
    result is exactly the catalog's rulesets.
    """
    members: dict[str, set[str]] = {name: set() for name in ruleset_names()}
    for handle in all_handles().values():
        for name in handle.meta.rulesets:
            if name in members:
                members[name].add(handle.meta.code)
    return {name: frozenset(codes) for name, codes in members.items()}
