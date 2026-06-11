"""Tests for GTR004: empty-element shorthand."""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_source.document import ToolDocument
from lxml import etree

from galaxy_tool_fmt.format import format_tool_document


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


def test_whitespace_only_content_bearing_text_is_preserved(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # A <configfile> body is template payload Galaxy reads verbatim (strip=False), so
    # a whitespace-only body is real content, not layout — it must NOT collapse to
    # <configfile/>. Behaviour-preservation GTR004 (docs/behavior_preservation.md).
    payload = (
        b"<tool id='t' name='T' version='0'><configfiles>"
        b"<configfile name='cfg'><![CDATA[   ]]></configfile>"
        b"</configfiles></tool>"
    )
    output = format_tool_document(make_doc(payload))
    configfile = etree.fromstring(output).find(".//configfile")
    assert configfile is not None
    assert configfile.text == "   "


def test_whitespace_only_help_still_collapses(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # <help> is NOT content-bearing for this purpose: whitespace-only help renders
    # empty either way, so the opinionated formatter still tidies it to <help/> (the
    # GTR004 content-bearing guard must stay surgical, not over-preserve).
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<help><![CDATA[\n   ]]></help>"
        b"</tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b"<help/>" in output


def test_schema_derived_text_bearing_leaves_are_preserved(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # The derivation widened the guard beyond the old hand list: option labels,
    # eval'd filter text, description are text content by schema.
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<description> </description>"
        b"<inputs><param name='s' type='select'>"
        b"<option value='x'> </option></param></inputs>"
        b"<outputs><data name='o'><filter> </filter></data></outputs></tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b"<description> </description>" in output
    assert b"<option value='x'> </option>".replace(b"'", b'"') in output
    assert b"<filter> </filter>" in output


def test_configfiles_inputs_text_is_preserved_tool_inputs_still_collapses(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # The same-named-element collision the derivation surfaced: <inputs> is
    # simpleContent under <configfiles> (a text body by schema) but
    # element-only under <tool> (layout, still tidied).
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<configfiles><inputs filename='f'> </inputs></configfiles>"
        b"<inputs>\n</inputs>"
        b"<outputs><data name='o'/></outputs></tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b'<inputs filename="f"> </inputs>' in output  # payload context kept
    assert b"<inputs/>" in output  # the tool-level structural one collapsed


def test_macros_whitespace_still_collapses(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    # xs:anyType in legacy schemas, but Galaxy's loader clears the element
    # after harvesting children (xml_macros.py:39-45) — its text is dead.
    payload = (
        b"<tool id='t' name='T' version='0'><macros>\n</macros>"
        b"<outputs><data name='o'/></outputs></tool>"
    )
    output = format_tool_document(make_doc(payload))
    assert b"<macros/>" in output
