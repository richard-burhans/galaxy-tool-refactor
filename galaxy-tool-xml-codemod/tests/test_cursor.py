"""Tests for the read-only ``Cursor`` navigation API (M1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from galaxy_tool_xml.binding import load_tool
from lxml import etree

from galaxy_tool_xml_codemod.cursor import Cursor


def _root_cursor(path: Path) -> Cursor:
    """Build a cursor at the root of the tool tree."""
    return Cursor(load_tool(path).root)


def test_text_reads_and_set_text_replaces_element_text() -> None:
    cursor = Cursor(etree.fromstring(b'<token name="@PROFILE@">16.01</token>'))
    assert cursor.text == "16.01"
    cursor.set_text("26.1")
    assert cursor.text == "26.1"
    assert cursor.get_attribute("name") == "@PROFILE@"  # attributes untouched


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


# ---------------------------------------------------------------------------
# Rename primitives (driven by the FixTypos codemod)
# ---------------------------------------------------------------------------


def test_rename_tag_changes_tag() -> None:
    """``rename_tag`` rewrites the element's tag in place."""
    from lxml import etree

    cursor = Cursor(etree.fromstring(b"<parm/>"))
    cursor.rename_tag("param")
    assert cursor.tag == "param"


def test_rename_tag_preserves_subtree_attrs_text_and_tail() -> None:
    """``rename_tag`` keeps children, attributes, text and tail untouched."""
    from lxml import etree

    parser = etree.XMLParser(strip_cdata=False)
    root = etree.fromstring(
        b"<inputs><parm name='x' type='text'>hi<child/></parm>tail</inputs>",
        parser=parser,
    )
    cursor = Cursor(root[0])
    cursor.rename_tag("param")
    renamed = root[0]
    assert renamed.tag == "param"
    assert renamed.get("name") == "x"
    assert renamed.get("type") == "text"
    assert renamed.text == "hi"
    assert renamed.tail == "tail"
    assert [child.tag for child in renamed] == ["child"]


def test_rename_tag_rejects_empty() -> None:
    """``rename_tag`` raises on an empty tag rather than corrupting the tree."""
    from lxml import etree

    cursor = Cursor(etree.fromstring(b"<parm/>"))
    with pytest.raises(ValueError):
        cursor.rename_tag("")


def test_rename_attribute_preserves_position_and_value() -> None:
    """``rename_attribute`` renames in place, keeping the slot index and value."""
    from lxml import etree

    root = etree.fromstring(b"<param name='x' typ='text' label='L'/>")
    cursor = Cursor(root)
    cursor.rename_attribute("typ", "type")
    assert cursor.attribute_names() == ("name", "type", "label")
    assert cursor.get_attribute("type") == "text"


def test_rename_attribute_rejects_absent_old() -> None:
    """``rename_attribute`` raises when the old name is not present."""
    from lxml import etree

    cursor = Cursor(etree.fromstring(b"<param name='x'/>"))
    with pytest.raises(ValueError):
        cursor.rename_attribute("nope", "type")


def test_rename_attribute_rejects_present_new() -> None:
    """``rename_attribute`` raises when the new name already exists (would clobber)."""
    from lxml import etree

    cursor = Cursor(etree.fromstring(b"<param typ='text' type='data'/>"))
    with pytest.raises(ValueError):
        cursor.rename_attribute("typ", "type")


def test_remove_detaches_element_from_parent() -> None:
    """``remove`` drops the element from its parent's children."""
    from lxml import etree

    root = etree.fromstring(b"<tool><a/><trackster_conf/><b/></tool>")
    Cursor(root[1]).remove()
    assert [child.tag for child in Cursor(root).children()] == ["a", "b"]


def test_remove_rejects_root() -> None:
    """``remove`` raises on an element with no parent — you can't drop the root."""
    from lxml import etree

    with pytest.raises(ValueError):
        Cursor(etree.fromstring(b"<tool/>")).remove()


def test_add_child_appends_new_element_with_text() -> None:
    """``add_child`` creates a child element with text and appends it last."""
    from lxml import etree

    root = etree.fromstring(b"<collection><data/></collection>")
    cursor = Cursor(root).add_child("filter", text="cond")
    assert cursor.tag == "filter"
    assert [child.tag for child in root] == ["data", "filter"]
    assert root[1].text == "cond"


