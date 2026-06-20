"""Shared Click option/argument decorators and selection helpers.

These are the only symbols shared across more than one command module: the
reusable option decorators (``--check`` / ``--diff`` / ``--quiet`` / …) and the
four selection helpers (``_split_codes`` / ``_split_names`` / ``_resolve`` /
``_resolve_upgrade``) used by ``format``/``check`` and ``upgrade``.
"""

from __future__ import annotations

from pathlib import Path

import click
from galaxy_tool_refactor_registry.errors import (
    UnknownRuleCode,
    UnknownRuleset,
)
from galaxy_tool_refactor_registry.resolve import (
    resolve_codes,
    resolve_upgrade_codes,
)

_PATH_ARGUMENT = click.argument(
    "paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
_CHECK_OPTION = click.option(
    "--check",
    is_flag=True,
    help="Don't write files. Exit non-zero if any file would change.",
)
_DIFF_OPTION = click.option(
    "--diff",
    is_flag=True,
    help="Don't write files. Print a unified diff of the rewrite to stdout.",
)
_QUIET_OPTION = click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Suppress per-file output; only errors and the summary are shown.",
)
_REPO_ROOT_OPTION = click.option(
    "--repo-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help=(
        "Repo directory used to prove a macro file is sole-owned before a rename "
        "edits it. Required only when a rename's references reach an imported macro."
    ),
)
_BACKUP_OPTION = click.option(
    "--backup",
    is_flag=True,
    help="Before overwriting a file, copy its current content to <file>.bak.",
)
_ACROSS_IMPORTERS_OPTION = click.option(
    "--across-importers",
    is_flag=True,
    help=(
        "When a rename reaches a macro shared by other tools, rename the parameter "
        "across all of its importers in lockstep (only if they all agree). Needs "
        "--repo-root."
    ),
)
_STRICT_OPTION = click.option(
    "--strict",
    is_flag=True,
    help="Also fail (exit non-zero) on advisory findings, not just fixable ones.",
)
_RULESET_OPTION = click.option(
    "--ruleset",
    "rulesets",
    multiple=True,
    metavar="NAME",
    help="Rule-set(s) to apply/report — the UNION of the named sets "
    "(cosmetic | default | iuc | strict). Repeatable or comma-separated, "
    "e.g. --ruleset default,strict. Default: default. "
    "See `galaxy-tool-refactor rulesets`.",
)
_SELECT_OPTION = click.option(
    "--select",
    "select",
    multiple=True,
    metavar="CODE",
    help="Run only these rules — GTR codes or planemo linter names "
    "(replaces the ruleset's set). Repeatable or comma-separated, "
    "e.g. --select GTR001,HelpMissing.",
)
_IGNORE_OPTION = click.option(
    "--ignore",
    "ignore",
    multiple=True,
    metavar="CODE",
    help="Drop these rules — GTR codes or planemo linter names — from the "
    "selection. Repeatable or comma-separated.",
)


def _split_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    """Flatten repeated / comma-separated select/ignore tokens, stripped.

    Case is preserved (the resolver matches GTR codes and planemo linter names
    case-insensitively) so an error message echoes the token the user typed.
    """
    codes: list[str] = []
    for value in values:
        codes.extend(token.strip() for token in value.split(",") if token.strip())
    return tuple(codes)


def _split_names(values: tuple[str, ...]) -> tuple[str, ...]:
    """Flatten repeated / comma-separated ruleset names, lower-cased and stripped."""
    names: list[str] = []
    for value in values:
        names.extend(
            token.strip().lower() for token in value.split(",") if token.strip()
        )
    return tuple(names)


def _resolve(
    *, rulesets: tuple[str, ...], select: tuple[str, ...], ignore: tuple[str, ...]
) -> frozenset[str]:
    """Resolve a format/check selection, mapping facade errors to the CLI boundary."""
    try:
        return resolve_codes(
            rulesets=_split_names(rulesets),
            select=_split_codes(select),
            ignore=_split_codes(ignore),
        )
    except (UnknownRuleset, UnknownRuleCode) as error:
        raise click.BadParameter(str(error)) from error


def _resolve_upgrade(
    *, select: tuple[str, ...], ignore: tuple[str, ...]
) -> frozenset[str]:
    """Resolve an upgrade selection (no ruleset), mapping facade errors to the CLI."""
    try:
        return resolve_upgrade_codes(
            select=_split_codes(select), ignore=_split_codes(ignore)
        )
    except UnknownRuleCode as error:
        raise click.BadParameter(str(error)) from error
