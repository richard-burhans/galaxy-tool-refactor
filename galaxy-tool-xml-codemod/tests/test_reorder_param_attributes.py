"""Tests for the ``ReorderParamAttributes`` codemod (port of fmt GTX002)."""

from __future__ import annotations

from galaxy_tool_xml_codemod.codemods.reorder_param_attributes import (
    ReorderParamAttributes,
)
from galaxy_tool_xml_codemod.cursor import Cursor
from galaxy_tool_xml_codemod.parse import parse_module


def _param_attrs(module_xml: bytes, *, name: str) -> tuple[str, ...]:
    """Helper — return the attribute order of the named ``<param>`` element."""
    module = parse_module(module_xml)
    ReorderParamAttributes().apply(module)
    for element in module.document.root.iter("param"):
        if element.get("name") == name:
            return tuple(element.attrib)
    raise AssertionError(f"no <param name={name!r}> found in fixture")


def test_param_with_canonical_order_is_unchanged() -> None:
    """Already-canonical attribute order produces no change."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs>
            <param name="x" type="text" value="v"/>
        </inputs>
    </tool>"""
    assert _param_attrs(xml, name="x") == ("name", "type", "value")


def test_param_attributes_are_reordered_to_iuc_priority() -> None:
    """Out-of-order attributes are rewritten in IUC priority order."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs>
            <param value="v" type="text" name="x"/>
        </inputs>
    </tool>"""
    assert _param_attrs(xml, name="x") == ("name", "type", "value")


def test_unknown_param_attributes_sort_alphabetical_after_known() -> None:
    """Attributes outside the IUC map sort alphabetically after the known ones."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs>
            <param zz="1" name="x" type="text" aa="2"/>
        </inputs>
    </tool>"""
    assert _param_attrs(xml, name="x") == ("name", "type", "aa", "zz")


def test_mutually_exclusive_slot_keeps_canonical_pair_order() -> None:
    """``truevalue`` precedes ``falsevalue`` (same slot, alphabetical tie-break)."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs>
            <param falsevalue="no" truevalue="yes" type="boolean" name="flag"/>
        </inputs>
    </tool>"""
    assert _param_attrs(xml, name="flag") == (
        "name",
        "type",
        "truevalue",
        "falsevalue",
    )


def test_each_param_in_a_multi_param_tool_is_reordered_independently() -> None:
    """Multiple ``<param>`` elements each get reordered."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs>
            <param value="v" type="text" name="a"/>
            <param type="integer" name="b" value="0"/>
            <conditional name="c">
                <param type="select" name="choice"/>
            </conditional>
        </inputs>
    </tool>"""
    module = parse_module(xml)
    ReorderParamAttributes().apply(module)
    orders = [tuple(p.attrib) for p in module.document.root.iter("param")]
    assert orders == [
        ("name", "type", "value"),
        ("name", "type", "value"),
        ("name", "type"),
    ]


def test_visits_only_param_elements() -> None:
    """The codemod ignores non-``<param>`` elements."""
    xml = b"""<tool profile="24.0" id="t" name="n" version="1">
        <inputs/>
    </tool>"""
    module = parse_module(xml)
    ReorderParamAttributes().apply(module)
    # Root <tool> attrs are NOT reordered by this codemod.
    assert tuple(module.document.root.attrib) == ("profile", "id", "name", "version")


def test_visit_param_returns_none_so_traversal_continues() -> None:
    """``visit_Param`` returns ``None`` so any nested elements are still visited."""

    class _Recorder(ReorderParamAttributes):
        def __init__(self) -> None:
            self.seen: list[str] = []

        def visit_Option(self, cursor: Cursor) -> None:
            self.seen.append(cursor.tag)

    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs>
            <param type="select" name="choice">
                <option value="a">A</option>
            </param>
        </inputs>
    </tool>"""
    recorder = _Recorder()
    recorder.apply(parse_module(xml))
    assert recorder.seen == ["option"]
