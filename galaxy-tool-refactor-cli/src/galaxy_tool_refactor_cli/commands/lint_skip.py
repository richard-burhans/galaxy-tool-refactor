"""The ``lint-skip`` subcommand: prune provably-resolved ``.lint_skip`` lines."""

from __future__ import annotations

from pathlib import Path

import click
from galaxy_tool_fmt.cli_support import is_tool_root, iter_targets, make_backup
from galaxy_tool_refactor_registry import facade
from galaxy_tool_refactor_registry.lint_skip import lint_skip_path, parse_lint_skip
from galaxy_tool_source.binding import ToolXmlSyntaxError, load_tool

from galaxy_tool_refactor_cli.options import _BACKUP_OPTION


@click.command(name="lint-skip")
@click.argument(
    "paths", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--check", is_flag=True, help="Report what would be removed and write nothing."
)
@_BACKUP_OPTION
def lint_skip_command(paths: tuple[Path, ...], check: bool, backup: bool) -> None:
    """Remove ``.lint_skip`` suppressions the toolchain can prove are resolved.

    A convenience for cleaning up planemo ``.lint_skip`` sidecars. For each tool
    directory under PATHS that carries a ``.lint_skip``, it applies the fixes the
    toolchain has and then deletes a suppression line **only when it can prove the
    line is no longer needed**: the planemo linter must be completely covered (every
    covering GTR rule is a faithful check-tier port or a canonical codemod) and clean
    on every tool in the directory after the fix. Anything it cannot fix, cannot
    prove, or does not cover is left untouched and unmentioned — the author suppressed
    it deliberately, and ``check`` reports the full picture. Like ``normalize-macros``
    and ``convert-help`` it rewrites files other than the one named (the tool XML and
    its ``.lint_skip``), so it is a deliberate, separate command — never part of
    ``format``/``upgrade`` (cli ``docs/decisions.md`` §D19).
    """
    skip_dirs = {
        target.parent
        for target in iter_targets(paths)
        if lint_skip_path(target).is_file()
    }
    removed_any = False
    for directory in sorted(skip_dirs):
        removed_any = _reconcile_one_lint_skip_dir(
            directory, check=check, backup=backup
        ) or removed_any
    if not removed_any:
        click.echo("no .lint_skip suppressions could be provably removed")
    elif check:
        raise SystemExit(1)


def _is_tool_file(path: Path) -> bool:
    """Whether *path* is a readable ``<tool>``-root XML file."""
    if not path.is_file():
        return False
    try:
        return is_tool_root(path.read_bytes())
    except OSError:
        return False


def _reconcile_one_lint_skip_dir(
    directory: Path, *, check: bool, backup: bool
) -> bool:
    """Reconcile one directory's ``.lint_skip``; return whether anything was removed.

    Loads **every** ``<tool>`` in the directory (the ``.lint_skip`` governs them
    all, so a line is removable only when clear for each), bails the whole
    directory if any tool fails to parse (we cannot prove dir-wide safety), and
    on success writes the fixed tools and the rewritten/deleted ``.lint_skip``.
    """
    sidecar = directory / ".lint_skip"
    tool_paths = sorted(p for p in directory.glob("*.xml") if _is_tool_file(p))
    documents = []
    for path in tool_paths:
        try:
            documents.append(load_tool(path))
        except ToolXmlSyntaxError as error:
            click.echo(
                f"skipped {sidecar}: {path.name} is malformed ({error})", err=True
            )
            return False
    if not documents:
        return False
    lines = parse_lint_skip(sidecar.read_text(encoding="utf-8"))
    result = facade.reconcile_lint_skip(documents, lines)
    if not result.removed:
        return False
    verb = "would remove" if check else "removed"
    for removal in result.removed:
        how = "fixed" if removal.fixed else "already clean"
        click.echo(
            f"{verb} from {sidecar}: {removal.name}"
            f" ({how}; {', '.join(removal.codes)})"
        )
    if not check:
        for path, formatted in zip(tool_paths, result.documents, strict=True):
            if formatted is not None:
                if backup:
                    make_backup(path)
                path.write_bytes(formatted)
        if backup:
            make_backup(sidecar)
        if result.file_emptied:
            sidecar.unlink()
        else:
            sidecar.write_text("\n".join(result.kept_lines) + "\n", encoding="utf-8")
    return True
