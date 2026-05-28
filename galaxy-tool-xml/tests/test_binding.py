"""Tests for parsing, the ToolDocument representation, and result types."""

from pathlib import Path

import pytest
from lxml import etree

from galaxy_tool_xml.binding import ToolXmlSyntaxError, load_tool, parse_tool
from galaxy_tool_xml.document import ToolDocument


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
