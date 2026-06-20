"""The ``rename-param`` subcommand: the mutating sibling of ``find-references``."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

import click
from galaxy_tool_fmt.cli_support import is_tool_root, iter_targets
from galaxy_tool_refactor_registry.bundle_rename import (
    BundleRenameResult,
    ConsensusRenameResult,
    build_importer_map,
    rename_param_bundle,
    rename_param_consensus,
)
from galaxy_tool_source.binding import ToolXmlSyntaxError

from galaxy_tool_refactor_cli.options import (
    _ACROSS_IMPORTERS_OPTION,
    _BACKUP_OPTION,
    _CHECK_OPTION,
    _PATH_ARGUMENT,
    _QUIET_OPTION,
    _REPO_ROOT_OPTION,
)


def _report_rename_skip(
    result: BundleRenameResult, target: Path, *, quiet: bool
) -> None:
    """Print an informative skip line for a non-applied rename.

    ``not-found`` is the common case (the tool has no such param) — it stays silent.
    """
    if result.reason == "not-found" or quiet:
        return
    if result.reason == "macro-edit-needs-repo-root":
        click.echo(
            f"skip {target}: '{result.old}' is referenced in an imported macro; "
            "rerun with --repo-root DIR to prove the macro is sole-owned"
        )
        return
    if result.reason == "macro-ownership-unprovable":
        names = ", ".join(str(macro) for macro in result.unprovable)
        click.echo(
            f"skip {target}: cannot prove macro file(s) {names} are sole-owned within "
            f"--repo-root (is {target} under the given --repo-root?)"
        )
        return
    if result.reason == "shared-macro":
        names = ", ".join(str(skip.macro_file) for skip in result.shared)
        click.echo(
            f"skip {target}: '{result.old}' is referenced in shared macro file(s) "
            f"{names}; editing them would affect other tools (rename not applied)"
        )
        for skip in result.shared:
            others = ", ".join(str(path) for path in skip.other_importers)
            click.echo(f"    {skip.macro_file} also imported by: {others}")
        return
    click.echo(f"skip {target}: {result.reason}")


def _report_consensus_skip(
    result: ConsensusRenameResult, target: Path, *, quiet: bool
) -> None:
    """Print an informative skip line for a non-applied consensus rename."""
    if result.reason == "not-found" or quiet:
        return
    if result.reason == "no-consensus":
        click.echo(
            f"skip {target}: cannot rename '{result.old}' across importers — "
            "these tools cannot rename it safely:"
        )
        for tool, reason in result.dissenting:
            click.echo(f"    {tool}: {reason}")
        return
    if result.reason == "macro-ownership-unprovable":
        click.echo(
            f"skip {target}: a shared macro is not covered by --repo-root; "
            "point --repo-root at the repository that holds every importer"
        )
        return
    click.echo(f"skip {target}: {result.reason}")


def _run_consensus_rename(
    paths: tuple[Path, ...],
    *,
    old: str,
    new: str,
    importers: Mapping[Path, frozenset[Path]],
    check: bool,
    backup: bool,
    quiet: bool,
) -> tuple[int, int, int, int]:
    """Run the lockstep across-importers rename.

    Returns the ``(renamed, would_change, skipped, errored)`` counts.
    """
    processed: set[Path] = set()
    renamed = would_change = skipped = errored = 0
    for target in iter_targets(paths):
        try:
            original = target.read_bytes()
        except OSError as error:
            click.echo(f"error: cannot read {target}: {error}", err=True)
            errored += 1
            continue
        if not is_tool_root(original):
            skipped += 1
            continue
        if target.resolve() in processed:
            continue  # already rewritten as part of an earlier consensus group
        try:
            result = rename_param_consensus(
                target, old=old, new=new, importers=importers,
                write=not check, backup=backup,
            )
        except ToolXmlSyntaxError as error:
            click.echo(f"error: {target}: malformed XML: {error}", err=True)
            errored += 1
            continue
        processed.add(target.resolve())
        processed.update(result.tools)
        if not result.changed:
            _report_consensus_skip(result, target, quiet=quiet)
            skipped += 1
            continue
        sites = sum(edit.renamed for edit in result.edits)
        summary = (
            f"{len(result.tools)} tool(s), {len(result.edits)} file(s), {sites} site(s)"
        )
        if check:
            would_change += 1
            if not quiet:
                click.echo(f"would rename across importers from {target}: {summary}")
        else:
            renamed += 1
            if not quiet:
                click.echo(f"renamed across importers from {target}: {summary}")
    return renamed, would_change, skipped, errored


@click.command(name="rename-param")
@click.argument("old")
@click.argument("new")
@_PATH_ARGUMENT
@_REPO_ROOT_OPTION
@_ACROSS_IMPORTERS_OPTION
@_CHECK_OPTION
@_BACKUP_OPTION
@_QUIET_OPTION
def rename_param_command(
    old: str,
    new: str,
    paths: tuple[Path, ...],
    repo_root: Path | None,
    across_importers: bool,
    check: bool,
    backup: bool,
    quiet: bool,
) -> None:
    """Rename parameter OLD to NEW across a tool **and its imported macro files**.

    The mutating sibling of ``find-references``. Rewrites every live ``$OLD`` reference
    (``<command>`` / inline ``<configfile>`` via the faithful lexer, attribute-Cheetah,
    by-name cross-reference attributes, and the ``<tests>`` mirrors) plus the
    definition — across the tool **and every macro file it imports**, so a reference
    that lives only in an imported macro is no longer left dangling.

    Rename is **atomic across the bundle**: every member is rewritten or none is. A
    tool is skipped with a reason when the rename cannot be proven safe (e.g. a ``#set``
    local shadows OLD, a section is mixed-content, or an output ``<filter>`` references
    OLD by bare Python name). Editing an imported macro
    requires ``--repo-root`` to prove the macro is **sole-owned** (imported by no other
    tool); a macro **shared** with another tool is reported and the rename is skipped —
    unless ``--across-importers`` is given, which renames OLD across *every* importer of
    the shared macro in lockstep (only when they all agree). PATHS may be files or
    directories; non-tool XML is skipped. ``--check`` previews without writing and exits
    non-zero if any file would change.
    """
    if not old.isidentifier() or not new.isidentifier():
        raise click.BadParameter("OLD and NEW must be valid identifiers")
    if across_importers:
        if repo_root is None:
            raise click.BadParameter(
                "--across-importers requires --repo-root to find every importer",
                param_hint="--across-importers",
            )
        renamed, would_change, skipped, errored = _run_consensus_rename(
            paths, old=old, new=new, importers=build_importer_map(repo_root),
            check=check, backup=backup, quiet=quiet,
        )
        if not quiet:
            done = would_change if check else renamed
            verb = "would rename" if check else "renamed"
            click.echo(f"{verb} {done} consensus group(s); skipped {skipped}")
        sys.exit(1 if errored or (check and would_change) else 0)
    importers = build_importer_map(repo_root) if repo_root is not None else None
    renamed = would_change = skipped = errored = 0
    for target in iter_targets(paths):
        try:
            original = target.read_bytes()
        except OSError as error:
            click.echo(f"error: cannot read {target}: {error}", err=True)
            errored += 1
            continue
        if not is_tool_root(original):
            skipped += 1
            continue
        try:
            result = rename_param_bundle(
                target,
                old=old,
                new=new,
                importers=importers,
                write=not check,
                backup=backup,
            )
        except ToolXmlSyntaxError as error:
            click.echo(f"error: {target}: malformed XML: {error}", err=True)
            errored += 1
            continue
        if not result.changed:
            _report_rename_skip(result, target, quiet=quiet)
            skipped += 1
            continue
        sites = sum(edit.renamed for edit in result.edits)
        files = len(result.edits)
        if check:
            would_change += 1
            if not quiet:
                click.echo(
                    f"would rename {target}: {sites} site(s) across {files} file(s)"
                )
            continue
        renamed += 1
        if not quiet:
            click.echo(f"renamed {target}: {sites} site(s) across {files} file(s)")
    if not quiet:
        done = would_change if check else renamed
        verb = "would rename" if check else "renamed"
        click.echo(f"{verb} {done} tool(s); skipped {skipped}")
    sys.exit(1 if errored or (check and would_change) else 0)
