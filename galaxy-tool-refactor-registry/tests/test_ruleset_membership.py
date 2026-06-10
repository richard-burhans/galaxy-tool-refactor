"""Validation guards for per-rule ruleset membership.

These pin the contract that membership declarations (``RuleMeta.rulesets``) and
the tier-0.5 catalog stay consistent: every declared name exists, every selectable
rule declares at least one ruleset, the non-selectable codemods are exactly the
known upgrade-pipeline + opt-in-command partition, and no catalog ruleset is empty.
"""

from __future__ import annotations

from galaxy_tool_refactor_rules.rulesets import ruleset_names

from galaxy_tool_refactor_registry.adapters import (
    OPT_IN_COMMAND_BY_CODE,
    non_selectable_codemods,
)
from galaxy_tool_refactor_registry.registry import all_handles, registry
from galaxy_tool_refactor_registry.rulesets import ruleset_codes

# The upgrade-pipeline codemods: GTR007–GTR012 are internal to ``UpgradeToLatest``
# (validity-gated); GTR014–GTR016 are the runtime-gated fixes the ``upgrade``
# command applies. Explicit by intent (the repo's hand-maintained-list convention)
# so a new no-ruleset codemod must be deliberately filed here or in
# ``OPT_IN_COMMAND_BY_CODE`` — never silently absorbed.
_UPGRADE_PIPELINE_CODES = frozenset(
    {"GTR007", "GTR008", "GTR009", "GTR010", "GTR011", "GTR012", "GTR093"}
    | {"GTR014", "GTR015", "GTR016"}
)


def test_every_declared_ruleset_name_is_in_the_catalog() -> None:
    catalog = set(ruleset_names())
    for handle in all_handles().values():
        stray = handle.meta.rulesets - catalog
        assert not stray, f"{handle.meta.code} declares unknown ruleset(s): {stray}"


def test_every_selectable_rule_declares_a_ruleset() -> None:
    for code, handle in registry().items():
        assert handle.meta.rulesets, f"{code} is selectable but declares no ruleset"


def test_non_selectable_codemods_are_the_known_partition() -> None:
    """Tripwire (B9): the no-ruleset codemods = upgrade pipeline ∪ opt-in-command.

    ``OPT_IN_COMMAND_BY_CODE`` is hand-known; this pins it (and the upgrade set)
    to exactly the codemods that declare no ruleset, so a new non-selectable
    codemod fails loudly until it is filed in one of the two groups.
    """
    codes = {cls.meta.code for cls in non_selectable_codemods()}
    assert codes == _UPGRADE_PIPELINE_CODES | set(OPT_IN_COMMAND_BY_CODE)
    assert not _UPGRADE_PIPELINE_CODES & set(OPT_IN_COMMAND_BY_CODE)


def test_opt_in_command_codes_are_not_selectable_anywhere() -> None:
    """Guard (B6): an opt-in-command code is in no ruleset and not selectable."""
    for code in OPT_IN_COMMAND_BY_CODE:
        assert code in all_handles(), code
        assert code not in registry(), f"{code} leaked into the selectable set"
        for name, codes in ruleset_codes().items():
            assert code not in codes, f"{code} leaked into ruleset {name!r}"


def test_no_catalog_ruleset_is_empty() -> None:
    code_map = ruleset_codes()
    for name in ruleset_names():
        assert code_map[name], f"ruleset {name!r} has no members"
