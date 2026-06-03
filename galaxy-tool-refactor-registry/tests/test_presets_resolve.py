"""Tests for the preset definitions and the select/ignore resolution."""

from __future__ import annotations

import pytest

from galaxy_tool_refactor_registry.errors import UnknownPreset, UnknownRuleCode
from galaxy_tool_refactor_registry.presets import DEFAULT_PRESET, presets
from galaxy_tool_refactor_registry.registry import known_codes
from galaxy_tool_refactor_registry.resolve import (
    resolve_codes,
    resolve_upgrade_codes,
    upgrade_base_codes,
)


def test_default_preset_is_iuc() -> None:
    assert DEFAULT_PRESET == "iuc"


def test_preset_contents() -> None:
    p = presets()
    assert p["cosmetic"] == {"GTX001", "GTX003", "GTX004"}
    assert p["iuc"] == {
        "GTX001", "GTX002", "GTX003", "GTX004", "GTX005", "GTX006", "GTX013",
        "GTX017", "GTX018", "GTX019",
    }
    # strict = iuc + every advisory check.
    assert p["iuc"] < p["strict"]
    assert p["strict"] - p["iuc"] == {c for c in known_codes() if c.startswith("IUC")}


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
    assert resolve_codes(select=["GTX001", "GTX003"], ignore=["GTX003"]) == {"GTX001"}
    # An explicit preset is overridden by --select.
    assert resolve_codes(preset="strict", select=["GTX001"]) == {"GTX001"}


def test_ignore_alone_subtracts_from_preset() -> None:
    assert resolve_codes(ignore=["GTX006"]) == presets()["iuc"] - {"GTX006"}


def test_unknown_preset_raises() -> None:
    with pytest.raises(UnknownPreset):
        resolve_codes(preset="nope")


def test_unknown_code_raises() -> None:
    with pytest.raises(UnknownRuleCode):
        resolve_codes(select=["GTX999"])
    with pytest.raises(UnknownRuleCode):
        resolve_codes(ignore=["GTX012"])  # upgrade-only: not selectable


def test_upgrade_base_is_fixtypos_plus_cosmetic() -> None:
    assert upgrade_base_codes() == {"GTX006", "GTX001", "GTX003", "GTX004"}


def test_resolve_upgrade_ignore_drops_fixtypos() -> None:
    assert resolve_upgrade_codes(ignore=["GTX006"]) == {"GTX001", "GTX003", "GTX004"}
