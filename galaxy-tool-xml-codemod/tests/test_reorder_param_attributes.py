"""Tests for the ``ReorderParamAttributes`` codemod (port of fmt GTR002)."""

from __future__ import annotations

from collections.abc import Iterable

from galaxy_tool_xml_codemod.change import Change
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


def test_detect_param_does_not_halt_descent_into_nested_elements() -> None:
    """The walk descends past a ``<param>`` so nested elements are still seen."""

    class _Recorder(ReorderParamAttributes):
        def __init__(self) -> None:
            self.seen: list[str] = []

        def detect_Option(self, cursor: Cursor) -> Iterable[Change]:
            self.seen.append(cursor.tag)
            return ()

    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs>
            <param type="select" name="choice">
                <option value="a">A</option>
            </param>
        </inputs>
    </tool>"""
    recorder = _Recorder()
    list(recorder.detect(parse_module(xml)))
    assert recorder.seen == ["option"]


def test_detect_yields_located_change_for_unordered_param() -> None:
    """``detect`` reports a GTR002 change at the param's xpath, without mutating."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs><param type="text" name="x"/></inputs></tool>"""
    module = parse_module(xml)
    changes = list(ReorderParamAttributes().detect(module))
    assert len(changes) == 1
    assert changes[0].code == "GTR002"
    # lxml omits the positional index for an only-child of its tag.
    assert changes[0].xpath == "/tool/inputs/param"
    # detect is non-mutating: the attribute order is untouched.
    param = next(module.document.root.iter("param"))
    assert tuple(param.attrib) == ("type", "name")


def test_detect_yields_nothing_for_already_ordered_param() -> None:
    """An already-ordered ``<param>`` produces no change."""
    xml = b"""<tool id="t" name="n" version="1" profile="24.0">
        <inputs><param name="x" type="text"/></inputs></tool>"""
    module = parse_module(xml)
    assert list(ReorderParamAttributes().detect(module)) == []
