"""Tests for the read-only ``Cursor`` navigation API (M1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from galaxy_tool_xml.binding import load_tool

from galaxy_tool_xml_codemod.cursor import Cursor


def _root_cursor(path: Path) -> Cursor:
    """Build a cursor at the root of the tool tree."""
    return Cursor(load_tool(path).root)


def test_cursor_tag_returns_element_tag(minimal_tool_path: Path) -> None:
    """``cursor.tag`` returns the lxml element's tag as a string."""
    cursor = _root_cursor(minimal_tool_path)
    assert cursor.tag == "tool"


def test_cursor_get_attribute_returns_attribute_value(
    minimal_tool_path: Path,
) -> None:
    """``cursor.get_attribute`` returns the requested attribute value."""
    cursor = _root_cursor(minimal_tool_path)
    assert cursor.get_attribute("id") == "minimal"
    assert cursor.get_attribute("profile") == "24.0"


def test_cursor_get_attribute_returns_none_for_missing(
    minimal_tool_path: Path,
) -> None:
    """``cursor.get_attribute`` returns ``None`` for an attribute that is not set."""
    cursor = _root_cursor(minimal_tool_path)
    assert cursor.get_attribute("nonexistent") is None


def test_cursor_children_returns_child_cursors_in_document_order(
    minimal_tool_path: Path,
) -> None:
    """``cursor.children()`` returns one Cursor per direct child, in order."""
    cursor = _root_cursor(minimal_tool_path)
    child_tags = [child.tag for child in cursor.children()]
    assert child_tags == ["command", "inputs", "outputs"]


def test_cursor_parent_of_root_is_none(minimal_tool_path: Path) -> None:
    """The root element has no parent — ``cursor.parent()`` returns ``None``."""
    cursor = _root_cursor(minimal_tool_path)
    assert cursor.parent() is None


def test_cursor_parent_returns_parent_cursor(minimal_tool_path: Path) -> None:
    """A child cursor's ``parent()`` points back at the root element."""
    root = _root_cursor(minimal_tool_path)
    children = root.children()
    parents = [child.parent() for child in children]
    for parent in parents:
        assert parent is not None
        assert parent._element is root._element


def test_cursor_attribute_names_returns_attribute_names_in_order() -> None:
    """``attribute_names()`` returns the element's attributes in document order."""
    from lxml import etree

    root = etree.fromstring(
        b"<tool id='t' name='T' version='1' profile='24.0'><inputs/></tool>"
    )
    cursor = Cursor(root)
    assert cursor.attribute_names() == ("id", "name", "version", "profile")


def test_cursor_attribute_names_empty_when_no_attributes() -> None:
    """``attribute_names()`` returns the empty tuple for elements with no attributes."""
    from lxml import etree

    cursor = Cursor(etree.fromstring(b"<tool/>"))
    assert cursor.attribute_names() == ()


def test_cursor_children_filters_comment_and_pi_nodes() -> None:
    """``children()`` returns only real elements — Comments and PIs are skipped."""
    from lxml import etree

    parser = etree.XMLParser(strip_cdata=False)
    root = etree.fromstring(
        b"<tool><!-- a comment --><inputs/><?pi target?><outputs/></tool>",
        parser=parser,
    )
    cursor = Cursor(root)
    child_tags = [child.tag for child in cursor.children()]
    assert child_tags == ["inputs", "outputs"]


# ---------------------------------------------------------------------------
# M2 — typed mutation primitives
# ---------------------------------------------------------------------------


def test_set_attribute_adds_new_attribute(minimal_tool_path: Path) -> None:
    """``set_attribute`` adds an attribute that did not previously exist."""
    cursor = _root_cursor(minimal_tool_path)
    cursor.set_attribute("hidden", "true")
    assert cursor.get_attribute("hidden") == "true"


def test_set_attribute_updates_existing(minimal_tool_path: Path) -> None:
    """``set_attribute`` overwrites the existing value when the attribute is set."""
    cursor = _root_cursor(minimal_tool_path)
    cursor.set_attribute("profile", "26.0")
    assert cursor.get_attribute("profile") == "26.0"


def test_delete_attribute_removes_existing(minimal_tool_path: Path) -> None:
    """``delete_attribute`` removes a present attribute."""
    cursor = _root_cursor(minimal_tool_path)
    cursor.delete_attribute("profile")
    assert cursor.get_attribute("profile") is None


def test_delete_attribute_is_noop_when_absent(minimal_tool_path: Path) -> None:
    """``delete_attribute`` does nothing when the attribute is not present."""
    cursor = _root_cursor(minimal_tool_path)
    cursor.delete_attribute("nonexistent")
    assert cursor.get_attribute("nonexistent") is None


def test_reorder_attributes_applies_requested_order(
    minimal_tool_path: Path,
) -> None:
    """``reorder_attributes`` rewrites attribute order to the requested permutation."""
    cursor = _root_cursor(minimal_tool_path)
    cursor.reorder_attributes(("profile", "id", "name", "version"))
    assert tuple(cursor._element.attrib) == ("profile", "id", "name", "version")


def test_reorder_attributes_is_noop_when_already_canonical(
    minimal_tool_path: Path,
) -> None:
    """No mutation when current order already matches the requested permutation."""
    cursor = _root_cursor(minimal_tool_path)
    original = tuple(cursor._element.attrib)
    cursor.reorder_attributes(original)
    assert tuple(cursor._element.attrib) == original


def test_reorder_attributes_rejects_non_permutation(
    minimal_tool_path: Path,
) -> None:
    """``reorder_attributes`` raises when ``names`` is not a permutation."""
    cursor = _root_cursor(minimal_tool_path)
    with pytest.raises(ValueError):
        cursor.reorder_attributes(("id", "name"))  # missing version, profile


def test_reorder_attributes_preserves_values(minimal_tool_path: Path) -> None:
    """``reorder_attributes`` preserves each attribute's value."""
    cursor = _root_cursor(minimal_tool_path)
    snapshot = dict(cursor._element.attrib)
    cursor.reorder_attributes(("profile", "version", "name", "id"))
    for name, value in snapshot.items():
        assert cursor.get_attribute(name) == value
