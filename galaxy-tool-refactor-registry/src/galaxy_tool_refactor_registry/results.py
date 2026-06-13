"""Structured result + introspection types the facade returns.

Library-first: every entry point returns one of these plain frozen dataclasses
(no printing, no exit codes), so the CLI and the MCP server both consume the
same structured data. ``Violation`` (tier 0.5) is the shared finding type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from galaxy_tool_refactor_rules.violation import Violation


def render_advisory_note(violation: Violation, /) -> str:
    """Render one advisory finding as an indented per-file note line."""
    return f"  {violation.code}  {violation.message} (advisory)"


@dataclass(frozen=True)
class FormatResult:
    """The outcome of ``run`` (apply the fixable selection, report advisory).

    Attributes:
        formatted: The canonical-form XML bytes.
        advisory: Advisory (report-only) findings the selection included.
        notes: ``advisory`` rendered as per-file note lines, for the CLI.
    """

    formatted: bytes
    advisory: list[Violation] = field(default_factory=list)
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class UpgradeResult:
    """The outcome of ``upgrade`` (profile repair/upgrade + selected fixers).

    Attributes:
        formatted: The canonical-form XML bytes after upgrade + format.
        baseline_profile: The runtime baseline the upgrade was measured
            against: the declared ``profile=`` (a macro token resolved to its
            version), or Galaxy's ``16.01`` legacy default when undeclared.
            ``None`` when unresolvable (an unplaceable macro token).
        reached_profile: The profile the tool runs under after the upgrade (a
            literal version, even when ``profile=`` is a macro token). Equals
            ``baseline_profile`` when the tool was kept where it sits.
        steps_applied: The from-profiles each structural upgrade step advanced
            past (in either mode).
        missing_upgrade: A profile the modernize walk stalled at with no
            registered upgrade, or ``None`` (always ``None`` under the minimal
            default, whose stall is "the floor is unreachable", reported via
            the notes with the profile left unchanged).
        behavior_preserving: Whether the profile bump crossed no Galaxy
            behaviour-change code that *applies* to this tool and was not
            cleared by an auto-fix (so it changes no runtime behaviour the tool
            exercises). ``True`` = clean pass (a kept tool crosses nothing, so
            it is vacuously preserving), ``False`` = ≥1 applicable uncleared
            code (a *needed* minimal bump reports its crossings honestly too),
            ``None`` = undetermined (the baseline is unplaceable, e.g. an
            unresolved macro token). Structurally independent of
            ``missing_upgrade``, which reports a structural stall.
        stopped_at: Walk-mode-only: the profile the modernize walk was
            deliberately capped at when below the latest (the behaviour gate's
            ceiling, or an explicit ``target_profile``); ``None`` when the walk
            was free to reach the latest profile, and always ``None`` under the
            minimal default (no walk runs).
        blocking_codes: Every applicable must_fix code between the baseline and
            the latest profile that no auto-fix clears. Under the minimal
            default this is the preview of what a ``modernize`` walk would stop
            at; in walk modes it is the user's review list, reported even when
            ``allow_behavior_change`` lifted the gate.
        auto_fixed_codes: The applicable must_fix codes the upgrade crossed and
            cleared by executing their mapped fix (verified by re-detection).
        advisory: Advisory findings the selection included.
        notes: The upgrade summary plus advisory note lines, for the CLI.
    """

    formatted: bytes
    baseline_profile: str | None = None
    reached_profile: str | None = None
    steps_applied: tuple[str, ...] = ()
    missing_upgrade: str | None = None
    behavior_preserving: bool | None = None
    stopped_at: str | None = None
    blocking_codes: tuple[str, ...] = ()
    auto_fixed_codes: tuple[str, ...] = ()
    advisory: list[Violation] = field(default_factory=list)
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConvertHelpResult:
    """The outcome of ``convert_help`` (the opt-in RST -> Markdown conversion).

    Attributes:
        formatted: The serialised XML bytes (unchanged when not converted).
        converted: Whether the ``<help>`` body was converted to Markdown.
        skip_reason: Why the conversion did not apply (``None`` when converted) —
            the same decision path the GTR092 codemod runs.
    """

    formatted: bytes
    converted: bool
    skip_reason: str | None = None


@dataclass(frozen=True)
class NewMacrosFile:
    """A macros file a facade entry point would write beside the tool.

    Attributes:
        path: The import path, relative to the tool (e.g. ``"macros.xml"``).
        content: The full fmt-serialised bytes of the file.
        created: ``True`` when the file is newly created, ``False`` when the tokens
            were merged into an existing file (the caller should back it up first).
    """

    path: str
    content: bytes
    created: bool = True


@dataclass(frozen=True)
class TokenizeVersionResult:
    """The outcome of ``tokenize_version`` (the opt-in @TOOL_VERSION@ extraction).

    Attributes:
        formatted: The serialised XML bytes (unchanged when not tokenized).
        tokenized: Whether the version was factored into the IUC tokens.
        skip_reason: Why the tokenization did not apply (``None`` when applied) —
            the same decision path the GTR094 codemod runs.
        new_macros: The separate ``macros.xml`` to create (``--macros-file`` mode),
            or ``None`` for the inline default. Set only when ``tokenized``.
    """

    formatted: bytes
    tokenized: bool
    skip_reason: str | None = None
    new_macros: NewMacrosFile | None = None


@dataclass(frozen=True)
class DetectResult:
    """The outcome of ``detect`` (report-only over the selection).

    Attributes:
        violations: Every finding, sorted by ``(sourceline, code)``.
        advisory_codes: Which of the codes present are advisory (report-only);
            the rest are fixable (what ``run`` would change).
    """

    violations: list[Violation] = field(default_factory=list)
    advisory_codes: frozenset[str] = frozenset()

    def is_advisory(self, violation: Violation, /) -> bool:
        """Whether *violation* is an advisory finding (vs. a fixable one)."""
        return violation.code in self.advisory_codes


@dataclass(frozen=True)
class RuleInfo:
    """Machine-readable metadata for one rule (``list_rules``)."""

    code: str
    summary: str
    family: str
    fixable: bool
    rulesets: tuple[str, ...]
    planemo_linters: tuple[str, ...]
    since: str
    cite: str | None = None


@dataclass(frozen=True)
class RulesetInfo:
    """Machine-readable metadata for one ruleset (``list_rulesets``)."""

    name: str
    codes: tuple[str, ...]
    is_default: bool
    description: str


@dataclass(frozen=True)
class ParamOccurrence:
    """One Cheetah ``$var`` reference site for ``find_references``."""

    section: str
    sourceline: int
    reference: str


@dataclass(frozen=True)
class FindReferencesResult:
    """Where a parameter name is referenced across a tool's Cheetah sections."""

    name: str
    occurrences: tuple[ParamOccurrence, ...] = ()


