"""The protocol-agnostic adapter: registry facade → JSON-serialisable ``dict``s.

This is the substance of the MCP server, with **no ``mcp`` import** — it takes
agent-friendly inputs (XML as a ``str``, ruleset names, code lists) and returns
plain JSON-able structures by calling the tier-3.6 facade. ``server`` wraps these
as MCP tools. Keeping the logic here means it is unit-testable without a transport
and the FastMCP binding stays a thin shell (the vision's "thin adapter").

XML content arrives as a ``str`` and is encoded to ``bytes`` before the facade
sees it, so it is always parsed as *content*, never mistaken for a path. Nothing
here writes to disk — agents supply content and get content back. Selection /
parse errors propagate as the facade's typed ``UnknownRuleset`` /
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
        ConvertHelpResult,
        DetectResult,
        FindReferencesResult,
        FormatResult,
        RenameParamResult,
        RuleInfo,
        RulesetInfo,
        TokenizeVersionResult,
        UpgradeResult,
    )
    from galaxy_tool_refactor_rules.violation import Violation


def _violation_to_dict(violation: Violation, /) -> dict[str, object]:
    """Serialise a Violation to a JSON-able dict for an agent.

    ``code`` is the **precise rule code**, including a partition sub-rule's dotted
    child code (``GTR020.1`` for the fix, ``GTR020.2`` for the advisory) — *not* the
    parent display code. Agents get the exact sub-rule so they can distinguish the
    fixable half from the advisory residual; the human CLI collapses both to the
    parent (``GTR020``) via ``display_code``. Intentional asymmetry (registry D10).
    """
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
        "baseline_profile": result.baseline_profile,
        "reached_profile": result.reached_profile,
        "steps_applied": list(result.steps_applied),
        "missing_upgrade": result.missing_upgrade,
        "behavior_preserving": result.behavior_preserving,
        "stopped_at": result.stopped_at,
        "blocking_codes": list(result.blocking_codes),
        "auto_fixed_codes": list(result.auto_fixed_codes),
        "advisory": [_violation_to_dict(v) for v in result.advisory],
        "notes": list(result.notes),
    }


def _convert_help_result_to_dict(result: ConvertHelpResult, /) -> dict[str, object]:
    return {
        "converted": result.converted,
        "formatted": result.formatted.decode("utf-8"),
        "skip_reason": result.skip_reason,
    }


def _tokenize_version_result_to_dict(
    result: TokenizeVersionResult, /
) -> dict[str, object]:
    return {
        "tokenized": result.tokenized,
        "formatted": result.formatted.decode("utf-8"),
        "skip_reason": result.skip_reason,
    }


def _detect_result_to_dict(result: DetectResult, /) -> dict[str, object]:
    return {
        "violations": [
            {**_violation_to_dict(v), "advisory": result.is_advisory(v)}
            for v in result.violations
        ],
        "advisory_codes": sorted(result.advisory_codes),
    }


def _find_references_result_to_dict(
    result: FindReferencesResult, /
) -> dict[str, object]:
    return {
        "name": result.name,
        "occurrences": [
            {
                "section": occ.section,
                "sourceline": occ.sourceline,
                "reference": occ.reference,
            }
            for occ in result.occurrences
        ],
    }


def _rename_param_result_to_dict(result: RenameParamResult, /) -> dict[str, object]:
    return {
        "old": result.old,
        "new": result.new,
        "changed": result.changed,
        "renamed": result.renamed,
        "reason": result.reason,
        "formatted": (
            result.formatted.decode("utf-8") if result.formatted is not None else None
        ),
    }


def _ruleset_info_to_dict(info: RulesetInfo, /) -> dict[str, object]:
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
        "rulesets": list(info.rulesets),
        "planemo_linters": list(info.planemo_linters),
        "since": info.since,
        "cite": info.cite,
    }


def format_tool(
    xml: str,
    /,
    *,
    rulesets: Sequence[str] = (),
    select: Sequence[str] = (),
    ignore: Sequence[str] = (),
) -> dict[str, object]:
    """Apply a ruleset's fixable rules then format; return the canonical XML + notes."""
    codes = resolve_codes(rulesets=rulesets, select=select, ignore=ignore)
    return _format_result_to_dict(facade.run(xml.encode("utf-8"), codes=codes))


