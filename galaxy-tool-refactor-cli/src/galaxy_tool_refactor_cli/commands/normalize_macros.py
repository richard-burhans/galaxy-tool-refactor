"""The ``normalize-macros`` subcommand: lowercase literal format/ftype in macros."""

from __future__ import annotations

from pathlib import Path

import click
from galaxy_tool_fmt.cli_support import is_macros_root
from galaxy_tool_refactor_registry.macro_datatype import normalize_macro_files

from galaxy_tool_refactor_cli.options import _BACKUP_OPTION


def _collect_macro_files(paths: tuple[Path, ...], /) -> list[Path]:
    """Resolve *paths* (files and/or directories) to ``<macros>``-root files.

    A directory is searched recursively for ``*.xml`` whose root opens ``<macros``;
    a file is included only when it is itself a macro-library file. De-duplicated by
    resolved path and returned in a stable (sorted) order for deterministic output.
    """
    found: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        candidates = sorted(path.rglob("*.xml")) if path.is_dir() else [path]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen or not candidate.is_file():
                continue
            seen.add(resolved)
            if is_macros_root(candidate.read_bytes()):
                found.append(candidate)
    return found


@click.command(name="normalize-macros")
@click.argument(
    "paths", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--check", is_flag=True, help="Report what would change and write nothing."
)
@_BACKUP_OPTION
def normalize_macros_command(
    paths: tuple[Path, ...], check: bool, backup: bool
) -> None:
    """Normalize literal format/ftype in macro-library files (opt-in, repo-scoped).

    Lowercases literal ``format`` / ``ftype`` datatype tokens (leaving ``@TOKEN@``
    placeholders alone) in every ``<macros>``-root file found under PATHS — the
    macro-library analog of the 24.2 normalization the per-tool ``upgrade`` cannot
    reach (a value defined in an imported macro file). Unlike ``format`` / ``upgrade``
    this rewrites files other than the one named — a shared macro file affects every
    importer — so it is a deliberate, separate command, never part of ``format``.
    """
    result = normalize_macro_files(
        _collect_macro_files(paths), write=not check, backup=backup
    )
    verb = "would normalize" if check else "normalized"
    for edit in result.edits:
        click.echo(f"{verb} {edit.macro_file} ({edit.elements_changed} element(s))")
    for bad in result.unparseable:
        click.echo(f"skipped (could not parse): {bad}", err=True)
    if not result.edits:
        click.echo("no macro-library files needed normalization")
