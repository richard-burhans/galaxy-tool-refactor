"""The ``galaxy-tool-refactor`` command-line interface.

Eight subcommands. ``format`` and ``upgrade`` share fmt's file-walking /
drift-detection engine (``galaxy_tool_xml_fmt.cli_support``) and differ only in
which rules run before serialisation; ``check`` is a report-only linter that
mutates nothing; ``find-references`` is a read-only query for a parameter's Cheetah
``$var`` reference sites and ``rename-param`` is its mutating sibling (rename a
parameter across those sites); ``rules`` / ``rulesets`` print the available baked-in
rules and rulesets; ``normalize-macros`` is a separate, opt-in pass over macro-library
files. All rule orchestration is delegated to the tier-3.6 registry facade
(``galaxy_tool_refactor_registry``); this module only does CLI plumbing.

- ``format`` — apply a ruleset's (or a ``--select``/``--ignore`` selection's)
  fixable rules then cosmetic formatting. Safe and idempotent; never changes
  ``profile=``. Default ruleset ``default`` reproduces the historical behaviour.
  Macro-library files (``<macros>`` root) are also cosmetically formatted
  (kind-applicable rules only — no codemods).
- ``upgrade`` — repair, then iteratively upgrade ``profile=`` toward the latest
  (applying the registered migration each step), then format. Opt-in and
  semantic; rulesets do not apply (``--select``/``--ignore`` adjust its rule set).
  Also bumps an imported ``@PROFILE@`` token in place when every profile-using
  importer in the run agrees on the target (else reports and skips); a
  ``profile="@TOKEN@"`` whose token is inline is handled per-file by GTR007.
- ``check`` — report where tools deviate from the selection, one
  ``file:line  CODE  message`` per finding, without changing anything. Fixable
  findings fail the run; advisory (``detect_only``) findings are informational
  unless ``--strict``. Macro files are checked for cosmetic (fixable) drift too.
- ``find-references`` — read-only query: print every Cheetah ``$NAME`` reference site
  (``file:line  [section]  $ref``) across a tool's templated sections. Mutates nothing,
  not a rule (no selection); the first read-only consumer of the Cheetah reference model
  (``galaxy_tool_xml.cheetah_refs``). See ``docs/decisions.md`` §D8.
- ``rename-param`` — the mutating sibling of ``find-references``: rename a parameter
  OLD to NEW across every Cheetah section, by-name cross-reference attribute, and
  ``<tests>`` mirror, plus the definition. Atomic per file (rewrites everything or skips
  with a reason); ``--check`` previews. Built on the faithful CDM lexer (M5.3); see
  ``docs/decisions.md`` §D9.
- ``rules`` / ``rulesets`` — introspection: the baked-in rules and the rulesets.
- ``normalize-macros`` — opt-in, repo-scoped: lowercase literal ``format`` /
  ``ftype`` in ``<macros>``-root files (the macro-library analog of the 24.2
  normalization the per-tool ``upgrade`` cannot reach — a value defined in an
  imported macro file). It rewrites files other than the one named (a shared
  macro file affects every importer), so it is never folded into ``format`` /
  ``upgrade``; see ``galaxy-tool-xml-codemod/docs/macro-aware-normalization.md``.

Selection (``--ruleset`` / ``--select`` / ``--ignore``) is shared by ``format``,
``upgrade`` (no ``--ruleset``), and ``check``; precedence is ruff-style
(``--ignore`` ▸ ``--select`` ▸ ``--ruleset``, where ``--ruleset`` unions the named
sets and ``--select`` replaces them).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

import click
from galaxy_tool_refactor_registry import facade
from galaxy_tool_refactor_registry.bundle_rename import (
    BundleRenameResult,
    ConsensusRenameResult,
    build_importer_map,
    find_references_in_bundle,
    rename_param_bundle,
    rename_param_consensus,
)
from galaxy_tool_refactor_registry.errors import UnknownRuleCode, UnknownRuleset
from galaxy_tool_refactor_registry.macro_datatype import normalize_macro_files
from galaxy_tool_refactor_registry.macro_profile import (
    apply_profile_token_plans,
    plan_from_sites,
    profile_token_site,
)
from galaxy_tool_refactor_registry.registry import display_code
from galaxy_tool_refactor_registry.resolve import (
    resolve_codes,
    resolve_upgrade_codes,
)
from galaxy_tool_xml.binding import ToolXmlSyntaxError, load_macros, load_tool
from galaxy_tool_xml.document import MacroDocument, ToolDocument
from galaxy_tool_xml_fmt.cli_support import (
    Action,
    RunOptions,
    TransformOutcome,
    is_macros_root,
    is_tool_root,
    iter_targets,
    run,
)
from galaxy_tool_xml_fmt.detect import detect_macro_document
from galaxy_tool_xml_fmt.format import format_macro_document

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
    help="Run only these rule codes (replaces the ruleset's set). "
    "Repeatable or comma-separated, e.g. --select GTR001,GTR003.",
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


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Refactor Galaxy tool XML: structural codemods plus cosmetic formatting."""


