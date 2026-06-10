"""Tests for ``parse_module`` — the entry point for the codemod framework."""

from __future__ import annotations

from pathlib import Path

import pytest
from galaxy_tool_source.binding import ToolXmlSyntaxError, load_macros, load_tool
from galaxy_tool_source.models.any_tool import AnyTool

from galaxy_tool_xml_codemod.module import MacroModule, Module
from galaxy_tool_xml_codemod.parse import parse_macro_module, parse_module

_MACROS = b'<macros><token name="@TOOL_VERSION@">1.0</token></macros>'


def test_parse_module_from_path(minimal_tool_path: Path) -> None:
    """``parse_module(Path)`` returns a Module rooted at ``<tool>``."""
    module = parse_module(minimal_tool_path)
    assert isinstance(module, Module)
    assert module.cursor.tag == "tool"
    assert isinstance(module.model, AnyTool)


def test_parse_module_from_bytes(minimal_tool_bytes: bytes) -> None:
    """``parse_module(bytes)`` returns a Module rooted at ``<tool>``."""
    module = parse_module(minimal_tool_bytes)
    assert isinstance(module, Module)
    assert module.cursor.tag == "tool"
    assert isinstance(module.model, AnyTool)


def test_parse_module_from_tool_document_shares_by_reference(
    minimal_tool_path: Path,
) -> None:
    """``parse_module(ToolDocument)`` wraps by reference; no deep-copy here."""
    document = load_tool(minimal_tool_path)
    module = parse_module(document)
    assert module.document is document


def test_parse_module_strict_on_malformed_bytes() -> None:
    """Any well-formedness error on ``bytes`` input raises ``ToolXmlSyntaxError``."""
    with pytest.raises(ToolXmlSyntaxError):
        parse_module(b"<tool")


def test_parse_module_returns_distinct_modules_for_same_document(
    minimal_tool_path: Path,
) -> None:
    """Calling ``parse_module`` twice on the same document yields distinct wrappers."""
    document = load_tool(minimal_tool_path)
    first = parse_module(document)
    second = parse_module(document)
    assert first is not second
    assert first.document is second.document


def test_parse_macro_module_from_bytes() -> None:
    """``parse_macro_module(bytes)`` returns a MacroModule rooted at ``<macros>``."""
    module = parse_macro_module(_MACROS)
    assert isinstance(module, MacroModule)
    assert module.cursor.tag == "macros"


def test_parse_macro_module_from_path(tmp_path: Path) -> None:
    path = tmp_path / "macros.xml"
    path.write_bytes(_MACROS)
    module = parse_macro_module(path)
    assert isinstance(module, MacroModule)
    assert module.document.source_path == path


def test_parse_macro_module_shares_macro_document_by_reference() -> None:
    document = load_macros(_MACROS)
    module = parse_macro_module(document)
    assert module.document is document


def test_parse_macro_module_strict_on_malformed_bytes() -> None:
    with pytest.raises(ToolXmlSyntaxError):
        parse_macro_module(b"<macros><token")
