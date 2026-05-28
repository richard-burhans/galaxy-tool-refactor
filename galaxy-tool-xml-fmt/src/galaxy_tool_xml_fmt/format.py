"""The format pipeline entry point."""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from galaxy_tool_xml_fmt.edits import apply_edits
from galaxy_tool_xml_fmt.rule_blank_line import BlankLineBetweenSections
from galaxy_tool_xml_fmt.rule_empty_element import EmptyElementShorthand
from galaxy_tool_xml_fmt.rule_indent import CanonicalIndent
from galaxy_tool_xml_fmt.rule_param_attr_order import ParamAttributeOrder
from galaxy_tool_xml_fmt.rule_tool_attr_order import ToolAttributeOrder
from galaxy_tool_xml_fmt.rules import Rule
from galaxy_tool_xml_fmt.serializer import to_bytes

if TYPE_CHECKING:
    from galaxy_tool_xml.document import ToolDocument


@cache
def all_rules() -> tuple[type[Rule], ...]:
    """Return the active formatter rules sorted by application order."""
    rule_classes: list[type[Rule]] = [
        BlankLineBetweenSections,
        CanonicalIndent,
        EmptyElementShorthand,
        ParamAttributeOrder,
        ToolAttributeOrder,
    ]
    return tuple(sorted(rule_classes, key=lambda cls: cls.meta.order))


def format_tool_document(document: ToolDocument) -> bytes:
    """Format *document* to canonical Galaxy tool XML bytes.

    Runs every active rule against the document's mutable lxml tree in
    order, then serializes the result. The input document is mutated
    in-place; callers that need the original tree should pass a copy.

    Args:
        document: A parsed Galaxy tool document.

    Returns:
        Canonical-form XML bytes.
    """
    tree = document.tree
    for rule_cls in all_rules():
        apply_edits(rule_cls().apply(tree))
    return to_bytes(tree)
