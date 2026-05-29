"""The cosmetic format pipeline entry point.

``format_tool_document`` applies fmt's cosmetic rules (indentation,
blank lines, empty-element shorthand) and serialises. It does **not**
perform structural canonicalisation — that's tier 2 (``galaxy-tool-xml-codemod``)'s
``CANONICAL_CODEMODS``. This package has no dependency on the codemod
package; minimal installs (xml + fmt) get cosmetic-only formatting. The
``galaxy-tool-refactor`` app (``galaxy-tool-refactor-cli``) composes the
codemod and fmt tiers for the full canonical / upgrade workflows.
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from galaxy_tool_xml_fmt.edits import apply_edits
from galaxy_tool_xml_fmt.rule_blank_line import BlankLineBetweenSections
from galaxy_tool_xml_fmt.rule_empty_element import EmptyElementShorthand
from galaxy_tool_xml_fmt.rule_indent import CanonicalIndent
from galaxy_tool_xml_fmt.rules import Rule
from galaxy_tool_xml_fmt.serializer import to_bytes

if TYPE_CHECKING:
    from galaxy_tool_xml.document import ToolDocument


@cache
def all_rules() -> tuple[type[Rule], ...]:
    """Return the active cosmetic formatter rules sorted by application order."""
    rule_classes: list[type[Rule]] = [
        BlankLineBetweenSections,
        CanonicalIndent,
        EmptyElementShorthand,
    ]
    return tuple(sorted(rule_classes, key=lambda cls: cls.meta.order))


def format_tool_document(document: ToolDocument) -> bytes:
    """Format *document* with cosmetic rules and serialise to bytes.

    Runs every active cosmetic rule against the document's mutable lxml
    tree in order, then serialises the result. The input document is
    mutated in-place; callers that need the original tree should pass a
    copy. **No structural canonicalisation** — for the full canonical
    pipeline use the ``galaxy-tool-refactor format`` app command, or apply
    ``galaxy_tool_xml_codemod.canonical.CANONICAL_CODEMODS`` yourself
    before calling this function.

    Args:
        document: A parsed Galaxy tool document.

    Returns:
        Canonical-form XML bytes (cosmetic-only).
    """
    tree = document.tree
    for rule_cls in all_rules():
        apply_edits(rule_cls().apply(tree))
    return to_bytes(tree)
