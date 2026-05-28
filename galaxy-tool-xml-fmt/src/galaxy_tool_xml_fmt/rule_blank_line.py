"""GTX003: one blank line between top-level <tool> children.

Editorial rule from ``PLAN.md``: "one blank between sibling top-level
sections, no blank inside dense leaf sequences." Only the top-level
children of ``<tool>`` are affected; nested elements retain the
single-newline indentation supplied by GTX001.

Depends on GTX001 having set canonical indentation first (registration
order in ``format`` is the ordering). ``safe_set_tail`` will only write
when the existing tail is whitespace-only, so this rule cannot trample
non-whitespace content.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_xml_fmt.edits import Edit, SetTail
from galaxy_tool_xml_fmt.rules import Rule, RuleMeta

if TYPE_CHECKING:
    from lxml import etree


_BLANK_TAIL = "\n\n    "


class BlankLineBetweenSections(Rule):
    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX003",
        summary="One blank line between top-level children of <tool>.",
        since="0.1.0",
        order=90,
    )

    def apply(self, tree: etree._ElementTree) -> Iterable[Edit]:
        """Yield ``SetTail`` edits adding a blank line between each top-level child."""
        root = tree.getroot()
        if root.tag != "tool":
            return []
        children = list(root)
        if len(children) < 2:
            return []
        return [SetTail(element=child, value=_BLANK_TAIL) for child in children[:-1]]
