"""Tests for the preset definitions and the select/ignore resolution."""

from __future__ import annotations

import pytest

from galaxy_tool_refactor_registry.errors import UnknownPreset, UnknownRuleCode
from galaxy_tool_refactor_registry.presets import DEFAULT_PRESET, presets
from galaxy_tool_refactor_registry.registry import advisory_codes, known_codes
from galaxy_tool_refactor_registry.resolve import (
    resolve_codes,
    resolve_upgrade_codes,
    upgrade_base_codes,
)


def test_default_preset_is_iuc() -> None:
    assert DEFAULT_PRESET == "iuc"


def test_preset_contents() -> None:
    p = presets()
    assert p["cosmetic"] == {"GTR001", "GTR003", "GTR004"}
    assert p["iuc"] == {
        "GTR001", "GTR002", "GTR003", "GTR004", "GTR005", "GTR006", "GTR013",
        "GTR017", "GTR018.1", "GTR019.1", "GTR020.1", "GTR035", "GTR036", "GTR037",
    }
    # strict = iuc + every advisory check. Advisory-ness is a rule property
    # (advisory_codes()), no longer inferable from a code prefix.
    assert p["iuc"] < p["strict"]
    assert p["strict"] - p["iuc"] == advisory_codes()


def test_every_preset_code_is_known() -> None:
    known = known_codes()
    for codes in presets().values():
        assert codes <= known


def test_resolve_default_is_iuc() -> None:
    assert resolve_codes() == presets()["iuc"]


def test_resolve_named_preset() -> None:
    assert resolve_codes(preset="cosmetic") == presets()["cosmetic"]


def test_select_replaces_preset_then_ignore_subtracts() -> None:
    # --select replaces the preset's set (ruff-style), --ignore then subtracts.
    assert resolve_codes(select=["GTR001", "GTR003"], ignore=["GTR003"]) == {"GTR001"}
    # An explicit preset is overridden by --select.
    assert resolve_codes(preset="strict", select=["GTR001"]) == {"GTR001"}


def test_ignore_alone_subtracts_from_preset() -> None:
    assert resolve_codes(ignore=["GTR006"]) == presets()["iuc"] - {"GTR006"}


def test_unknown_preset_raises() -> None:
    with pytest.raises(UnknownPreset):
        resolve_codes(preset="nope")


def test_unknown_code_raises() -> None:
    with pytest.raises(UnknownRuleCode):
        resolve_codes(select=["GTR999"])
    with pytest.raises(UnknownRuleCode):
        resolve_codes(ignore=["GTR012"])  # upgrade-only: not selectable


def test_upgrade_base_is_fixtypos_plus_cosmetic() -> None:
    assert upgrade_base_codes() == {"GTR006", "GTR001", "GTR003", "GTR004"}


def test_resolve_upgrade_ignore_drops_fixtypos() -> None:
    assert resolve_upgrade_codes(ignore=["GTR006"]) == {"GTR001", "GTR003", "GTR004"}
