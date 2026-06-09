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

from galaxy_tool_refactor_rules.rulesets import (
    DEFAULT_RULESET,
    ruleset_description,
    ruleset_names,
)
from galaxy_tool_xml.binding import Source, load_tool, newest_valid_profile
from galaxy_tool_xml.cheetah_refs import tool_cheetah_references
from galaxy_tool_xml.cheetah_rename import rename_param as _rename_in_tree
from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml_check.detect import sort_violations
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.module import Module
from galaxy_tool_xml_codemod.profile_semantics import (
    crossed_and_applicable_codes,
    tripped_upgrade_codes,
    upgrade_is_behavior_preserving,
)
from galaxy_tool_xml_codemod.runtime_fixes import runtime_fixes_for
from galaxy_tool_xml_codemod.upgrades import UpgradeToLatest
from galaxy_tool_xml_fmt.detect import detect_tool_document_subset
from galaxy_tool_xml_fmt.format import format_tool_document_subset

from galaxy_tool_refactor_registry.adapters import fmt_rule_by_code
from galaxy_tool_refactor_registry.apply import apply_selection
from galaxy_tool_refactor_registry.registry import all_handles, registry
from galaxy_tool_refactor_registry.results import (
    DetectResult,
    FindReferencesResult,
    FormatResult,
    ParamOccurrence,
    RenameParamResult,
    RuleInfo,
    RulesetInfo,
    UpgradeResult,
    render_advisory_note,
)
from galaxy_tool_refactor_registry.rulesets import ruleset_codes

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
    it bailed (see ``galaxy_tool_xml.cheetah_rename``). The work runs on a deep copy, so
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


def _semantic_baseline(declared_profile: str | None) -> str | None:
    """The runtime-behaviour baseline a profile bump is measured against.

    A missing ``profile=`` runs under Galaxy's ``16.01`` default, so that is the
    baseline. A declared literal version is itself. A macro-token (or otherwise
    unparseable) profile can't be placed cheaply, so return ``None`` — the upgrade
    proceeds, but we raise no semantic warning rather than a misleading one.
    """
    if declared_profile is None:
        return "16.01"
    return declared_profile


def _semantic_warning(
    baseline: str | None, target: str | None, tripped: frozenset[str]
) -> str | None:
    """Warn when the bump crosses runtime-behaviour the XSD can't verify.

    Profile upgrade is structurally sound but not behaviour-preserving (codemod
    ``docs/decisions.md`` §22): some bumps change runtime defaults. We can't
    auto-preserve them, so we surface the crossed boundaries for the user to
    review. Of the codes the bump *crosses*, only those whose per-tool detector
    fired (*tripped*, captured on the pre-upgrade tool) actually *apply* — Galaxy's
    advisor detects per-tool, so we do too. ``None`` (no warning) when either
    profile is unknown/unparseable, nothing is crossed, or nothing applies.
    """
    pair = crossed_and_applicable_codes(
        baseline=baseline, target=target, tripped=tripped
    )
    if pair is None:
        return None
    crossed, applicable = pair
    if not applicable:
        return None
    # The catalogue is profile-ascending, so first-seen dedup keeps release order.
    releases = ", ".join(dict.fromkeys(change.profile for change in applicable))
    must_fix = sum(1 for change in applicable if change.level == "must_fix")
    must_fix_note = f", {must_fix} must-fix" if must_fix else ""
    return (
        f"  profile {baseline}→{target}: {len(applicable)} of {len(crossed)}"
        f" crossed Galaxy profile-behaviour change(s) apply to this tool"
        f"{must_fix_note} (releases {releases}); review against"
        " docs/profile_upgrades.md before relying on this upgrade."
    )


def _behavior_preserving_note(
    baseline: str | None, target: str | None, *, preserving: bool | None, advanced: bool
) -> str | None:
    """The positive clean-pass note, or ``None`` when there is no story to tell.

    Emitted only when the bump actually *advanced* the profile (*advanced*) and is
    behaviour-preserving — the affirmative complement of ``_semantic_warning``. A
    no-op upgrade (already latest) is vacuously preserving but says nothing, and a
    bump that crosses an applicable code is reported by the warning instead.
    """
    if not (advanced and preserving):
        return None
    return (
        f"  profile {baseline}→{target}: upgrade crosses no behaviour change that"
        " applies to this tool — behavior-preserving."
    )


