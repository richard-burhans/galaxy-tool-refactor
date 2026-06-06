"""Tests for ``WrapHelpCdata`` (GTR019) — wrap a pure-text <help> in CDATA.

Behaviour-preserving: lxml exposes the entity-unescaped help text, so wrapping
changes only the serialised bytes, not the reStructuredText Galaxy renders.
Mixed-content / already-wrapped / ``]]>``-bearing bodies are left for GTR019.2.
"""

from __future__ import annotations

import pytest
from lxml import etree

from galaxy_tool_xml_codemod.codemods.wrap_help_cdata import WrapHelpCdata
from galaxy_tool_xml_codemod.parse import parse_module


def _tool(help_: bytes) -> bytes:
    return (
        b'<tool id="m" name="M" version="1.0.0" profile="26.0">'
        b"<command><![CDATA[echo x]]></command><inputs/>" + help_ + b"</tool>"
    )


def _help(module: object) -> etree._Element:
    return module.document.root.find("help")  # type: ignore[attr-defined]


def test_wraps_pure_text_help_and_detects_it() -> None:
    module = parse_module(_tool(b"<help>See &lt;http://x&gt; for info</help>"))
    assert _help(module).text == "See <http://x> for info"  # entity-unescaped
    changes = list(WrapHelpCdata().detect(module))
    assert len(changes) == 1
    assert changes[0].code == "GTR019.1"
    assert "help" in changes[0].message
    WrapHelpCdata().apply(module)
    serialized = etree.tostring(module.document.root)
    assert b"<![CDATA[See <http://x> for info]]>" in serialized
    assert _help(module).text == "See <http://x> for info"  # rendered value unchanged


def test_noop_when_already_cdata() -> None:
    module = parse_module(_tool(b"<help><![CDATA[Some help.]]></help>"))
    assert not list(WrapHelpCdata().detect(module))
    before = etree.tostring(module.document.root)
    WrapHelpCdata().apply(module)
    assert etree.tostring(module.document.root) == before


def test_noop_when_whitespace_only_or_empty() -> None:
    ws = parse_module(_tool(b"<help>\n   </help>"))
    assert not list(WrapHelpCdata().detect(ws))
    empty = parse_module(_tool(b"<help/>"))
    assert not list(WrapHelpCdata().detect(empty))


def test_noop_when_mixed_content() -> None:
    module = parse_module(_tool(b"<help>See <foo/> here</help>"))
    assert not list(WrapHelpCdata().detect(module))


def test_is_idempotent() -> None:
    module = parse_module(_tool(b"<help>See &lt;x&gt;</help>"))
    WrapHelpCdata().apply(module)
    once = etree.tostring(module.document.root)
    WrapHelpCdata().apply(module)
    assert etree.tostring(module.document.root) == once


@pytest.mark.xfail(
    strict=True,
    reason="behavior-preservation bug GTR019.1: a carriage return makes the CDATA wrap "
    "non-idempotent (&#13; -> raw 0x0d -> \\n on reparse); see "
    "docs/behavior_preservation.md. Fix: shared cdata_wrappable must reject \\r.",
)
def test_carriage_return_wrap_is_idempotent() -> None:
    # A <help> body with a literal CR: wrapping it in CDATA loses the CR (no in-CDATA
    # form for &#13;), so a second pass over the re-parsed (CR->LF) body differs.
    module = parse_module(_tool(b"<help>line one&#13;\nmore</help>"))
    WrapHelpCdata().apply(module)
    once = etree.tostring(module.document.root)
    module2 = parse_module(once)
    WrapHelpCdata().apply(module2)
    assert etree.tostring(module2.document.root) == once
