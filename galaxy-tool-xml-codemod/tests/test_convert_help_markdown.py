"""Tests for the GTR092 ``ConvertHelpToMarkdown`` codemod (opt-in, never canonical)."""

from __future__ import annotations

from galaxy_tool_xml.binding import load_tool, validate_tool
from lxml import etree

from galaxy_tool_xml_codemod.codemods.convert_help_markdown import (
    _HELP_FORMAT_PROFILE,
    ConvertHelpToMarkdown,
)
from galaxy_tool_xml_codemod.parse import parse_module


def _tool(
    *, profile: str | None = "24.2", help_body: str = "", attrs: str = ""
) -> bytes:
    profile_attr = f" profile='{profile}'" if profile else ""
    return (
        f"<tool id='x' name='X' version='1.0'{profile_attr}>"
        f"<command><![CDATA[echo hi]]></command>"
        f"<help{attrs}>{help_body}</help></tool>"
    ).encode()


_RST = "Section Title\n=============\n\nSome **bold** body text.\n"


def _help(module: object) -> etree._Element:
    return module.document.root.find("help")  # type: ignore[attr-defined,union-attr,return-value]


def test_detect_flags_convertible_help() -> None:
    module = parse_module(_tool(help_body=_RST))
    changes = list(ConvertHelpToMarkdown().detect(module))
    assert len(changes) == 1
    assert changes[0].code == "GTR092"


def test_apply_converts_and_marks_format() -> None:
    module = parse_module(_tool(help_body=_RST))
    ConvertHelpToMarkdown().apply(module)
    help_element = _help(module)
    assert help_element.get("format") == "markdown"
    assert "# Section Title" in (help_element.text or "")
    assert "**bold**" in (help_element.text or "")


def test_apply_is_idempotent() -> None:
    module = parse_module(_tool(help_body=_RST))
    ConvertHelpToMarkdown().apply(module)
    once = etree.tostring(module.document.tree)
    ConvertHelpToMarkdown().apply(module)
    assert etree.tostring(module.document.tree) == once


def test_profile_gate_skips_old_profiles() -> None:
    # help@format is XSD-valid only at >= 24.2; older (and defaulted) profiles skip.
    for profile in (None, "21.09", "24.1"):
        module = parse_module(_tool(profile=profile, help_body=_RST))
        assert list(ConvertHelpToMarkdown().detect(module)) == []
        before = etree.tostring(module.document.tree)
        ConvertHelpToMarkdown().apply(module)
        assert etree.tostring(module.document.tree) == before


def test_converted_tool_validates_at_the_gate_profile() -> None:
    # The pin behind _HELP_FORMAT_PROFILE: a converted tool is XSD-valid there,
    # and the same converted shape is XSD-invalid one profile earlier.
    module = parse_module(_tool(help_body=_RST))
    ConvertHelpToMarkdown().apply(module)
    converted = etree.tostring(module.document.tree)
    assert validate_tool(load_tool(converted)).valid
    downgraded = converted.replace(b'profile="24.2"', b'profile="24.1"')
    assert downgraded != converted
    assert not validate_tool(load_tool(downgraded)).valid


def test_skips_already_markdown() -> None:
    module = parse_module(
        _tool(help_body="# already markdown", attrs=" format='markdown'")
    )
    assert list(ConvertHelpToMarkdown().detect(module)) == []


def test_skips_macro_bearing_help() -> None:
    module = parse_module(_tool(help_body="Intro.\n\n@HELP_BODY@\n"))
    assert list(ConvertHelpToMarkdown().detect(module)) == []


def test_skips_non_commonmark_help() -> None:
    module = parse_module(_tool(help_body="term\n   the definition\n"))
    assert list(ConvertHelpToMarkdown().detect(module)) == []
    before = etree.tostring(module.document.tree)
    ConvertHelpToMarkdown().apply(module)
    assert etree.tostring(module.document.tree) == before


def test_skips_gate_failing_help() -> None:
    module = parse_module(_tool(help_body="A paragraph with a ``lit`eral`` span.\n"))
    assert list(ConvertHelpToMarkdown().detect(module)) == []


def test_repairs_then_converts_invalid_help() -> None:
    # short title underline: GTR089.1-repairable, then convertible
    module = parse_module(_tool(help_body="Long Title\n====\n\nA paragraph.\n"))
    ConvertHelpToMarkdown().apply(module)
    help_element = _help(module)
    assert help_element.get("format") == "markdown"
    assert "# Long Title" in (help_element.text or "")


def test_preserves_cdata_wrapping() -> None:
    raw = (
        b"<tool id='x' name='X' version='1.0' profile='24.2'>"
        b"<command><![CDATA[echo hi]]></command>"
        b"<help><![CDATA[Section Title\n=============\n\nSome **bold** text.\n]]>"
        b"</help></tool>"
    )
    module = parse_module(raw)
    ConvertHelpToMarkdown().apply(module)
    serialized = etree.tostring(module.document.tree)
    assert b"<![CDATA[" in serialized
    assert _help(module).get("format") == "markdown"


def test_meta_is_opt_in_only() -> None:
    meta = ConvertHelpToMarkdown.meta
    assert meta.code == "GTR092"
    assert meta.rulesets == frozenset()  # never canonical / never in any ruleset
    assert meta.planemo_linters == frozenset()  # our capability, no planemo linter
    assert _HELP_FORMAT_PROFILE == "24.2"
