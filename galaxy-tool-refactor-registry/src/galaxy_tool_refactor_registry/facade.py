"""The library-first entry points: ``run`` / ``upgrade`` / ``detect`` /
``find_references`` + introspection.

Every function takes a *source* (a filesystem path, raw XML ``bytes``, or an
existing ``ToolDocument``) and a resolved *codes* set, and returns a structured
result — no ``click``, no ``sys.exit``, no printing. Files are written only when
a ``write_path`` is given. This is the shared core the ``galaxy-tool-refactor``
CLI and the MCP server (``galaxy-tool-refactor-mcp``) both sit on top of.

``codes`` is what ``resolve.resolve_codes`` / ``resolve.resolve_upgrade_codes``
produce — a set of **real rule codes** with any partition-parent code already
expanded to its sub-rules (e.g. ``GTR020`` → ``GTR020.1`` / ``GTR020.2``). The facade
indexes the registry by code directly, so callers must resolve first; passing a bare
parent code is a caller error. ``run`` applies the fixable rules in the selection and
reports advisory (``detect_only``) ones as notes (never mutating for them);
``detect`` reports all of them without mutating; ``upgrade`` always performs the
profile upgrade and additionally applies the fixable rules in the selection.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING

from galaxy_tool_codemod import behavior_gate
from galaxy_tool_codemod.codemods.convert_help_markdown import (
    ConvertHelpToMarkdown,
    conversion_skip_reason,
)
from galaxy_tool_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_codemod.codemods.tokenize_version import (
    TokenizeVersion,
    tokenization_skip_reason,
)
from galaxy_tool_codemod.module import Module
from galaxy_tool_codemod.profile_semantics import (
    ProfileUpgradeCode,
    crossed_and_applicable_codes,
    tripped_upgrade_codes,
)
from galaxy_tool_codemod.runtime_fixes import runtime_fixes_for
from galaxy_tool_codemod.upgrades import UpgradeToLatest, UpgradeToValid
from galaxy_tool_fmt.detect import detect_tool_document_subset
from galaxy_tool_fmt.format import format_tool_document_subset
from galaxy_tool_lint.detect import sort_violations
from galaxy_tool_refactor_rules.rulesets import (
    DEFAULT_RULESET,
    ruleset_description,
    ruleset_names,
)
from galaxy_tool_source import version_tokens
from galaxy_tool_source.binding import (
    Source,
    load_tool,
    newest_valid_profile,
    validate_tool,
)
from galaxy_tool_source.cheetah_refs import tool_cheetah_references
from galaxy_tool_source.cheetah_rename import rename_param as _rename_in_tree
from galaxy_tool_source.document import ToolDocument
from galaxy_tool_source.profiles import available_profiles, latest_profile
from packaging.version import Version

from galaxy_tool_refactor_registry.adapters import fmt_rule_by_code
from galaxy_tool_refactor_registry.apply import apply_selection
from galaxy_tool_refactor_registry.errors import UnknownProfile, UpgradeFlagError
from galaxy_tool_refactor_registry.registry import all_handles, registry
from galaxy_tool_refactor_registry.results import (
    ConvertHelpResult,
    DetectResult,
    FindReferencesResult,
    FormatResult,
    NewMacrosFile,
    ParamOccurrence,
    RenameParamResult,
    RuleInfo,
    RulesetInfo,
    TokenizeVersionResult,
    UpgradeResult,
    render_advisory_note,
)
from galaxy_tool_refactor_registry.rulesets import ruleset_codes
from galaxy_tool_refactor_registry.version_token_share import (
    SharedTokenizePlan,
    plan_shared_tokenization,
)

if TYPE_CHECKING:
    from galaxy_tool_refactor_rules.violation import Violation


def _to_document(source: Source | ToolDocument, /) -> ToolDocument:
    """Coerce *source* to a ``ToolDocument`` (path / bytes / str → parsed)."""
    if isinstance(source, ToolDocument):
        return source
    return load_tool(source)


def _detect_advisory(
    document: ToolDocument, codes: frozenset[str]
) -> list[Violation]:
    """Run the advisory (non-fixable) rules in *codes*; sort findings by line."""
    reg = registry()
    violations: list[Violation] = []
    for code in codes:
        handle = reg[code]
        if not handle.fixable:
            violations.extend(handle.detect(document))
    return sort_violations(violations)


def run(
    source: Source | ToolDocument,
    /,
    *,
    codes: frozenset[str],
    write_path: Path | None = None,
) -> FormatResult:
    """Apply the fixable rules in *codes*; report advisory ones as notes.

    The document is mutated in place when *source* is a ``ToolDocument``. Advisory
    findings are detected on the pre-format tree and never cause a mutation.
    Writes *write_path* only if given.
    """
    document = _to_document(source)
    advisory = _detect_advisory(document, codes)
    formatted = apply_selection(document, codes=codes)
    notes = tuple(render_advisory_note(violation) for violation in advisory)
    if write_path is not None:
        write_path.write_bytes(formatted)
    return FormatResult(formatted=formatted, advisory=advisory, notes=notes)


def detect(
    source: Source | ToolDocument, /, *, codes: frozenset[str]
) -> DetectResult:
    """Report every finding for the rules in *codes*, without mutating anything.

    The selected cosmetic fmt rules are detected **as one group** (their net
    effect, via ``detect_tool_document_subset``) rather than per-rule, so an
    already-canonical document reports nothing — matching what ``run`` would do.
    Codemod and advisory rules are independent and run per-code.
    """
    document = _to_document(source)
    reg = registry()
    violations: list[Violation] = []
    fmt_codes: list[str] = []
    for code in codes:
        handle = reg[code]
        if handle.family == "fmt":
            fmt_codes.append(code)
        else:
            violations.extend(handle.detect(document))
    if fmt_codes:
        fmt_by_code = fmt_rule_by_code()
        fmt_classes = tuple(fmt_by_code[code] for code in fmt_codes)
        violations.extend(
            detect_tool_document_subset(document, rule_classes=fmt_classes)
        )
    sort_violations(violations)
    advisory = frozenset(code for code in codes if not reg[code].fixable)
    return DetectResult(violations=violations, advisory_codes=advisory)


def find_references(
    source: Source | ToolDocument, /, *, name: str
) -> FindReferencesResult:
    """Every Cheetah ``$var`` reference whose identifier path includes *name*.

    Read-only: scans the tool's Cheetah-templated sections (``tool_cheetah_references``)
    and keeps the references one of whose segments is *name* — so a bare ``$name`` and a
    qualified ``$cond.name`` / ``$name.ext`` both match. No rule selection, no mutation.
    """
    document = _to_document(source)
    occurrences = tuple(
        ParamOccurrence(
            section=ref.section, sourceline=ref.sourceline, reference=ref.name
        )
        for ref in tool_cheetah_references(document.root)
        if name in ref.segments
    )
    return FindReferencesResult(name=name, occurrences=occurrences)


def rename_param(
    source: Source | ToolDocument,
    /,
    *,
    old: str,
    new: str,
    write_path: Path | None = None,
) -> RenameParamResult:
    """Rename parameter *old* to *new* across the tool's Cheetah sections, atomically.

    The mutating sibling of ``find_references``: rewrites every live ``$old`` reference
    (``<command>`` / ``<configfile>`` via the faithful lexer, attribute-Cheetah, by-name
    cross-reference attributes) plus the definition, or changes nothing and reports why
    it bailed (see ``galaxy_tool_source.cheetah_rename``). The work runs on a deep
    copy, so
    a bail never mutates *source*; on success the serialised bytes are returned (and
    written to *write_path* if given). Serialisation goes through fmt — the only
    serializer — with no cosmetic rules, so only the renamed tokens (and lxml's
    attribute-quote normalisation) differ.
    """
    document = _to_document(source)
    working = copy.deepcopy(document.tree)
    outcome = _rename_in_tree(working.getroot(), old=old, new=new)
    if outcome.bailed:
        return RenameParamResult(old=old, new=new, changed=False, reason=outcome.reason)
    formatted = format_tool_document_subset(ToolDocument(working), rule_classes=())
    if write_path is not None:
        write_path.write_bytes(formatted)
    return RenameParamResult(
        old=old,
        new=new,
        changed=True,
        renamed=outcome.renamed,
        formatted=formatted,
    )


def _upgrade_summary(steps: tuple[str, ...], missing: str | None) -> str | None:
    """One-line summary of an ``UpgradeToLatest`` run, or ``None`` if it did nothing."""
    parts: list[str] = []
    if steps:
        parts.append("upgraded past " + ", ".join(steps))
    if missing is not None:
        parts.append(f"stalled at {missing} (no registered upgrade)")
    if not parts:
        return None
    return "  " + "; ".join(parts)


def _semantic_warning(
    baseline: str | None,
    target: str | None,
    *,
    crossed: list[ProfileUpgradeCode],
    residual: list[ProfileUpgradeCode],
) -> str | None:
    """Warn when the bump crosses runtime-behaviour the XSD can't verify.

    Profile upgrade is structurally sound but not behaviour-preserving (codemod
    ``docs/decisions.md`` §22): some bumps change runtime defaults. We surface
    the crossed boundaries for the user to review. *residual* is the applicable
    set minus the codes an auto-fix already cleared (a cleared code needs no
    review; it gets its own fixed-automatically note). ``None`` (no warning)
    when nothing applies after crediting the fixes.
    """
    if not residual:
        return None
    # The catalogue is profile-ascending, so first-seen dedup keeps release order.
    releases = ", ".join(dict.fromkeys(change.profile for change in residual))
    must_fix = sum(1 for change in residual if change.level == "must_fix")
    must_fix_note = f", {must_fix} must-fix" if must_fix else ""
    return (
        f"  profile {baseline}→{target}: {len(residual)} of {len(crossed)}"
        f" crossed Galaxy profile-behaviour change(s) apply to this tool"
        f"{must_fix_note} (releases {releases}); review against"
        " docs/profile_boundaries.md before relying on this upgrade."
    )


def _behavior_preserving_note(
    baseline: str | None,
    target: str | None,
    *,
    preserving: bool | None,
    crossed_any: bool,
) -> str | None:
    """The positive clean-pass note, or ``None`` when there is no story to tell.

    Emitted only when the bump actually crossed at least one catalogue boundary
    (*crossed_any*) and is behaviour-preserving, the affirmative complement of
    ``_semantic_warning``. A no-op upgrade (already at its target) is vacuously
    preserving but says nothing, and a bump that crosses an applicable,
    uncleared code is reported by the warning instead.
    """
    if not (crossed_any and preserving):
        return None
    return (
        f"  profile {baseline}→{target}: upgrade crosses no behaviour change that"
        " applies to this tool — behavior-preserving."
    )


def _behavior_stop_note(
    blockers: tuple[ProfileUpgradeCode, ...],
    *,
    stopped_at: str | None,
    walked: bool,
    target_profile: str | None,
) -> str | None:
    """The loud, actionable stop report for a gated walk, or ``None``.

    Covers the two gate outcomes: the walk capped at a profile below the
    latest (*walked*), and the declaration left in place entirely because no
    vendored profile predates the first blocker. Always names the blocking
    code, where to read about it, and the opt-out. Phrased per the Galaxy
    Community Code of Conduct: the tool is not "broken", it is not yet provably
    safe to upgrade further.
    """
    if not blockers:
        return None
    latest = latest_profile()
    if walked and (stopped_at is None or stopped_at == latest):
        return None
    codes = ", ".join(
        f"{change.code} ({change.level} at {change.profile})" for change in blockers
    )
    next_steps = (
        "see docs/profile_boundaries.md for what changes there and how to update"
        " the tool, or rerun with --allow-behavior-change to upgrade anyway"
    )
    if not walked:
        return (
            f"  profile upgrade left profile= unchanged: {codes} appl"
            f"{'y' if len(blockers) > 1 else 'ies'} to this tool and no vendored"
            f" profile predates the first change; {next_steps}."
        )
    requested = (
        f" The requested target {target_profile} lies past this boundary and"
        " also needs --allow-behavior-change."
        if target_profile is not None
        and Version(target_profile) > Version(str(stopped_at))
        else ""
    )
    return (
        f"  profile upgrade stopped at {stopped_at} (latest is {latest}):"
        f" {codes} appl{'y' if len(blockers) > 1 else 'ies'} to this tool and"
        f" cannot be fixed automatically yet; {next_steps}.{requested}"
    )


def _minimal_outcome_note(
    *,
    declared: str | None,
    baseline: str | None,
    reached: str | None,
    unreachable: str | None,
) -> str | None:
    """The per-tool report for the minimal default: kept / bumped / unreachable.

    ``None`` for an unplaceable baseline (the unplaceable note covers that
    case). Phrased per the Galaxy Community Code of Conduct: an unreachable
    floor means the tool needs repairs a profile bump cannot make, not that the
    tool is "broken".
    """
    if baseline is None:
        return None
    if declared is None:
        return (
            "  no profile= declared: left undeclared (Galaxy runs the tool"
            f" under its {baseline} legacy defaults); rerun with --modernize"
            " to declare and upgrade a profile."
        )
    if unreachable is not None:
        return (
            "  profile= left unchanged: the tool does not validate at any"
            f" vendored profile at or above {baseline}, so no profile bump can"
            " make it valid; `galaxy-tool-source validate` shows what to fix"
            " first."
        )
    if reached == baseline:
        return (
            f"  profile {baseline} kept: the tool validates at its declared"
            " profile; rerun with --modernize to walk newer profiles."
        )
    return (
        f"  profile {baseline}→{reached}: bumped to the minimum profile the"
        " tool validates at after repair."
    )


def _validated_target_profile(target_profile: str | None) -> str | None:
    """Pass through a vendored *target_profile*, or raise ``UnknownProfile``."""
    if target_profile is None:
        return None
    profiles = available_profiles()
    if target_profile not in profiles:
        raise UnknownProfile(
            target_profile, oldest=profiles[0], latest=latest_profile()
        )
    return target_profile


def upgrade(
    source: Source | ToolDocument,
    /,
    *,
    codes: frozenset[str],
    write_path: Path | None = None,
    modernize: bool = False,
    allow_behavior_change: bool = False,
    target_profile: str | None = None,
) -> UpgradeResult:
    """Repair *source*, move ``profile=`` only as far as needed, then format.

    **Minimal bump by default**: after the repair the tool's ``profile=`` is
    left untouched when the tool validates at its resolved baseline (its
    declared profile, or Galaxy's ``16.01`` legacy default — an undeclared
    tool stays undeclared); when it does not, the declaration moves to the
    **minimum** vendored profile at or above the baseline that validates
    (``UpgradeToValid``), no further. A tool that validates nowhere at or
    above its baseline is left unchanged and reported. Galaxy servers lag the
    newest profile, so a gratuitous bump would only narrow where the tool can
    run.

    *modernize* opts into the walk toward the latest profile, stopping at the
    behaviour ceiling: the newest vendored profile reachable without crossing
    a Galaxy ``must_fix`` behaviour change that applies to this tool and that
    no runtime-gated fix provably clears (``behavior_gate``). Applicable
    consider-level changes are warned about but do not stop the walk.
    *target_profile* caps the walk at an explicit vendored profile (raising
    ``UnknownProfile`` otherwise), implying the walk mode by itself, and
    composes with the gate (the lower wins). *allow_behavior_change* lifts
    the gate (the historical walk-to-latest); it requires a walk mode
    (raising ``UpgradeFlagError`` otherwise — the minimal default has no gate
    to lift).

    ``FixTypos`` runs first when its code is in *codes* (the repair
    precondition). Runtime-gated fixes for the profile actually crossed then
    apply (e.g. the 21.09 ``from_work_dir`` strip — a kept tool crosses
    nothing, so none apply), and codes they provably clear (re-detected after
    the fix) are credited to the behaviour verdict. Any other selected
    codemods run after (canonical order), then the selected cosmetic fmt
    rules. Advisory rules in *codes* are reported as notes.
    """
    target = _validated_target_profile(target_profile)
    walk_mode = modernize or target is not None
    if allow_behavior_change and not walk_mode:
        raise UpgradeFlagError()
    document = _to_document(source)
    # Capture the runtime baseline AND which upgrade codes the tool trips BEFORE
    # any codemod rewrites ``profile=`` or mutates the features detectors inspect
    # (GTR014/GTR015 fix the very things some detectors look for).
    baseline = behavior_gate.resolved_baseline(document)
    placeable = behavior_gate.placeable_baseline(baseline)
    declared = document.profile
    tripped = tripped_upgrade_codes(document)
    advisory = _detect_advisory(document, codes)

    # Blockers are computed whenever the baseline is placeable: in the walk
    # mode they gate the walk (or, under the opt-out, are reporting-only, the
    # user's review list); under the minimal default they are the preview of
    # where a modernize walk would stop.
    blockers: tuple[ProfileUpgradeCode, ...] = ()
    if placeable and baseline is not None:
        blockers = behavior_gate.blocking_codes(document, baseline=baseline)

    module = Module(document)
    if FixTypos.meta.code in codes:
        FixTypos().apply(module)

    steps: tuple[str, ...] = ()
    missing: str | None = None
    unreachable: str | None = None
    walk = False
    ceiling = target
    if walk_mode:
        walk = True
        if placeable and baseline is not None:
            if not allow_behavior_change:
                gate_ceiling = behavior_gate.behavior_ceiling(blockers)
                if behavior_gate.blocked_below_baseline(
                    ceiling=gate_ceiling, baseline=baseline
                ):
                    walk = False
                elif ceiling is None or (
                    gate_ceiling is not None
                    and Version(gate_ceiling) < Version(ceiling)
                ):
                    ceiling = gate_ceiling
        elif not allow_behavior_change:
            # An unplaceable baseline (an unresolved @PROFILE@ token): crossing
            # boundaries we cannot place would void the guarantee, so fail closed.
            walk = False
        if walk:
            upgrader = UpgradeToLatest(ceiling=ceiling)
            upgrader.apply(module)
            steps = tuple(upgrader.upgrade_steps_applied())
            missing = upgrader.missing_upgrade()
        # The profile actually reached (a literal version, even when
        # ``profile=`` is a macro token), measured under the same ceiling as
        # the walk; the runtime baseline when the walk did not run.
        reached_profile = (
            newest_valid_profile(document, ceiling=ceiling) if walk else baseline
        )
    elif placeable and baseline is not None:
        # The minimal default. An undeclared tool stays undeclared (declaring
        # a profile is best practice, not strictly needed); a declared tool
        # that validates at its baseline is kept there; only an invalid one
        # moves, to the minimum validating profile at or above the baseline.
        if declared is None or validate_tool(document, profile=baseline).valid:
            reached_profile = baseline
        else:
            minimal = UpgradeToValid(floor=baseline)
            minimal.apply(module)
            steps = tuple(minimal.upgrade_steps_applied())
            unreachable = minimal.unreachable_floor()
            reached_profile = (
                baseline
                if unreachable is not None
                else behavior_gate.resolved_baseline(document)
            )
    else:
        # Unplaceable baseline under the minimal default: fail closed.
        reached_profile = baseline

    # Runtime-gated fixes correct profile behaviours the XSD does not enforce, so
    # they ride neither the validity loop nor the selection. Apply each fix the tool
    # actually CROSSES (`baseline < introduced_profile <= reached`): a tool that
    # stalled below it is left alone (Galaxy ran it under the old behaviour), and one
    # that already declared a profile at/above it is left alone too (Galaxy already
    # applied the new behaviour; rewriting would change, not preserve, behaviour).
    # A kept tool crosses nothing, so the strict lower bound applies none.
    # Upgrade-only: never in `format`/canonical.
    applied_fixes = (
        runtime_fixes_for(reached_profile, baseline_profile=baseline)
        if reached_profile is not None
        else ()
    )
    for fix in applied_fixes:
        fix().apply(module)
    # Credit only the codes the executed fixes provably cleared: tripped before,
    # quiet after (proof by execution, the same standard as the gate's probe).
    auto_fixed: tuple[str, ...] = ()
    if applied_fixes:
        still_tripped = tripped_upgrade_codes(document)
        auto_fixed = tuple(
            fix.upgrade_code
            for fix in applied_fixes
            if fix.upgrade_code in tripped and fix.upgrade_code not in still_tripped
        )

    # The remaining fixable rules (any selected reorderers + cosmetic fmt) run
    # through the shared apply pipeline; FixTypos already ran as the repair
    # precondition, so it is excluded to avoid a redundant second pass.
    formatted = apply_selection(document, codes=codes - {FixTypos.meta.code})

    summary = _upgrade_summary(steps, missing)
    # Warning and verdict derive from one applicable set (minus the credited
    # auto-fixes), so they can never disagree.
    pair = crossed_and_applicable_codes(
        baseline=baseline, target=reached_profile, tripped=tripped
    )
    crossed: list[ProfileUpgradeCode] = []
    residual: list[ProfileUpgradeCode] = []
    preserving: bool | None = None
    if pair is not None:
        crossed, applicable = pair
        residual = [change for change in applicable if change.code not in auto_fixed]
        preserving = not residual
    semantic = _semantic_warning(
        baseline, reached_profile, crossed=crossed, residual=residual
    )
    pass_note = _behavior_preserving_note(
        baseline, reached_profile, preserving=preserving, crossed_any=bool(crossed)
    )
    # ``stopped_at`` is a walk-mode concept: the deliberate cap below latest.
    if not walk_mode:
        stopped_at = None
    elif not walk:
        stopped_at = baseline if placeable else None
    elif ceiling is not None and ceiling != latest_profile():
        stopped_at = ceiling
    else:
        stopped_at = None
    stop_note = (
        _behavior_stop_note(
            blockers, stopped_at=stopped_at, walked=walk, target_profile=target
        )
        if walk_mode and not allow_behavior_change
        else None
    )
    minimal_note = (
        _minimal_outcome_note(
            declared=declared,
            baseline=baseline,
            reached=reached_profile,
            unreachable=unreachable,
        )
        if not walk_mode
        else None
    )
    opt_out = (
        "--allow-behavior-change"
        if walk_mode
        else "--modernize --allow-behavior-change"
    )
    unplaceable_note = (
        "  profile= is a macro token that does not resolve to a version, so"
        " behaviour boundaries cannot be placed; profile= was left unchanged."
        f" Rerun with {opt_out} to upgrade without the behavior gate."
        if not placeable and not allow_behavior_change
        else None
    )
    fixed_notes = [
        f"  crossed {fix.introduced_profile} {fix.upgrade_code}: fixed"
        f" automatically ({fix.meta.code})."
        for fix in applied_fixes
        if fix.upgrade_code in auto_fixed
    ]
    notes = tuple(
        note
        for note in (
            summary,
            stop_note,
            minimal_note,
            unplaceable_note,
            semantic,
            pass_note,
            *fixed_notes,
            *(render_advisory_note(violation) for violation in advisory),
        )
        if note is not None
    )
    if write_path is not None:
        write_path.write_bytes(formatted)
    return UpgradeResult(
        formatted=formatted,
        baseline_profile=baseline,
        reached_profile=reached_profile,
        steps_applied=steps,
        missing_upgrade=missing,
        behavior_preserving=preserving,
        stopped_at=stopped_at,
        blocking_codes=tuple(change.code for change in blockers),
        auto_fixed_codes=auto_fixed,
        advisory=advisory,
        notes=notes,
    )


def convert_help(
    source: Source | ToolDocument,
    /,
    *,
    write_path: Path | None = None,
) -> ConvertHelpResult:
    """Convert an RST ``<help>`` body to Markdown (GTR092) — opt-in, gated.

    Runs the ``ConvertHelpToMarkdown`` codemod: XSD-valid only at profile >=
    24.2, behaviour-gated by tier-1 render equivalence, and a no-op (with the
    reason reported) whenever the conversion cannot be proven. Never part of
    ``run``/``upgrade`` — the conversion swaps Galaxy's rendering engine, so it
    is exposed solely through this dedicated entry point (the ``convert-help``
    command). Serialisation goes through fmt with no rules selected, so nothing
    but the ``<help>`` element changes. Writes *write_path* only if given AND
    the conversion applied.
    """
    document = _to_document(source)
    module = Module(document)
    reason = conversion_skip_reason(module)
    if reason is None:
        ConvertHelpToMarkdown().apply(module)
    formatted = apply_selection(document, codes=frozenset())
    if reason is None and write_path is not None:
        write_path.write_bytes(formatted)
    return ConvertHelpResult(
        formatted=formatted, converted=reason is None, skip_reason=reason
    )


def _tokenize_one_to_macros_file(
    document: ToolDocument, macros_file: str
) -> tuple[bytes, str | None, NewMacrosFile | None]:
    """Tokenize a single tool into ``macros_file`` via the shared planner.

    Returns ``(formatted, reason, new_macros)``: the retargeted tool bytes (or the
    unchanged tool on a decline), the decline reason or ``None``, and the macros file
    to write (``None`` when the file already defines the tokens, or on a decline).
    """
    echoed = apply_selection(document, codes=frozenset())
    if document.source_path is None:
        return (
            echoed,
            "--macros-file needs a tool path to resolve the new file beside it "
            "(pass a path, not in-memory bytes)",
            None,
        )
    if "/" in macros_file or "\\" in macros_file or macros_file in {"", ".", ".."}:
        return (
            echoed,
            f"--macros-file {macros_file!r} must be a plain filename beside the tool",
            None,
        )
    macros_path = document.source_path.parent / macros_file
    plan = plan_shared_tokenization(macros_path, target_tools=[document.source_path])
    if not plan.tool_edits:
        reason = plan.skip_reason or (
            plan.skipped[0][1] if plan.skipped else "not eligible for tokenization"
        )
        return echoed, reason, None
    new_macros = (
        NewMacrosFile(
            path=macros_file, content=plan.macros_content, created=plan.macros_created
        )
        if plan.macros_content is not None
        else None
    )
    return plan.tool_edits[0].content, None, new_macros


def tokenize_version(
    source: Source | ToolDocument,
    /,
    *,
    write_path: Path | None = None,
    macros_file: str | None = None,
) -> TokenizeVersionResult:
    """Factor a literal version into @TOOL_VERSION@/@VERSION_SUFFIX@ (GTR094).

    Fail-closed preconditions plus the expansion-equality gate (tokenizing must
    reproduce the original macro expansion byte-for-byte). Never part of
    ``run``/``upgrade``, a multi-element style restructure exposed solely through
    this dedicated entry point (the ``tokenize-version`` command). Serialisation
    goes through fmt.

    With ``macros_file`` (the ``--macros-file`` mode) the tokens go in a macros file
    the tool ``<import>``s instead of an inline ``<macros>`` block: created when
    absent, or merged into an existing file when proven inert for its other importers
    (``version_token_share``). ``new_macros`` carries the file's fmt-serialised content.
    For multi-tool consensus across a shared file use ``tokenize_version_shared``.
    Writes *write_path* (and the macros file beside it) only if given AND tokenized.
    """
    document = _to_document(source)
    module = Module(document)
    reason = tokenization_skip_reason(module)
    new_macros: NewMacrosFile | None = None
    if reason is not None:
        # unchanged tool echoed
        formatted = apply_selection(document, codes=frozenset())
    elif macros_file is None:
        # Inline (default): the GTR094 codemod path.
        TokenizeVersion().apply(module)
        if document.root.get("version") != "@TOOL_VERSION@+galaxy@VERSION_SUFFIX@":
            reason = (
                "expansion-equality gate could not prove the tokenization a "
                "no-op, left untouched"
            )
        formatted = apply_selection(document, codes=frozenset())
    else:
        formatted, reason, new_macros = _tokenize_one_to_macros_file(
            document, macros_file
        )
    if reason is None and write_path is not None:
        write_path.write_bytes(formatted)
        if new_macros is not None:
            (write_path.parent / new_macros.path).write_bytes(new_macros.content)
    return TokenizeVersionResult(
        formatted=formatted,
        tokenized=reason is None,
        skip_reason=reason,
        new_macros=new_macros,
    )


def tokenize_version_shared(
    macros_path: Path, /, *, target_tools: list[Path], write: bool = False
) -> SharedTokenizePlan:
    """Tokenize *target_tools* into the shared ``macros_path`` (create/merge/consensus).

    The group sibling of ``tokenize_version``: it plans the edits for every eligible
    target that shares ``macros_path`` (defining the tokens once, retargeting each tool)
    and, when ``write`` is set, applies them. No backup is taken here (backup ordering
    is the caller's policy, as with ``tokenize_version``). The soundness gate (every
    tool still expands to its original; the token addition is inert for other importers)
    lives in ``version_token_share``.
    """
    plan = plan_shared_tokenization(macros_path, target_tools=list(target_tools))
    if write and plan.skip_reason is None:
        if plan.macros_content is not None:
            plan.macros_path.write_bytes(plan.macros_content)
        for edit in plan.tool_edits:
            edit.path.write_bytes(edit.content)
    return plan


def adopt_version_suffix(
    source: Source | ToolDocument, /, *, write_path: Path | None = None
) -> TokenizeVersionResult:
    """Adopt the IUC ``+galaxy0`` suffix for a bare version (opt-in, identity-changing).

    For a tool whose bare ``version`` equals a package ``<requirement>`` but lacks the
    ``+galaxy`` revision suffix: *add* ``+galaxy0`` and tokenize. This **changes the
    published version** (``1.20`` becomes ``1.20+galaxy0``), so it is never part of
    ``run``/``upgrade`` and is not a behaviour-preserving fix; the author is adopting a
    convention and bumping intentionally. Gated on the controlled-change gate (the macro
    expansion differs solely in the version attribute). Inline only; ``new_macros`` is
    always ``None``.
    """
    document = _to_document(source)
    reason = version_tokens.adopt_suffix_skip_reason(document)
    if reason is None:
        base = document.root.get("version") or ""
        if version_tokens.adopt_suffix_equality_holds(document, base=base):
            version_tokens.tokenize_tree(document.root, base=base, suffix="0")
        else:
            reason = (
                "adopting +galaxy0 would change more than the version (could not prove "
                "the controlled change)"
            )
    formatted = apply_selection(document, codes=frozenset())
    if reason is None and write_path is not None:
        write_path.write_bytes(formatted)
    return TokenizeVersionResult(
        formatted=formatted, tokenized=reason is None, skip_reason=reason
    )


def list_rulesets() -> list[RulesetInfo]:
    """Structured metadata for every ruleset (for the CLI and the MCP server)."""
    code_map = ruleset_codes()
    return [
        RulesetInfo(
            name=name,
            codes=tuple(sorted(code_map[name])),
            is_default=name == DEFAULT_RULESET,
            description=ruleset_description(name) or "",
        )
        for name in ruleset_names()
    ]


def list_rules(*, include_upgrade: bool = False) -> list[RuleInfo]:
    """Structured metadata for every rule, sorted by code.

    With ``include_upgrade=True`` the non-selectable codemods are listed too —
    the upgrade-pipeline ones (GTR007–GTR012 + GTR093, plus the runtime-gated
    GTR014–GTR016) and the opt-in ``convert-help`` conversion (GTR092); by
    default only the selectable rules appear.
    """
    handles = all_handles() if include_upgrade else registry()
    code_map = ruleset_codes()
    return [
        RuleInfo(
            code=code,
            summary=handles[code].meta.summary,
            family=handles[code].family,
            fixable=handles[code].fixable,
            rulesets=tuple(
                name for name in ruleset_names() if code in code_map[name]
            ),
            planemo_linters=tuple(sorted(handles[code].meta.planemo_linters)),
            since=handles[code].meta.since,
            cite=handles[code].meta.cite,
        )
        for code in sorted(handles)
    ]