def test_add_child_without_text_has_no_text() -> None:
    """``add_child`` with no text leaves the new element's text unset."""
    from lxml import etree

    root = etree.fromstring(b"<collection/>")
    Cursor(root).add_child("filter")
    assert root[0].tag == "filter"
    assert root[0].text is None


def test_add_child_returns_cursor_to_new_element() -> None:
    """The returned cursor points at the freshly created child (chainable)."""
    from lxml import etree

    root = etree.fromstring(b"<outputs/>")
    child = Cursor(root).add_child("data")
    child.set_attribute("name", "out")
    assert root[0].get("name") == "out"


def test_add_child_rejects_empty_tag() -> None:
    """``add_child`` raises on an empty tag rather than corrupting the tree."""
    from lxml import etree

    with pytest.raises(ValueError):
        Cursor(etree.fromstring(b"<outputs/>")).add_child("")


# ---------------------------------------------------------------------------
# reorder_children (driven by the ReorderToolChildren codemod)
# ---------------------------------------------------------------------------


def test_reorder_children_applies_canonical_order() -> None:
    """Child elements are placed in the requested canonical tag order."""
    from lxml import etree

    root = etree.fromstring(b"<tool><help/><inputs/><description/><command/></tool>")
    Cursor(root).reorder_children(("description", "command", "inputs", "help"))
    assert [child.tag for child in root] == [
        "description",
        "command",
        "inputs",
        "help",
    ]


def test_reorder_children_keeps_unknowns_stably_after_known() -> None:
    """Tags absent from the order keep their relative position, after the known."""
    from lxml import etree

    root = etree.fromstring(b"<tool><zeta/><help/><alpha/><command/></tool>")
    Cursor(root).reorder_children(("command", "help"))
    assert [child.tag for child in root] == ["command", "help", "zeta", "alpha"]


def test_reorder_children_is_noop_when_already_ordered() -> None:
    """When the order is unchanged, the same element objects stay in place."""
    from lxml import etree

    root = etree.fromstring(b"<tool><description/><command/><help/></tool>")
    before = list(root)
    Cursor(root).reorder_children(("description", "command", "help"))
    assert list(root) == before


def test_reorder_children_skips_when_comment_present() -> None:
    """A free-floating comment makes reordering a no-op (can't be done safely)."""
    from lxml import etree

    parser = etree.XMLParser(strip_cdata=False)
    root = etree.fromstring(
        b"<tool><help/><!-- c --><description/></tool>", parser=parser
    )
    Cursor(root).reorder_children(("description", "help"))
    assert [child.tag for child in root if isinstance(child.tag, str)] == [
        "help",
        "description",
    ]


def test_reorder_children_is_idempotent() -> None:
    """A second reorder with the same order produces byte-identical output."""
    from lxml import etree

    root = etree.fromstring(b"<tool><help/><inputs/><description/></tool>")
    cursor = Cursor(root)
    cursor.reorder_children(("description", "inputs", "help"))
    once = etree.tostring(root)
    cursor.reorder_children(("description", "inputs", "help"))
    assert etree.tostring(root) == once


def test_cursor_sourceline_returns_parsed_line(tool_with_params_path: Path) -> None:
    """``cursor.sourceline`` returns the 1-based source line of the element."""
    root = _root_cursor(tool_with_params_path)
    assert root.sourceline == 1
    first_param = root.children()[1].children()[0]  # tool -> inputs -> first param
    assert first_param.tag == "param"
    assert first_param.sourceline == 4


def test_cursor_sourceline_is_zero_for_synthesised_element() -> None:
    """An element built in memory (no source) reports sourceline ``0``."""
    from lxml import etree

    synthetic = etree.Element("param")
    assert Cursor(synthetic).sourceline == 0


def test_cursor_xpath_returns_absolute_path(tool_with_params_path: Path) -> None:
    """``cursor.xpath`` returns an absolute, indexed path to the element."""
    root = _root_cursor(tool_with_params_path)
    assert root.xpath == "/tool"
    inputs = root.children()[1]
    params = inputs.children()
    assert params[0].xpath == "/tool/inputs/param[1]"
    assert params[1].xpath == "/tool/inputs/param[2]"