def upgrade(
    source: Source | ToolDocument,
    /,
    *,
    codes: frozenset[str],
    write_path: Path | None = None,
) -> UpgradeResult:
    """Profile-upgrade *source*, plus the fixable rules in *codes*, then format.

    ``UpgradeToLatest`` always runs (it is the command's purpose); ``FixTypos``
    runs first when its code is in *codes* (the repair precondition). Runtime-gated
    fixes for the reached profile then apply (e.g. the 21.09 ``from_work_dir``
    strip — a correctness fix the XSD can't enforce). Any other selected codemods
    run after (canonical order), then the selected cosmetic fmt rules. Advisory
    rules in *codes* are reported as notes.
    """
    document = _to_document(source)
    # Capture the runtime baseline AND which upgrade codes the tool trips BEFORE
    # any codemod rewrites ``profile=`` or mutates the features detectors inspect
    # (GTR014/GTR015 fix the very things some detectors look for).
    baseline = _semantic_baseline(document.profile)
    tripped = tripped_upgrade_codes(document)
    advisory = _detect_advisory(document, codes)
    module = Module(document)
    if FixTypos.meta.code in codes:
        FixTypos().apply(module)
    upgrader = UpgradeToLatest()
    upgrader.apply(module)

    # Runtime-gated fixes correct profile behaviours the XSD does not enforce, so
    # they ride neither the validity loop nor the selection. Apply each fix the tool
    # actually CROSSES (`baseline < introduced_profile <= reached`): a tool that
    # stalled below it is left alone (Galaxy ran it under the old behaviour), and one
    # that already declared a profile at/above it is left alone too (Galaxy already
    # applied the new behaviour — rewriting would change, not preserve, behaviour).
    # `baseline` is the pre-upgrade runtime baseline captured above. Upgrade-only —
    # never in `format`/canonical.
    reached = newest_valid_profile(document)
    if reached is not None:
        for fix in runtime_fixes_for(reached, baseline_profile=baseline):
            fix().apply(module)

    # The remaining fixable rules (any selected reorderers + cosmetic fmt) run
    # through the shared apply pipeline; FixTypos already ran as the repair
    # precondition, so it is excluded to avoid a redundant second pass.
    formatted = apply_selection(document, codes=codes - {FixTypos.meta.code})

    steps = tuple(upgrader.upgrade_steps_applied())
    missing = upgrader.missing_upgrade()
    summary = _upgrade_summary(steps, missing)
    # The profile actually reached (a literal version, even when ``profile=`` is a
    # macro token), so the warning and verdict are measured against where the tool
    # landed. The verdict is the positive complement of the warning over the same
    # applicable set (``crossed_and_applicable_codes``), so they can't disagree.
    reached_profile = newest_valid_profile(document)
    semantic = _semantic_warning(baseline, reached_profile, tripped)
    preserving = upgrade_is_behavior_preserving(
        baseline=baseline, target=reached_profile, tripped=tripped
    )
    pass_note = _behavior_preserving_note(
        baseline, reached_profile, preserving=preserving, advanced=bool(steps)
    )
    notes = tuple(
        note
        for note in (
            summary,
            semantic,
            pass_note,
            *(render_advisory_note(violation) for violation in advisory),
        )
        if note is not None
    )
    if write_path is not None:
        write_path.write_bytes(formatted)
    return UpgradeResult(
        formatted=formatted,
        steps_applied=steps,
        missing_upgrade=missing,
        behavior_preserving=preserving,
        advisory=advisory,
        notes=notes,
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

    With ``include_upgrade=True`` the upgrade-only codemods (GTR007–GTR012 plus the
    runtime-gated GTR014–GTR015) are listed too; by default only the selectable
    rules appear.
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