def upgrade_tool(
    xml: str,
    /,
    *,
    select: Sequence[str] = (),
    ignore: Sequence[str] = (),
    modernize: bool = False,
    allow_behavior_change: bool = False,
    target_profile: str | None = None,
) -> dict[str, object]:
    """Repair then format; ``profile=`` moves only as far as strictly needed.

    Minimal bump by default: a tool that validates at its declared profile
    keeps it (an undeclared tool stays undeclared); an invalid one is bumped
    to the minimum valid profile at or above its baseline. *modernize* opts
    into the behaviour-gated walk toward the latest profile, capped by the
    lower of the behaviour ceiling (reported via the blocking codes) and the
    deployment ceiling (the newest profile every major public Galaxy server
    runs); *allow_behavior_change* lifts the behaviour gate only (requiring a
    walk mode, raising ``UpgradeFlagError`` otherwise); *target_profile* walks
    up to an explicit vendored profile (raising ``UnknownProfile`` otherwise),
    implying the walk mode by itself and exceeding the deployment ceiling when
    asked.
    """
    codes = resolve_upgrade_codes(select=select, ignore=ignore)
    return _upgrade_result_to_dict(
        facade.upgrade(
            xml.encode("utf-8"),
            codes=codes,
            modernize=modernize,
            allow_behavior_change=allow_behavior_change,
            target_profile=target_profile,
        )
    )


def check_tool(
    xml: str,
    /,
    *,
    rulesets: Sequence[str] = (),
    select: Sequence[str] = (),
    ignore: Sequence[str] = (),
) -> dict[str, object]:
    """Report-only detect over the selected rules; never mutates the tool."""
    codes = resolve_codes(rulesets=rulesets, select=select, ignore=ignore)
    return _detect_result_to_dict(facade.detect(xml.encode("utf-8"), codes=codes))


def convert_help_tool(xml: str, /) -> dict[str, object]:
    """Convert an RST ``<help>`` to Markdown when provable; else report why not.

    The opt-in GTR092 conversion (registry D18): profile >= 24.2 (the XSD gate —
    the skip reason says to run ``upgrade_tool`` first) + the tier-1
    render-equivalence gate. ``converted=False`` is a normal outcome, not an
    error; ``formatted`` then echoes the (serialised) unchanged tool.
    """
    return _convert_help_result_to_dict(facade.convert_help(xml.encode("utf-8")))


def tokenize_version_tool(xml: str, /) -> dict[str, object]:
    """Factor a literal version into @TOOL_VERSION@ tokens when provable (GTR094).

    The opt-in tokenization (registry D19): fail-closed preconditions plus the
    expansion-equality gate. ``tokenized=False`` is a normal outcome with the
    codemod's own ``skip_reason``. Content-based like every MCP tool, so a tool
    whose ``<macros>`` imports files fails closed (the gate cannot resolve
    imports without a source directory) — the skip reason says so; use the CLI
    ``tokenize-version`` (path-based) for those.
    """
    return _tokenize_version_result_to_dict(
        facade.tokenize_version(xml.encode("utf-8"))
    )


def find_references_tool(xml: str, /, *, name: str) -> dict[str, object]:
    """Every Cheetah ``$name`` reference site across the tool's templated sections.

    Read-only. Single-document like every MCP tool: it scans the sections of the
    provided tool (``<command>`` / inline ``<configfile>`` / attribute-Cheetah), so a
    reference that lives only in an *imported* macro file is not visible here — the
    bundle-aware, filesystem-walking view is the CLI ``find-references`` (path-based).
    """
    return _find_references_result_to_dict(
        facade.find_references(xml.encode("utf-8"), name=name)
    )


def rename_param_tool(xml: str, /, *, old: str, new: str) -> dict[str, object]:
    """Rename parameter *old* to *new* across the provided tool, atomically.

    The mutating sibling of ``find_references_tool``: rewrites every live ``$old``
    reference plus the definition, or changes nothing and reports ``reason`` (e.g.
    ``not-found`` / ``shadowed`` / ``lexer-bail``). ``formatted`` is the new XML on
    success and ``None`` on a bail. Content-based and single-document: the rename
    spans only the tool supplied — the cross-file rename across **imported macros**
    (with the sole-owned ``--repo-root`` gate) is the filesystem-aware CLI
    ``rename-param``, not available to a string-only call.
    """
    return _rename_param_result_to_dict(
        facade.rename_param(xml.encode("utf-8"), old=old, new=new)
    )


def list_rulesets() -> list[dict[str, object]]:
    """The baked-in rulesets (name / codes / is_default / description)."""
    return [_ruleset_info_to_dict(info) for info in facade.list_rulesets()]


def list_rules(*, include_upgrade: bool = False) -> list[dict[str, object]]:
    """The baked-in rules as JSON — every RuleInfo field (incl. cite)."""
    return [
        _rule_info_to_dict(info)
        for info in facade.list_rules(include_upgrade=include_upgrade)
    ]
