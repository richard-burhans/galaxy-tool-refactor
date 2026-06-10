"""The shared payload guard: which elements' whitespace may be meaningful.

GTR004 (empty-element collapse) and GTR001 (indent) must not rewrite whitespace
that could be content. The tag set is **derived from the vendored schemas**
(tier-1 ``galaxy_tool_xml.schema_content.text_bearing_tags`` — an element is
text-bearing iff its content model admits character data, unioned across every
Galaxy release), replacing the hand-maintained lists (behaviour-preservation
ledger, GTR004 derivation proposal, applied 2026-06-10).

Two same-named-element collisions get proof-carried handling instead of the
blanket set:

- ``<inputs>`` is element-only under ``<tool>`` (layout whitespace, fine to
  rewrite) but ``simpleContent`` under ``<configfiles>`` (``ConfigInputs`` — a
  text body by schema), so it is payload **only in the configfiles context** —
  a latent hand-list gap the derivation surfaced.
- ``<macros>`` is ``xs:anyType`` in the legacy schemas, but Galaxy's macro
  loader harvests its children and then **clears the element**
  (``galaxy/util/xml_macros.py:39-45``) — its text is provably dead, so it is
  excepted (the D18-help style: a justified, cited exception).
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from galaxy_tool_xml.schema_content import text_bearing_tags

if TYPE_CHECKING:
    from lxml import etree

# Tags whose schema-text-bearing status needs context or is proof-excepted —
# handled explicitly in element_text_may_be_payload, never via the blanket set.
_CONTEXTUAL_TAGS = frozenset({"inputs", "macros"})


@cache
def _unconditional_payload_tags() -> frozenset[str]:
    return text_bearing_tags() - _CONTEXTUAL_TAGS


def element_text_may_be_payload(element: etree._Element, /) -> bool:
    """Whether *element*'s body text could be meaningful content (see module doc)."""
    tag = element.tag
    if not isinstance(tag, str):
        return False  # comment / processing instruction
    if tag in _unconditional_payload_tags():
        return True
    if tag == "inputs":
        parent = element.getparent()
        return parent is not None and parent.tag == "configfiles"
    return False
