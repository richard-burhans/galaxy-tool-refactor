"""Navigation + typed mutation primitives over the parsed lxml tree.

M1 supplied read-only navigation (tag, attribute reads, child / parent
traversal). M2 added the mutation primitives codemods need:
``set_attribute``, ``delete_attribute``, ``reorder_attributes``,
``attribute_names``, plus the ``rename_tag`` / ``rename_attribute``
primitives the typo-repair codemod relies on and ``remove`` (used by
profile-upgrade codemods to drop obsolete elements). All mutations apply
immediately to the underlying lxml tree.

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

    @property
    def sourceline(self) -> int:
        """The element's 1-based source line, or ``0`` if it has no source position.

        lxml records ``sourceline`` for parsed elements and leaves it ``None``
        for elements built in memory (a codemod-synthesised node). Detect
        phases surface this as the ``Violation.sourceline`` location, which is a
        plain ``int``, so an absent position maps to ``0``.
        """
        line = self._element.sourceline
        return line if line is not None else 0

    @property
    def xpath(self) -> str:
        """The element's absolute, indexed xpath (e.g. ``/tool/inputs/param[1]``).

        Derived from the live tree via lxml ``ElementTree.getpath`` — a stable
        textual location for the detect phase's ``Violation.xpath``.
        """
        return str(self._element.getroottree().getpath(self._element))

    @property
    def text(self) -> str | None:
        """The element's direct text content (a ``<token>``'s value), or ``None``."""
        text = self._element.text
        return None if text is None else str(text)

    @property
    def element(self) -> etree._Element:
        """The underlying lxml element — for tier-1 predicates that take an element
        (e.g. ``galaxy_tool_xml.cdata.cdata_wrappable``)."""
        return self._element

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

    def child_node_count(self) -> int:
        """Number of child nodes — elements, comments and PIs alike.

        Unlike ``children()`` (which yields only real elements) this counts every
        node, so ``0`` means the element's content is a single run of text or one
        CDATA section. That is the precondition for wrapping a ``<command>`` /
        ``<help>`` body in one CDATA section (``WrapCommandCdata`` /
        ``WrapHelpCdata``) — a mixed-content body can't be expressed as one.
        """
        return len(self._element)

    def is_cdata_wrapped(self) -> bool:
        """Whether the element's body is a leading ``<![CDATA[…]]>`` section.

        lxml exposes CDATA as plain ``.text`` with no marker, so this re-serialises
        (the tier-1 parser keeps CDATA, ``strip_cdata=False``, so it round-trips)
        and inspects the body — mirroring the advisory tier's GTR018.2/GTR019.2
        predicate. Leading whitespace before the section still counts as wrapped.
        """
        serialised: str = etree.tostring(
            self._element, encoding="unicode", with_tail=False
        )
        body = serialised[serialised.index(">") + 1 :]
        return bool(body.lstrip().startswith("<![CDATA["))

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

    def set_text(self, value: str, /, *, cdata: bool = False) -> None:
        """Set the element's direct text content (e.g. a ``<token>``'s value).

        Replaces ``text`` only; child elements, ``tail``, and attributes are
        untouched. Used by the token-aware profile upgrade to rewrite a
        ``<token name="@PROFILE@">`` value in place.

        With ``cdata=True`` the value is wrapped in a ``<![CDATA[…]]>`` section so
        shell operators (``&&``, ``<``, ``|``) stay literal — required when
        rewriting a ``<command>`` body (which is CDATA by convention, GTR018.2).
        """
        self._element.text = etree.CDATA(value) if cdata else value

    def rename_tag(self, new_tag: str, /) -> None:
        """Rename this element's tag in place.

        Children, attributes, ``text`` and ``tail`` are untouched — only the
        tag name changes. ``new_tag`` must be a non-empty string; an empty tag
        would corrupt the tree, so it is rejected loudly (LBYL) rather than
        silently produced.
        """
        if not new_tag:
            raise ValueError("rename_tag: new_tag must be a non-empty string")
        self._element.tag = new_tag

    def rename_attribute(self, old: str, new: str, /) -> None:
        """Rename attribute ``old`` to ``new``, preserving its position and value.

        ``ValueError`` is raised if ``old`` is absent or ``new`` is already
        present — either case would silently drop or clobber an attribute,
        which a codemod bug could otherwise hide. The slot index is preserved
        by rebuilding the attribute dict (lxml ``_Attrib`` has no rename), the
        same clear-and-rebuild pattern ``reorder_attributes`` uses.
        """
        attrib = self._element.attrib
        if old not in attrib:
            raise ValueError(f"rename_attribute: attribute {old!r} is not present")
        if new in attrib:
            raise ValueError(f"rename_attribute: attribute {new!r} already present")
        snapshot = [
            (new if name == old else name, value) for name, value in attrib.items()
        ]
        attrib.clear()
        for name, value in snapshot:
            attrib[name] = value

    def remove(self, /) -> None:
        """Detach this element (and its subtree) from its parent.

        Raises ``ValueError`` if the element has no parent — the document root
        cannot be removed. lxml drops the element's tail text along with it,
        which the cosmetic formatter re-normalises.
        """
        parent = self._element.getparent()
        if parent is None:
            raise ValueError("remove: element has no parent (cannot remove the root)")
        parent.remove(self._element)

    def add_child(self, tag: str, /, *, text: str | None = None) -> Cursor:
        """Create a new child element ``<tag>``, append it last, return its cursor.

        ``text`` sets the child's text content when given. ``tag`` must be a
        non-empty string — an empty tag would corrupt the tree, so it is
        rejected loudly (LBYL). The new element is appended after any existing
        children; the cosmetic formatter re-normalises indentation afterwards.
        """
        if not tag:
            raise ValueError("add_child: tag must be a non-empty string")
        child = etree.SubElement(self._element, tag)
        if text is not None:
            child.text = text
        return Cursor(child)

    def _plan_reorder_children(
        self, order: Sequence[str]
    ) -> list[etree._Element] | None:
        """Return the reordered child nodes, or ``None`` if nothing would move.

        Children whose tag appears in ``order`` are placed in that order; tags
        not in ``order`` keep their original relative position, after the known
        ones (a stable sort by ``(rank, original index)`` — no alphabetical
        guess, unlike ``reorder_attributes``). Returns ``None`` when the element
        has any non-element child (Comment / ProcessingInstruction) — see
        ``reorder_children`` — or when the order already matches, so neither the
        detect predicate nor the mutator churns an already-ordered element.
        """
        nodes = list(self._element)
        if any(not _is_element(node) for node in nodes):
            return None
        rank = {tag: index for index, tag in enumerate(order)}
        sentinel = len(order)
        reordered = sorted(nodes, key=lambda node: rank.get(str(node.tag), sentinel))
        if all(before is after for before, after in zip(nodes, reordered, strict=True)):
            return None
        return reordered

    def would_reorder_children(self, order: Sequence[str], /) -> bool:
        """Whether ``reorder_children(order)`` would move any child element.

        The detect-phase predicate: it shares ``_plan_reorder_children`` with the
        mutator, so a codemod reports a reorder exactly when applying one would.
        """
        return self._plan_reorder_children(order) is not None

    def reorder_children(self, order: Sequence[str], /) -> None:
        """Reorder this element's child *elements* to the canonical tag ``order``.

        Children whose tag appears in ``order`` are placed in that order; tags
        not in ``order`` keep their relative position, after the known ones.
        When nothing would move — the order already matches, or a free-floating
        Comment / ProcessingInstruction is present (``children()`` hides those,
        and moving elements past one would silently re-associate it with the
        wrong element; a comment is a normal tree state, not a codemod bug) —
        the element is left untouched. lxml moves an existing child when it is
        re-appended; each element's ``tail`` travels with it, so inter-element
        whitespace is left for the cosmetic formatter to re-normalise.
        """
        reordered = self._plan_reorder_children(order)
        if reordered is None:
            return
        for node in reordered:
            self._element.append(node)

    def would_reorder_attributes(self, names: Sequence[str], /) -> bool:
        """Whether ``reorder_attributes(names)`` would change the attribute order.

        ``names`` must be a permutation of the element's current attribute names;
        otherwise ``ValueError`` is raised on the same guard as the mutator, so
        the detect phase fails as loudly as the fix phase on a codemod bug. The
        detect predicate and the mutator share this check, so they never drift.
        """
        current = tuple(self._element.attrib)
        ordered = tuple(names)
        if set(ordered) != set(current):
            raise ValueError(
                f"reorder_attributes: names {ordered!r} is not a permutation "
                f"of element's current attributes {current!r}"
            )
        return ordered != current

    def reorder_attributes(self, names: Sequence[str], /) -> None:
        """Rewrite the element's attribute order to match ``names``.

        ``names`` must be a permutation of the element's current attribute
        names (see ``would_reorder_attributes``, which performs the guard).
        If ``names`` equals the current order, no mutation is performed.
        """
        if not self.would_reorder_attributes(names):
            return
        ordered = tuple(names)
        snapshot = [(name, self._element.attrib[name]) for name in ordered]
        self._element.attrib.clear()
        for name, value in snapshot:
            self._element.attrib[name] = value
