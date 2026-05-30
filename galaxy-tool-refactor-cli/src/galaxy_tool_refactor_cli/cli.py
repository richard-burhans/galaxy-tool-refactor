"""The ``galaxy-tool-refactor`` command-line interface.

Five subcommands. ``format`` and ``upgrade`` share fmt's file-walking /
drift-detection engine (``galaxy_tool_xml_fmt.cli_support``) and differ only in
which rules run before serialisation; ``check`` is a report-only linter that
mutates nothing; ``rules`` / ``presets`` print the available baked-in rules and
presets. All rule orchestration is delegated to the tier-3.6 registry facade
(``galaxy_tool_refactor_registry``); this module only does CLI plumbing.

- ``format`` — apply a preset's (or a ``--select``/``--ignore`` selection's)
  fixable rules then cosmetic formatting. Safe and idempotent; never changes
  ``profile=``. Default preset ``iuc`` reproduces the historical behaviour.
- ``upgrade`` — repair, then iteratively upgrade ``profile=`` toward the latest
  (applying the registered migration each step), then format. Opt-in and
  semantic; presets do not apply (``--select``/``--ignore`` adjust its rule set).
- ``check`` — report where tools deviate from the selection, one
  ``file:line  CODE  message`` per finding, without changing anything. Fixable
  (GTX) findings fail the run; advisory (IUC) findings are informational unless
  ``--strict``.
- ``rules`` / ``presets`` — introspection: the baked-in rules and the presets.

Selection (``--preset`` / ``--select`` / ``--ignore``) is shared by ``format``,
``upgrade`` (no ``--preset``), and ``check``; precedence is ruff-style
(``--ignore`` ▸ ``--select`` ▸ ``--preset``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from galaxy_tool_refactor_registry import facade
from galaxy_tool_refactor_registry.errors import UnknownPreset, UnknownRuleCode
from galaxy_tool_refactor_registry.resolve import (
    resolve_codes,
    resolve_upgrade_codes,
)
from galaxy_tool_xml.binding import ToolXmlSyntaxError, load_tool
from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml_fmt.cli_support import (
    Action,
    RunOptions,
    TransformOutcome,
    is_tool_root,
    iter_targets,
    run,
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
_STRICT_OPTION = click.option(
    "--strict",
    is_flag=True,
    help="Also fail (exit non-zero) on advisory findings, not just fixable ones.",
)
_PRESET_OPTION = click.option(
    "--preset",
    default=None,
    metavar="NAME",
    help="Named rule subset to apply/report (cosmetic | iuc | strict). "
    "Default: iuc. See `galaxy-tool-refactor presets`.",
)
_SELECT_OPTION = click.option(
    "--select",
    "select",
    multiple=True,
    metavar="CODE",
    help="Run only these rule codes (replaces the preset's set). "
    "Repeatable or comma-separated, e.g. --select GTX001,GTX003.",
)
_IGNORE_OPTION = click.option(
    "--ignore",
    "ignore",
    multiple=True,
    metavar="CODE",
    help="Drop these rule codes from the selection. Repeatable or comma-separated.",
)


def _split_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    """Flatten repeated / comma-separated code options, upper-cased and stripped."""
    codes: list[str] = []
    for value in values:
        codes.extend(
            token.strip().upper() for token in value.split(",") if token.strip()
        )
    return tuple(codes)


def _resolve(
    *, preset: str | None, select: tuple[str, ...], ignore: tuple[str, ...]
) -> frozenset[str]:
    """Resolve a format/check selection, mapping facade errors to the CLI boundary."""
    try:
        return resolve_codes(
            preset=preset,
            select=_split_codes(select),
            ignore=_split_codes(ignore),
        )
    except (UnknownPreset, UnknownRuleCode) as error:
        raise click.BadParameter(str(error)) from error


def _resolve_upgrade(
    *, select: tuple[str, ...], ignore: tuple[str, ...]
) -> frozenset[str]:
    """Resolve an upgrade selection (no preset), mapping facade errors to the CLI."""
    try:
        return resolve_upgrade_codes(
            select=_split_codes(select), ignore=_split_codes(ignore)
        )
    except UnknownRuleCode as error:
        raise click.BadParameter(str(error)) from error


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Refactor Galaxy tool XML: structural codemods plus cosmetic formatting."""


@main.command(name="format")
@_PATH_ARGUMENT
@_CHECK_OPTION
@_DIFF_OPTION
@_QUIET_OPTION
@_PRESET_OPTION
@_SELECT_OPTION
@_IGNORE_OPTION
def format_command(
    paths: tuple[Path, ...],
    check: bool,
    diff: bool,
    quiet: bool,
    preset: str | None,
    select: tuple[str, ...],
    ignore: tuple[str, ...],
) -> None:
    """Apply a preset's fixable rules then cosmetic formatting (never ``profile=``).

    The default preset ``iuc`` applies the canonical codemods (typo repair,
    attribute / element order) and the cosmetic rules — the historical ``format``
    behaviour. Advisory rules in a selection (e.g. under ``--preset strict``) are
    reported as notes but never change a file. PATHS may be files or directories
    (searched recursively for ``*.xml``); non-Galaxy-tool XML is skipped.
    """
    codes = _resolve(preset=preset, select=select, ignore=ignore)

    def transform(document: ToolDocument) -> TransformOutcome:
        result = facade.run(document, codes=codes)
        return TransformOutcome(result.formatted, notes=result.notes)

    exit_code = run(
        paths,
        transform=transform,
        action=Action(past="reformatted", conditional="would reformat"),
        options=RunOptions(check=check, diff=diff, quiet=quiet),
    )
    sys.exit(exit_code)