@main.command(name="format")
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


@main.command(name="upgrade")
@_PATH_ARGUMENT
@_CHECK_OPTION
@_DIFF_OPTION
@_QUIET_OPTION
@_BACKUP_OPTION
@_RULESET_OPTION
@_SELECT_OPTION
@_IGNORE_OPTION
def upgrade_command(
    paths: tuple[Path, ...],
    check: bool,
    diff: bool,
    quiet: bool,
    backup: bool,
    rulesets: tuple[str, ...],
    select: tuple[str, ...],
    ignore: tuple[str, ...],
) -> None:
    """Repair and upgrade tools to the latest profile they can reach, then format.

    Opt-in and semantic. The profile upgrade always runs; ``--select`` / ``--ignore``
    adjust the *other* fixable rules (by default typo repair + cosmetic
    formatting) — e.g. ``--ignore GTR006`` upgrades without typo repair. Rulesets
    are a ``format``/``check`` concept and are **not** accepted here.

    A ``profile="@PROFILE@"`` whose token lives in an *imported* macro file is
    upgraded by bumping that token in place — but only when every profile-using
    importer in this run agrees on the target profile; a macro file whose
    importers disagree is reported and left untouched (no over-declaration). The
    inline-token case is handled per-file by GTR007. The token value is the *only*
    semantic edit, but the macro file it lives in **is** reserialised through fmt's
    ``format_macro_document`` when the token is bumped (so a bumped file is also
    cosmetically normalised — GTR001/GTR004); ``upgrade`` runs no *separate*
    cosmetic macro pass over un-bumped macro files the way ``format`` does. PATHS
    may be files or directories.

    The upgrade is structural, not behaviour-preserving: bumping ``profile=`` opts
    the tool into newer Galaxy runtime defaults the XSD can't verify. When a bump
    crosses such a boundary (e.g. ``set -e``, Python 3, optional-value templating),
    a note lists the crossed versions to review — see ``docs/profile_upgrades.md``.
    A few of those changes have a safe mechanical fix that is **applied
    automatically** once the reached profile crosses them (e.g. stripping
    whitespace from ``from_work_dir`` at 21.09); the rest are warn-only.
    """
    if rulesets:
        raise click.BadParameter(
            "--ruleset is not applicable to 'upgrade'; rulesets govern "
            "'format' / 'check'. Use --select / --ignore to adjust the rule set.",
            param_hint="--ruleset",
        )
    codes = _resolve_upgrade(select=select, ignore=ignore)

    # Whole-run phase first: bump imported @PROFILE@ tokens where every
    # profile-using importer agrees on the target (the inline case is handled
    # per-file by GTR007 in the transform below). This edits *macro* files, so it
    # cannot ride the per-file tool transform.
    macro_pending = _upgrade_macro_profile_tokens(
        paths, check=check, diff=diff, quiet=quiet, backup=backup
    )

    def transform(document: ToolDocument) -> TransformOutcome:
        result = facade.upgrade(document, codes=codes)
        return TransformOutcome(result.formatted, notes=result.notes)

    exit_code = run(
        paths,
        transform=transform,
        action=Action(past="upgraded", conditional="would upgrade"),
        options=RunOptions(check=check, diff=diff, quiet=quiet, backup=backup),
    )
    # A pending macro-token bump is a "would change" under either preview mode
    # (--check or --diff), so both must surface it in the exit code (cli D6).
    sys.exit(exit_code or (1 if ((check or diff) and macro_pending) else 0))


