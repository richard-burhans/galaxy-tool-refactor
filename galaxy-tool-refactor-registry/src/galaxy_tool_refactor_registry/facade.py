"""The library-first entry points: ``run`` / ``upgrade`` / ``detect`` + introspection.

Every function takes a *source* (a filesystem path, raw XML ``bytes``, or an
existing ``ToolDocument``) and a resolved *codes* set, and returns a structured
result — no ``click``, no ``sys.exit``, no printing. Files are written only when
a ``write_path`` is given. This is the shared core the ``galaxy-tool-refactor``
CLI and a future MCP server (``galaxy-tool-refactor-mcp``) both sit on top of.

``codes`` is what ``resolve.resolve_codes`` / ``resolve.resolve_upgrade_codes``
produce. ``run`` applies the fixable rules in the selection and reports advisory
(``detect_only``) ones as notes (never mutating for them); ``detect`` reports all
of them without mutating; ``upgrade`` always performs the profile upgrade and
additionally applies the fixable rules in the selection.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from galaxy_tool_xml.binding import Source, load_tool
from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml_check.detect import sort_violations
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.module import Module
from galaxy_tool_xml_codemod.upgrades import UpgradeToLatest
from galaxy_tool_xml_fmt.detect import detect_tool_document_subset

from galaxy_tool_refactor_registry.adapters import fmt_rule_by_code
from galaxy_tool_refactor_registry.apply import apply_selection
from galaxy_tool_refactor_registry.presets import (
    DEFAULT_PRESET,
    preset_description,
    preset_names,
    presets,
)
from galaxy_tool_refactor_registry.registry import all_handles, registry
from galaxy_tool_refactor_registry.results import (
    DetectResult,
    FormatResult,
    PresetInfo,
    RuleInfo,
    UpgradeResult,
    render_advisory_note,
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


def upgrade(
    source: Source | ToolDocument,
    /,
    *,
    codes: frozenset[str],
    write_path: Path | None = None,
) -> UpgradeResult:
    """Profile-upgrade *source*, plus the fixable rules in *codes*, then format.

    ``UpgradeToLatest`` always runs (it is the command's purpose); ``FixTypos``
    runs first when its code is in *codes* (the repair precondition). Any other
    selected codemods run after the upgrade (canonical order), then the selected
    cosmetic fmt rules. Advisory rules in *codes* are reported as notes.
    """
    document = _to_document(source)
    advisory = _detect_advisory(document, codes)
    module = Module(document)
    if FixTypos.meta.code in codes:
        FixTypos().apply(module)
    upgrader = UpgradeToLatest()
    upgrader.apply(module)

    # The remaining fixable rules (any selected reorderers + cosmetic fmt) run
    # through the shared apply pipeline; FixTypos already ran as the repair
    # precondition, so it is excluded to avoid a redundant second pass.
    formatted = apply_selection(document, codes=codes - {FixTypos.meta.code})

    steps = tuple(upgrader.upgrade_steps_applied())
    missing = upgrader.missing_upgrade()
    summary = _upgrade_summary(steps, missing)
    notes = tuple(
        note
        for note in (
            summary,
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
        advisory=advisory,
        notes=notes,
    )


def list_presets() -> list[PresetInfo]:
    """Structured metadata for every preset (for the CLI and a future MCP)."""
    preset_map = presets()
    return [
        PresetInfo(
            name=name,
            codes=tuple(sorted(preset_map[name])),
            is_default=name == DEFAULT_PRESET,
            description=preset_description(name),
        )
        for name in preset_names()
    ]


def list_rules(*, include_upgrade: bool = False) -> list[RuleInfo]:
    """Structured metadata for every rule, sorted by code.

    With ``include_upgrade=True`` the upgrade-only codemods (GTX007–GTX012) are
    listed too; by default only the selectable rules appear.
    """
    handles = all_handles() if include_upgrade else registry()
    preset_map = presets()
    return [
        RuleInfo(
            code=code,
            summary=handles[code].meta.summary,
            family=handles[code].family,
            fixable=handles[code].fixable,
            presets=tuple(
                name for name in preset_names() if code in preset_map[name]
            ),
            since=handles[code].meta.since,
            cite=handles[code].meta.cite,
        )
        for code in sorted(handles)
    ]
