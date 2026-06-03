"""The protocol-agnostic adapter: registry facade → JSON-serialisable ``dict``s.

This is the substance of the MCP server, with **no ``mcp`` import** — it takes
agent-friendly inputs (XML as a ``str``, preset name, code lists) and returns
plain JSON-able structures by calling the tier-3.6 facade. ``server`` wraps these
as MCP tools. Keeping the logic here means it is unit-testable without a transport
and the FastMCP binding stays a thin shell (the vision's "thin adapter").

XML content arrives as a ``str`` and is encoded to ``bytes`` before the facade
sees it, so it is always parsed as *content*, never mistaken for a path. Nothing
here writes to disk — agents supply content and get content back. Selection /
parse errors propagate as the facade's typed ``UnknownPreset`` /
``UnknownRuleCode`` and tier-1's ``ToolXmlSyntaxError``; the *server* is the error
boundary that turns them into MCP error responses (mirroring the CLI).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from galaxy_tool_refactor_registry import facade
from galaxy_tool_refactor_registry.resolve import resolve_codes, resolve_upgrade_codes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from galaxy_tool_refactor_registry.results import (
        DetectResult,
        FormatResult,
        PresetInfo,
        RuleInfo,
        UpgradeResult,
    )
    from galaxy_tool_refactor_rules.violation import Violation


def _violation_to_dict(violation: Violation, /) -> dict[str, object]:
    return {
        "code": violation.code,
        "sourceline": violation.sourceline,
        "xpath": violation.xpath,
        "message": violation.message,
    }


def _format_result_to_dict(result: FormatResult, /) -> dict[str, object]:
    return {
        "formatted": result.formatted.decode("utf-8"),
        "advisory": [_violation_to_dict(v) for v in result.advisory],
        "notes": list(result.notes),
    }


def _upgrade_result_to_dict(result: UpgradeResult, /) -> dict[str, object]:
    return {
        "formatted": result.formatted.decode("utf-8"),
        "steps_applied": list(result.steps_applied),
        "missing_upgrade": result.missing_upgrade,
        "behavior_preserving": result.behavior_preserving,
        "advisory": [_violation_to_dict(v) for v in result.advisory],
        "notes": list(result.notes),
    }


def _detect_result_to_dict(result: DetectResult, /) -> dict[str, object]:
    return {
        "violations": [
            {**_violation_to_dict(v), "advisory": result.is_advisory(v)}
            for v in result.violations
        ],
        "advisory_codes": sorted(result.advisory_codes),
    }


def _preset_info_to_dict(info: PresetInfo, /) -> dict[str, object]:
    return {
        "name": info.name,
        "codes": list(info.codes),
        "is_default": info.is_default,
        "description": info.description,
    }


def _rule_info_to_dict(info: RuleInfo, /) -> dict[str, object]:
    return {
        "code": info.code,
        "summary": info.summary,
        "family": info.family,
        "fixable": info.fixable,
        "presets": list(info.presets),
        "since": info.since,
        "cite": info.cite,
    }


def format_tool(
    xml: str,
    /,
    *,
    preset: str | None = None,
    select: Sequence[str] = (),
    ignore: Sequence[str] = (),
) -> dict[str, object]:
    """Apply a preset's fixable rules then format; return the canonical XML + notes."""
    codes = resolve_codes(preset=preset, select=select, ignore=ignore)
    return _format_result_to_dict(facade.run(xml.encode("utf-8"), codes=codes))


def upgrade_tool(
    xml: str,
    /,
    *,
    select: Sequence[str] = (),
    ignore: Sequence[str] = (),
) -> dict[str, object]:
    """Profile-upgrade then format; return the upgraded XML, steps, and notes."""
    codes = resolve_upgrade_codes(select=select, ignore=ignore)
    return _upgrade_result_to_dict(facade.upgrade(xml.encode("utf-8"), codes=codes))


def check_tool(
    xml: str,
    /,
    *,
    preset: str | None = None,
    select: Sequence[str] = (),
    ignore: Sequence[str] = (),
) -> dict[str, object]:
    """Report-only detect over the selected rules; never mutates the tool."""
    codes = resolve_codes(preset=preset, select=select, ignore=ignore)
    return _detect_result_to_dict(facade.detect(xml.encode("utf-8"), codes=codes))


def list_presets() -> list[dict[str, object]]:
    """The baked-in presets (name / codes / is_default / description)."""
    return [_preset_info_to_dict(info) for info in facade.list_presets()]


def list_rules(*, include_upgrade: bool = False) -> list[dict[str, object]]:
    """The baked-in rules as JSON — every RuleInfo field (incl. cite)."""
    return [
        _rule_info_to_dict(info)
        for info in facade.list_rules(include_upgrade=include_upgrade)
    ]
