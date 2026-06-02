"""Tests for ``FixOutputFormatInput`` (GTX015), the format=input runtime-gated fix."""

from __future__ import annotations

from lxml import etree

from galaxy_tool_xml_codemod.codemods.fix_output_format_input import (
    FixOutputFormatInput,
)
from galaxy_tool_xml_codemod.parse import parse_module


def _tool(inputs: bytes, outputs: bytes) -> bytes:
    return (
        b'<tool id="m" name="M" version="1.0.0" profile="26.0">'
        b"<command><![CDATA[echo x]]></command>"
        b"<inputs>" + inputs + b"</inputs>"
        b"<outputs>" + outputs + b"</outputs></tool>"
    )


def test_single_data_input_swaps_to_format_source() -> None:
    module = parse_module(
        _tool(b'<param type="data" name="i"/>', b'<data name="o" format="input"/>')
    )
    changes = list(FixOutputFormatInput().detect(module))
    assert len(changes) == 1 and changes[0].code == "GTX015"
    FixOutputFormatInput().apply(module)
    data = module.document.root.find("outputs/data")
    assert data.get("format") is None
    assert data.get("format_source") == "i"


def test_multiple_format_input_outputs_all_swapped() -> None:
    module = parse_module(
        _tool(
            b'<param type="data" name="i"/>',
            b'<data name="a" format="input"/><data name="b" format="input"/>',
        )
    )
    FixOutputFormatInput().apply(module)
    data = module.document.root.findall("outputs/data")
    assert [d.get("format_source") for d in data] == ["i", "i"]


def test_two_data_inputs_left_untouched() -> None:
    module = parse_module(
        _tool(
            b'<param type="data" name="i"/><param type="data" name="j"/>',
            b'<data name="o" format="input"/>',
        )
    )
    assert not list(FixOutputFormatInput().detect(module))
    before = etree.tostring(module.document.root)
    FixOutputFormatInput().apply(module)
    assert etree.tostring(module.document.root) == before


def test_nested_single_data_input_left_untouched() -> None:
    # A single data input nested in a conditional needs a qualified reference.
    module = parse_module(
        _tool(
            b'<conditional name="c"><param type="data" name="i"/></conditional>',
            b'<data name="o" format="input"/>',
        )
    )
    before = etree.tostring(module.document.root)
    FixOutputFormatInput().apply(module)
    assert etree.tostring(module.document.root) == before


def test_existing_format_source_left_untouched() -> None:
    # With a co-present format_source, format="input" is already inert at runtime
    # (Galaxy's format_source branch wins), so the author's source must be preserved
    # even when it points at a non-data-param input (here a data_collection element).
    module = parse_module(
        _tool(
            b'<param type="data" name="i"/>'
            b'<param type="data_collection" name="coll"/>',
            b'<data name="o" format="input" format_source="coll"/>',
        )
    )
    assert not list(FixOutputFormatInput().detect(module))
    before = etree.tostring(module.document.root)
    FixOutputFormatInput().apply(module)
    assert etree.tostring(module.document.root) == before


def test_noop_when_not_format_input() -> None:
    module = parse_module(
        _tool(b'<param type="data" name="i"/>', b'<data name="o" format="txt"/>')
    )
    before = etree.tostring(module.document.root)
    FixOutputFormatInput().apply(module)
    assert etree.tostring(module.document.root) == before


def test_is_idempotent() -> None:
    module = parse_module(
        _tool(b'<param type="data" name="i"/>', b'<data name="o" format="input"/>')
    )
    FixOutputFormatInput().apply(module)
    once = etree.tostring(module.document.root)
    FixOutputFormatInput().apply(module)
    assert etree.tostring(module.document.root) == once


def test_introduced_at_1604() -> None:
    assert FixOutputFormatInput.introduced_profile == "16.04"
