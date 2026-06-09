"""Tests for the named-ruleset catalog."""

from __future__ import annotations

import dataclasses

import pytest

from galaxy_tool_refactor_rules.rulesets import (
    DEFAULT_RULESET,
    Ruleset,
    ruleset_description,
    ruleset_names,
    rulesets_catalog,
)


def test_ruleset_is_frozen() -> None:
    ruleset = Ruleset(name="default", description="default")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ruleset.name = "other"  # type: ignore[misc]


def test_catalog_has_the_seeded_rulesets() -> None:
    assert ruleset_names() == ("cosmetic", "default", "iuc", "strict")


def test_default_ruleset_is_in_the_catalog() -> None:
    assert DEFAULT_RULESET == "default"
    assert DEFAULT_RULESET in ruleset_names()


def test_descriptions_resolve_for_every_name() -> None:
    for name in ruleset_names():
        description = ruleset_description(name)
        assert description is not None
        assert description != ""
        # A description equal to the name is a placeholder, not a description
        # (the user-facing `rulesets` command / MCP `list_rulesets` shows it).
        assert description != name


def test_unknown_ruleset_description_is_none() -> None:
    assert ruleset_description("nope") is None


def test_catalog_names_are_unique() -> None:
    names = [ruleset.name for ruleset in rulesets_catalog()]
    assert len(names) == len(set(names))
