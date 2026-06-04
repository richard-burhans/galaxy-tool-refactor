"""Regression tests for the always-double-quote-attributes policy.

There is no GTR rule for this — lxml's ``etree.tostring`` default
already always uses double quotes for attribute values, escaping any
embedded ``"`` as ``&quot;``. These tests lock that behaviour in so a
future lxml change can't silently drift our output away from the
documented policy (see ``docs/decisions.md`` D7).
"""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_xml.document import ToolDocument
from lxml import etree

from galaxy_tool_xml_fmt.format import format_tool_document


def test_simple_attribute_values_are_double_quoted(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool id='t' name='T' version='1'><inputs/></tool>"
    output = format_tool_document(make_doc(payload))
    assert b'id="t"' in output
    assert b'name="T"' in output
    assert b'version="1"' in output


def test_single_quoted_input_serializes_double_quoted(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool id='t' name='T' version='1'><inputs/></tool>"
    output = format_tool_document(make_doc(payload))
    assert b"id='t'" not in output
    assert b"name='T'" not in output


def test_double_quote_inside_value_is_escaped_as_entity() -> None:
    parser = etree.XMLParser(strip_cdata=False)
    root = etree.fromstring(
        b'<tool id="t" name="T" version="1"><inputs/></tool>', parser=parser
    )
    inputs = root.find("inputs")
    assert inputs is not None
    inputs.set("label", 'has "quote" in it')
    doc = ToolDocument(etree.ElementTree(root))
    output = format_tool_document(doc)
    assert b'label="has &quot;quote&quot; in it"' in output


def test_single_quote_inside_value_stays_unescaped() -> None:
    parser = etree.XMLParser(strip_cdata=False)
    root = etree.fromstring(
        b'<tool id="t" name="T" version="1"><inputs/></tool>', parser=parser
    )
    inputs = root.find("inputs")
    assert inputs is not None
    inputs.set("label", "it's fine")
    doc = ToolDocument(etree.ElementTree(root))
    output = format_tool_document(doc)
    assert b'label="it\'s fine"' in output
