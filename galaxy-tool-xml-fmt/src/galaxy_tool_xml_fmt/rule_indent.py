"""GTR001: canonical 4-space indentation.

Walks the tree and emits ``SetText`` / ``SetTail`` edits so every
element's child-leading and sibling-trailing whitespace matches the
canonical form: one ``\\n`` followed by ``4 * depth`` spaces.

CDATA content is preserved because both ``SetText`` and ``SetTail``
route through ``safe_set_text`` / ``safe_set_tail``, which only write
when the existing value is ``None`` or pure whitespace.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_fmt.edits import Edit, SetTail, SetText
from galaxy_tool_xml_fmt.rules import Rule

if TYPE_CHECKING:
    from lxml import etree


_INDENT = "    "


class CanonicalIndent(Rule):
    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR001",
        summary="Canonical 4-space indentation; no tabs.",
        since="0.0.1",
        cite="https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html",
        order=10,
        applies_to=frozenset({"tool", "macro"}),
    )

    def edits(self, tree: etree._ElementTree) -> Iterable[Edit]:
        """Yield ``SetText``/``SetTail`` edits normalising indentation to 4 spaces."""
        return list(_walk(tree.getroot(), depth=0))


def _walk(element: etree._Element, *, depth: int) -> Iterable[Edit]:
    children = list(element)
    if not children:
        return
    inner = "\n" + _INDENT * (depth + 1)
    outer = "\n" + _INDENT * depth
    yield SetText(element=element, value=inner)
    last_index = len(children) - 1
    for index, child in enumerate(children):
        yield from _walk(child, depth=depth + 1)
        yield SetTail(
            element=child,
            value=outer if index == last_index else inner,
        )
