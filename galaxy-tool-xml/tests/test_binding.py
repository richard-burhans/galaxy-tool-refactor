"""Tests for parsing, the ToolDocument representation, and result types."""

from pathlib import Path

import pytest
from lxml import etree

from galaxy_tool_xml.binding import (
    ToolXmlSyntaxError,
    load_macros,
    load_tool,
    parse_tool,
)
from galaxy_tool_xml.document import MacroDocument, ToolDocument


def test_load_tool_returns_document(data_dir: Path) -> None:
    document = load_tool(data_dir / "minimal_tool.xml")
    assert isinstance(document, ToolDocument)
    assert document.profile == "24.0"
    assert document.root.tag == "tool"


def test_representation_preserves_cdata_and_comments(data_dir: Path) -> None:
    document = load_tool(data_dir / "representative_tool.xml")
    serialized = etree.tostring(document.tree)
    assert b"<![CDATA[" in serialized
    assert b"<!--" in serialized


def test_source_path_set_for_path_input(data_dir: Path) -> None:
    document = load_tool(data_dir / "minimal_tool.xml")
    assert document.source_path == data_dir / "minimal_tool.xml"


def test_source_path_none_for_bytes_input(data_dir: Path) -> None:
    document = load_tool((data_dir / "minimal_tool.xml").read_bytes())
    assert document.source_path is None


def test_load_macros_returns_macro_document(data_dir: Path) -> None:
    document = load_macros(data_dir / "token_macros.xml")
    assert isinstance(document, MacroDocument)
    assert document.root.tag == "macros"
    assert document.source_path == data_dir / "token_macros.xml"
    # The mutable tree is the source of truth: the <token>s are present.
    assert {token.get("name") for token in document.root.findall("token")} == {
        "@TOOL_VERSION@",
        "@PROFILE@",
    }


def test_load_macros_preserves_comments(data_dir: Path) -> None:
    document = load_macros(
        b"<macros><!-- keep me --><token name='@X@'>1</token></macros>"
    )
    assert b"<!-- keep me -->" in etree.tostring(document.tree)
    assert document.source_path is None


def test_load_macros_raises_on_malformed_xml() -> None:
    with pytest.raises(ToolXmlSyntaxError):
        load_macros(b"<macros><token")


def test_model_exposes_typed_fields(data_dir: Path) -> None:
    document = load_tool(data_dir / "minimal_tool.xml")
    model = document.model()
    assert model.id == "minimal"
    assert model.name == "Minimal Tool"
    assert model.version == "1.0.0"


def test_parse_tool_collects_multiple_syntax_errors(data_dir: Path) -> None:
    result = parse_tool(data_dir / "malformed_tool.xml")
    assert not result.well_formed
    assert len(result.syntax_errors) > 1


def test_parse_tool_well_formed(data_dir: Path) -> None:
    result = parse_tool(data_dir / "minimal_tool.xml")
    assert result.well_formed
    assert result.document is not None
    assert not result.syntax_errors


def test_load_tool_raises_on_malformed(data_dir: Path) -> None:
    with pytest.raises(ToolXmlSyntaxError) as excinfo:
        load_tool(data_dir / "malformed_tool.xml")
    assert excinfo.value.errors


def test_xml_error_str_format(data_dir: Path) -> None:
    result = parse_tool(data_dir / "malformed_tool.xml")
    rendered = str(result.syntax_errors[0])
    assert "malformed_tool.xml:" in rendered
