"""Tests for the shared CDATA predicates (GTR018/GTR019 substrate)."""

from __future__ import annotations

from lxml import etree

from galaxy_tool_xml.cdata import cdata_wrappable, is_cdata_wrapped, needs_cdata

_PARSER = etree.XMLParser(strip_cdata=False)  # mirror the tier-1 parser


def _command(body: bytes) -> etree._Element:
    root = etree.fromstring(b"<tool><command>" + body + b"</command></tool>", _PARSER)
    command = root.find("command")
    assert command is not None
    return command


def test_is_cdata_wrapped() -> None:
    assert is_cdata_wrapped(_command(b"<![CDATA[echo hi]]>"))
    assert not is_cdata_wrapped(_command(b"echo hi"))
    # Leading whitespace before the section still counts as wrapped.
    assert is_cdata_wrapped(_command(b"\n  <![CDATA[echo hi]]>"))


def test_cdata_wrappable_pure_text() -> None:
    assert cdata_wrappable(_command(b"echo hi"))
    # already wrapped → no.
    assert not cdata_wrappable(_command(b"<![CDATA[echo hi]]>"))
    # whitespace-only → no.
    assert not cdata_wrappable(_command(b"   \n  "))


def test_cdata_wrappable_residual_cases() -> None:
    # Mixed content (a child element) is not wrappable as one section.
    assert not cdata_wrappable(_command(b"echo <foo/> hi"))
    # A ]]> terminator cannot live inside a CDATA section.
    assert not cdata_wrappable(_command(b"echo ]]&gt; hi"))


def test_needs_cdata_is_the_union() -> None:
    # needs_cdata = has text, not wrapped — the population the practice applies to.
    assert needs_cdata(_command(b"echo hi"))  # fix-eligible
    assert needs_cdata(_command(b"echo <foo/> hi"))  # advisory residual
    assert not needs_cdata(_command(b"<![CDATA[echo hi]]>"))  # already wrapped
    assert not needs_cdata(_command(b"   "))  # no text


def test_partition_is_disjoint_and_exhaustive() -> None:
    # For every body that needs CDATA, exactly one of {wrappable, residual} holds.
    for body in (b"echo hi", b"echo <foo/> hi", b"echo ]]&gt; hi"):
        element = _command(body)
        assert needs_cdata(element)
        residual = needs_cdata(element) and not cdata_wrappable(element)
        assert cdata_wrappable(element) != residual  # exactly one
