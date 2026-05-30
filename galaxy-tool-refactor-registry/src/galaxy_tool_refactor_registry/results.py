"""Structured result + introspection types the facade returns.

Library-first: every entry point returns one of these plain frozen dataclasses
(no printing, no exit codes), so the CLI and a future MCP server both consume the
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
    """The outcome of ``upgrade`` (profile upgrade + selected fixers).

    Attributes:
        formatted: The canonical-form XML bytes after upgrade + format.
        steps_applied: The from-profiles each upgrade step advanced past.
        missing_upgrade: A profile the tool stalled at with no registered
            upgrade, or ``None`` if it reached the latest (or had nothing to do).
        advisory: Advisory findings the selection included.
        notes: The upgrade summary plus advisory note lines, for the CLI.
    """

    formatted: bytes
    steps_applied: tuple[str, ...] = ()
    missing_upgrade: str | None = None
    advisory: list[Violation] = field(default_factory=list)
    notes: tuple[str, ...] = ()


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
    presets: tuple[str, ...]
    since: str
    cite: str | None = None


@dataclass(frozen=True)
class PresetInfo:
    """Machine-readable metadata for one preset (``list_presets``)."""

    name: str
    codes: tuple[str, ...]
    is_default: bool
    description: str
