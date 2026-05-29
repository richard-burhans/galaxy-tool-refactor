"""Tests for the ``ReorderToolChildren`` codemod (GTX013, IUC element order)."""

from __future__ import annotations

from galaxy_tool_xml_codemod.codemods.reorder_tool_children import (
    ReorderToolChildren,
)
from galaxy_tool_xml_codemod.parse import parse_module


def _child_tags(module_xml: bytes) -> list[str]:
    """Apply the codemod and return the root ``<tool>``'s child element tags."""
    module = parse_module(module_xml)
    ReorderToolChildren().apply(module)
    return [
        str(child.tag)
        for child in module.document.root
        if isinstance(child.tag, str)
    ]


def test_scrambled_tool_children_reordered_to_iuc_order() -> None:
    """Out-of-order children are reordered to the documented IUC convention."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <help>h</help>
        <outputs/>
        <inputs/>
        <command>c</command>
        <description>d</description>
    </tool>"""
    assert _child_tags(xml) == [
        "description",
        "command",
        "inputs",
        "outputs",
        "help",
    ]


def test_already_ordered_tool_is_unchanged() -> None:
    """A tool whose children already follow the convention is left as-is."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <description>d</description>
        <command>c</command>
        <inputs/>
        <outputs/>
        <help>h</help>
    </tool>"""
    assert _child_tags(xml) == [
        "description",
        "command",
        "inputs",
        "outputs",
        "help",
    ]


def test_unknown_children_kept_stably_after_known() -> None:
    """Tags outside the IUC order keep their relative position, after the known."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <help/>
        <custom_thing/>
        <command/>
        <another_custom/>
    </tool>"""
    assert _child_tags(xml) == [
        "command",
        "help",
        "custom_thing",
        "another_custom",
    ]


def test_tool_with_root_comment_is_left_untouched() -> None:
    """A free-floating comment at the tool root suppresses reordering entirely."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <!-- license header -->
        <help/>
        <command/>
    </tool>"""
    assert _child_tags(xml) == ["help", "command"]


def test_tool_attributes_are_not_touched() -> None:
    """The codemod reorders children only; the root attributes are unchanged."""
    xml = b"""<tool profile="24.0" id="t" name="n" version="1">
        <help/>
        <command/>
    </tool>"""
    module = parse_module(xml)
    ReorderToolChildren().apply(module)
    assert tuple(module.document.root.attrib) == ("profile", "id", "name", "version")
