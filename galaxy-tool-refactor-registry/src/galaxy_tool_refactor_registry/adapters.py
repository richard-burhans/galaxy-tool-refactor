"""Wrap each rule family into a uniform ``RuleHandle``.

Three builders, one per family, plus the family class enumerations the registry
and apply phase consume. The *selectable* codemods are exactly
``CANONICAL_CODEMODS`` (typo repair + the reorderers — the safe, format-time
rules); the remaining GTR codemods are the upgrade-only steps
(``UpdateProfile`` + the per-version ``Upgrade*`` + the ``UpgradeToLatest``
orchestrator) which are internal to the ``upgrade`` pipeline and not
independently selectable — they are exposed for introspection only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from galaxy_tool_xml_check.detect import all_checks
from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS
from galaxy_tool_xml_codemod.catalog import coded_codemods
from galaxy_tool_xml_codemod.module import Module
from galaxy_tool_xml_fmt.detect import detect_tool_document_subset
from galaxy_tool_xml_fmt.format import all_rules, format_tool_document_subset

from galaxy_tool_refactor_registry.handle import RuleHandle

if TYPE_CHECKING:
    from galaxy_tool_refactor_rules.violation import Violation
    from galaxy_tool_xml.document import ToolDocument
    from galaxy_tool_xml_check.rules import CheckRule
    from galaxy_tool_xml_codemod.codemod import CodemodCommand
    from galaxy_tool_xml_fmt.rules import Rule


def selectable_codemods() -> tuple[type[CodemodCommand], ...]:
    """Codemods a user may select — the canonical (format-time) pipeline set."""
    return CANONICAL_CODEMODS


def upgrade_only_codemods() -> tuple[type[CodemodCommand], ...]:
    """The GTR codemods internal to ``upgrade`` (not independently selectable)."""
    canonical = set(CANONICAL_CODEMODS)
    return tuple(cls for cls in coded_codemods() if cls not in canonical)


def fmt_rules() -> tuple[type[Rule], ...]:
    """The cosmetic fmt rules, in ``meta.order``."""
    return all_rules()


def fmt_rule_by_code() -> dict[str, type[Rule]]:
    """Map each cosmetic fmt rule code to its class (for code→class lookup)."""
    return {cls.meta.code: cls for cls in all_rules()}


def advisory_checks() -> tuple[type[CheckRule], ...]:
    """The advisory (detect-only) checks."""
    return all_checks()


def codemod_handle(cls: type[CodemodCommand], /) -> RuleHandle:
    """Wrap a codemod class as a ``RuleHandle`` (detect/apply via a ``Module``)."""

    def detect(document: ToolDocument) -> list[Violation]:
        return [change.to_violation() for change in cls().detect(Module(document))]

    def apply(document: ToolDocument) -> None:
        cls().apply(Module(document))

    return RuleHandle(
        meta=cls.meta,
        family="codemod",
        fixable=not cls.meta.detect_only,
        detect=detect,
        apply=apply,
    )


def fmt_handle(cls: type[Rule], /) -> RuleHandle:
    """Wrap a single fmt rule via the per-rule subset seams (tier-3 D15)."""

    def detect(document: ToolDocument) -> list[Violation]:
        return detect_tool_document_subset(document, rule_classes=(cls,))

    def apply(document: ToolDocument) -> None:
        # Mutates the document's tree in place; the returned bytes are discarded
        # here (apply_selection serialises once at the end of the fmt phase).
        #
        # Caveat: this applies ONE fmt rule in isolation. fmt's whitespace rules
        # are order-sensitive and can cancel each other's churn, so a single-rule
        # apply can leave non-canonical trivia (same warning as
        # `format_tool_document_subset`). The facade does NOT use this path — its
        # `apply.apply_selection` batches all selected fmt rules through one
        # `format_tool_document_subset` call so they run as a coherent group. This
        # closure exists only to keep the `RuleHandle` interface uniform
        # (`fixable` codemod/fmt rules both expose a non-None `apply`); call it
        # per-rule only when you mean to.
        format_tool_document_subset(document, rule_classes=(cls,))

    return RuleHandle(
        meta=cls.meta,
        family="fmt",
        fixable=not cls.meta.detect_only,
        detect=detect,
        apply=apply,
    )


def check_handle(cls: type[CheckRule], /) -> RuleHandle:
    """Wrap an advisory check (detect-only: ``apply is None``)."""

    def detect(document: ToolDocument) -> list[Violation]:
        return list(cls().detect(document))

    return RuleHandle(
        meta=cls.meta,
        family="check",
        fixable=False,
        detect=detect,
        apply=None,
    )
