"""Wrap each rule family into a uniform ``RuleHandle``.

Three builders, one per family, plus the family class enumerations the registry
and apply phase consume. The *selectable* codemods are those that declare at least
one ruleset (``RuleMeta.rulesets`` — typo repair + the reorderers + the CDATA/quote
fixes, the safe format-time rules); the remaining GTR codemods declare no ruleset
and are **non-selectable**: the upgrade-pipeline steps (``UpdateProfile`` + the
per-version ``Upgrade*`` + the ``UpgradeToLatest`` orchestrator + the runtime-gated
fixes) and the opt-in-command-only codemods (``OPT_IN_COMMAND_BY_CODE``) — all
exposed for introspection only.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from galaxy_tool_codemod.catalog import coded_codemods
from galaxy_tool_codemod.codemods.reorder_tool_children import ReorderToolChildren
from galaxy_tool_codemod.module import Module
from galaxy_tool_fmt.detect import detect_tool_document_subset
from galaxy_tool_fmt.format import all_rules, format_tool_document_subset
from galaxy_tool_lint.detect import all_checks
from galaxy_tool_source.macros import top_level_expand_tags

from galaxy_tool_refactor_registry.handle import RuleHandle

if TYPE_CHECKING:
    from collections.abc import Mapping

    from galaxy_tool_codemod.codemod import CodemodCommand
    from galaxy_tool_fmt.rules import Rule
    from galaxy_tool_lint.rules import CheckRule
    from galaxy_tool_refactor_rules.violation import Violation
    from galaxy_tool_source.document import ToolDocument

# The opt-in-command-only codemods: no ruleset (never selectable) and not part of
# the upgrade pipeline either — each is applied solely by its own dedicated
# command (codemod ``docs/decisions.md`` §38, registry D18). Hand-known, code →
# command name; pinned by a partition tripwire in ``test_ruleset_membership.py``.
OPT_IN_COMMAND_BY_CODE: Mapping[str, str] = MappingProxyType(
    {"GTR092": "convert-help", "GTR094": "tokenize-version"}
)


def selectable_codemods() -> tuple[type[CodemodCommand], ...]:
    """Codemods a user may select — those that declare at least one ruleset."""
    return tuple(cls for cls in coded_codemods() if cls.meta.rulesets)


def non_selectable_codemods() -> tuple[type[CodemodCommand], ...]:
    """The GTR codemods with no ruleset → not independently selectable.

    The ``upgrade``-pipeline codemods (GTR007–GTR016, GTR093) plus the
    opt-in-command-only ones (``OPT_IN_COMMAND_BY_CODE`` — ``convert-help``/GTR092
    and ``tokenize-version``/GTR094); exposed for introspection
    (``list_rules(include_upgrade=True)``) only.
    """
    return tuple(cls for cls in coded_codemods() if not cls.meta.rulesets)


def fmt_rules() -> tuple[type[Rule], ...]:
    """The cosmetic fmt rules, in ``meta.order``."""
    return all_rules()


def fmt_rule_by_code() -> dict[str, type[Rule]]:
    """Map each cosmetic fmt rule code to its class (for code→class lookup)."""
    return {cls.meta.code: cls for cls in all_rules()}


def advisory_checks() -> tuple[type[CheckRule], ...]:
    """The advisory (detect-only) checks."""
    return all_checks()


def gtr013_expand_ranks(document: ToolDocument) -> dict[int, str]:
    """Resolve each top-level ``<expand>`` to the single IUC tag it produces.

    The facade-side input to the GTR013 ``<expand>`` resolution layer (codemod
    ``docs/decisions.md`` §53): for each top-level ``<expand>`` child, faithfully
    expand it (tier-1 ``top_level_expand_tags``) and, when it yields exactly one
    element tag, record ``{child index -> tag}`` so ``ReorderToolChildren`` can
    place it in that tag's IUC slot. Anything that does not resolve to a single tag
    (multi-element, unresolvable import, unknown macro) is omitted, so the codemod
    pins it (the safe floor). Lives here, not in the codemod, because macro
    expansion is tier-1 work the facade orchestrates — the codemod stays a pure
    tree op that receives a plain index→tag map (registry decisions D25).
    """
    ranks: dict[int, str] = {}
    for index, child in enumerate(document.root):
        if not isinstance(child.tag, str) or child.tag != "expand":
            continue
        tags = top_level_expand_tags(document, child)
        if tags is not None and len(tags) == 1:
            ranks[index] = tags[0]
    return ranks


def codemod_handle(cls: type[CodemodCommand], /) -> RuleHandle:
    """Wrap a codemod class as a ``RuleHandle`` (detect/apply via a ``Module``).

    ``ReorderToolChildren`` (GTR013) is the one codemod the facade gives more than
    the bare tree: it is constructed with a per-document ``expand_ranks`` map
    (``gtr013_expand_ranks``) so an opaque top-level ``<expand>`` is placed in its
    resolved IUC slot rather than pinned. This is a documented, intentional
    asymmetry — every other codemod is `cls()` (the canonical-pipeline contract);
    only GTR013 needs the facade's tier-1 macro resolution (registry decisions D25).
    """

    def _instance(document: ToolDocument) -> CodemodCommand:
        if cls is ReorderToolChildren:
            return cls(expand_ranks=gtr013_expand_ranks(document))
        return cls()

    def detect(document: ToolDocument) -> list[Violation]:
        changes = _instance(document).detect(Module(document))
        return [change.to_violation() for change in changes]

    def apply(document: ToolDocument) -> None:
        _instance(document).apply(Module(document))

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
