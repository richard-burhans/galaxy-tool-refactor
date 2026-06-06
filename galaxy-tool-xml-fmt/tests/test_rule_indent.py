"""Tests for GTR001 canonical 4-space indentation."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from galaxy_tool_xml.document import ToolDocument
from lxml import etree

from galaxy_tool_xml_fmt.format import format_tool_document


@pytest.mark.xfail(
    strict=True,
    reason="behavior-preservation bug GTR001: a whitespace-only .tail inside MIXED "
    "content is rewritten by the indent rule, changing rendered text (zero corpus "
    "incidence); see docs/behavior_preservation.md. Fix: skip ws-tail rewrite when the "
    "parent holds mixed content.",
)
def test_mixed_content_inline_whitespace_is_preserved(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # In mixed content, the single space between </b> and <i> is a significant word
    # separator; reindenting it to newline+spaces changes the rendered <help> text.
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<help>See <b>this</b> <i>tool</i> docs.</help></tool>"
    )
    output = format_tool_document(make_doc(payload))
    rendered = "".join(etree.fromstring(output).find("help").itertext())
    assert rendered == "See this tool docs."


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
