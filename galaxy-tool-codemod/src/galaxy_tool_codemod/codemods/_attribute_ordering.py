"""Shared helper for attribute-reordering codemods.

Given an element's current attribute names and a priority map (attribute
name → integer; lower runs first), returns the canonical order:
priority-ascending, with unknown attributes sorting alphabetically after
the known ones. Originally lived in ``galaxy-tool-fmt`` as
``attribute_ordering``; moved here when the attribute-reorder rules
became structural codemods.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

_UNKNOWN_PRIORITY = 100


def canonical_order(
    names: Iterable[str], priority: Mapping[str, int]
) -> tuple[str, ...]:
    """Return *names* sorted by *priority*; unknowns alphabetical at the end."""
    return tuple(
        sorted(names, key=lambda name: (priority.get(name, _UNKNOWN_PRIORITY), name))
    )
