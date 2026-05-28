"""Navigation + typed mutation primitives over the parsed lxml tree.

M1 supplied read-only navigation (tag, attribute reads, child / parent
traversal). M2 added the mutation primitives codemods need:
``set_attribute``, ``delete_attribute``, ``reorder_attributes``,
``attribute_names``. All mutations apply immediately to the underlying
lxml tree.

``children()`` returns **only real elements** — lxml Comment and
ProcessingInstruction nodes are skipped, so codemods never have to
defend against ``cursor.tag`` returning a non-string sentinel.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from lxml import etree


def _is_element(node: etree._Element) -> bool:
    """Whether *node* is a real XML element (not a Comment or PI).

    lxml represents Comments and ProcessingInstructions with a
    non-string ``.tag`` (a cyfunction). Real elements always have a
    string tag — that's the LBYL check.
    """
    return isinstance(node.tag, str)


@dataclass
class Cursor:
    """A position in the lxml element tree, with typed navigation and mutation."""

    _element: etree._Element = field(repr=False)

    @property
    def tag(self) -> str:
        return str(self._element.tag)

    def get_attribute(self, name: str, /) -> str | None:
        value = self._element.get(name)
        return None if value is None else str(value)

    def attribute_names(self) -> tuple[str, ...]:
        """Return the element's attribute names in document order."""
        return tuple(self._element.attrib)

    def children(self) -> list[Cursor]:
        """Return cursors for the element's child *elements* in document order.

        Comment and ProcessingInstruction nodes are skipped — codemods
        only see real XML elements.
        """
        return [Cursor(child) for child in self._element if _is_element(child)]

    def parent(self) -> Cursor | None:
        parent = self._element.getparent()
        return Cursor(parent) if parent is not None else None

    def set_attribute(self, name: str, value: str, /) -> None:
        """Add or overwrite ``name`` with ``value``."""
        self._element.set(name, value)

    def delete_attribute(self, name: str, /) -> None:
        """Remove ``name`` if present; otherwise no-op."""
        if name in self._element.attrib:
            del self._element.attrib[name]

    def reorder_attributes(self, names: Sequence[str], /) -> None:
        """Rewrite the element's attribute order to match ``names``.

        ``names`` must be a permutation of the element's current attribute
        names. Otherwise ``ValueError`` is raised — defensively, because a
        codemod bug that silently dropped or invented attributes would be
        very hard to debug after the fact.

        If ``names`` equals the current order, no mutation is performed.
        """
        current = tuple(self._element.attrib)
        ordered = tuple(names)
        if set(ordered) != set(current):
            raise ValueError(
                f"reorder_attributes: names {ordered!r} is not a permutation "
                f"of element's current attributes {current!r}"
            )
        if ordered == current:
            return
        snapshot = [(name, self._element.attrib[name]) for name in ordered]
        self._element.attrib.clear()
        for name, value in snapshot:
            self._element.attrib[name] = value
