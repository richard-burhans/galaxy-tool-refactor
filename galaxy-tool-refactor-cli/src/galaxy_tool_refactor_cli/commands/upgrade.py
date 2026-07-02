"""The ``upgrade`` subcommand: repair, profile placement, then format."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from galaxy_tool_fmt.cli_support import (
    Action,
    RunOptions,
    TransformOutcome,
    is_tool_root,
    iter_targets,
    run,
)
from galaxy_tool_refactor_registry import facade
from galaxy_tool_refactor_registry.errors import (
    UnknownProfile,
    UpgradeFlagConflict,
    UpgradeFlagError,
)
from galaxy_tool_refactor_registry.macro_profile import (
    apply_profile_token_plans,
    plan_from_sites,
    profile_token_site,
)
from galaxy_tool_source.binding import ToolXmlSyntaxError, load_tool
from galaxy_tool_source.document import ToolDocument
from galaxy_tool_source.profiles import available_profiles, latest_profile

from galaxy_tool_refactor_cli.options import (
    _BACKUP_OPTION,
    _CHECK_OPTION,
    _DIFF_OPTION,
    _IGNORE_OPTION,
    _PATH_ARGUMENT,
    _QUIET_OPTION,
    _RULESET_OPTION,
    _SELECT_OPTION,
    _resolve_upgrade,
)


@click.command(name="upgrade")
@_PATH_ARGUMENT
@_CHECK_OPTION
@_DIFF_OPTION
@_QUIET_OPTION
@_BACKUP_OPTION
@_RULESET_OPTION
@_SELECT_OPTION
@_IGNORE_OPTION
@click.option(
    "--modernize",
    is_flag=True,
    help=(
        "Walk profile= toward the latest profile (capped at the lower of the"
        " behaviour ceiling and the deployment ceiling, the newest profile"
        " every major public Galaxy server runs) instead of the default"
        " minimal bump, which moves profile= only as far as validity strictly"
        " requires."
    ),
)
@click.option(
    "--allow-behavior-change",
    is_flag=True,
    help=(
        "Let the --modernize / --target-profile walk cross Galaxy behaviour"
        " changes that apply to the tool. Requires one of those flags: the"
        " default minimal bump has no gated walk to lift. Lifts the behaviour"
        " gate only; exceeding the deployment ceiling takes an explicit"
        " --target-profile."
    ),
)
@click.option(
    "--block-consider",
    is_flag=True,
    help=(
        "Tighten the --modernize / --target-profile walk's behaviour gate to"
        " also stop at applicable consider-level Galaxy changes (by default"
        " they warn but do not stop). Requires one of those flags and cannot"
        " be combined with --allow-behavior-change. A review-everything mode:"
        " Galaxy emits one consider change unconditionally at 16.04, so most"
        " low-baseline tools stop immediately."
    ),
)
@click.option(
    "--target-profile",
    default=None,
    metavar="PROFILE",
    help=(
        "Walk the upgrade up to this vendored Galaxy profile (e.g. 23.0);"
        " implies the walk mode. Composes with the behaviour gate (the lower"
        " of the two wins) and, being deliberate, may exceed the deployment"
        " ceiling (a note still mentions it)."
    ),
)
def upgrade_command(
    paths: tuple[Path, ...],
    check: bool,
    diff: bool,
    quiet: bool,
    backup: bool,
    rulesets: tuple[str, ...],
    select: tuple[str, ...],
    ignore: tuple[str, ...],
    modernize: bool,
    allow_behavior_change: bool,
    block_consider: bool,
    target_profile: str | None,
) -> None:
    """Repair tools, moving ``profile=`` only as far as strictly needed.

    Opt-in and semantic. The profile repair always runs; ``--select`` / ``--ignore``
    adjust the *other* fixable rules (by default typo repair + cosmetic
    formatting) — e.g. ``--ignore GTR006`` upgrades without typo repair. Rulesets
    are a ``format``/``check`` concept and are **not** accepted here.

    **Minimal bump by default.** A tool that validates at its declared
    ``profile=`` (after repair) keeps it, and an undeclared tool stays
    undeclared; only a tool that does not validate where it sits has its
    declaration moved — to the *minimum* vendored profile at or above its
    baseline that validates, no further. Galaxy servers lag the newest
    profile, so a gratuitous bump would only narrow where a tool can install.

    **--modernize** opts into the behaviour-gated walk toward the latest
    profile, capped by the lower of two ceilings: the behaviour ceiling, the
    newest vendored profile reachable without crossing a Galaxy ``must_fix``
    behaviour change that applies to this tool and that no bundled fix
    provably clears (a fix is credited only when re-detection proves the
    construct gone), and the deployment ceiling, the newest profile every
    major public Galaxy server runs (a newer declaration could not install
    everywhere yet; vendored from the committed server-poll snapshot). A stop
    is reported with the blocking code(s) and where to read about them
    (``docs/profile_boundaries.md``), or with the deployment cap. Applicable
    consider-level changes are warned about but do not stop the walk unless
    ``--block-consider`` opts into stopping at them too.
    ``--target-profile`` walks up to an explicit vendored profile (implying
    the walk mode by itself), composes with the behaviour gate (the lower
    wins), and may exceed the deployment ceiling deliberately;
    ``--allow-behavior-change`` lifts the behaviour gate only and requires
    one of the walk flags (``--block-consider`` likewise, and the two cannot
    be combined).

    A ``profile="@PROFILE@"`` whose token lives in an *imported* macro file is
    handled by editing that token in place — but only when every profile-using
    importer in this run agrees on the target profile; a macro file whose
    importers disagree is reported and left untouched (no over-declaration).
    Each importer's target honors the same mode and flags (under the default,
    a token its importers validate at is left alone). The inline-token case is
    handled per-file by GTR007. The token value is the *only* semantic edit,
    but the macro file it lives in **is** reserialised through fmt's
    ``format_macro_document`` when the token is bumped (so a bumped file is
    also cosmetically normalised — GTR001/GTR004); ``upgrade`` runs no
    *separate* cosmetic macro pass over un-bumped macro files the way
    ``format`` does. PATHS may be files or directories.

    Bumping ``profile=`` opts the tool into newer Galaxy runtime defaults the
    XSD can't verify; that is exactly what the gate guards on the walk. A few
    of those changes have a safe mechanical fix that is **applied
    automatically** once the reached profile crosses them (e.g. stripping
    whitespace from ``from_work_dir`` at 21.09); the rest stop the walk
    (``must_fix``) or are warn-only (``consider``). A tool kept at its
    baseline crosses nothing, so no such fix applies to it.
    """
    if rulesets:
        raise click.BadParameter(
            "--ruleset is not applicable to 'upgrade'; rulesets govern "
            "'format' / 'check'. Use --select / --ignore to adjust the rule set.",
            param_hint="--ruleset",
        )
    if block_consider and allow_behavior_change:
        raise click.BadParameter(
            str(UpgradeFlagConflict()), param_hint="--block-consider"
        )
    if allow_behavior_change and not (modernize or target_profile is not None):
        raise click.BadParameter(
            str(UpgradeFlagError()), param_hint="--allow-behavior-change"
        )
    if block_consider and not (modernize or target_profile is not None):
        raise click.BadParameter(
            str(UpgradeFlagError("block_consider")), param_hint="--block-consider"
        )
    if target_profile is not None and target_profile not in available_profiles():
        profiles = available_profiles()
        raise click.BadParameter(
            str(
                UnknownProfile(
                    target_profile, oldest=profiles[0], latest=latest_profile()
                )
            ),
            param_hint="--target-profile",
        )
    codes = _resolve_upgrade(select=select, ignore=ignore)

    # Whole-run phase first: bump imported @PROFILE@ tokens where every
    # profile-using importer agrees on the target (the inline case is handled
    # per-file by GTR007 in the transform below). This edits *macro* files, so it
    # cannot ride the per-file tool transform.
    macro_pending = _upgrade_macro_profile_tokens(
        paths,
        check=check,
        diff=diff,
        quiet=quiet,
        backup=backup,
        modernize=modernize,
        allow_behavior_change=allow_behavior_change,
        block_consider=block_consider,
        target_profile=target_profile,
    )

    def transform(document: ToolDocument) -> TransformOutcome:
        result = facade.upgrade(
            document,
            codes=codes,
            modernize=modernize,
            allow_behavior_change=allow_behavior_change,
            block_consider=block_consider,
            target_profile=target_profile,
        )
        return TransformOutcome(result.formatted, notes=result.notes)

    exit_code = run(
        paths,
        transform=transform,
        action=Action(past="upgraded", conditional="would upgrade"),
        options=RunOptions(check=check, diff=diff, quiet=quiet, backup=backup),
    )
    # A pending macro-token bump is a "would change" under either preview mode
    # (--check or --diff), so both must surface it in the exit code (cli D6).
    sys.exit(exit_code or (1 if ((check or diff) and macro_pending) else 0))


def _upgrade_macro_profile_tokens(
    paths: tuple[Path, ...],
    *,
    check: bool,
    diff: bool,
    quiet: bool,
    backup: bool,
    modernize: bool = False,
    allow_behavior_change: bool = False,
    block_consider: bool = False,
    target_profile: str | None = None,
) -> bool:
    """Upgrade imported ``@PROFILE@`` tokens across the run; return would-edit.

    Walks the run's tool files, collects each one's imported-profile-token site
    (each importer's target honors the mode and flags exactly as the per-tool
    path does: minimal by default, the behaviour-gated walk under
    ``--modernize`` / ``--target-profile``), and for every macro file whose
    profile-using importers agree on a target bumps the ``<token>`` in place
    (writing unless ``check``/``diff``). A macro file whose importers disagree
    is reported and left untouched. Returns whether any macro file was (or,
    under preview, would be) edited; the caller folds that into the
    ``--check`` exit code.
    """
    sites = []
    for path in iter_targets(paths):
        try:
            original = path.read_bytes()
        except OSError:
            continue
        if not is_tool_root(original):
            continue
        try:
            document = load_tool(path)  # load from path so imports resolve
        except ToolXmlSyntaxError:
            continue  # malformed tools are surfaced by the per-file run() below
        site = profile_token_site(
            document,
            modernize=modernize,
            allow_behavior_change=allow_behavior_change,
            block_consider=block_consider,
            target_profile=target_profile,
        )
        if site is not None:
            sites.append(site)
    plans = plan_from_sites(sites)
    result = apply_profile_token_plans(
        plans, write=not (check or diff), backup=backup
    )
    if not quiet:
        verb = "would upgrade" if (check or diff) else "upgraded"
        for edit in result.edits:
            click.echo(
                f"{verb} {edit.token_name} {edit.old_value} -> {edit.new_value} "
                f"in {edit.macro_file} ({len(edit.importers)} tool(s))"
            )
        for skip in result.skips:
            click.echo(
                f"skipped {skip.macro_file}: {skip.token_name} importers disagree "
                f"on target profile ({len(skip.importers)} tool(s))"
            )
    return bool(result.edits)
