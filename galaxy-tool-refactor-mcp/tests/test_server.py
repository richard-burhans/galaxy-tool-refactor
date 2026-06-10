"""Tests for the FastMCP binding: tool registration + the error boundary."""

from __future__ import annotations

import asyncio

import pytest

from galaxy_tool_refactor_mcp.server import (
    _check_tool,
    _format_tool,
    build_server,
)

_TOOL = (
    '<tool id="m" name="M" version="1.0.0" profile="24.0">'
    "<command><![CDATA[echo x]]></command>"
    '<inputs><param value="v" type="text" name="a"/></inputs>'
    '<outputs><data name="o"/></outputs></tool>'
)


def test_build_server_registers_every_tool() -> None:
    server = build_server()
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == {
        "format_tool",
        "upgrade_tool",
        "check_tool",
        "convert_help_tool",
        "list_rulesets",
        "list_rules",
    }


def test_handler_maps_unknown_ruleset_to_plain_valueerror() -> None:
    """The error boundary downgrades the typed UnknownRuleset to a plain message."""
    with pytest.raises(ValueError) as exc_info:
        _format_tool(_TOOL, rulesets=["does-not-exist"])
    # Not the UnknownRuleset subclass — a clean message for the agent.
    assert type(exc_info.value) is ValueError


def test_handler_maps_malformed_xml_to_value_error() -> None:
    with pytest.raises(ValueError, match="invalid tool XML"):
        _format_tool("<tool><unclosed></tool>")


def test_handler_success_path_returns_dict() -> None:
    result = _check_tool(_TOOL)
    assert isinstance(result, dict)
    assert "violations" in result
