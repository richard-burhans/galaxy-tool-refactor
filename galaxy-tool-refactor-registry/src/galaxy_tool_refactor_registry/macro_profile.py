"""Consensus analysis for upgrading an imported ``@PROFILE@`` token (Phase 3b-1).

A tool whose ``profile="@TOKEN@"`` resolves to a token defined in an *imported*
macro file cannot be upgraded by editing the tool alone (that is the inline case,
handled by ``UpdateProfile``/GTR007). Editing the macro file's ``<token>`` value
is safe **only when every tool whose profile uses that token agrees on the same
target profile** — otherwise bumping the shared token would over-declare a
profile some importer does not validate at. This module computes that agreement;
the orchestration that performs the edit (or reports-and-skips) consumes it.

Two pieces, kept separate so the decision logic is pure and testable:

- ``profile_token_site`` reads one tool's ``ToolDocument`` and returns the
  imported-token *site* (the defining macro file, the token name, and the tool's
  newest-valid target), or ``None`` when the profile is not an imported token.
- ``plan_from_sites`` groups sites by the macro file they edit and decides, per
  file, whether the importers agree on a single target — pure, no I/O.

Editing the *defining* file works whether the token is in a directly-imported
file or deeper in the chain (we always edit where the token lives), so there is
no direct-vs-deeper split here — the corpus has no deeper cases anyway
(``scripts/measure.py macro-profile-ownership``). The shared-file safety is
carried entirely by the agreement check, not by a copy-on-write fork: the
ownership sweep found no shared file whose importers diverge, so an in-place
bump suffices and fork machinery is deferred until divergence has a consumer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from galaxy_tool_codemod import behavior_gate
from galaxy_tool_fmt.cli_support import make_backup
from galaxy_tool_fmt.format import format_macro_document
from galaxy_tool_source.binding import (
    load_macros,
    newest_valid_profile,
    oldest_valid_profile,
    validate_tool,
)
from galaxy_tool_source.macros import token_definitions
from galaxy_tool_source.profiles import is_newer_profile
from packaging.version import Version

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from galaxy_tool_source.document import ToolDocument


@dataclass(frozen=True)
class ProfileTokenSite:
    """One tool's use of a profile macro token defined in an imported file.

    Attributes:
        tool: The tool file declaring ``profile="@TOKEN@"``.
        macro_file: The macro file that *defines* the token (where the edit lands).
        token_name: The token name as written, e.g. ``"@PROFILE@"``.
        target: The newest profile the tool validates at, or ``None`` if it
            validates nowhere (then no safe target exists).
    """

    tool: Path
    macro_file: Path
    token_name: str
    target: str | None


@dataclass(frozen=True)
class ProfileTokenPlan:
    """The consensus decision for one imported macro file's profile token.

    Attributes:
        macro_file: The macro file whose ``<token>`` would be edited.
        token_name: The token name to rewrite.
        importers: The tool files whose profile uses this token (sorted).
        target: The agreed target profile to bump the token to, or ``None`` when
            the importers do not agree (then the orchestration reports-and-skips).
        agree: Whether every importer has a target and they are all identical.
    """

    macro_file: Path
    token_name: str
    importers: tuple[Path, ...]
    target: str | None
    agree: bool


def _minimal_target(document: ToolDocument, *, baseline: str) -> str | None:
    """The minimal-default target for one importer: keep, or the minimum bump.

    Mirrors the facade's minimal default: an importer that validates at the
    token's current value targets exactly that value (the bump-up-only apply
    then makes the plan a no-op), an invalid one targets the minimum vendored
    profile at or above it that validates, and an unplaceable baseline (or one
    nothing validates at or above) yields ``None`` — no safe target, so the
    group cannot agree.
    """
    if not behavior_gate.placeable_baseline(baseline):
        return None
    if validate_tool(document, profile=baseline).valid:
        return baseline
    return oldest_valid_profile(document, floor=baseline)


def _gated_target(
    document: ToolDocument, *, baseline: str, target_profile: str | None
) -> str | None:
    """The newest profile this importer may reach under the behaviour gate.

    Mirrors the facade's modernize walk: blockers cap the walk at the
    behaviour ceiling; an importer whose ceiling falls at (or below) its
    baseline keeps its current value (the bump becomes a no-op for it); an
    unplaceable baseline yields ``None`` (no safe target, so the group cannot
    agree). An explicit *target_profile* lowers the cap further, never raises
    it.
    """
    if not behavior_gate.placeable_baseline(baseline):
        return None
    blockers = behavior_gate.blocking_codes(document, baseline=baseline)
    ceiling = behavior_gate.behavior_ceiling(blockers)
    if behavior_gate.blocked_below_baseline(ceiling=ceiling, baseline=baseline):
        return baseline
    if target_profile is not None and (
        ceiling is None or Version(target_profile) < Version(ceiling)
    ):
        ceiling = target_profile
    return newest_valid_profile(document, ceiling=ceiling)


def profile_token_site(
    document: ToolDocument,
    /,
    *,
    modernize: bool = False,
    allow_behavior_change: bool = False,
    target_profile: str | None = None,
) -> ProfileTokenSite | None:
    """Return the imported-profile-token site for *document*, or ``None``.

    ``None`` covers a literal profile, no profile, an inline token (``UpdateProfile``
    handles those), an unresolved token, and an in-memory document with no
    ``source_path`` (imports cannot be resolved without a location on disk).

    The site's target follows the same mode policy as the facade's ``upgrade``
    (the token's value is the importer's runtime baseline): by default the
    minimal target (keep a valid importer's value, else the minimum valid
    profile at or above it); *modernize* or *target_profile* opts into the
    behaviour-gated walk, and *allow_behavior_change* lifts the gate, exactly
    as on the per-tool path (the caller validates the flag composition).
    """
    profile_raw = document.profile
    if profile_raw is None or "@" not in profile_raw:
        return None
    source_path = document.source_path
    if source_path is None:
        return None
    definition = next(
        (
            candidate
            for candidate in token_definitions(document)
            if candidate.name == profile_raw and candidate.source is not None
        ),
        None,
    )
    if definition is None or definition.source is None:
        return None  # inline (GTR007), or the token resolves nowhere
    if not (modernize or target_profile is not None):
        target = _minimal_target(document, baseline=definition.value)
    elif allow_behavior_change:
        target = newest_valid_profile(document, ceiling=target_profile)
    else:
        target = _gated_target(
            document, baseline=definition.value, target_profile=target_profile
        )
    return ProfileTokenSite(
        tool=source_path,
        macro_file=definition.source,
        token_name=profile_raw,
        target=target,
    )


@dataclass(frozen=True)
class MacroTokenEdit:
    """An applied (or, under preview, would-apply) macro-token profile bump."""

    macro_file: Path
    token_name: str
    old_value: str
    new_value: str
    importers: tuple[Path, ...]


@dataclass(frozen=True)
class MacroTokenSkip:
    """A shared macro token left untouched because its importers disagree."""

    macro_file: Path
    token_name: str
    importers: tuple[Path, ...]


@dataclass(frozen=True)
class MacroProfileResult:
    """Outcome of applying profile-token plans across a run.

    ``edits`` are the bumps performed (or, when ``write=False``, that would be);
    ``skips`` are no-consensus files reported and left alone. A plan whose token
    is already current (or ahead) is a silent no-op and appears in neither.
    """

    edits: tuple[MacroTokenEdit, ...]
    skips: tuple[MacroTokenSkip, ...]




def apply_profile_token_plans(
    plans: Iterable[ProfileTokenPlan], /, *, write: bool, backup: bool = False
) -> MacroProfileResult:
    """Bump each agreed macro file's profile token; report no-consensus skips.

    For an agreeing plan whose token is stale (older than the agreed target), the
    ``<token>`` text is rewritten to the target and — when *write* is true — the
    macro file is reserialised through ``format_macro_document`` and written back
    (copied to ``<file>.bak`` first when *backup*). Bump-up-only: a token already at
    (or newer than) the target is a no-op. A non-agreeing plan is recorded as a skip
    and never written.
    """
    edits: list[MacroTokenEdit] = []
    skips: list[MacroTokenSkip] = []
    for plan in plans:
        if not plan.agree or plan.target is None:
            skips.append(
                MacroTokenSkip(plan.macro_file, plan.token_name, plan.importers)
            )
            continue
        document = load_macros(plan.macro_file)
        token = document.root.find(f'token[@name="{plan.token_name}"]')
        if token is None:
            continue  # defensive: the defining file should carry the token
        current = (token.text or "").strip()
        if not is_newer_profile(plan.target, current):
            continue  # already current, or token ahead of validity — no-op
        if write:
            token.text = plan.target
            if backup:
                make_backup(plan.macro_file)
            plan.macro_file.write_bytes(format_macro_document(document))
        edits.append(
            MacroTokenEdit(
                macro_file=plan.macro_file,
                token_name=plan.token_name,
                old_value=current,
                new_value=plan.target,
                importers=plan.importers,
            )
        )
    return MacroProfileResult(edits=tuple(edits), skips=tuple(skips))


def plan_from_sites(sites: Iterable[ProfileTokenSite], /) -> list[ProfileTokenPlan]:
    """Group sites by (macro file, token) and decide per-file agreement.

    A group *agrees* when every importer has a non-``None`` target and they are
    all identical — only then is an in-place token bump safe for all of them.
    Plans are returned in a stable order (by macro-file path, then token name).
    """
    groups: dict[tuple[Path, str], list[ProfileTokenSite]] = {}
    for site in sites:
        groups.setdefault((site.macro_file, site.token_name), []).append(site)
    plans: list[ProfileTokenPlan] = []
    for (macro_file, token_name), group in sorted(
        groups.items(), key=lambda item: (str(item[0][0]), item[0][1])
    ):
        targets = {site.target for site in group}
        agree = None not in targets and len(targets) == 1
        plans.append(
            ProfileTokenPlan(
                macro_file=macro_file,
                token_name=token_name,
                importers=tuple(sorted((site.tool for site in group), key=str)),
                target=next(iter(targets)) if agree else None,
                agree=agree,
            )
        )
    return plans
