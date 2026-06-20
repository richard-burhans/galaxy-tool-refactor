"""User-facing note-string builders for ``upgrade`` — pure formatting lifted out
of the library-first facade so the facade returns structured data and these
render it. dignified-python house rules.
"""

from __future__ import annotations

from datetime import date

from galaxy_tool_codemod.profile_semantics import ProfileUpgradeCode
from galaxy_tool_source.profiles import latest_profile
from packaging.version import Version

from galaxy_tool_refactor_registry import deployment


def _upgrade_summary(steps: tuple[str, ...], missing: str | None) -> str | None:
    """One-line summary of an ``UpgradeToLatest`` run, or ``None`` if it did nothing."""
    parts: list[str] = []
    if steps:
        parts.append("upgraded past " + ", ".join(steps))
    if missing is not None:
        parts.append(f"stalled at {missing} (no registered upgrade)")
    if not parts:
        return None
    return "  " + "; ".join(parts)


def _semantic_warning(
    baseline: str | None,
    target: str | None,
    *,
    crossed: list[ProfileUpgradeCode],
    residual: list[ProfileUpgradeCode],
) -> str | None:
    """Warn when the bump crosses runtime-behaviour the XSD can't verify.

    Profile upgrade is structurally sound but not behaviour-preserving (codemod
    ``docs/decisions.md`` §22): some bumps change runtime defaults. We surface
    the crossed boundaries for the user to review. *residual* is the applicable
    set minus the codes an auto-fix already cleared (a cleared code needs no
    review; it gets its own fixed-automatically note). ``None`` (no warning)
    when nothing applies after crediting the fixes.
    """
    if not residual:
        return None
    # The catalogue is profile-ascending, so first-seen dedup keeps release order.
    releases = ", ".join(dict.fromkeys(change.profile for change in residual))
    must_fix = sum(1 for change in residual if change.level == "must_fix")
    must_fix_note = f", {must_fix} must-fix" if must_fix else ""
    return (
        f"  profile {baseline}→{target}: {len(residual)} of {len(crossed)}"
        f" crossed Galaxy profile-behaviour change(s) apply to this tool"
        f"{must_fix_note} (releases {releases}); review against"
        " docs/profile_boundaries.md before relying on this upgrade."
    )


def _behavior_preserving_note(
    baseline: str | None,
    target: str | None,
    *,
    preserving: bool | None,
    crossed_any: bool,
) -> str | None:
    """The positive clean-pass note, or ``None`` when there is no story to tell.

    Emitted only when the bump actually crossed at least one catalogue boundary
    (*crossed_any*) and is behaviour-preserving, the affirmative complement of
    ``_semantic_warning``. A no-op upgrade (already at its target) is vacuously
    preserving but says nothing, and a bump that crosses an applicable,
    uncleared code is reported by the warning instead.
    """
    if not (crossed_any and preserving):
        return None
    return (
        f"  profile {baseline}→{target}: upgrade crosses no behaviour change that"
        " applies to this tool — behavior-preserving."
    )


def _behavior_stop_note(
    blockers: tuple[ProfileUpgradeCode, ...],
    *,
    stopped_at: str | None,
    walked: bool,
    target_profile: str | None,
) -> str | None:
    """The loud, actionable stop report for a gated walk, or ``None``.

    Covers the two gate outcomes: the walk capped at a profile below the
    latest (*walked*), and the declaration left in place entirely because no
    vendored profile predates the first blocker. Always names the blocking
    code, where to read about it, and the opt-out. Phrased per the Galaxy
    Community Code of Conduct: the tool is not "broken", it is not yet provably
    safe to upgrade further.
    """
    if not blockers:
        return None
    latest = latest_profile()
    if walked and (stopped_at is None or stopped_at == latest):
        return None
    codes = ", ".join(
        f"{change.code} ({change.level} at {change.profile})" for change in blockers
    )
    next_steps = (
        "see docs/profile_boundaries.md for what changes there and how to update"
        " the tool, or rerun with --allow-behavior-change to upgrade anyway"
    )
    if not walked:
        return (
            f"  profile upgrade left profile= unchanged: {codes} appl"
            f"{'y' if len(blockers) > 1 else 'ies'} to this tool and no vendored"
            f" profile predates the first change; {next_steps}."
        )
    requested = (
        f" The requested target {target_profile} lies past this boundary and"
        " also needs --allow-behavior-change."
        if target_profile is not None
        and Version(target_profile) > Version(str(stopped_at))
        else ""
    )
    return (
        f"  profile upgrade stopped at {stopped_at} (latest is {latest}):"
        f" {codes} appl{'y' if len(blockers) > 1 else 'ies'} to this tool and"
        f" cannot be fixed automatically yet; {next_steps}.{requested}"
    )


