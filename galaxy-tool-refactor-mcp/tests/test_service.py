"""Tests for the protocol-agnostic service adapter (facade → JSON dicts)."""

from __future__ import annotations

import pytest
from galaxy_tool_refactor_registry.errors import UnknownRuleCode, UnknownRuleset
from galaxy_tool_xml.binding import ToolXmlSyntaxError
from galaxy_tool_xml.profiles import latest_profile

from galaxy_tool_refactor_mcp import service

# A tool with out-of-order <param> attributes (value, type, name) — GTR002
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
    # GTR002 reordered the param attributes to name, type, value.
    param = formatted.partition("<param")[2]
    assert param.index("name=") < param.index("type=") < param.index("value=")
    assert isinstance(result["advisory"], list)
    assert isinstance(result["notes"], list)


def test_format_tool_unknown_ruleset_raises() -> None:
    with pytest.raises(UnknownRuleset):
        service.format_tool(_MESSY, rulesets=["does-not-exist"])


def test_format_tool_unknown_select_code_raises() -> None:
    with pytest.raises(UnknownRuleCode):
        service.format_tool(_MESSY, select=["GTR999"])


def test_check_tool_reports_violations() -> None:
    result = service.check_tool(_MESSY)
    violations = result["violations"]
    assert isinstance(violations, list)
    codes = {v["code"] for v in violations}  # type: ignore[index]
    assert "GTR002" in codes  # the out-of-order param attributes
    assert isinstance(result["advisory_codes"], list)


def test_check_tool_strict_marks_advisory() -> None:
    result = service.check_tool(_MESSY, rulesets=["strict"])
    advisory_codes = result["advisory_codes"]
    assert isinstance(advisory_codes, list)
    # Strict adds the advisory checks; an advisory finding is marked advisory
    # (a per-violation flag, not a code prefix).
    advisory = [v for v in result["violations"] if v["advisory"]]  # type: ignore[index]
    assert advisory


def test_upgrade_tool_bumps_profile() -> None:
    result = service.upgrade_tool(_UPGRADABLE)
    formatted = result["formatted"]
    assert isinstance(formatted, str)
    assert f'profile="{latest_profile()}"' in formatted
    assert "24.1" in result["steps_applied"]  # type: ignore[operator]
    assert result["missing_upgrade"] is None
    assert result["behavior_preserving"] in (True, False, None)


def test_list_rulesets_includes_default() -> None:
    rulesets = service.list_rulesets()
    assert rulesets
    names = {r["name"] for r in rulesets}
    assert "default" in names
    assert any(r["is_default"] for r in rulesets)


def test_list_rules_has_codes_and_families() -> None:
    rules = service.list_rules()
    codes = {r["code"] for r in rules}
    assert all(c.startswith("GTR") for c in codes)  # unified namespace
    families = {r["family"] for r in rules}
    assert {"codemod", "fmt", "check"} <= families


def test_list_rules_include_upgrade_adds_more() -> None:
    base = len(service.list_rules())
    extended = len(service.list_rules(include_upgrade=True))
    assert extended > base


def test_malformed_xml_raises_syntax_error() -> None:
    with pytest.raises(ToolXmlSyntaxError):
        service.format_tool("<tool><unclosed></tool>")


_CONVERTIBLE = (
    '<tool id="m" name="M" version="1.0.0" profile="24.2">'
    "<command><![CDATA[echo x]]></command>"
    "<help>Title\n=====\n\nSome **bold** text.\n</help></tool>"
)


def test_convert_help_tool_converts() -> None:
    result = service.convert_help_tool(_CONVERTIBLE)
    assert result["converted"] is True
    assert result["skip_reason"] is None
    formatted = result["formatted"]
    assert isinstance(formatted, str)
    assert 'format="markdown"' in formatted
    assert "# Title" in formatted


def test_convert_help_tool_reports_profile_skip() -> None:
    old = _CONVERTIBLE.replace(' profile="24.2"', "")
    result = service.convert_help_tool(old)
    assert result["converted"] is False
    skip_reason = result["skip_reason"]
    assert isinstance(skip_reason, str) and "upgrade" in skip_reason
