"""Tests for the protocol-agnostic service adapter (facade → JSON dicts)."""

from __future__ import annotations

import pytest
from galaxy_tool_refactor_registry.errors import UnknownPreset, UnknownRuleCode
from galaxy_tool_xml.binding import ToolXmlSyntaxError
from galaxy_tool_xml.profiles import latest_profile

from galaxy_tool_refactor_mcp import service

# A tool with out-of-order <param> attributes (value, type, name) — GTX002
# reorders them, so `format` changes it and `check` reports a fixable finding.
_MESSY = (
    '<tool id="m" name="M" version="1.0.0" profile="24.0">'
    "<command><![CDATA[echo x]]></command>"
    '<inputs><param value="v" type="text" name="a"/></inputs>'
    '<outputs><data name="o"/></outputs></tool>'
)
# A 24.1 tool whose BAM format normalises on the 24.1 -> 24.2 bump.
_UPGRADABLE = (
    '<tool id="m" name="M" version="1.0.0" profile="24.1">'
    "<command><![CDATA[echo x]]></command>"
    '<inputs><param name="i" type="data" format="BAM"/></inputs>'
    '<outputs><data name="o"/></outputs></tool>'
)


def test_format_tool_returns_canonical_xml() -> None:
    result = service.format_tool(_MESSY)
    formatted = result["formatted"]
    assert isinstance(formatted, str)
    # GTX002 reordered the param attributes to name, type, value.
    param = formatted.partition("<param")[2]
    assert param.index("name=") < param.index("type=") < param.index("value=")
    assert isinstance(result["advisory"], list)
    assert isinstance(result["notes"], list)


def test_format_tool_unknown_preset_raises() -> None:
    with pytest.raises(UnknownPreset):
        service.format_tool(_MESSY, preset="does-not-exist")


def test_format_tool_unknown_select_code_raises() -> None:
    with pytest.raises(UnknownRuleCode):
        service.format_tool(_MESSY, select=["GTX999"])


def test_check_tool_reports_violations() -> None:
    result = service.check_tool(_MESSY)
    violations = result["violations"]
    assert isinstance(violations, list)
    codes = {v["code"] for v in violations}  # type: ignore[index]
    assert "GTX002" in codes  # the out-of-order param attributes
    assert isinstance(result["advisory_codes"], list)


def test_check_tool_strict_marks_advisory() -> None:
    result = service.check_tool(_MESSY, preset="strict")
    advisory_codes = result["advisory_codes"]
    assert isinstance(advisory_codes, list)
    # Strict adds the IUC advisory family; an IUC finding is marked advisory.
    iuc = [v for v in result["violations"] if v["code"].startswith("IUC")]  # type: ignore[index]
    assert iuc and all(v["advisory"] for v in iuc)  # type: ignore[index]


def test_upgrade_tool_bumps_profile() -> None:
    result = service.upgrade_tool(_UPGRADABLE)
    formatted = result["formatted"]
    assert isinstance(formatted, str)
    assert f'profile="{latest_profile()}"' in formatted
    assert "24.1" in result["steps_applied"]  # type: ignore[operator]
    assert result["missing_upgrade"] is None
    assert result["behavior_preserving"] in (True, False, None)


def test_list_presets_includes_default() -> None:
    presets = service.list_presets()
    assert presets
    names = {p["name"] for p in presets}
    assert "iuc" in names
    assert any(p["is_default"] for p in presets)


def test_list_rules_has_codes_and_families() -> None:
    rules = service.list_rules()
    codes = {r["code"] for r in rules}
    assert any(c.startswith("GTX") for c in codes)
    assert any(c.startswith("IUC") for c in codes)
    families = {r["family"] for r in rules}
    assert {"codemod", "fmt", "check"} <= families


def test_list_rules_include_upgrade_adds_more() -> None:
    base = len(service.list_rules())
    extended = len(service.list_rules(include_upgrade=True))
    assert extended > base


def test_malformed_xml_raises_syntax_error() -> None:
    with pytest.raises(ToolXmlSyntaxError):
        service.format_tool("<tool><unclosed></tool>")
