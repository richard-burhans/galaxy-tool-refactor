"""Tests for GTR003: blank line between top-level <tool> children."""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_source.document import ToolDocument

from galaxy_tool_xml_fmt.format import format_tool_document


def test_blank_line_between_top_level_children(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<description>D</description>"
        b"<inputs><param name='p' type='text'/></inputs>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b"</description>\n\n    <inputs>" in output


def test_no_blank_line_after_last_top_level_child(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<description>D</description>"
        b"<inputs><param name='p' type='text'/></inputs>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b"</inputs>\n</tool>" in output


def test_no_blank_line_between_nested_children(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<inputs>"
        b"<param name='p1' type='text'/>"
        b"<param name='p2' type='text'/>"
        b"</inputs>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    inputs_block = output[output.index(b"<inputs>") : output.index(b"</inputs>")]
    assert b"\n\n" not in inputs_block


def test_single_top_level_child_emits_no_blank(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool id='t' name='T' version='0'><description>D</description></tool>"
    output = format_tool_document(make_doc(payload))
    assert b"\n\n" not in output


def test_blank_line_policy_is_idempotent(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<description>D</description>"
        b"<inputs><param name='p' type='text'/></inputs>"
        b"<outputs><data name='o' format='txt'/></outputs>"
        b"</tool>"
    )
    once = format_tool_document(make_doc(payload))
    twice = format_tool_document(make_doc(once))
    assert once == twice


def test_non_tool_root_is_untouched(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    output = format_tool_document(make_doc(b"<other><child/><child/></other>"))
    assert b"\n\n" not in output
