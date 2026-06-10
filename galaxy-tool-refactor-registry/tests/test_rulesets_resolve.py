"""Tests for the derived ruleset definitions and select/ignore resolution."""

from __future__ import annotations

import pytest
from galaxy_tool_refactor_rules.rulesets import DEFAULT_RULESET

from galaxy_tool_refactor_registry.errors import UnknownRuleCode, UnknownRuleset
from galaxy_tool_refactor_registry.registry import advisory_codes, known_codes
from galaxy_tool_refactor_registry.resolve import (
    resolve_codes,
    resolve_upgrade_codes,
    upgrade_base_codes,
)
from galaxy_tool_refactor_registry.rulesets import ruleset_codes

# The `iuc` ruleset: cosmetic fmt + the canonical codemods. `default` reproduces it
# exactly. Behaviour-preserving fixers join this set as they ship (e.g. GTR089.1, which
# repairs deterministically-fixable invalid <help> RST), so `format` output evolves with
# the canonical pipeline — the facade-vs-pipeline regression pin still holds.
_TODAY_DEFAULT = frozenset({
    "GTR001", "GTR002", "GTR003", "GTR004", "GTR005", "GTR006", "GTR013",
    "GTR017", "GTR018.1", "GTR019.1", "GTR020.1", "GTR035.1", "GTR036", "GTR037",
    "GTR089.1",
})


def test_default_ruleset_is_default() -> None:
    assert DEFAULT_RULESET == "default"


def test_ruleset_contents_preserve_todays_behavior() -> None:
    sets = ruleset_codes()
    assert sets["cosmetic"] == {"GTR001", "GTR003", "GTR004"}
    # `default` reproduces the historical default `format` set; `iuc` mirrors it
    # for now (placeholder membership, reassigned per-rule later).
    assert sets["default"] == _TODAY_DEFAULT
    assert sets["iuc"] == _TODAY_DEFAULT
    # strict = default + every advisory check (advisory-ness is a rule property).
    assert sets["default"] < sets["strict"]
    assert sets["strict"] - sets["default"] == advisory_codes()


def test_every_ruleset_code_is_known() -> None:
    known = known_codes()
    for codes in ruleset_codes().values():
        assert codes <= known


def test_resolve_default_is_the_default_ruleset() -> None:
    assert resolve_codes() == ruleset_codes()["default"]


def test_resolve_named_ruleset() -> None:
    assert resolve_codes(rulesets=["cosmetic"]) == ruleset_codes()["cosmetic"]


def test_resolve_unions_multiple_rulesets() -> None:
    # `--ruleset a,b` is the union of the named sets.
    sets = ruleset_codes()
    assert resolve_codes(rulesets=["cosmetic", "strict"]) == (
        sets["cosmetic"] | sets["strict"]
    )
    assert resolve_codes(rulesets=["cosmetic", "strict"]) == sets["strict"]


def test_select_replaces_ruleset_then_ignore_subtracts() -> None:
    # --select replaces the ruleset base (ruff-style), --ignore then subtracts.
    assert resolve_codes(select=["GTR001", "GTR003"], ignore=["GTR003"]) == {"GTR001"}
    # Explicit rulesets are overridden by --select.
    assert resolve_codes(rulesets=["strict"], select=["GTR001"]) == {"GTR001"}


def test_ignore_alone_subtracts_from_default() -> None:
    assert resolve_codes(ignore=["GTR006"]) == ruleset_codes()["default"] - {"GTR006"}


def test_unknown_ruleset_raises() -> None:
    with pytest.raises(UnknownRuleset):
        resolve_codes(rulesets=["nope"])


def test_unknown_code_raises() -> None:
    with pytest.raises(UnknownRuleCode):
        resolve_codes(select=["GTR999"])
    with pytest.raises(UnknownRuleCode):
        resolve_codes(ignore=["GTR012"])  # upgrade-pipeline: not selectable


def test_genuinely_unknown_code_carries_no_hint() -> None:
    with pytest.raises(UnknownRuleCode, match=r"^unknown rule code: 'GTR999'$"):
        resolve_codes(select=["GTR999"])


def test_opt_in_command_code_raises_with_a_pointer_to_its_command() -> None:
    """`--select GTR092` is rejected by design — but says where the rule lives."""
    with pytest.raises(UnknownRuleCode, match="convert-help"):
        resolve_codes(select=["GTR092"])
    with pytest.raises(UnknownRuleCode, match="convert-help"):
        resolve_upgrade_codes(select=["GTR092"])


def test_upgrade_pipeline_code_raises_with_an_upgrade_hint() -> None:
    with pytest.raises(UnknownRuleCode, match="upgrade"):
        resolve_codes(select=["GTR012"])


def test_upgrade_base_is_fixtypos_plus_cosmetic() -> None:
    assert upgrade_base_codes() == {"GTR006", "GTR001", "GTR003", "GTR004"}


def test_resolve_upgrade_ignore_drops_fixtypos() -> None:
    assert resolve_upgrade_codes(ignore=["GTR006"]) == {"GTR001", "GTR003", "GTR004"}
