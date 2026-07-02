"""The behavior gate: how far an upgrade can walk while preserving behaviour.

The ``upgrade_vN`` walk (``upgrades.py``) is validity-gated, which is sound for
*structure* only (``docs/decisions.md`` §22). This module supplies the missing
behavioural half: given a tool and its pre-upgrade baseline, compute the Galaxy
behaviour codes (``profile_semantics.PROFILE_UPGRADE_CODES``) that would survive
an upgrade-to-latest as genuine blockers, and the **ceiling**: the newest
vendored profile the tool can reach without crossing any of them.

A crossed code stops being a blocker in exactly two ways, both proofs:

- its per-tool detector does not fire (``tripped_upgrade_codes``; the construct
  is absent, so the tool is free to move past it; §23), or
- its mapped auto-fix (``RuntimeGatedFix.upgrade_code``) clears it **by
  execution**: the fix is applied to a throwaway copy and the detector re-run;
  only a detector that goes quiet counts. Never a static "fixable codes" set:
  GTR015 fixes only the sole-data-input subset and GTR016 only bucket A, and a
  macro-supplied construct (which the raw-tree codemod cannot reach) must stay a
  blocker.

The gate is pure and precomputable: every catalogue code is keyed to a fixed
profile boundary and detection is a property of the pre-upgrade tree, so the
ceiling is decided before the walk starts (no per-step re-evaluation needed).
Policy (which severity levels block, and the default flip) lives in the
tier-3.6 facade; this module is the mechanism. The corpus measure
(``scripts.measure upgrade-behavior-blocks``) consumes these same functions, so
the shipped gate and the published statistics cannot drift.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from galaxy_tool_source.document import ToolDocument
from galaxy_tool_source.macros import token_definitions
from galaxy_tool_source.profiles import available_profiles, latest_profile
from lxml import etree
from packaging.version import Version

from galaxy_tool_codemod._version import version_or_none
from galaxy_tool_codemod.module import Module
from galaxy_tool_codemod.profile_semantics import (
    ProfileUpgradeCode,
    tripped_upgrade_codes,
    upgrade_codes_crossed,
)
from galaxy_tool_codemod.runtime_fixes import RUNTIME_GATED_FIXES

if TYPE_CHECKING:
    from galaxy_tool_codemod.codemods._runtime_gated import RuntimeGatedFix

# The default blocking policy: stop only at codes Galaxy marks must_fix (the
# tool breaks or changes output). Applicable consider-level codes are surfaced
# as warnings by the facade but do not stop the walk; blocking on them would
# freeze nearly every tool at its baseline, because Galaxy emits one consider
# code unconditionally (16_04_consider_implicit_extra_file_collection; see
# docs/upgrade_behavior_block_stats.md). The strict policy below also blocks
# on consider — the facade's opt-in ``block_consider`` mode (registry D28);
# ``levels`` on ``blocking_codes`` stays the seam, the policy choice lives in
# the facade.
DEFAULT_BLOCKING_LEVELS: frozenset[str] = frozenset({"must_fix"})
STRICT_BLOCKING_LEVELS: frozenset[str] = frozenset({"must_fix", "consider"})


def auto_fixes_by_code() -> dict[str, type[RuntimeGatedFix]]:
    """Map each Galaxy behaviour code to the runtime-gated fix that clears it.

    Derived from ``RUNTIME_GATED_FIXES``, the single source of truth for what
    the toolchain can auto-fix (the measure consumes this too, so the shipped
    gate and the published statistics agree by construction).
    """
    return {fix.upgrade_code: fix for fix in RUNTIME_GATED_FIXES}


def code_cleared_by_autofix(
    document: ToolDocument, *, fix: type[RuntimeGatedFix], code: str
) -> bool:
    """Whether *fix* provably clears *code* for this tool: proof by execution.

    Applies *fix* to a deep copy of the document's tree (the caller's tree is
    never touched) and re-runs detection on the result through the same
    macro-expanded view the live ``tripped`` set uses, preserving the source
    path so ``<import>``s resolve. The code is cleared iff its detector no
    longer fires. A construct supplied by an imported macro stays a blocker:
    the raw-tree fix cannot reach it, so the expanded re-detection still sees it.
    """
    copied_root = copy.deepcopy(document.root)
    probe = ToolDocument(
        etree.ElementTree(copied_root), source_path=document.source_path
    )
    fix().apply(Module(probe))
    return code not in tripped_upgrade_codes(probe)


def blocking_codes(
    document: ToolDocument,
    /,
    *,
    baseline: str,
    levels: frozenset[str] = DEFAULT_BLOCKING_LEVELS,
) -> tuple[ProfileUpgradeCode, ...]:
    """The behaviour codes that genuinely block this tool's walk to latest.

    A code blocks when it is crossed over ``(baseline, latest]``, its severity
    is in *levels*, its per-tool detector fires (on the macro-expanded view),
    and its auto-fix, if one exists, fails to clear it by execution. The
    result preserves catalogue (profile) order.

    An unparseable *baseline* (e.g. a ``@PROFILE@`` macro token) cannot range
    the bump, so nothing is reported crossed; the caller is responsible for
    failing closed on unplaceable baselines (the facade does).
    """
    crossed = upgrade_codes_crossed(from_profile=baseline, to_profile=latest_profile())
    candidates = [change for change in crossed if change.level in levels]
    if not candidates:
        return ()
    tripped = tripped_upgrade_codes(document)
    applicable = [change for change in candidates if change.code in tripped]
    if not applicable:
        return ()
    fixes = auto_fixes_by_code()
    return tuple(
        change
        for change in applicable
        if change.code not in fixes
        or not code_cleared_by_autofix(
            document, fix=fixes[change.code], code=change.code
        )
    )


def behavior_ceiling(blockers: tuple[ProfileUpgradeCode, ...], /) -> str | None:
    """The newest vendored profile reachable without crossing any of *blockers*.

    ``latest_profile()`` when there are none. Otherwise the newest
    ``available_profiles()`` entry strictly below the lowest blocker's profile;
    declaring that version crosses none of the blocked boundaries. ``None`` when
    no vendored profile lies below the lowest blocker (e.g. an unfixable 16.04
    code on a legacy-default baseline: the oldest vendored profile is 16.10, so
    even declaring it would cross 16.04; the tool's profile must not move).
    """
    if not blockers:
        return latest_profile()
    first = min(Version(change.profile) for change in blockers)
    below = [
        profile for profile in available_profiles() if Version(profile) < first
    ]
    if not below:
        return None
    return max(below, key=Version)


def resolved_baseline(document: ToolDocument, /) -> str | None:
    """The runtime-behaviour baseline an upgrade is measured against.

    A missing ``profile=`` runs under Galaxy's ``16.01`` default, so that is
    the baseline. A declared literal version is itself. A ``@TOKEN@``
    declaration is resolved through the tool's token definitions (inline, then
    imported macro files); ``None`` when no definition resolves it, in which
    case callers fail closed (crossing boundaries they cannot place would void
    the guarantee).
    """
    declared = document.profile
    if declared is None:
        return "16.01"
    if "@" not in declared:
        return declared
    for definition in token_definitions(document):
        if definition.name == declared:
            return definition.value
    return None


def placeable_baseline(baseline: str | None, /) -> bool:
    """Whether *baseline* is a version the gate can place boundaries against.

    ``False`` for ``None`` and for unparseable values (e.g. an unresolved
    ``@PROFILE@`` macro token). The facade fails closed on an unplaceable
    baseline: crossing boundaries it cannot place would void the guarantee.
    """
    return baseline is not None and version_or_none(baseline) is not None


def blocked_below_baseline(*, ceiling: str | None, baseline: str) -> bool:
    """Whether *ceiling* would take the tool *backwards* from *baseline*.

    The gate never lowers a declared profile: a tool already at or above the
    ceiling keeps its declaration (the blockers were crossed when its author
    declared that profile, which is not this upgrade's doing). ``True`` when
    the ceiling is ``None`` or strictly below a parseable baseline.
    """
    if ceiling is None:
        return True
    baseline_version = version_or_none(baseline)
    return baseline_version is not None and Version(ceiling) < baseline_version
