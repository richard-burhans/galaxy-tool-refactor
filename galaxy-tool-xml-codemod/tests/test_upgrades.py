"""Tests for the upgrade registry and the ``UpgradeToLatest`` orchestrator.

``UpgradeToLatest`` loops: declare the newest valid profile (``UpdateProfile``),
and while the tool is below the latest profile, apply the registered single-step
upgrade for its current sticking version — until it reaches latest or hits a
version with no registered upgrade (an unhandled sticking point the discovery
sweep surfaces).
"""

from __future__ import annotations

from galaxy_tool_xml.binding import newest_valid_profile
from galaxy_tool_xml.profiles import latest_profile
from lxml import etree

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.upgrade_24_1 import Upgrade24_1
from galaxy_tool_xml_codemod.parse import parse_module
from galaxy_tool_xml_codemod.upgrades import UPGRADE_CODEMODS, UpgradeToLatest


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
