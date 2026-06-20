"""The ``format`` subcommand: ruleset fixable rules + cosmetic formatting."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from galaxy_tool_fmt.cli_support import (
    Action,
    RunOptions,
    TransformOutcome,
    run,
)
from galaxy_tool_fmt.format import format_macro_document
from galaxy_tool_refactor_registry import facade
from galaxy_tool_source.document import MacroDocument, ToolDocument

from galaxy_tool_refactor_cli.options import (
    _BACKUP_OPTION,
    _CHECK_OPTION,
    _DIFF_OPTION,
    _IGNORE_OPTION,
    _PATH_ARGUMENT,
    _QUIET_OPTION,
    _RULESET_OPTION,
    _SELECT_OPTION,
    _resolve,
)


@click.command(name="format")
@_PATH_ARGUMENT
@_CHECK_OPTION
@_DIFF_OPTION
@_QUIET_OPTION
@_BACKUP_OPTION
@_RULESET_OPTION
@_SELECT_OPTION
@_IGNORE_OPTION
def format_command(
    paths: tuple[Path, ...],
    check: bool,
    diff: bool,
    quiet: bool,
    backup: bool,
    rulesets: tuple[str, ...],
    select: tuple[str, ...],
    ignore: tuple[str, ...],
) -> None:
    """Apply a ruleset's fixable rules then cosmetic formatting (never ``profile=``).

    The default ruleset ``default`` applies the canonical codemods (typo repair,
    attribute / element order) and the cosmetic rules — the historical ``format``
    behaviour. Advisory rules in a selection (e.g. under ``--ruleset strict``) are
    reported as notes but never change a file. Macro-library files (``<macros>``
    root) are also **cosmetically** formatted (the kind-applicable rules — no
    codemods, which are tool-only; rule selection governs tools). PATHS may be
    files or directories (searched recursively for ``*.xml``); other XML is
    skipped.
    """
    codes = _resolve(rulesets=rulesets, select=select, ignore=ignore)

    def transform(document: ToolDocument) -> TransformOutcome:
        result = facade.run(document, codes=codes)
        return TransformOutcome(result.formatted, notes=result.notes)

    def macro_transform(document: MacroDocument) -> TransformOutcome:
        # Macro files get cosmetic formatting only; codemods are tool-only.
        return TransformOutcome(format_macro_document(document))

    exit_code = run(
        paths,
        transform=transform,
        action=Action(past="reformatted", conditional="would reformat"),
        options=RunOptions(check=check, diff=diff, quiet=quiet, backup=backup),
        macro_transform=macro_transform,
    )
    sys.exit(exit_code)
