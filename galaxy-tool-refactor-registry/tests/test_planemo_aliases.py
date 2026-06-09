"""Tests for the planemo-linter alias index and name-based selection."""

from __future__ import annotations

import pytest

from galaxy_tool_refactor_registry import facade
from galaxy_tool_refactor_registry.errors import UnknownRuleCode
from galaxy_tool_refactor_registry.planemo import planemo_index
from galaxy_tool_refactor_registry.resolve import resolve_codes


def test_index_maps_planemo_names_to_covering_codes() -> None:
    index = planemo_index()
    # A single-linter rule.
    assert index["outputsmissing"] == {"GTR048"}
    # A bundled rule: both planemo names of GTR028 resolve to it.
    assert index["helpmissing"] == {"GTR028"}
    assert index["helpempty"] == {"GTR028"}


def test_select_by_planemo_name() -> None:
    assert resolve_codes(select=["HelpMissing"]) == {"GTR028"}


def test_select_by_planemo_name_is_case_insensitive() -> None:
    assert resolve_codes(select=["helpmissing"]) == {"GTR028"}
    assert resolve_codes(select=["HELPMISSING"]) == {"GTR028"}


def test_select_a_bundle_name_selects_the_whole_covering_rule() -> None:
    # GTR027 covers EDAMTermsValid + BioToolsValid; either name selects GTR027.
    assert resolve_codes(select=["EDAMTermsValid"]) == {"GTR027"}
    assert resolve_codes(select=["BioToolsValid"]) == {"GTR027"}


def test_ignore_by_planemo_name_subtracts_from_the_base() -> None:
    strict = resolve_codes(rulesets=["strict"])
    assert "GTR027" in strict
    assert resolve_codes(rulesets=["strict"], ignore=["EDAMTermsValid"]) == strict - {
        "GTR027"
    }


def test_select_mixes_codes_and_planemo_names() -> None:
    assert resolve_codes(select=["GTR001", "HelpMissing"]) == {"GTR001", "GTR028"}


def test_unknown_planemo_name_raises() -> None:
    with pytest.raises(UnknownRuleCode):
        resolve_codes(select=["NotARealLinter"])


def test_rule_info_carries_planemo_linters() -> None:
    rules = {r.code: r for r in facade.list_rules()}
    assert rules["GTR028"].planemo_linters == ("HelpEmpty", "HelpMissing")
    # An own-rule with no planemo equivalent.
    assert rules["GTR001"].planemo_linters == ()
