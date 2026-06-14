"""The cosmetic format pipeline entry point.

``format_tool_document`` applies fmt's cosmetic rules (indentation,
blank lines, empty-element shorthand) and serialises. It does **not**
perform structural canonicalisation — that's tier 2 (``galaxy-tool-codemod``)'s
``canonical_codemods()``. This package has no dependency on the codemod
package; minimal installs (xml + fmt) get cosmetic-only formatting. The
``galaxy-tool-refactor`` app (``galaxy-tool-refactor-cli``) composes the
codemod and fmt tiers for the full canonical / upgrade workflows.
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from galaxy_tool_fmt.edits import apply_edits
from galaxy_tool_fmt.rule_empty_element import EmptyElementShorthand
from galaxy_tool_fmt.rule_indent import CanonicalIndent
from galaxy_tool_fmt.rules import Rule
from galaxy_tool_fmt.serializer import to_bytes

if TYPE_CHECKING:
    from galaxy_tool_source.document import MacroDocument, ToolDocument
    from lxml import etree


@cache
def all_rules() -> tuple[type[Rule], ...]:
    """Return the active cosmetic formatter rules sorted by application order.

    GTR003 (``BlankLineBetweenSections``) is **parked** pending IUC input on whether
    the blank-line-between-top-level-sections convention is wanted (it has no external
    citation, and a corpus sweep found only 13.3% of section boundaries / 30% of tools
    already use it: ``scripts.measure blank-line-adoption``). The rule stays in source
    (``rule_blank_line.py``, still unit-tested) for a one-line re-enable; leaving it out
    of ``all_rules()`` ceases emission everywhere (the standalone CLI and the registry
    both build from this list). See ``docs/decisions.md`` §D4 and
    ``../../docs/iuc_conference_questions.md`` §4.
    """
    rule_classes: list[type[Rule]] = [
        CanonicalIndent,
        EmptyElementShorthand,
    ]
    return tuple(sorted(rule_classes, key=lambda cls: cls.meta.order))


def rules_for_kind(kind: str, /) -> tuple[type[Rule], ...]:
    """Return the active cosmetic rules that apply to a *kind* of document.

    *kind* is ``"tool"`` or ``"macro"``; a rule applies when *kind* is in its
    ``meta.applies_to``. Generic XML rules (indent, empty-element shorthand)
    apply to both; the blank-line-between-``<tool>``-sections rule applies only
    to tools. Order is preserved (``all_rules()`` is already ``meta.order``-sorted).
    """
    return tuple(cls for cls in all_rules() if kind in cls.meta.applies_to)


def _apply_rules(
    tree: etree._ElementTree, rule_classes: tuple[type[Rule], ...]
) -> bytes:
    """Run *rule_classes* (in ``meta.order``) over *tree*; serialise to bytes."""
    for rule_cls in sorted(rule_classes, key=lambda cls: cls.meta.order):
        apply_edits(rule_cls().edits(tree))
    return to_bytes(tree)


def format_tool_document(document: ToolDocument) -> bytes:
    """Format *document* with the tool-applicable cosmetic rules; serialise to bytes.

    Runs every active cosmetic rule that applies to a ``<tool>`` against the
    document's mutable lxml tree in order, then serialises. The input document is
    mutated in-place; callers that need the original tree should pass a copy.
    **No structural canonicalisation** — for the full canonical pipeline use the
    ``galaxy-tool-refactor format`` app command, or apply
    ``galaxy_tool_codemod.canonical.canonical_codemods()`` yourself first.

    Args:
        document: A parsed Galaxy tool document.

    Returns:
        Canonical-form XML bytes (cosmetic-only).
    """
    return _apply_rules(document.tree, rules_for_kind("tool"))


def format_macro_document(document: MacroDocument) -> bytes:
    """Format a macro-library document with the macro-applicable cosmetic rules.

    The ``<macros>``-file counterpart to ``format_tool_document``: runs only the
    cosmetic rules whose ``meta.applies_to`` includes ``"macro"`` (the generic
    XML rules — indentation, empty-element shorthand — but not the
    blank-line-between-``<tool>``-sections rule, which is tool-specific). The
    document's tree is mutated in place.
    """
    return _apply_rules(document.tree, rules_for_kind("macro"))


def format_tool_document_subset(
    document: ToolDocument, *, rule_classes: tuple[type[Rule], ...]
) -> bytes:
    """Format *document* with only *rule_classes*, then serialise to bytes.

    Like ``format_tool_document`` but runs a caller-chosen subset of the
    cosmetic rules. The rules run in ``meta.order`` regardless of the order
    *rule_classes* is given in (the formatter's whitespace rules are
    order-sensitive; see ``docs/decisions.md`` D15). An empty *rule_classes*
    serialises the tree unchanged.

    This is the per-rule seam the rule-selection facade
    (``galaxy-tool-refactor-registry``) uses. A coherent subset (the shipped
    rulesets always include the full GTR001/GTR003/GTR004 trio) is idempotent;
    an arbitrary single-rule subset is the caller's responsibility — running
    one whitespace rule without the others can leave non-canonical trivia.

    Args:
        document: A parsed Galaxy tool document (mutated in place).
        rule_classes: The cosmetic rules to run; reordered to ``meta.order``.

    Returns:
        XML bytes after applying the selected rules.
    """
    return _apply_rules(document.tree, rule_classes)
