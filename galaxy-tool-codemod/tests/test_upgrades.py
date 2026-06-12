"""Tests for the upgrade registry and the ``UpgradeToLatest`` orchestrator.

``UpgradeToLatest`` loops: declare the newest valid profile (``UpdateProfile``),
and while the tool is below the latest profile, apply the registered single-step
upgrade for its current sticking version — until it reaches latest or hits a
version with no registered upgrade (an unhandled sticking point the discovery
sweep surfaces).
"""

from __future__ import annotations

import pytest
from galaxy_tool_source.binding import newest_valid_profile, validate_tool
from galaxy_tool_source.profiles import latest_profile
from lxml import etree

from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.codemods.upgrade_24_1 import Upgrade24_1
from galaxy_tool_codemod.parse import parse_module
from galaxy_tool_codemod.upgrades import (
    UPGRADE_CODEMODS,
    UpgradeToLatest,
    UpgradeToValid,
)


# A tool whose <required_files> entered the schema at 21.09: invalid at its
# declared 20.09 (and every older profile), valid as-is at 21.09+. The
# bump-direct case — no structural step is needed, only a profile declaration.
def _required_files_tool(*, profile: str) -> bytes:
    return (
        f'<tool id="r" name="R" version="1.0.0" profile="{profile}">'
        '<required_files><include path="x.py"/></required_files>'
        "<command><![CDATA[echo x]]></command>"
        "<inputs/><outputs/></tool>"
    ).encode()


def _tool(
    *, profile: str, param_fmt: str | None = None, data_fmt: str | None = None
) -> bytes:
    param = (
        f'<param name="i" type="data" format="{param_fmt}"/>'
        if param_fmt is not None
        else ""
    )
    data = (
        f'<data name="o" format="{data_fmt}"/>'
        if data_fmt is not None
        else '<data name="o"/>'
    )
    return (
        f'<tool id="m" name="M" version="1.0.0" profile="{profile}">'
        "<command><![CDATA[echo x]]></command>"
        f"<inputs>{param}</inputs><outputs>{data}</outputs></tool>"
    ).encode()


def test_registry_maps_24_1_to_its_codemod() -> None:
    assert UPGRADE_CODEMODS["24.1"] is Upgrade24_1


def test_upgrade_to_latest_is_a_codemod_command() -> None:
    assert issubclass(UpgradeToLatest, CodemodCommand)


def test_upgrades_stuck_tool_to_latest_and_declares_it() -> None:
    """A 24.1-stuck tool is upgraded and its profile re-declared to latest."""
    module = parse_module(_tool(profile="24.1", param_fmt="BAM"))
    UpgradeToLatest().apply(module)
    root = module.document.root
    assert root.find(".//param[@format]").get("format") == "bam"
    assert newest_valid_profile(module.document) == latest_profile()
    assert root.get("profile") == latest_profile()


def test_noop_on_already_latest_tool() -> None:
    module = parse_module(_tool(profile=latest_profile()))
    before = etree.tostring(module.document.root)
    UpgradeToLatest().apply(module)
    assert etree.tostring(module.document.root) == before


def test_stops_at_unhandled_sticking_point() -> None:
    """A tool that stays stuck after its upgrade (data comma-list) halts cleanly."""
    module = parse_module(_tool(profile="24.1", data_fmt="fasta,fastq"))
    UpgradeToLatest().apply(module)
    assert newest_valid_profile(module.document) == "24.1"
    assert module.document.root.get("profile") == "24.1"


def test_is_idempotent() -> None:
    module = parse_module(_tool(profile="24.1", param_fmt="BAM"))
    UpgradeToLatest().apply(module)
    once = etree.tostring(module.document.root)
    UpgradeToLatest().apply(module)
    assert etree.tostring(module.document.root) == once


def test_upgrade_steps_applied_reports_advanced_versions() -> None:
    """The orchestrator records each from-version its upgrade actually advanced."""
    module = parse_module(_tool(profile="24.1", param_fmt="BAM"))
    upgrade = UpgradeToLatest()
    upgrade.apply(module)
    assert upgrade.upgrade_steps_applied() == ("24.1",)


