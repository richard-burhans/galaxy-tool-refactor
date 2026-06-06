"""Tests for GTR004: empty-element shorthand."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from galaxy_tool_xml.document import ToolDocument
from lxml import etree

from galaxy_tool_xml_fmt.format import format_tool_document


def test_parsed_empty_long_form_serializes_short(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool id='t' name='T' version='0'><inputs></inputs></tool>"
    output = format_tool_document(make_doc(payload))
    assert b"<inputs/>" in output
    assert b"<inputs></inputs>" not in output


def test_whitespace_only_text_collapses_to_short_form(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool id='t' name='T' version='0'><inputs>\n    </inputs></tool>"
    output = format_tool_document(make_doc(payload))
    assert b"<inputs/>" in output


def test_text_content_is_preserved(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<description>real content</description>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b"<description>real content</description>" in output


def test_element_with_children_is_not_collapsed(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<inputs><param name='p' type='text'/></inputs>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b"<inputs>" in output
    assert b"</inputs>" in output


def test_cdata_with_real_content_is_preserved(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<command><![CDATA[echo hi]]></command>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b"<![CDATA[echo hi]]>" in output


def test_empty_element_shorthand_is_idempotent(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool id='t' name='T' version='0'><inputs>\n</inputs><outputs/></tool>"
    once = format_tool_document(make_doc(payload))
    twice = format_tool_document(make_doc(once))
    assert once == twice


def test_whitespace_only_xml_comment_is_preserved(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # GTR004 must not iterate Comment / ProcessingInstruction nodes — their
    # ``.text`` mimics a whitespace-only empty element, and clearing it makes
    # lxml drop the comment from the output (the 12 corpus regressions of
    # 2026-05-28 were all variants of this).
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<inputs>"
        b"<param name='a' type='text'/>"
        b"<!--  -->"
        b"<param name='b' type='text'/>"
        b"</inputs>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b"<!--  -->" in output


@pytest.mark.xfail(
    strict=True,
    reason="behavior-preservation bug GTR004: whitespace-only .text on a content-"
    "bearing leaf (<configfile>/<command>/<token>) is cleared, dropping runtime "
    "template content (Galaxy reads it verbatim, strip=False); see "
    "docs/behavior_preservation.md. Fix: exclude content-bearing tags from the clear.",
)
def test_whitespace_only_configfile_content_is_preserved(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # A <configfile> whose body is three spaces is a real (whitespace) template
    # payload; collapsing it to <configfile/> silently drops that content.
    payload = (
        b"<tool id='t' name='T' version='0'><configfiles>"
        b"<configfile name='cfg'><![CDATA[   ]]></configfile>"
        b"</configfiles></tool>"
    )
    output = format_tool_document(make_doc(payload))
    configfile = etree.fromstring(output).find(".//configfile")
    assert configfile is not None
    assert configfile.text == "   "
