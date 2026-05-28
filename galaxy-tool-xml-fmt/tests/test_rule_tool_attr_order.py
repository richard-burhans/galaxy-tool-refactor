"""Tests for GTX005: canonical <tool> attribute ordering."""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_xml.document import ToolDocument

from galaxy_tool_xml_fmt.format import format_tool_document


def _tool_start(output: bytes, tag: bytes = b"<tool") -> bytes:
    start = output.index(tag)
    end = output.index(b">", start) + 1
    return output[start:end]


def test_reorders_tool_attributes_to_canonical_order(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool version='1' name='T' id='t'><inputs/></tool>"
    output = format_tool_document(make_doc(payload))
    tool = _tool_start(output)
    assert tool.index(b"id=") < tool.index(b"name=") < tool.index(b"version=")


def test_profile_after_required_attributes(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool profile='16.04' id='t' name='T' version='1'><inputs/></tool>"
    output = format_tool_document(make_doc(payload))
    tool = _tool_start(output)
    assert (
        tool.index(b"id=")
        < tool.index(b"name=")
        < tool.index(b"version=")
        < tool.index(b"profile=")
    )


def test_unknown_attributes_sort_alphabetically_after_known(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool zzz='z' aaa='a' id='t' name='T' version='1'><inputs/></tool>"
    output = format_tool_document(make_doc(payload))
    tool = _tool_start(output)
    assert (
        tool.index(b"id=")
        < tool.index(b"version=")
        < tool.index(b"aaa=")
        < tool.index(b"zzz=")
    )


def test_tool_attribute_reordering_is_idempotent(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool version='1' name='T' id='t' profile='16.04'><inputs/></tool>"
    once = format_tool_document(make_doc(payload))
    twice = format_tool_document(make_doc(once))
    assert once == twice


def test_non_tool_root_attributes_untouched(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    output = format_tool_document(
        make_doc(b"<other version='1' name='T' id='t'><child/></other>")
    )
    other = _tool_start(output, tag=b"<other")
    assert other.index(b"version=") < other.index(b"name=") < other.index(b"id=")
