"""Validation guards for per-rule ruleset membership.

These pin the contract that membership declarations (``RuleMeta.rulesets``) and
the tier-0.5 catalog stay consistent: every declared name exists, every selectable
rule declares at least one ruleset, the upgrade-only codemods declare none, and no
catalog ruleset is empty.
"""

from __future__ import annotations

from galaxy_tool_refactor_rules.rulesets import ruleset_names

from galaxy_tool_refactor_registry.adapters import upgrade_only_codemods
from galaxy_tool_refactor_registry.registry import all_handles, registry
from galaxy_tool_refactor_registry.rulesets import ruleset_codes


def test_every_declared_ruleset_name_is_in_the_catalog() -> None:
    catalog = set(ruleset_names())
    for handle in all_handles().values():
        stray = handle.meta.rulesets - catalog
        assert not stray, f"{handle.meta.code} declares unknown ruleset(s): {stray}"


def test_every_selectable_rule_declares_a_ruleset() -> None:
    for code, handle in registry().items():
        assert handle.meta.rulesets, f"{code} is selectable but declares no ruleset"


def test_upgrade_only_codemods_declare_no_ruleset() -> None:
    for cls in upgrade_only_codemods():
        assert not cls.meta.rulesets, (
            f"{cls.meta.code} is upgrade-only but declares a ruleset"
        )


def test_no_catalog_ruleset_is_empty() -> None:
    code_map = ruleset_codes()
    for name in ruleset_names():
        assert code_map[name], f"ruleset {name!r} has no members"
