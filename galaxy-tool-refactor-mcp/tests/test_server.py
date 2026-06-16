"""Tests for the FastMCP binding: tool registration + the error boundary."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from galaxy_tool_refactor_mcp import service
from galaxy_tool_refactor_mcp.server import (
    _check_tool,
    _find_references_tool,
    _format_tool,
    _rename_param_tool,
    build_server,
)


def _public_service_ops() -> set[str]:
    """The public (agent-facing) operations defined in the ``service`` adapter.

    Functions defined in ``service`` itself (not the imported ``resolve_codes`` /
    facade) whose name does not start with ``_`` (excludes the ``_*_to_dict``
    serialiser helpers) — i.e. exactly the ops a server tool should wrap.
    """
    return {
        name
        for name, obj in inspect.getmembers(service, inspect.isfunction)
        if obj.__module__ == service.__name__ and not name.startswith("_")
    }

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
        "tokenize_version_tool",
        "find_references_tool",
        "rename_param_tool",
        "list_rulesets",
        "list_rules",
    }


def test_server_tools_match_service_ops_exactly() -> None:
    """The registered server tools equal the public service ops — no drift.

    ``server.py`` hand-registers a tool per ``service`` op; this derives both sets
    independently (the live ``build_server`` registration vs. introspecting
    ``service``) and asserts equality, so a new ``service`` op with no server
    binding, an orphaned binding, or a rename on one side fails loudly instead of
    drifting silently. (The architecture audit 2026-06-16 proposal.)
    """
    server = build_server()
    registered = {tool.name for tool in asyncio.run(server.list_tools())}
    assert registered == _public_service_ops()


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


_REFERENCED = (
    '<tool id="m" name="M" version="1.0.0" profile="24.0">'
    "<command><![CDATA[echo '$a']]></command>"
    '<inputs><param value="v" type="text" name="a"/></inputs>'
    '<outputs><data name="o"/></outputs></tool>'
)


def test_find_references_handler_returns_occurrences() -> None:
    result = _find_references_tool(_REFERENCED, name="a")
    assert result["name"] == "a"
    assert isinstance(result["occurrences"], list)


def test_rename_param_handler_returns_dict() -> None:
    result = _rename_param_tool(_REFERENCED, old="a", new="b")
    assert result["changed"] is True
    assert isinstance(result["formatted"], str)


def test_rename_param_handler_maps_malformed_xml_to_value_error() -> None:
    with pytest.raises(ValueError, match="invalid tool XML"):
        _rename_param_tool("<tool><unclosed></tool>", old="a", new="b")
