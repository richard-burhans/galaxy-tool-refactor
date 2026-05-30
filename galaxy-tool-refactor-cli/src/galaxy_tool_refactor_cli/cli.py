"""The ``galaxy-tool-refactor`` command-line interface.

Three subcommands. ``format`` and ``upgrade`` share fmt's file-walking /
drift-detection engine (``galaxy_tool_xml_fmt.cli_support``) and differ only in
which codemod pipeline they apply before serialisation; ``check`` is a
report-only linter that mutates nothing.

- ``format`` — apply ``CANONICAL_CODEMODS`` (repair + attribute order) then
  cosmetic formatting. Safe and idempotent; never changes ``profile=``.
- ``upgrade`` — apply ``AUTO_UPGRADE_CODEMODS`` (repair, then iterative profile
  upgrade) then cosmetic formatting. Opt-in and semantic; reports the profile
  steps applied and warns if it stalls below the latest profile.
- ``check`` — report where tools deviate from canonical form, one
  ``file:line  CODE  message`` per finding, without changing anything. Covers the
  *fixable* GTX rules (what ``format`` would change) plus the *advisory* IUC
  best-practice checks (``galaxy-tool-xml-check``). Exits non-zero on any fixable
  finding; advisory findings are informational unless ``--strict``.

``format`` and ``upgrade`` write through fmt's serializer, so output is
canonical-form XML; the difference is purely which transforms ran.
"""

from __future__ import annotations

import sys
from functools import cache
from pathlib import Path

import click
from galaxy_tool_refactor_rules.violation import Violation
from galaxy_tool_xml.binding import ToolXmlSyntaxError, load_tool
from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml_check.detect import all_checks
from galaxy_tool_xml_check.detect import detect_violations as detect_advisory
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
    is_tool_root,
    iter_targets,
    run,
)
from galaxy_tool_xml_fmt.detect import detect_tool_document
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
_STRICT_OPTION = click.option(
    "--strict",
    is_flag=True,
    help="Also fail (exit non-zero) on advisory findings, not just fixable ones.",
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


@cache
def _advisory_codes() -> frozenset[str]:
    """The set of ``detect_only`` (advisory) rule codes — the IUC check tier."""
    return frozenset(
        check_cls.meta.code
        for check_cls in all_checks()
        if check_cls.meta.detect_only
    )


def _detect_violations(document: ToolDocument) -> list[Violation]:
    """Collect every reported violation in *document*, without mutating it.

    Composes three non-mutating detect phases over the one document: the
    structural canonical codemods (each ``Change`` projected to a ``Violation``),
    fmt's cosmetic detect, and the advisory IUC checks. The first two are
    *fixable* (``format`` applies the same rules); the IUC checks are *advisory*
    (``detect_only``). Findings are sorted by source line so a report reads top
    to bottom.

    Each codemod detect runs against the document *as-is*, not pipelined, so for
    the small population that validates at no profile — where ``format`` would
    run ``FixTypos`` first — the reported structural findings are computed before
    that repair and may differ slightly from the final ``format`` result.
    """
    module = Module(document)
    violations = [
        change.to_violation()
        for codemod_cls in CANONICAL_CODEMODS
        for change in codemod_cls().detect(module)
    ]
    violations.extend(detect_tool_document(document))
    violations.extend(detect_advisory(document))
    violations.sort(key=lambda violation: (violation.sourceline, violation.code))
    return violations


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
def check_command(paths: tuple[Path, ...], quiet: bool, strict: bool) -> None:
    """Report where tools deviate from canonical form, without changing them.

    Runs three report-only detect phases: the structural canonical codemods and
    cosmetic fmt rules (*fixable* — what ``format`` would change) plus the
    advisory IUC best-practice checks (marked ``(advisory)``). Prints one
    ``file:line  CODE  message`` line per finding. Exits non-zero on any
    *fixable* finding or error; advisory findings are informational unless
    ``--strict`` is given. PATHS may be files or directories (searched
    recursively for ``*.xml``); non-Galaxy-tool XML is skipped.
    """
    advisory_codes = _advisory_codes()
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
        violations = _detect_violations(document)
        if not violations:
            clean += 1
            continue
        flagged += 1
        for violation in violations:
            is_advisory = violation.code in advisory_codes
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


if __name__ == "__main__":
    main()
