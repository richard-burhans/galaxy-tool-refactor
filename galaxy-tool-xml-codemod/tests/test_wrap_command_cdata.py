"""Tests for ``WrapCommandCdata`` (GTR018) — wrap a pure-text <command> in CDATA.

Behaviour-preserving: lxml already exposes the entity-unescaped command text, so
wrapping changes only the serialised bytes (entities become literal inside CDATA),
not the value Galaxy runs. Mixed-content / already-wrapped / ``]]>``-bearing bodies
are left for the advisory GTR022 check.
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_xml_codemod.codemods.wrap_command_cdata import WrapCommandCdata
from galaxy_tool_xml_codemod.parse import parse_module


def _tool(command: bytes) -> bytes:
    return (
        b'<tool id="m" name="M" version="1.0.0" profile="26.0">'
        + command
        + b"<inputs/></tool>"
    )


def _command(module: object) -> etree._Element:
    return module.document.root.find("command")  # type: ignore[attr-defined]


def test_wraps_pure_text_command_and_detects_it() -> None:
    module = parse_module(_tool(b"<command>echo a &amp;&amp; b</command>"))
    assert _command(module).text == "echo a && b"  # entity-unescaped by lxml
    changes = list(WrapCommandCdata().detect(module))
    assert len(changes) == 1
    assert changes[0].code == "GTR018"
    assert "command" in changes[0].message
    assert b"CDATA" not in etree.tostring(module.document.root)  # detect is read-only
    WrapCommandCdata().apply(module)
    assert b"<![CDATA[echo a && b]]>" in etree.tostring(module.document.root)
    assert _command(module).text == "echo a && b"  # rendered value unchanged


def test_noop_when_already_cdata() -> None:
    module = parse_module(_tool(b"<command><![CDATA[echo a && b]]></command>"))
    assert not list(WrapCommandCdata().detect(module))
    before = etree.tostring(module.document.root)
    WrapCommandCdata().apply(module)
    assert etree.tostring(module.document.root) == before


def test_noop_when_whitespace_only_or_empty() -> None:
    ws = parse_module(_tool(b"<command>   </command>"))
    assert not list(WrapCommandCdata().detect(ws))
    empty = parse_module(_tool(b"<command/>"))
    assert not list(WrapCommandCdata().detect(empty))


def test_noop_when_mixed_content() -> None:
    # A child element means the body can't be expressed as one CDATA section.
    module = parse_module(_tool(b"<command>echo <foo/></command>"))
    assert not list(WrapCommandCdata().detect(module))


def test_noop_when_cdata_terminator_present() -> None:
    # `]]>` (parsed from the required `]]&gt;` escaping) can't live in a section.
    module = parse_module(_tool(b"<command>echo a]]&gt;b</command>"))
    assert _command(module).text == "echo a]]>b"
    assert not list(WrapCommandCdata().detect(module))


def test_is_idempotent() -> None:
    module = parse_module(_tool(b"<command>echo a &amp;&amp; b</command>"))
    WrapCommandCdata().apply(module)
    once = etree.tostring(module.document.root)
    WrapCommandCdata().apply(module)
    assert etree.tostring(module.document.root) == once