@dataclass(frozen=True)
class RenameParamResult:
    """The outcome of ``rename_param`` (the mutating sibling of ``find_references``).

    Rename is atomic: either every live reference plus the definition is rewritten
    (``changed``), or nothing is and ``reason`` explains why it bailed.

    Attributes:
        old: The parameter name renamed from.
        new: The parameter name renamed to.
        changed: Whether the rename was applied.
        renamed: How many sites were rewritten (``0`` on a bail).
        reason: The bail reason (``shadowed`` / ``mixed-content`` / ``lexer-bail`` /
            ``filter-bare-ref`` / ``cross-ref-residual`` / ``not-found`` /
            ``invalid-name`` / ``no-op``), or ``None`` when ``changed``.
        formatted: The serialised XML bytes after rename, or ``None`` on a bail.
    """

    old: str
    new: str
    changed: bool
    renamed: int = 0
    reason: str | None = None
    formatted: bytes | None = None


@dataclass(frozen=True)
class LintSkipRemoval:
    """One ``.lint_skip`` line the toolchain proved is no longer needed.

    Attributes:
        name: The planemo linter name whose suppression line was removed.
        codes: The GTR codes that completely cover that linter.
        fixed: ``True`` when a fix cleared the linter (it had been firing);
            ``False`` when it was already clean (a stale suppression).
    """

    name: str
    codes: tuple[str, ...]
    fixed: bool


@dataclass(frozen=True)
class LintSkipResult:
    """The outcome of ``reconcile_lint_skip`` over one ``.lint_skip`` directory.

    Only provable removals are reported; suppressions the toolchain cannot fix,
    cannot prove, or does not cover are left untouched and unmentioned (the
    author suppressed them deliberately; ``check`` reports the full picture).

    Attributes:
        removed: The lines proven removable (fixed-and-clean or already-clean
            under complete coverage).
        kept_lines: The rewritten ``.lint_skip`` raw lines, in original order
            with the removed name-lines dropped and every other line (comments,
            blanks, names left alone) preserved verbatim.
        file_emptied: Whether nothing but blank lines remains (the caller may
            delete the ``.lint_skip`` file).
        documents: Per input document, the serialised bytes when a persisted fix
            changed it, else ``None`` (so the caller writes only what changed).
    """

    removed: tuple[LintSkipRemoval, ...] = ()
    kept_lines: tuple[str, ...] = ()
    file_emptied: bool = False
    documents: tuple[bytes | None, ...] = ()
