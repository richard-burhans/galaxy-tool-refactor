"""GTX004: empty-element shorthand.

When a leaf element carries only whitespace as text (e.g. a tool author
wrote ``<inputs>\\n</inputs>`` rather than ``<inputs/>``), normalise it
to the short form by clearing ``element.text``. lxml then serialises
the element as ``<foo/>``.

Empty-string text (``element.text == ""``) is deliberately left alone:
it may be the surface form of an empty CDATA wrapper, and there is no
lxml-level way to distinguish an empty CDATA section from an empty
string. The conservative choice is to only touch text that is actually
whitespace.

Editorial; no IUC citation. PLAN.md prescribes ``<foo/>`` over
``<foo></foo>`` where the content model permits.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_fmt.edits import ClearText, Edit
from galaxy_tool_xml_fmt.rules import Rule

if TYPE_CHECKING:
    from lxml import etree


class EmptyElementShorthand(Rule):
    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX004",
        summary="Collapse empty-with-whitespace leaves to <foo/> form.",
        since="0.0.1",
        order=20,
        applies_to=frozenset({"tool", "macro"}),
    )

    def edits(self, tree: etree._ElementTree) -> Iterable[Edit]:
        """Yield ``ClearText`` edits collapsing whitespace-only leaf elements."""
        edits: list[Edit] = []
        for element in tree.iter():
            # ``tree.iter()`` yields ``Comment`` and ``ProcessingInstruction``
            # nodes alongside elements; their ``.tag`` is a callable, not a
            # string. They look like empty elements with whitespace-only
            # ``.text`` (e.g. ``<!--  -->``), and assigning ``.text = None``
            # to a Comment makes lxml drop the node entirely from output.
            # Restrict the rule to real elements.
            if not isinstance(element.tag, str):
                continue
            if len(element) == 0:
                text = element.text
                if text and not text.strip():
                    edits.append(ClearText(element=element))
        return edits
