"""The ``tokenize-version`` subcommand: factor a literal version into tokens."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import click
from galaxy_tool_fmt.cli_support import is_tool_root, iter_targets, make_backup
from galaxy_tool_refactor_registry import facade

from galaxy_tool_refactor_cli.options import _BACKUP_OPTION


@click.command(name="tokenize-version")
@click.argument(
    "paths", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--check", is_flag=True, help="Report what would tokenize and write nothing."
)
@click.option(
    "--macros-file",
    default=None,
    metavar="NAME",
    help=(
        "Put the two tokens in a separate macros file NAME (e.g. macros.xml) the "
        "tool imports, instead of an inline <macros> block (the default). NAME is "
        "created when absent, or the tokens are merged into an existing NAME when "
        "proven not to change any other importer; tools in a directory that share "
        "NAME at the same version are tokenized together."
    ),
)
@click.option(
    "--adopt-suffix",
    is_flag=True,
    help=(
        "IDENTITY-CHANGING: for a tool whose bare version equals a package "
        "<requirement> but has no +galaxy suffix, ADD +galaxy0 and tokenize. This "
        "changes the published version (1.20 -> 1.20+galaxy0); use only when you are "
        "intentionally adopting the convention. Inline only; not combinable with "
        "--macros-file."
    ),
)
@_BACKUP_OPTION
def tokenize_version_command(
    paths: tuple[Path, ...],
    check: bool,
    macros_file: str | None,
    adopt_suffix: bool,
    backup: bool,
) -> None:
    """Factor a literal version into @TOOL_VERSION@/@VERSION_SUFFIX@ (opt-in, gated).

    Rewrites ``version="<base>+galaxy<suffix>"`` as
    ``@TOOL_VERSION@+galaxy@VERSION_SUFFIX@``, retargets the matching package
    ``<requirement>`` versions to ``@TOOL_VERSION@``, and defines the two
    tokens in the tool's inline ``<macros>`` (or, with ``--macros-file``, in a
    separate macros file the tool imports), only when *provable*: the
    expansion-equality gate keeps the change solely when macro-expanding the
    tokenized tool reproduces the original expansion byte-for-byte. Anything
    unprovable is skipped with the reason. A multi-element style restructure,
    which is why it is a deliberate, separate command, never part of
    ``format``/``upgrade``. Files are passed by path so imported macros resolve.

    ``--adopt-suffix`` is the **identity-changing** sibling: for a tool whose *bare*
    version equals a package requirement, it adds ``+galaxy0`` (so ``1.20`` becomes
    ``1.20+galaxy0``) and tokenizes. The published version changes, so it is opt-in and
    gated only on the controlled-change gate (the expansion changes solely in the
    version attribute).
    """
    if adopt_suffix and macros_file is not None:
        click.echo(
            "error: --adopt-suffix cannot be combined with --macros-file", err=True
        )
        raise SystemExit(1)
    if adopt_suffix:
        _run_adopt_suffix(paths, check=check, backup=backup)
        return
    if macros_file is not None:
        _run_tokenize_shared(paths, macros_file=macros_file, check=check, backup=backup)
        return
    tokenized = skipped = errored = 0
    for target in iter_targets(paths):
        try:
            original = target.read_bytes()
        except OSError as error:
            click.echo(f"error: cannot read {target}: {error}", err=True)
            errored += 1
            continue
        if not is_tool_root(original):
            continue
        # Pass the PATH (not bytes): the expansion gate resolves <import>ed
        # macro files against the tool's own directory.
        result = facade.tokenize_version(target)
        if result.tokenized:
            tokenized += 1
            if not check:
                if backup:
                    make_backup(target)
                target.write_bytes(result.formatted)
            verb = "would tokenize" if check else "tokenized"
            click.echo(f"{verb} {target}")
        else:
            skipped += 1
            click.echo(f"skipped {target}: {result.skip_reason}")
    click.echo(
        f"{tokenized} tokenized, {skipped} skipped"
        + (f", {errored} error(s)" if errored else "")
    )
    if errored:
        raise SystemExit(1)


def _run_adopt_suffix(
    paths: tuple[Path, ...], *, check: bool, backup: bool
) -> None:
    """``tokenize-version --adopt-suffix``: add +galaxy0 to a bare version, tokenize.

    Identity-changing (the published version changes), so each applied tool is
    reported loudly. Gated per tool by the controlled-change gate.
    """
    adopted = skipped = errored = 0
    for target in iter_targets(paths):
        try:
            original = target.read_bytes()
        except OSError as error:
            click.echo(f"error: cannot read {target}: {error}", err=True)
            errored += 1
            continue
        if not is_tool_root(original):
            continue
        result = facade.adopt_version_suffix(target)
        if result.tokenized:
            adopted += 1
            if not check:
                if backup:
                    make_backup(target)
                target.write_bytes(result.formatted)
            verb = "would adopt" if check else "adopted"
            click.echo(f"{verb} +galaxy0 in {target} (published version changed)")
        else:
            skipped += 1
            click.echo(f"skipped {target}: {result.skip_reason}")
    click.echo(
        f"{adopted} adopted, {skipped} skipped"
        + (f", {errored} error(s)" if errored else "")
    )
    if errored:
        raise SystemExit(1)


def _run_tokenize_shared(
    paths: tuple[Path, ...], *, macros_file: str, check: bool, backup: bool
) -> None:
    """``tokenize-version --macros-file``: group tools by directory, tokenize each set.

    Each directory's target tools that share ``macros_file`` at the same version are
    tokenized together (consensus), defining the shared tokens once. See
    ``galaxy_tool_refactor_registry.version_token_share``.
    """
    if "/" in macros_file or "\\" in macros_file or macros_file in {"", ".", ".."}:
        click.echo(
            f"error: --macros-file must be a plain filename, not {macros_file!r}",
            err=True,
        )
        raise SystemExit(1)
    groups: dict[Path, list[Path]] = defaultdict(list)
    errored = 0
    for target in iter_targets(paths):
        try:
            raw = target.read_bytes()
        except OSError as error:
            click.echo(f"error: cannot read {target}: {error}", err=True)
            errored += 1
            continue
        if is_tool_root(raw):
            groups[target.parent].append(target)
    tokenized = skipped = 0
    verb = "would tokenize" if check else "tokenized"
    for directory, tools in sorted(groups.items()):
        plan = facade.tokenize_version_shared(
            directory / macros_file, target_tools=tools
        )
        for tool_path, reason in plan.skipped:
            click.echo(f"skipped {tool_path}: {reason}")
            skipped += 1
        if not plan.tool_edits:
            unreported = len(tools) - len(plan.skipped)
            if plan.skip_reason is not None and unreported > 0:
                click.echo(f"skipped {directory} ({macros_file}): {plan.skip_reason}")
                skipped += unreported
            continue
        if not check:
            if plan.macros_content is not None:
                if not plan.macros_created and backup:
                    make_backup(plan.macros_path)
                plan.macros_path.write_bytes(plan.macros_content)
            for edit in plan.tool_edits:
                if backup:
                    make_backup(edit.path)
                edit.path.write_bytes(edit.content)
        file_note = f"{'created' if plan.macros_created else 'updated'} {macros_file}"
        for edit in plan.tool_edits:
            click.echo(f"{verb} {edit.path} (-> {file_note})")
        tokenized += len(plan.tool_edits)
    click.echo(
        f"{tokenized} tokenized, {skipped} skipped"
        + (f", {errored} error(s)" if errored else "")
    )
    if errored:
        raise SystemExit(1)
