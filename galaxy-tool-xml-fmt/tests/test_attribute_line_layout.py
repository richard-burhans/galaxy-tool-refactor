"""Regression tests for the attributes-on-one-line policy.

There is no GTR rule for this — lxml's ``etree.tostring`` default
already keeps all of an element's attributes on a single line, even
when the source spread them across multiple lines or when the value
contains literal whitespace (which it escapes as ``&#10;`` / ``&#9;``).
These tests lock that behaviour in; see ``docs/decisions.md`` D8.
"""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_xml.document import ToolDocument
from lxml import etree

from galaxy_tool_xml_fmt.format import format_tool_document


def test_multiline_attributes_collapse_to_one_line(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='1'>"
        b"<inputs>"
        b"<param\n"
        b"    name='x'\n"
        b"    type='text'\n"
        b"    label='L'\n"
        b"    help='H'/>"
        b"</inputs>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b'<param name="x" type="text" label="L" help="H"/>' in output


def test_many_attributes_stay_on_one_line(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='1'>"
        b"<inputs>"
        b"<param name='x' type='text' format='txt' value='v'"
        b" label='L' help='H' optional='false'/>"
        b"</inputs>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    param_lines = [line for line in output.splitlines() if b"<param" in line]
    assert len(param_lines) == 1
    assert b'help="H"' in param_lines[0]


def test_newline_inside_attribute_value_preserved_as_entity() -> None:
    parser = etree.XMLParser(strip_cdata=False)
    root = etree.fromstring(
        b'<tool id="t" name="T" version="1">'
        b"<inputs><param name='x' type='text'/></inputs>"
        b"</tool>",
        parser=parser,
    )
    param = root.find("inputs/param")
    assert param is not None
    param.set("label", "line1\nline2")
    doc = ToolDocument(etree.ElementTree(root))
    output = format_tool_document(doc)
    assert b'label="line1&#10;line2"' in output


def test_no_newline_appears_inside_a_start_tag(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='1'>"
        b"<inputs>"
        b"<param name='x' type='text' label='L' help='H'/>"
        b"</inputs>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    in_tag = False
    for byte in output:
        if byte == ord("<"):
            in_tag = True
        elif byte == ord(">"):
            in_tag = False
        elif in_tag and byte == ord("\n"):
            raise AssertionError("newline found inside a tag")
