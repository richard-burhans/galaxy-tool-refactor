"""The ``bump-version-suffix`` subcommand: bump the ``+galaxy<N>`` revision suffix."""

from __future__ import annotations

from pathlib import Path

import click
from galaxy_tool_fmt.cli_support import is_tool_root, iter_targets, make_backup
from galaxy_tool_refactor_registry import facade

from galaxy_tool_refactor_cli.options import _BACKUP_OPTION, _CHECK_OPTION


@click.command(name="bump-version-suffix")
@click.argument(
    "paths", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--scope",
    type=click.Choice(["per-tool", "suite"]),
    default="suite",
    show_default=True,
    help=(
        "How to bump a suffix held in an IMPORTED macros file. 'suite' (default) "
        "bumps the shared @VERSION_SUFFIX@ token once, moving every importer in "
        "lockstep; 'per-tool' declines a shared bump and reports it instead."
    ),
)
@_CHECK_OPTION
@_BACKUP_OPTION
def bump_version_suffix_command(
    paths: tuple[Path, ...], scope: str, check: bool, backup: bool
) -> None:
    """Bump a tool's +galaxy<N> revision suffix by one (opt-in, IDENTITY-CHANGING).

    Rewrites ``+galaxy7`` to ``+galaxy8`` (and so on): the integer Galaxy revision
    suffix a published tool must bump whenever its content changes. This **changes the
    tool's published version**, so it is author-invoked and never detects whether the
    content actually changed — like ``tokenize-version --adopt-suffix``. It has no GTR
    code and is in no ruleset; it is never part of ``format``/``upgrade``.

    A literal ``version="...+galaxy<N>"`` and an inline ``@VERSION_SUFFIX@`` token are
    bumped in the tool itself. When the suffix lives in an *imported* macros file the
    bump moves every importer at once: ``--scope suite`` (the default) bumps the shared
    token once behind a proof-by-execution gate and lists the tools it lifts;
    ``--scope per-tool`` declines and tells you to rerun with ``--scope suite``. Files
    are passed by path so imported macros resolve.
    """
    bumped = skipped = errored = 0
    for target in iter_targets(paths):
        try:
            original = target.read_bytes()
        except OSError as error:
            click.echo(f"error: cannot read {target}: {error}", err=True)
            errored += 1
            continue
        if not is_tool_root(original):
            continue
        # Preview first (no write): so backups of the tool AND any shared macros file
        # can be taken before the facade rewrites them.
        preview = facade.bump_version_suffix(target, scope=scope)
        if not preview.bumped:
            skipped += 1
            click.echo(f"skipped {target}: {preview.skip_reason}")
            continue
        bumped += 1
        if not check:
            if backup:
                make_backup(target)
                for affected in preview.affected_paths:
                    make_backup(affected)
            facade.bump_version_suffix(target, scope=scope, write_path=target)
        verb = "would bump" if check else "bumped"
        if preview.affected_importers:
            others = sorted(
                str(path) for path in preview.affected_importers if path != target
            )
            others_note = f" (also lifts {', '.join(others)})" if others else ""
            click.echo(
                f"{verb} {target} via {preview.affected_paths[0]}"
                f" (published revision changed){others_note}"
            )
        else:
            click.echo(
                f"{verb} {target} to {preview.new_version}"
                " (published revision changed)"
            )
    click.echo(
        f"{bumped} bumped, {skipped} skipped"
        + (f", {errored} error(s)" if errored else "")
    )
    if errored:
        raise SystemExit(1)
