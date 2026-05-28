"""Tests for GTX002 canonical <param> attribute ordering."""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_xml.document import ToolDocument
from lxml import etree

from galaxy_tool_xml_fmt.edits import ReorderAttributes, apply_edits
from galaxy_tool_xml_fmt.format import format_tool_document


def test_reorders_param_attributes_to_iuc_order(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'><inputs>"
        b"<param label='L' type='text' name='n'/>"
        b"</inputs></tool>"
    )
    output = format_tool_document(make_doc(payload))
    param_line = next(line for line in output.splitlines() if b"<param" in line)
    name_idx = param_line.index(b"name=")
    type_idx = param_line.index(b"type=")
    label_idx = param_line.index(b"label=")
    assert name_idx < type_idx < label_idx


def test_unknown_attributes_sort_alphabetically_after_known(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'><inputs>"
        b"<param zzz='z' aaa='a' name='n' type='text'/>"
        b"</inputs></tool>"
    )
    output = format_tool_document(make_doc(payload))
    param_line = next(line for line in output.splitlines() if b"<param" in line)
    name_idx = param_line.index(b"name=")
    type_idx = param_line.index(b"type=")
    aaa_idx = param_line.index(b"aaa=")
    zzz_idx = param_line.index(b"zzz=")
    assert name_idx < type_idx < aaa_idx < zzz_idx


def test_param_reordering_is_idempotent(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'><inputs>"
        b"<param label='L' type='text' name='n' optional='true'/>"
        b"</inputs></tool>"
    )
    once = format_tool_document(make_doc(payload))
    twice = format_tool_document(make_doc(once))
    assert once == twice


def test_non_param_elements_are_untouched(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'><inputs>"
        b"<conditional label='L' name='n'>"
        b"<param name='n2' type='text'/>"
        b"</conditional>"
        b"</inputs></tool>"
    )
    output = format_tool_document(make_doc(payload))
    conditional_line = next(
        line for line in output.splitlines() if b"<conditional" in line
    )
    assert conditional_line.index(b"label=") < conditional_line.index(b"name=")


def test_apply_edits_drops_reorder_when_names_mismatch() -> None:
    payload = b"<root><param a='1' b='2'/></root>"
    parser = etree.XMLParser(strip_cdata=False)
    root = etree.fromstring(payload, parser=parser)
    param = root.find("param")
    assert param is not None
    apply_edits([ReorderAttributes(element=param, names=("a",))])
    assert dict(param.attrib) == {"a": "1", "b": "2"}
