"""GTR004: empty-element shorthand.

When a leaf element carries only whitespace as text (e.g. a tool author
wrote ``<inputs>\\n</inputs>`` rather than ``<inputs/>``), normalise it
to the short form by clearing ``element.text``. lxml then serialises
the element as ``<foo/>``.

Empty-string text (``element.text == ""``) is deliberately left alone:
it may be the surface form of an empty CDATA wrapper, and there is no
lxml-level way to distinguish an empty CDATA section from an empty
string. The conservative choice is to only touch text that is actually
whitespace.

A handful of **content-bearing** elements are also left alone: their
``.text`` is runtime/expansion payload Galaxy reads *verbatim*
(``strip=False``), so a whitespace-only body is real content, not layout
— clearing it would silently drop the payload (behaviour-preservation
finding GTR004; ``../../docs/behavior_preservation.md``). These are
``<command>`` (shell/Cheetah script), ``<configfile>`` (template body),
and ``<token>`` (macro substitution value). Whitespace-only ``<help>``
is *not* in this set: it renders empty either way, so it still collapses
(the formatter stays opinionated about layout-only whitespace).

Editorial; no IUC citation. PLAN.md prescribes ``<foo/>`` over
``<foo></foo>`` where the content model permits.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_fmt.edits import ClearText, Edit
from galaxy_tool_xml_fmt.payload import element_text_may_be_payload
from galaxy_tool_xml_fmt.rules import Rule

# The content-bearing guard is now schema-derived (fmt ``payload`` module — every
# tag whose content model admits text, with the configfiles-``<inputs>`` context
# check and the cleared-``<macros>`` exception); ``<help>`` stays a deliberate,
# cited exception below (a whitespace-only help renders empty either way, D18).

if TYPE_CHECKING:
    from lxml import etree


class EmptyElementShorthand(Rule):
    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR004",
        summary="Collapse empty-with-whitespace leaves to <foo/> form.",
        since="0.0.1",
        order=20,
        applies_to=frozenset({"tool", "macro"}),
        rulesets=frozenset({"cosmetic", "default", "iuc", "strict"}),
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
            if element.tag != "help" and element_text_may_be_payload(element):
                continue  # whitespace-only body is payload, not layout — keep it
            if len(element) == 0:
                text = element.text
                if text and not text.strip():
                    edits.append(ClearText(element=element))
        return edits
