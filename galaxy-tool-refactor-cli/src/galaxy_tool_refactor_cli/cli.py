"""The ``galaxy-tool-refactor`` command-line interface.

Two subcommands, sharing fmt's file-walking / drift-detection engine
(``galaxy_tool_xml_fmt.cli_support``) and differing only in which codemod
pipeline they apply before serialisation:

- ``format`` — apply ``CANONICAL_CODEMODS`` (repair + attribute order) then
  cosmetic formatting. Safe and idempotent; never changes ``profile=``.
- ``upgrade`` — apply ``AUTO_UPGRADE_CODEMODS`` (repair, then iterative profile
  upgrade) then cosmetic formatting. Opt-in and semantic; reports the profile
  steps applied and warns if it stalls below the latest profile.

Both write through fmt's serializer, so output is canonical-form XML in either
case; the difference is purely which transforms ran.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml_codemod.canonical import (
    AUTO_UPGRADE_CODEMODS,
    CANONICAL_CODEMODS,
)
from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.module import Module
from galaxy_tool_xml_codemod.upgrades import UpgradeToLatest
from galaxy_tool_xml_fmt.cli_support import (
    Action,
    RunOptions,
    TransformOutcome,
    run,
)
from galaxy_tool_xml_fmt.format import format_tool_document

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


def _apply_pipeline(
    document: ToolDocument,
    codemods: tuple[type[CodemodCommand], ...],
) -> None:
    """Apply each codemod in *codemods* to *document* in document order."""
    module = Module(document)
    for codemod_cls in codemods:
        codemod_cls().apply(module)


def _format_transform(document: ToolDocument) -> TransformOutcome:
    """Canonicalise (no profile change) then cosmetically format."""
    _apply_pipeline(document, CANONICAL_CODEMODS)
    return TransformOutcome(format_tool_document(document))


def _upgrade_note(upgrader: UpgradeToLatest) -> str | None:
    """Summarise what an ``UpgradeToLatest`` run did, for the per-file note."""
    steps = upgrader.upgrade_steps_applied()
    missing = upgrader.missing_upgrade()
    parts: list[str] = []
    if steps:
        parts.append("upgraded past " + ", ".join(steps))
    if missing is not None:
        parts.append(f"stalled at {missing} (no registered upgrade)")
    if not parts:
        return None
    return "  " + "; ".join(parts)


def _upgrade_transform(document: ToolDocument) -> TransformOutcome:
    """Repair, upgrade the profile to the latest reachable, then format."""
    module = Module(document)
    upgrader: UpgradeToLatest | None = None
    for codemod_cls in AUTO_UPGRADE_CODEMODS:
        instance = codemod_cls()
        instance.apply(module)
        if isinstance(instance, UpgradeToLatest):
            upgrader = instance
    note = _upgrade_note(upgrader) if upgrader is not None else None
    return TransformOutcome(format_tool_document(document), note)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Refactor Galaxy tool XML: structural codemods plus cosmetic formatting."""


@main.command(name="format")
@_PATH_ARGUMENT
@_CHECK_OPTION
@_DIFF_OPTION
@_QUIET_OPTION
def format_command(
    paths: tuple[Path, ...], check: bool, diff: bool, quiet: bool
) -> None:
    """Canonicalise and cosmetically format tools (never changes ``profile=``).

    Applies the structural canonical codemods (typo repair, attribute order)
    and fmt's cosmetic rules. PATHS may be files or directories (searched
    recursively for ``*.xml``); non-Galaxy-tool XML is skipped.
    """
    code = run(
        paths,
        transform=_format_transform,
        action=Action(past="reformatted", conditional="would reformat"),
        options=RunOptions(check=check, diff=diff, quiet=quiet),
    )
    sys.exit(code)


@main.command(name="upgrade")
@_PATH_ARGUMENT
@_CHECK_OPTION
@_DIFF_OPTION
@_QUIET_OPTION
def upgrade_command(
    paths: tuple[Path, ...], check: bool, diff: bool, quiet: bool
) -> None:
    """Repair and upgrade tools to the latest profile they can reach.

    Opt-in and semantic: repairs near-miss typos, then iteratively upgrades the
    tool's ``profile=`` toward the latest, applying the registered structural
    migration at each step. Reports the steps applied and warns if a tool
    stalls below the latest profile. PATHS may be files or directories.
    """
    code = run(
        paths,
        transform=_upgrade_transform,
        action=Action(past="upgraded", conditional="would upgrade"),
        options=RunOptions(check=check, diff=diff, quiet=quiet),
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