def _upgrade_macro_profile_tokens(
    paths: tuple[Path, ...], *, check: bool, diff: bool, quiet: bool, backup: bool
) -> bool:
    """Upgrade imported ``@PROFILE@`` tokens across the run; return would-edit.

    Walks the run's tool files, collects each one's imported-profile-token site,
    and for every macro file whose profile-using importers agree on a target
    bumps the ``<token>`` in place (writing unless ``check``/``diff``). A macro
    file whose importers disagree is reported and left untouched. Returns whether
    any macro file was (or, under preview, would be) edited — the caller folds
    that into the ``--check`` exit code.
    """
    sites = []
    for path in iter_targets(paths):
        try:
            original = path.read_bytes()
        except OSError:
            continue
        if not is_tool_root(original):
            continue
        try:
            document = load_tool(path)  # load from path so imports resolve
        except ToolXmlSyntaxError:
            continue  # malformed tools are surfaced by the per-file run() below
        site = profile_token_site(document)
        if site is not None:
            sites.append(site)
    plans = plan_from_sites(sites)
    result = apply_profile_token_plans(
        plans, write=not (check or diff), backup=backup
    )
    if not quiet:
        verb = "would upgrade" if (check or diff) else "upgraded"
        for edit in result.edits:
            click.echo(
                f"{verb} {edit.token_name} {edit.old_value} -> {edit.new_value} "
                f"in {edit.macro_file} ({len(edit.importers)} tool(s))"
            )
        for skip in result.skips:
            click.echo(
                f"skipped {skip.macro_file}: {skip.token_name} importers disagree "
                f"on target profile ({len(skip.importers)} tool(s))"
            )
    return bool(result.edits)


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


@main.command(name="check")
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
    ``file:line  CODE  message`` per finding. Exits non-zero on any *fixable*
    finding or error; advisory findings are informational unless ``--strict``.
    Macro-library files (``<macros>`` root) are also checked, for cosmetic
    (fixable) drift only — the selection governs tools; macro files get the
    standard cosmetic checks. PATHS may be files or directories; other XML is
    skipped.
    """
    codes = _resolve(rulesets=rulesets, select=select, ignore=ignore)
    fixable = advisory = flagged = clean = skipped = errored = 0
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
                tool_document = load_tool(original)
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
                macro_document = load_macros(original)
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
            if not quiet:
                suffix = "  (advisory)" if is_advisory else ""
                click.echo(
                    f"{target}:{violation.sourceline}  "
                    f"{display_code(violation.code)}  {violation.message}{suffix}"
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


@main.command(name="find-references")
@click.argument("name")
@_PATH_ARGUMENT
@_QUIET_OPTION
def find_references_command(
    name: str, paths: tuple[Path, ...], quiet: bool
) -> None:
    """Report every Cheetah $NAME reference across a tool **and its imported macros**.

    Read-only query (mutates nothing). For each tool it scans the tool's own
    ``<command>``, inline ``<configfile>``\\ s, env vars, output labels and dynamic
    options **plus every macro file it imports** (where a reference frequently lives),
    and prints one ``file:line  [section]  $ref`` per occurrence whose identifier path
    includes NAME (so ``$NAME``, ``$cond.NAME`` and ``$NAME.ext`` all match). PATHS may
    be files or directories; non-tool XML is skipped. Occurrences are de-duplicated, so
    a macro shared by several scanned tools is reported once. Conservative — may include
    occurrences in comments/``#raw`` (see ``galaxy_tool_xml.cheetah_refs``). Non-zero
    exit on errors.
    """
    total = scanned = skipped = errored = 0
    seen: set[tuple[str, int, str, str]] = set()
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
            result = find_references_in_bundle(target, name=name)
        except ToolXmlSyntaxError as error:
            click.echo(f"error: {target}: malformed XML: {error}", err=True)
            errored += 1
            continue
        scanned += 1
        for ref in result.references:
            key = (str(ref.path), ref.sourceline, ref.section, ref.reference)
            if key in seen:
                continue
            seen.add(key)
            total += 1
            if not quiet:
                click.echo(
                    f"{ref.path}:{ref.sourceline}  [{ref.section}]  {ref.reference}"
                )
    if not quiet:
        click.echo(f"{total} reference(s) to '{name}' across {scanned} tool(s)")
    sys.exit(1 if errored else 0)


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


@main.command(name="rename-param")
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


@main.command(name="rulesets")
def rulesets_command() -> None:
    """List the available rulesets and the rule codes each one selects."""
    for info in facade.list_rulesets():
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
    """List the baked-in rules: code, family, fixable/advisory, and rulesets."""
    for info in facade.list_rules(include_upgrade=include_upgrade):
        kind = "fixable" if info.fixable else "advisory"
        in_rulesets = ",".join(info.rulesets) if info.rulesets else "-"
        click.echo(
            f"{info.code}  [{info.family}/{kind}]  rulesets:{in_rulesets}  "
            f"{info.summary}"
        )


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


@main.command(name="normalize-macros")
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


if __name__ == "__main__":
    main()
