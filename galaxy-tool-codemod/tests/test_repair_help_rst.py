"""Tests for the GTR089.1 ``RepairHelpRst`` codemod."""

from __future__ import annotations

from galaxy_tool_source.rst import rst_is_invalid
from lxml import etree

from galaxy_tool_codemod.codemods.repair_help_rst import RepairHelpRst
from galaxy_tool_codemod.parse import parse_module

# Title underline shorter than the title -> "Title underline too short." (fixable).
_INVALID_HELP = (
    b"<tool id='x' name='X' version='1.0'>"
    b"<help>Section Title\n=====\n\nbody text here\n</help></tool>"
)
_VALID_HELP = (
    b"<tool id='x' name='X' version='1.0'>"
    b"<help>Section Title\n=============\n\nbody text here\n</help></tool>"
)
_MACRO_HELP = (
    b"<tool id='x' name='X' version='1.0'>"
    b"<help>Section Title\n=====\n\n@HELP_BODY@\n</help></tool>"
)


def _help_text(module: object) -> str:
    return module.document.root.find("help").text  # type: ignore[attr-defined,union-attr]


def test_detect_flags_invalid_help() -> None:
    module = parse_module(_INVALID_HELP)
    changes = list(RepairHelpRst().detect(module))
    assert len(changes) == 1
    assert changes[0].code == "GTR089.1"


def test_apply_repairs_invalid_help() -> None:
    module = parse_module(_INVALID_HELP)
    assert rst_is_invalid(_help_text(module))
    RepairHelpRst().apply(module)
    assert not rst_is_invalid(_help_text(module))


def test_apply_is_idempotent() -> None:
    module = parse_module(_INVALID_HELP)
    RepairHelpRst().apply(module)
    once = etree.tostring(module.document.tree)
    RepairHelpRst().apply(module)
    assert etree.tostring(module.document.tree) == once


def test_noop_on_valid_help() -> None:
    module = parse_module(_VALID_HELP)
    assert list(RepairHelpRst().detect(module)) == []
    before = etree.tostring(module.document.tree)
    RepairHelpRst().apply(module)
    assert etree.tostring(module.document.tree) == before


def test_skips_macro_bearing_help() -> None:
    module = parse_module(_MACRO_HELP)
    before = etree.tostring(module.document.tree)
    RepairHelpRst().apply(module)
    # unchanged (the unprovable-macro case)
    assert etree.tostring(module.document.tree) == before


def test_preserves_cdata_wrapping() -> None:
    source = (
        b"<tool id='x' name='X' version='1.0'>"
        b"<help><![CDATA[Section Title\n=====\n\nbody text here\n]]></help></tool>"
    )
    module = parse_module(source)
    RepairHelpRst().apply(module)
    out = etree.tostring(module.document.tree)
    assert b"<![CDATA[" in out  # still CDATA-wrapped after the repair
    assert not rst_is_invalid(_help_text(module))
