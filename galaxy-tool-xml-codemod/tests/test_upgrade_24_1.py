"""Tests for the ``Upgrade24_1`` codemod (single-step 24.1 -> 24.2 upgrade).

The 24.1 -> 24.2 schema delta that real corpus tools trip on is the ``format``
attribute gaining a pattern facet: ``FormatList`` (``<param>``) requires
comma-separated ``[a-z0-9._-]`` tokens, ``Format`` (``<data>``) a single such
token. ``Upgrade24_1`` normalizes ``format`` values — lowercase + strip
whitespace around comma-separated tokens — which unsticks tools whose only
problem is case/whitespace. A value that normalizes to empty (``format=""`` or
all-whitespace) is *dropped*: an empty datatype restriction is no restriction,
and ``""`` violates the pattern. A ``<data>`` comma-list (which ``Format``
forbids) has no single-token coercion and is left untouched.
"""

from __future__ import annotations

from galaxy_tool_xml.binding import newest_valid_profile
from lxml import etree

from galaxy_tool_xml_codemod.codemods.upgrade_24_1 import Upgrade24_1
from galaxy_tool_xml_codemod.parse import parse_module


def _tool(*, param_fmt: str | None = None, data_fmt: str | None = None) -> bytes:
    param = (
        f'<param name="i" type="data" format="{param_fmt}"/>'
        if param_fmt is not None
        else ""
    )
    data = (
        f'<data name="o" format="{data_fmt}"/>'
        if data_fmt is not None
        else '<data name="o"/>'
    )
    return (
        '<tool id="m" name="M" version="1.0.0" profile="24.1">'
        "<command><![CDATA[echo x]]></command>"
        f"<inputs>{param}</inputs><outputs>{data}</outputs></tool>"
    ).encode()


def _apply(xml: bytes) -> etree._Element:
    module = parse_module(xml)
    Upgrade24_1().apply(module)
    return module.document.root


def _format_of(root: etree._Element, tag: str) -> str | None:
    el = root.find(f".//{tag}[@format]")
    return None if el is None else el.get("format")


def test_lowercases_param_format_and_unsticks() -> None:
    root = _apply(_tool(param_fmt="BAM"))
    assert _format_of(root, "param") == "bam"
    assert newest_valid_profile(etree.tostring(root)) not in (None, "24.1")


def test_strips_spaces_in_param_format_list() -> None:
    root = _apply(_tool(param_fmt="fa, fasta"))
    assert _format_of(root, "param") == "fa,fasta"
    assert newest_valid_profile(etree.tostring(root)) not in (None, "24.1")


def test_trims_data_format() -> None:
    root = _apply(_tool(data_fmt="txt "))
    assert _format_of(root, "data") == "txt"
    assert newest_valid_profile(etree.tostring(root)) not in (None, "24.1")


def test_leaves_unfixable_data_comma_list_untouched() -> None:
    """A ``<data>`` comma-list has no single-token coercion — left as-is."""
    root = _apply(_tool(data_fmt="fasta,fastq"))
    assert _format_of(root, "data") == "fasta,fastq"
    assert newest_valid_profile(etree.tostring(root)) == "24.1"


def test_lowercases_data_comma_list_but_stays_stuck() -> None:
    """An uppercase ``<data>`` comma-list is lowercased, but ``Format`` still
    forbids the comma — the codemod mutates yet the tool stays stuck."""
    root = _apply(_tool(data_fmt="FASTA,FASTQ"))
    assert _format_of(root, "data") == "fasta,fastq"
    assert newest_valid_profile(etree.tostring(root)) == "24.1"


def test_leaves_help_format_enum_untouched() -> None:
    """``<help format>`` is an enum (markdown/restructuredtext), not a datatype.

    The codemod's ``format`` sweep is global, but a clean lowercase enum value
    normalizes to itself, so help is left untouched — pinning that the breadth
    is benign on the one non-datatype ``format`` attribute in the schema.
    """
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="24.1">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs>'
        b'<help format="markdown">doc</help></tool>'
    )
    module = parse_module(xml)
    Upgrade24_1().apply(module)
    help_element = module.document.root.find("help")
    assert help_element is not None
    assert help_element.get("format") == "markdown"


def test_deletes_empty_param_format_and_unsticks() -> None:
    """An empty ``format`` restricts nothing and violates the pattern — dropped."""
    root = _apply(_tool(param_fmt=""))
    param = root.find(".//param")
    assert param is not None
    assert param.get("format") is None
    assert newest_valid_profile(etree.tostring(root)) not in (None, "24.1")


def test_deletes_format_that_normalizes_to_empty() -> None:
    """A whitespace/comma-only value normalizes to empty and is dropped."""
    root = _apply(_tool(data_fmt=" , "))
    data = root.find(".//data[@name='o']")
    assert data is not None
    assert data.get("format") is None


def test_deletes_empty_ftype_in_test_output() -> None:
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="24.1">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs>'
        b'<tests><test><output name="o" ftype=""/></test></tests></tool>'
    )
    module = parse_module(xml)
    Upgrade24_1().apply(module)
    output = module.document.root.find(".//output")
    assert output is not None
    assert output.get("ftype") is None


def test_lowercases_ftype_in_test_output() -> None:
    """24.2 also pattern-restricts ``ftype``; uppercase test ftypes are normalized."""
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="24.1">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs>'
        b'<tests><test><output name="o" ftype="TXT"/></test></tests></tool>'
    )
    module = parse_module(xml)
    Upgrade24_1().apply(module)
    output = module.document.root.find(".//output[@ftype]")
    assert output is not None
    assert output.get("ftype") == "txt"
    assert newest_valid_profile(module.document) not in (None, "24.1")


def test_noop_on_already_clean_format() -> None:
    xml = _tool(param_fmt="bam")
    module = parse_module(xml)
    before = etree.tostring(module.document.root)
    Upgrade24_1().apply(module)
    assert etree.tostring(module.document.root) == before


def test_is_idempotent() -> None:
    module = parse_module(_tool(param_fmt="BAM"))
    Upgrade24_1().apply(module)
    once = etree.tostring(module.document.root)
    Upgrade24_1().apply(module)
    assert etree.tostring(module.document.root) == once