@main.command(name="upgrade")
@_PATH_ARGUMENT
@_CHECK_OPTION
@_DIFF_OPTION
@_QUIET_OPTION
@_PRESET_OPTION
@_SELECT_OPTION
@_IGNORE_OPTION
def upgrade_command(
    paths: tuple[Path, ...],
    check: bool,
    diff: bool,
    quiet: bool,
    preset: str | None,
    select: tuple[str, ...],
    ignore: tuple[str, ...],
) -> None:
    """Repair and upgrade tools to the latest profile they can reach, then format.

    Opt-in and semantic. The profile upgrade always runs; ``--select`` / ``--ignore``
    adjust the *other* fixable rules (by default typo repair + cosmetic
    formatting) — e.g. ``--ignore GTX006`` upgrades without typo repair. Presets
    are a ``format``/``check`` concept and are **not** accepted here. PATHS may be
    files or directories.
    """
    if preset is not None:
        raise click.BadParameter(
            "--preset is not applicable to 'upgrade'; presets govern "
            "'format' / 'check'. Use --select / --ignore to adjust the rule set.",
            param_hint="--preset",
        )
    codes = _resolve_upgrade(select=select, ignore=ignore)

    def transform(document: ToolDocument) -> TransformOutcome:
        result = facade.upgrade(document, codes=codes)
        return TransformOutcome(result.formatted, notes=result.notes)

    exit_code = run(
        paths,
        transform=transform,
        action=Action(past="upgraded", conditional="would upgrade"),
        options=RunOptions(check=check, diff=diff, quiet=quiet),
    )
    sys.exit(exit_code)


def _check_summary(
    *,
    fixable: int,
    advisory: int,
    flagged: int,
    clean: int,
    skipped: int,
    errored: int,
) -> str:
    """Render the trailing summary line for ``check``."""
    parts: list[str] = []
    if fixable or advisory:
        counts = []
        if fixable:
            counts.append(f"{fixable} fixable")
        if advisory:
            counts.append(f"{advisory} advisory")
        parts.append(", ".join(counts) + f" finding(s) in {flagged} file(s)")
    if clean:
        parts.append(f"{clean} file(s) clean")
    if skipped:
        parts.append(f"{skipped} skipped (not a Galaxy tool)")
    if errored:
        parts.append(f"{errored} errored")
    return "; ".join(parts) + "." if parts else "no files checked."


@main.command(name="check")
@_PATH_ARGUMENT
@_QUIET_OPTION
@_STRICT_OPTION
@_PRESET_OPTION
@_SELECT_OPTION
@_IGNORE_OPTION
def check_command(
    paths: tuple[Path, ...],
    quiet: bool,
    strict: bool,
    preset: str | None,
    select: tuple[str, ...],
    ignore: tuple[str, ...],
) -> None:
    """Report where tools deviate from the selection, without changing them.

    Runs the selected rules' detect phases (default preset ``iuc``): *fixable*
    (GTX — what ``format`` would change) and, under ``--preset strict``, the
    *advisory* IUC best-practice checks (marked ``(advisory)``). Prints one
    ``file:line  CODE  message`` per finding. Exits non-zero on any *fixable*
    finding or error; advisory findings are informational unless ``--strict``.
    PATHS may be files or directories; non-Galaxy-tool XML is skipped.
    """
    codes = _resolve(preset=preset, select=select, ignore=ignore)
    fixable = advisory = flagged = clean = skipped = errored = 0
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
            document = load_tool(original)
        except ToolXmlSyntaxError as error:
            click.echo(f"error: {target}: malformed XML: {error}", err=True)
            errored += 1
            continue
        if document.root.tag != "tool":
            skipped += 1
            continue
        result = facade.detect(document, codes=codes)
        if not result.violations:
            clean += 1
            continue
        flagged += 1
        for violation in result.violations:
            is_advisory = result.is_advisory(violation)
            if is_advisory:
                advisory += 1
            else:
                fixable += 1
            if not quiet:
                suffix = "  (advisory)" if is_advisory else ""
                click.echo(
                    f"{target}:{violation.sourceline}  "
                    f"{violation.code}  {violation.message}{suffix}"
                )
    if not quiet:
        click.echo(
            _check_summary(
                fixable=fixable,
                advisory=advisory,
                flagged=flagged,
                clean=clean,
                skipped=skipped,
                errored=errored,
            )
        )
    fail = bool(errored or fixable or (strict and advisory))
    sys.exit(1 if fail else 0)


@main.command(name="presets")
def presets_command() -> None:
    """List the available presets and the rule codes each one selects."""
    for info in facade.list_presets():
        default = " (default)" if info.is_default else ""
        click.echo(f"{info.name}{default}: {info.description}")
        click.echo(f"  rules: {', '.join(info.codes)}")


@main.command(name="rules")
@click.option(
    "--include-upgrade",
    is_flag=True,
    help="Also list the upgrade-only codemods (not independently selectable).",
)
def rules_command(include_upgrade: bool) -> None:
    """List the baked-in rules: code, family, fixable/advisory, and presets."""
    for info in facade.list_rules(include_upgrade=include_upgrade):
        kind = "fixable" if info.fixable else "advisory"
        in_presets = ",".join(info.presets) if info.presets else "-"
        click.echo(
            f"{info.code}  [{info.family}/{kind}]  presets:{in_presets}  "
            f"{info.summary}"
        )


if __name__ == "__main__":
    main()
