"""Tests for GTR001 canonical 4-space indentation."""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_source.document import ToolDocument
from lxml import etree

from galaxy_tool_xml_fmt.format import format_tool_document


def test_mixed_content_inline_whitespace_is_preserved(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # In mixed content, the single space between </b> and <i> is a significant word
    # separator; reindenting it to newline+spaces would change the rendered <help>
    # text (behaviour-preservation GTR001 — now guarded, was a strict xfail).
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<help>See <b>this</b> <i>tool</i> docs.</help></tool>"
    )
    output = format_tool_document(make_doc(payload))
    rendered = "".join(etree.fromstring(output).find("help").itertext())
    assert rendered == "See this tool docs."


def test_ws_tail_between_command_expands_is_preserved(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # A whitespace-only tail between <expand> children of <command> is shell payload:
    # the macros splice into one command line, and rewriting the space to
    # newline+indent would turn a word separator into a shell command separator.
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<command><expand macro='a'/> <expand macro='b'/></command></tool>"
    )
    output = format_tool_document(make_doc(payload))
    command = etree.fromstring(output).find("command")
    first_expand = command[0]
    assert first_expand.tail == " "


def test_ws_text_of_command_with_children_is_preserved(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # <command> body is read verbatim (strip=False): even a whitespace-only .text
    # ahead of an <expand> child is payload, not layout.
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<command> <expand macro='a'/>$input</command></tool>"
    )
    output = format_tool_document(make_doc(payload))
    command = etree.fromstring(output).find("command")
    assert command.text == " "
    assert command[0].tail == "$input"


def test_help_with_expand_children_is_left_alone(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # RST is indentation-sensitive: indenting inside <help> around a macro-supplied
    # body would prepend leading spaces to the expanded RST (blockquote drift).
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<help><expand macro='helpdoc'/></help></tool>"
    )
    output = format_tool_document(make_doc(payload))
    help_element = etree.fromstring(output).find("help")
    assert help_element.text is None
    assert help_element[0].tail is None


def test_mixed_content_guard_is_idempotent(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<help>See <b>this</b> <i>tool</i> docs.</help>"
        b"<command><expand macro='a'/> <expand macro='b'/></command>"
        b"<inputs><param/></inputs></tool>"
    )
    once = format_tool_document(make_doc(payload))
    twice = format_tool_document(make_doc(once))
    assert once == twice
    # Structural siblings around the guarded subtrees still get canonical indent.
    assert b"\n    <inputs>" in once


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
