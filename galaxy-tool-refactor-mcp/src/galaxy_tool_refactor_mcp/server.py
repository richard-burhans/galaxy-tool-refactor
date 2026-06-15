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

from galaxy_tool_refactor_registry.errors import (
    UnknownProfile,
    UnknownRuleCode,
    UnknownRuleset,
    UpgradeFlagError,
)
from galaxy_tool_source.binding import ToolXmlSyntaxError
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
    except (
        UnknownRuleset,
        UnknownRuleCode,
        UnknownProfile,
        UpgradeFlagError,
    ) as error:
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
    modernize: bool = False,
    allow_behavior_change: bool = False,
    target_profile: str | None = None,
) -> dict[str, object]:
    """Repair then format; profile= moves only as far as strictly needed.

    Minimal bump by default: a tool valid at its declared profile keeps it (an
    undeclared tool stays undeclared); an invalid one is bumped to the minimum
    valid profile at or above its baseline (baseline_profile/reached_profile in
    the result). Set modernize to walk toward the latest profile instead — the
    walk is capped by the lower of the behaviour ceiling (reported via
    stopped_at / blocking_codes) and the deployment ceiling, the newest profile
    every major public Galaxy server runs. Set allow_behavior_change to walk
    past applicable behaviour changes (requires modernize or target_profile;
    the deployment ceiling still caps); set target_profile to walk up to an
    explicit vendored profile (it may exceed the deployment ceiling).
    """
    return _guarded(
        lambda: service.upgrade_tool(
            xml,
            select=select or (),
            ignore=ignore or (),
            modernize=modernize,
            allow_behavior_change=allow_behavior_change,
            target_profile=target_profile,
        )
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


def _convert_help_tool(xml: str) -> dict[str, object]:
    """Convert an RST <help> to Markdown when provably render-equivalent (opt-in)."""
    return _guarded(lambda: service.convert_help_tool(xml))


def _tokenize_version_tool(xml: str) -> dict[str, object]:
    """Factor a literal version into @TOOL_VERSION@ tokens when provable (opt-in)."""
    return _guarded(lambda: service.tokenize_version_tool(xml))


def _find_references_tool(xml: str, name: str) -> dict[str, object]:
    """Every Cheetah $name reference site across the tool's templated sections."""
    return _guarded(lambda: service.find_references_tool(xml, name=name))


def _rename_param_tool(xml: str, old: str, new: str) -> dict[str, object]:
    """Rename a parameter across the tool (single-document); report a bail reason."""
    return _guarded(lambda: service.rename_param_tool(xml, old=old, new=new))


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
    server.add_tool(_convert_help_tool, name="convert_help_tool")
    server.add_tool(_tokenize_version_tool, name="tokenize_version_tool")
    server.add_tool(_find_references_tool, name="find_references_tool")
    server.add_tool(_rename_param_tool, name="rename_param_tool")
    server.add_tool(_list_rulesets, name="list_rulesets")
    server.add_tool(_list_rules, name="list_rules")
    return server


def main() -> None:
    """Console-script entry point: serve over stdio."""
    build_server().run()
