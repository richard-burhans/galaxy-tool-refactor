"""Tests for GTX001 canonical 4-space indentation."""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_xml.document import ToolDocument

from galaxy_tool_xml_fmt.format import format_tool_document


def test_indents_unindented_tool_to_four_spaces(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool id='t' name='T' version='0'><inputs><param/></inputs></tool>"
    output = format_tool_document(make_doc(payload))
    assert b"\n    <inputs>" in output
    assert b"\n        <param" in output
    assert b"\n    </inputs>" in output


def test_indents_idempotently(make_doc: Callable[[bytes], ToolDocument]) -> None:
    payload = b"<tool id='t' name='T' version='0'><inputs><param/></inputs></tool>"
    once = format_tool_document(make_doc(payload))
    twice = format_tool_document(make_doc(once))
    assert once == twice


def test_preserves_cdata_in_command_element(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<command><![CDATA[echo hi]]></command>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b"<![CDATA[echo hi]]>" in output


def test_leaf_element_text_is_untouched(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool id='t' name='T' version='0'><help>some help text</help></tool>"
    output = format_tool_document(make_doc(payload))
    assert b"<help>some help text</help>" in output