def _deployment_cap_note(*, cap: str, baseline: str | None) -> str:
    """The walk was capped by the deployment ceiling, not a behaviour code.

    Phrased per the Galaxy Community Code of Conduct: the cap is about where
    the tool can install today, not a problem with the tool.
    """
    snapshot = deployment.DEPLOYMENT_SNAPSHOT_DATE.isoformat()
    if baseline == cap and cap != deployment.DEPLOYMENT_CEILING:
        return (
            f"  profile walk capped at the declared baseline {cap}: it already"
            f" exceeds the deployment ceiling"
            f" {deployment.DEPLOYMENT_CEILING} (the newest profile every major"
            f" public Galaxy server runs; snapshot {snapshot}). Pass"
            " --target-profile to walk newer profiles."
        )
    return (
        f"  profile walk capped at {cap}, the deployment ceiling: the newest"
        f" profile every major public Galaxy server runs (snapshot {snapshot},"
        " docs/galaxy_server_versions.json). A newer declaration could not"
        " install on the lagging servers yet; pass --target-profile to upgrade"
        " past it deliberately."
    )


def _deployment_target_note(target: str, /) -> str | None:
    """An explicit target above the ceiling gets an informational note."""
    if Version(target) <= Version(deployment.DEPLOYMENT_CEILING):
        return None
    return (
        f"  note: the requested target {target} is newer than the deployment"
        f" ceiling {deployment.DEPLOYMENT_CEILING} (the newest profile every"
        f" major public Galaxy server runs; snapshot"
        f" {deployment.DEPLOYMENT_SNAPSHOT_DATE.isoformat()}), so the tool may"
        " not install everywhere yet."
    )


def _deployment_stale_note() -> str | None:
    """A re-poll suggestion when the vendored snapshot may lag a release."""
    if not deployment.snapshot_is_stale(today=date.today()):
        return None
    return (
        "  note: the deployment-ceiling snapshot is from"
        f" {deployment.DEPLOYMENT_SNAPSHOT_DATE.isoformat()} and may lag a"
        " Galaxy release; re-run `python -m scripts.poll_galaxy_servers` to"
        " refresh docs/galaxy_server_versions.json and update the vendored"
        " ceiling."
    )


def _is_profile_token(value: str | None, /) -> bool:
    """True when a ``profile=`` value is a Cheetah macro token (e.g. ``@PROFILE@``)."""
    return value is not None and value.startswith("@") and value.endswith("@")


def _minimal_outcome_note(
    *,
    declared: str | None,
    baseline: str | None,
    reached: str | None,
    unreachable: str | None,
) -> str | None:
    """The per-tool report for the minimal default: kept / bumped / unreachable.

    ``None`` for an unplaceable baseline (the unplaceable note covers that
    case). Phrased per the Galaxy Community Code of Conduct: an unreachable
    floor means the tool needs repairs a profile bump cannot make, not that the
    tool is "broken".
    """
    if baseline is None:
        return None
    if declared is None:
        return (
            "  no profile= declared: left undeclared (Galaxy runs the tool"
            f" under its {baseline} legacy defaults); rerun with --modernize"
            " to declare and upgrade a profile."
        )
    if _is_profile_token(declared):
        # The tool file's profile= is a macro token (e.g. @PROFILE@); its value
        # lives where the token is defined, so the token (not this per-tool line)
        # carries the real bump decision. Don't claim "kept / validates at its
        # declared profile" here, which misleads when the token is being bumped
        # (issue #262): the imported-@PROFILE@ phase reports its own line.
        return (
            f"  profile= is the macro token {declared}; its value is handled"
            " where the token is defined (inline by GTR007, or in the macros"
            " file when every importer agrees), not assessed per-tool here."
        )
    if unreachable is not None:
        return (
            "  profile= left unchanged: the tool does not validate at any"
            f" vendored profile at or above {baseline}, so no profile bump can"
            " make it valid; `galaxy-tool-source validate` shows what to fix"
            " first."
        )
    if reached == baseline:
        return (
            f"  profile {baseline} kept: the tool validates at its declared"
            " profile; rerun with --modernize to walk newer profiles."
        )
    return (
        f"  profile {baseline}→{reached}: bumped to the minimum profile the"
        " tool validates at after repair."
    )
