"""The cosmetic detect (lint) phase: report where a document is non-canonical.

``detect_tool_document`` is the non-mutating counterpart to
``format_tool_document``. The fmt rules emit overlapping, *unconditional*
whitespace rewrites (GTR001 and GTR003 both target top-level-child tails, with
GTR003 winning by order), so an individual ``Edit`` "changing the tree" does not
mean the document deviates from canonical form — the intermediate change may be
reverted by a later rule. The only faithful signal is the **net** effect of the
whole pipeline.

So detection formats a throwaway copy through the same pipeline, records for each
element the last rule that altered its whitespace, then diffs the formatted copy
against the original. Each element whose net text/tail differs yields one
``Violation`` attributed to that owning rule. Net-zero churn is silent, so an
already-canonical document reports nothing — exact parity with
``format_tool_document`` (which leaves a canonical document byte-identical). See
``docs/decisions.md`` § on the detect/fix split.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from galaxy_tool_refactor_rules.violation import Violation

from galaxy_tool_xml_fmt.edits import apply_edits
from galaxy_tool_xml_fmt.format import all_rules, rules_for_kind

if TYPE_CHECKING:
    from galaxy_tool_refactor_rules.meta import RuleMeta
    from galaxy_tool_xml.document import MacroDocument, ToolDocument
    from lxml import etree

    from galaxy_tool_xml_fmt.rules import Rule


def _trivia(element: etree._Element, /) -> tuple[str | None, str | None]:
    """The whitespace an fmt rule can touch: an element's ``text`` and ``tail``."""
    return element.text, element.tail


def detect_tool_document(document: ToolDocument, /) -> list[Violation]:
    """Report each element whose cosmetic whitespace deviates from canonical form.

    Non-mutating: the input document is untouched; all work happens on a deep
    copy. Returns one ``Violation`` per element whose net ``text``/``tail`` the
    cosmetic pipeline would change, located on the *original* tree (so line
    numbers match the source) and attributed to the rule that produced the final
    value.
    """
    return detect_tool_document_subset(document, rule_classes=all_rules())


def detect_tool_document_subset(
    document: ToolDocument, *, rule_classes: tuple[type[Rule], ...]
) -> list[Violation]:
    """Like ``detect_tool_document`` but only for *rule_classes*.

    Runs the chosen subset (in ``meta.order``) over a throwaway copy and reports
    the net trivia change per element, attributed to the owning rule. This is the
    per-rule detect seam the rule-selection facade
    (``galaxy-tool-refactor-registry``) uses; the whole-pipeline
    ``detect_tool_document`` is this called with ``all_rules()``.

    The same caveat as ``format_tool_document_subset`` applies: an incoherent
    single-rule subset may report churn a coherent subset would cancel out.
    """
    return _detect_over_tree(document.tree, rule_classes)


def detect_macro_document(document: MacroDocument, /) -> list[Violation]:
    """Report where a macro-library file's cosmetic whitespace is non-canonical.

    The ``<macros>``-file counterpart to ``detect_tool_document``: runs the
    macro-applicable cosmetic rules (``rules_for_kind("macro")`` — the generic
    XML rules) net-diff over a throwaway copy, attributing each changed node to
    its owning rule. Non-mutating.
    """
    return _detect_over_tree(document.tree, rules_for_kind("macro"))


def _detect_over_tree(
    original: etree._ElementTree, rule_classes: tuple[type[Rule], ...]
) -> list[Violation]:
    """Net-diff the cosmetic *rule_classes* over a copy of *original*; report changes.

    The shared core of the tool and macro detect functions: format a deep copy
    through the rules (in ``meta.order``), recording the last rule to touch each
    node's whitespace, then report one ``Violation`` per node whose net
    ``text``/``tail`` differs from the source, located on the source tree.
    """
    work = copy.deepcopy(original)
    ordered_rules = sorted(rule_classes, key=lambda cls: cls.meta.order)
    # Include Comment / PI nodes, not just elements: GTR001 and GTR003 rewrite the
    # *tail* of every child of an element, comments included (a blank line after a
    # top-level comment is a real format change), so omitting them would let
    # detect miss changes the pipeline makes.
    #
    # lxml hands out a fresh Python proxy per ``.iter()`` call, so ``id()`` is
    # only stable for proxies we hold onto. Capture each node list once and reuse
    # those proxies throughout; reads still see live mutations because a proxy is
    # a view over the shared underlying node.
    work_nodes = list(work.iter())
    # Per node, the last rule that changed its whitespace — after the pipeline
    # that is the rule which owns the node's final, net value.
    owner: dict[int, RuleMeta] = {}
    for rule_cls in ordered_rules:
        before = {id(node): _trivia(node) for node in work_nodes}
        apply_edits(rule_cls().edits(work))
        for node in work_nodes:
            if _trivia(node) != before[id(node)]:
                owner[id(node)] = rule_cls.meta
    source_nodes = list(original.iter())
    violations: list[Violation] = []
    for source_node, formatted_node in zip(source_nodes, work_nodes, strict=True):
        if _trivia(source_node) == _trivia(formatted_node):
            continue  # net-unchanged — already canonical (or churn cancelled out)
        meta = owner[id(formatted_node)]
        line = source_node.sourceline
        violations.append(
            Violation(
                code=meta.code,
                sourceline=line if line is not None else 0,
                xpath=str(original.getpath(source_node)),
                message=meta.summary,
            )
        )
    return violations
