"""GTR001: canonical 4-space indentation.

Walks the tree and emits ``SetText`` / ``SetTail`` edits so every
element's child-leading and sibling-trailing whitespace matches the
canonical form: one ``\\n`` followed by ``4 * depth`` spaces.

CDATA content is preserved because both ``SetText`` and ``SetTail``
route through ``safe_set_text`` / ``safe_set_tail``, which only write
when the existing value is ``None`` or pure whitespace.

Two subtree classes are **left entirely alone** (behaviour-preservation
GTR001; ``../../docs/behavior_preservation.md``) — provable layout-only
whitespace does not exist inside them, so the sound move for a novel
tool is to not touch it:

- **Mixed content** (text interspersed with child elements, e.g.
  ``See <b>x</b> <i>y</i>``): a whitespace-only tail there is a rendered
  word separator — XML 1.0 calls inter-element whitespace
  non-significant only for *element* content.
- **Payload elements with children** (``<command>`` / ``<configfile>`` /
  ``<token>`` — read verbatim by Galaxy, ``strip=False``, the GTR004
  set — plus indentation-sensitive RST ``<help>``): even an all-
  whitespace text/tail between ``<expand>`` children is spliced into
  the script/template/RST, where a space→newline rewrite changes
  meaning (in shell, a newline *separates commands*).
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

# Elements whose body Galaxy consumes verbatim (shell/Cheetah script, template,
# macro substitution value — the GTR004 ``_CONTENT_BEARING_TAGS``) or renders
# whitespace-sensitively (RST <help>): with child elements present, every
# text/tail inside is potential payload, never provably layout.
_PAYLOAD_TAGS = frozenset({"command", "configfile", "token", "help"})


def _holds_mixed_content(element: etree._Element, /) -> bool:
    """Text interspersed with elements — inter-element whitespace is rendered."""
    if (element.text or "").strip():
        return True
    return any((child.tail or "").strip() for child in element)


class CanonicalIndent(Rule):
    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR001",
        summary="Canonical 4-space indentation; no tabs.",
        since="0.0.1",
        cite="https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html",
        order=10,
        applies_to=frozenset({"tool", "macro"}),
        rulesets=frozenset({"cosmetic", "default", "iuc", "strict"}),
    )

    def edits(self, tree: etree._ElementTree) -> Iterable[Edit]:
        """Yield ``SetText``/``SetTail`` edits normalising indentation to 4 spaces."""
        return list(_walk(tree.getroot(), depth=0))


def _walk(element: etree._Element, *, depth: int) -> Iterable[Edit]:
    children = list(element)
    if not children:
        return
    if element.tag in _PAYLOAD_TAGS or _holds_mixed_content(element):
        return  # whole subtree: whitespace may be payload / rendered text
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