def test_upgrade_steps_empty_when_already_latest() -> None:
    module = parse_module(_tool(profile=latest_profile()))
    upgrade = UpgradeToLatest()
    upgrade.apply(module)
    assert upgrade.upgrade_steps_applied() == ()


def test_upgrade_steps_empty_when_stuck_without_advancing() -> None:
    """A step that runs but does not advance the tool is not counted."""
    module = parse_module(_tool(profile="24.1", data_fmt="fasta,fastq"))
    upgrade = UpgradeToLatest()
    upgrade.apply(module)
    assert upgrade.upgrade_steps_applied() == ()


def test_reports_missing_upgrade_codemod(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A sub-latest sticking version with no registered upgrade is reported.

    Covers tools not in the corpus: if the canonical pipeline ever hits a
    profile it has no ``upgrade_vN`` for, it must surface it (warn + expose)
    so the missing codemod gets written.
    """
    # Patch the exact globals dict ``UpgradeToLatest.apply`` reads, not a module
    # looked up by name — another test may have dropped and re-imported the
    # codemod package, leaving the class bound to a different module object.
    monkeypatch.setitem(UpgradeToLatest.apply.__globals__, "UPGRADE_CODEMODS", {})
    module = parse_module(_tool(profile="24.1", param_fmt="BAM"))
    upgrade = UpgradeToLatest()
    with caplog.at_level("WARNING"):
        upgrade.apply(module)
    assert upgrade.missing_upgrade() == "24.1"
    assert any("24.1" in record.message for record in caplog.records)


def test_no_missing_upgrade_when_latest_reached() -> None:
    """Reaching the latest profile leaves no missing-upgrade report."""
    module = parse_module(_tool(profile="24.1", param_fmt="BAM"))
    upgrade = UpgradeToLatest()
    upgrade.apply(module)
    assert upgrade.missing_upgrade() is None


def test_walk_stops_at_the_requested_ceiling() -> None:
    """A ceiling equal to the starting profile means no step runs at all."""
    module = parse_module(_tool(profile="24.1", param_fmt="BAM"))
    before = etree.tostring(module.document.root)
    upgrade = UpgradeToLatest(ceiling="24.1")
    upgrade.apply(module)
    # The walk never crossed 24.1: the uppercase format (the 24.2 repair) is
    # untouched and the declaration stays put.
    assert etree.tostring(module.document.root) == before
    assert upgrade.upgrade_steps_applied() == ()


def test_walk_advances_up_to_but_not_past_the_ceiling() -> None:
    """Intermediate steps below the ceiling run; the declaration caps there."""
    module = parse_module(_tool(profile="24.1", param_fmt="BAM"))
    upgrade = UpgradeToLatest(ceiling="25.1")
    upgrade.apply(module)
    root = module.document.root
    assert root.get("profile") == "25.1"
    assert upgrade.upgrade_steps_applied() == ("24.1",)
    # The 24.1 step ran (format lowercased), even though the walk capped at 25.1.
    assert root.find(".//param[@format]").get("format") == "bam"


def test_a_deliberate_cap_is_not_a_missing_upgrade(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Stalling at the requested ceiling is silent: no warning, no report."""
    module = parse_module(_tool(profile="24.1", param_fmt="BAM"))
    upgrade = UpgradeToLatest(ceiling="24.1")
    with caplog.at_level("WARNING"):
        upgrade.apply(module)
    assert upgrade.missing_upgrade() is None
    assert not caplog.records


# --- UpgradeToValid: the minimal-bump orchestrator -------------------------


def test_upgrade_to_valid_is_a_codemod_command() -> None:
    assert issubclass(UpgradeToValid, CodemodCommand)


def test_keeps_a_tool_already_valid_at_its_floor() -> None:
    """A tool valid at its floor keeps its profile and is left byte-identical."""
    module = parse_module(_tool(profile="24.0"))
    before = etree.tostring(module.document.root)
    upgrade = UpgradeToValid(floor="24.0")
    upgrade.apply(module)
    assert etree.tostring(module.document.root) == before
    assert module.document.root.get("profile") == "24.0"
    assert upgrade.upgrade_steps_applied() == ()
    assert upgrade.unreachable_floor() is None


def test_declares_a_floor_on_an_undeclared_but_valid_tool() -> None:
    """No structural step: a missing declaration is set to exactly the floor."""
    tool = (
        b'<tool id="m" name="M" version="1.0.0">'
        b"<command><![CDATA[echo x]]></command><inputs/><outputs/></tool>"
    )
    module = parse_module(tool)
    upgrade = UpgradeToValid(floor="24.0")
    upgrade.apply(module)
    assert module.document.root.get("profile") == "24.0"
    assert upgrade.upgrade_steps_applied() == ()


def test_bumps_directly_to_the_minimum_valid_profile() -> None:
    """Invalid at the floor, valid as-is higher: bump to the minimum, no step."""
    module = parse_module(_required_files_tool(profile="20.09"))
    upgrade = UpgradeToValid(floor="20.09")
    upgrade.apply(module)
    # <required_files> first validates at 21.09 — the minimum, not latest.
    assert module.document.root.get("profile") == "21.09"
    assert validate_tool(module.document, profile="21.09").valid
    assert upgrade.upgrade_steps_applied() == ()
    assert upgrade.unreachable_floor() is None


def test_does_not_bump_past_the_minimum() -> None:
    """The declaration lands at the minimum valid profile, never at latest."""
    module = parse_module(_required_files_tool(profile="20.09"))
    UpgradeToValid(floor="20.09").apply(module)
    assert module.document.root.get("profile") != latest_profile()


def test_step_assisted_minimal_bump() -> None:
    """Valid nowhere >= floor as-is, but a step codemod unblocks the minimum.

    An uppercase ``format="BAM"`` is valid at 24.1 but rejected at 24.2; with a
    floor of 24.2 nothing validates as-is, so the 24.1 step (lowercasing the
    format) runs and the declaration lands at exactly 24.2.
    """
    module = parse_module(_tool(profile="24.1", param_fmt="BAM"))
    upgrade = UpgradeToValid(floor="24.2")
    upgrade.apply(module)
    root = module.document.root
    assert root.get("profile") == "24.2"
    assert root.find(".//param[@format]").get("format") == "bam"
    assert upgrade.upgrade_steps_applied() == ("24.1",)
    assert upgrade.unreachable_floor() is None


def test_unreachable_when_nothing_validates_at_or_above_the_floor() -> None:
    """A tool stuck below the floor with no advancing step reports unreachable."""
    module = parse_module(_tool(profile="24.1", data_fmt="fasta,fastq"))
    before = etree.tostring(module.document.root)
    upgrade = UpgradeToValid(floor=latest_profile())
    upgrade.apply(module)
    # The comma-list data format never validates at latest and no step clears
    # it: the tool is left untouched and the floor reported unreachable.
    assert etree.tostring(module.document.root) == before
    assert upgrade.unreachable_floor() == latest_profile()


def test_unreachable_reverts_a_partial_multi_step_walk() -> None:
    """A walk that advances partway but stalls below the floor is fully reverted.

    Uppercase ``format="BAM"`` advances 24.1 -> 24.2 (the step lowercases it),
    but a comma-list data format blocks every profile beyond, so a floor of the
    latest profile is unreachable. The tool must be left byte-identical, never
    half-upgraded with the format lowercased and the profile left undeclared.
    """
    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="24.1">'
        b"<command><![CDATA[echo x]]></command>"
        b'<inputs><param name="i" type="data" format="BAM"/></inputs>'
        b'<outputs><data name="o" format="fasta,fastq"/></outputs></tool>'
    )
    module = parse_module(tool)
    before = etree.tostring(module.document.root)
    upgrade = UpgradeToValid(floor=latest_profile())
    upgrade.apply(module)
    assert etree.tostring(module.document.root) == before
    assert upgrade.unreachable_floor() == latest_profile()
    assert upgrade.upgrade_steps_applied() == ()


def test_is_idempotent_minimal_bump() -> None:
    module = parse_module(_required_files_tool(profile="20.09"))
    UpgradeToValid(floor="20.09").apply(module)
    once = etree.tostring(module.document.root)
    UpgradeToValid(floor="20.09").apply(module)
    assert etree.tostring(module.document.root) == once
