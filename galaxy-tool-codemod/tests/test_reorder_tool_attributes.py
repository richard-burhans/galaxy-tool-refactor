"""Tests for the ``ReorderToolAttributes`` codemod (port of fmt GTR005)."""

from __future__ import annotations

from galaxy_tool_codemod.codemods.reorder_tool_attributes import (
    ReorderToolAttributes,
)
from galaxy_tool_codemod.parse import parse_module


def _tool_attrs(module_xml: bytes) -> tuple[str, ...]:
    """Apply the codemod and return the resulting root ``<tool>`` attribute order."""
    module = parse_module(module_xml)
    ReorderToolAttributes().apply(module)
    return tuple(module.document.root.attrib)


def test_tool_with_canonical_order_is_unchanged() -> None:
    """Already-canonical order produces no change."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs/>
    </tool>"""
    assert _tool_attrs(xml) == ("id", "name", "version", "profile")


def test_tool_attributes_are_reordered_to_documented_prefix() -> None:
    """``id``, ``name``, ``version``, ``profile`` lead in that order."""
    xml = b"""<tool profile="24.0" version="1" name="n" id="t">
        <inputs/>
    </tool>"""
    assert _tool_attrs(xml) == ("id", "name", "version", "profile")


def test_unknown_tool_attributes_sort_alphabetical_after_known() -> None:
    """Attributes outside the documented prefix sort alphabetically at the end."""
    xml = b"""<tool zz="1" id="t" name="n" version="1" profile="24.0" aa="2">
        <inputs/>
    </tool>"""
    assert _tool_attrs(xml) == ("id", "name", "version", "profile", "aa", "zz")


def test_does_not_touch_param_attributes() -> None:
    """``ReorderToolAttributes`` ignores ``<param>`` elements."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs>
            <param value="v" type="text" name="x"/>
        </inputs>
    </tool>"""
    module = parse_module(xml)
    ReorderToolAttributes().apply(module)
    param = next(module.document.root.iter("param"))
    assert tuple(param.attrib) == ("value", "type", "name")




def test_detect_yields_located_change_for_unordered_tool() -> None:
    """``detect`` reports a GTR005 change at the root, without mutating."""
    from galaxy_tool_codemod.parse import parse_module

    xml = b'<tool profile="24.0" id="t" name="n" version="1"><inputs/></tool>'
    module = parse_module(xml)
    changes = list(ReorderToolAttributes().detect(module))
    assert len(changes) == 1
    assert changes[0].code == "GTR005"
    assert changes[0].xpath == "/tool"
    assert tuple(module.document.root.attrib) == ("profile", "id", "name", "version")


def test_detect_yields_nothing_for_already_ordered_tool() -> None:
    """An already-ordered root ``<tool>`` produces no change."""
    from galaxy_tool_codemod.parse import parse_module

    xml = b'<tool id="t" name="n" version="1" profile="24.0"><inputs/></tool>'
    module = parse_module(xml)
    assert list(ReorderToolAttributes().detect(module)) == []
