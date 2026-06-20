"""The ``check`` subcommand: report-only linter over selected detect phases."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from galaxy_tool_fmt.cli_support import (
    is_macros_root,
    is_tool_root,
    iter_targets,
)
from galaxy_tool_fmt.detect import detect_macro_document
from galaxy_tool_refactor_registry import facade
from galaxy_tool_refactor_registry.registry import display_code
from galaxy_tool_source.binding import ToolXmlSyntaxError, load_macros, load_tool

from galaxy_tool_refactor_cli.options import (
    _IGNORE_OPTION,
    _PATH_ARGUMENT,
    _QUIET_OPTION,
    _RULESET_OPTION,
    _SELECT_OPTION,
    _STRICT_OPTION,
    _resolve,
)


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
        parts.append(f"{skipped} skipped (not a Galaxy tool or macro file)")
    if errored:
        parts.append(f"{errored} errored")
    return "; ".join(parts) + "." if parts else "no files checked."


@click.command(name="check")
@_PATH_ARGUMENT
@_QUIET_OPTION
@_STRICT_OPTION
@_RULESET_OPTION
@_SELECT_OPTION
@_IGNORE_OPTION
def check_command(
    paths: tuple[Path, ...],
    quiet: bool,
    strict: bool,
    rulesets: tuple[str, ...],
    select: tuple[str, ...],
    ignore: tuple[str, ...],
) -> None:
    """Report where tools deviate from the selection, without changing them.

    Runs the selected rules' detect phases (default ruleset ``default``): *fixable*
    (GTR — what ``format`` would change) and, under ``--ruleset strict``, the
    *advisory* IUC best-practice checks (marked ``(advisory)``). Prints one
    ``file:line  CODE  message`` per finding, then a deduplicated ``References``
    block mapping each fired code to its documentation URL (so every finding points
    at what to do). Exits non-zero on any *fixable* finding or error; advisory
    findings are informational unless ``--strict``.
    Macro-library files (``<macros>`` root) are also checked, for cosmetic
    (fixable) drift only — the selection governs tools; macro files get the
    standard cosmetic checks. PATHS may be files or directories; other XML is
    skipped.
    """
    codes = _resolve(rulesets=rulesets, select=select, ignore=ignore)
    fixable = advisory = flagged = clean = skipped = errored = 0
    # Displayed code -> documentation URL, accumulated across every finding so the
    # closing "References" block can point each emitted code at its detailed doc
    # (the overarching-goal contract: a finding we surface must point to what to do;
    # docs/design_principles.md). Deduplicated — cites are shared, so one line per
    # fired code, not per occurrence.
    cite_by_code = {
        info.code: info.cite
        for info in facade.list_rules(include_upgrade=True)
    }
    references: dict[str, str] = {}
    for target in iter_targets(paths):
        try:
            original = target.read_bytes()
        except OSError as error:
            click.echo(f"error: cannot read {target}: {error}", err=True)
            errored += 1
            continue
        # Each finding is a (violation, is_advisory) pair. Tool files run the
        # full selected detect (fixable GTR + advisory); macro files run the
        # cosmetic macro rules only (all fixable). Other XML is skipped.
        if is_tool_root(original):
            try:
                tool_document = load_tool(target)  # load from path so imports resolve
            except ToolXmlSyntaxError as error:
                click.echo(f"error: {target}: malformed XML: {error}", err=True)
                errored += 1
                continue
            if tool_document.root.tag != "tool":
                skipped += 1
                continue
            result = facade.detect(tool_document, codes=codes)
            findings = [(v, result.is_advisory(v)) for v in result.violations]
        elif is_macros_root(original):
            try:
                # load from path, mirroring the tool branch
                macro_document = load_macros(target)
            except ToolXmlSyntaxError as error:
                click.echo(f"error: {target}: malformed XML: {error}", err=True)
                errored += 1
                continue
            if macro_document.root.tag != "macros":
                skipped += 1
                continue
            # Sort to match the tool path (facade.detect returns line-sorted
            # violations), so `check` output ordering is consistent across kinds.
            macro_violations = sorted(
                detect_macro_document(macro_document),
                key=lambda v: (v.sourceline, v.code),
            )
            findings = [(v, False) for v in macro_violations]
        else:
            skipped += 1
            continue
        if not findings:
            clean += 1
            continue
        flagged += 1
        for violation, is_advisory in findings:
            if is_advisory:
                advisory += 1
            else:
                fixable += 1
            displayed = display_code(violation.code)
            # Resolve the doc pointer by the rule's own code, falling back to the
            # partition parent (a sub-rule like GTR020.2 shares the parent's cite).
            cite = cite_by_code.get(violation.code) or cite_by_code.get(
                violation.code.split(".")[0]
            )
            if cite:
                references.setdefault(displayed, cite)
            if not quiet:
                suffix = "  (advisory)" if is_advisory else ""
                click.echo(
                    f"{target}:{violation.sourceline}  "
                    f"{displayed}  {violation.message}{suffix}"
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
        if references:
            click.echo("\nReferences (what each code means + how to fix):")
            for code in sorted(references):
                click.echo(f"  {code}  {references[code]}")
            click.echo("  Run `galaxy-tool-refactor rules` for the full reference.")
    fail = bool(errored or fixable or (strict and advisory))
    sys.exit(1 if fail else 0)
