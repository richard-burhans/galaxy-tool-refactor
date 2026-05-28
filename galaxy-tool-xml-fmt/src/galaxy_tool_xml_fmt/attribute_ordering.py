"""Shared helper for per-element attribute-ordering rules.

A rule chooses a class of elements and a ``priority`` map (attribute
name → integer; lower runs first) and asks this module to produce the
corresponding ``ReorderAttributes`` edits. Attributes not in the
priority map sort alphabetically after the known set.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from galaxy_tool_xml_fmt.edits import Edit, ReorderAttributes

if TYPE_CHECKING:
    from lxml import etree


_UNKNOWN_PRIORITY = 100


def canonical_order(
    names: Iterable[str], priority: Mapping[str, int]
) -> tuple[str, ...]:
    """Return *names* sorted by *priority*; unknowns sort alphabetically at the end."""
    return tuple(
        sorted(names, key=lambda name: (priority.get(name, _UNKNOWN_PRIORITY), name))
    )


def reorder_attribute_edits(
    elements: Iterable[etree._Element],
    priority: Mapping[str, int],
) -> Iterable[Edit]:
    """Yield ``ReorderAttributes`` edits for elements with out-of-order attributes."""
    for element in elements:
        current = tuple(element.attrib)
        canonical = canonical_order(current, priority)
        if canonical != current:
            yield ReorderAttributes(element=element, names=canonical)
