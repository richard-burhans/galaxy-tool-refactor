"""The FastMCP binding — a thin protocol shell over ``service``.

Each MCP tool is a small handler with agent-facing named arguments that delegates
to the protocol-agnostic ``service`` adapter. The handlers are the **error
boundary** (the MCP analogue of the CLI's): they translate the facade's typed
``UnknownRuleset`` / ``UnknownRuleCode`` and tier-1's ``ToolXmlSyntaxError`` into a
plain ``ValueError`` whose message FastMCP returns as a tool error, so a malformed
tool or an unknown ruleset is a clean error result rather than a crashed server.

Run it with the ``galaxy-tool-refactor-mcp`` console script (stdio transport).
``build_server()`` is factored out so tests can introspect the registered tools
without starting a transport. See ``docs/decisions.md`` D1; agent-authored rules
(vision Goal 2) are out of scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from galaxy_tool_refactor_registry.errors import UnknownRuleCode, UnknownRuleset
from galaxy_tool_xml.binding import ToolXmlSyntaxError
from mcp.server.fastmcp import FastMCP

from galaxy_tool_refactor_mcp import service

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TypeVar

    T = TypeVar("T")

_SERVER_NAME = "galaxy-tool-refactor"


def _guarded(produce: Callable[[], T], /) -> T:
    """Run *produce*, mapping the facade/parse errors to an agent-facing message."""
    try:
        return produce()
    except (UnknownRuleset, UnknownRuleCode) as error:
        raise ValueError(str(error)) from error
    except ToolXmlSyntaxError as error:
        raise ValueError(f"invalid tool XML: {error}") from error


def _format_tool(
    xml: str,
    rulesets: list[str] | None = None,
    select: list[str] | None = None,
    ignore: list[str] | None = None,
) -> dict[str, object]:
    """Apply a ruleset's fixable rules then format; return canonical XML + notes."""
    return _guarded(
        lambda: service.format_tool(
            xml, rulesets=rulesets or (), select=select or (), ignore=ignore or ()
        )
    )


def _upgrade_tool(
    xml: str,
    select: list[str] | None = None,
    ignore: list[str] | None = None,
) -> dict[str, object]:
    """Profile-upgrade then format; return upgraded XML, steps applied, and notes."""
    return _guarded(
        lambda: service.upgrade_tool(xml, select=select or (), ignore=ignore or ())
    )


def _check_tool(
    xml: str,
    rulesets: list[str] | None = None,
    select: list[str] | None = None,
    ignore: list[str] | None = None,
) -> dict[str, object]:
    """Report-only detect over the selected rules; never mutates the tool."""
    return _guarded(
        lambda: service.check_tool(
            xml, rulesets=rulesets or (), select=select or (), ignore=ignore or ()
        )
    )


def _list_rulesets() -> list[dict[str, object]]:
    """The baked-in rulesets (name / codes / is_default / description)."""
    return service.list_rulesets()


def _list_rules(include_upgrade: bool = False) -> list[dict[str, object]]:
    """The baked-in rules as JSON — every RuleInfo field (incl. cite)."""
    return service.list_rules(include_upgrade=include_upgrade)


def build_server() -> FastMCP:
    """Construct the FastMCP server with every tool registered (no transport)."""
    server = FastMCP(_SERVER_NAME)
    server.add_tool(_format_tool, name="format_tool")
    server.add_tool(_upgrade_tool, name="upgrade_tool")
    server.add_tool(_check_tool, name="check_tool")
    server.add_tool(_list_rulesets, name="list_rulesets")
    server.add_tool(_list_rules, name="list_rules")
    return server


def main() -> None:
    """Console-script entry point: serve over stdio."""
    build_server().run()
