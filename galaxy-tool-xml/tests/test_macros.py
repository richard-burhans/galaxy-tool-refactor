"""Tests for macro detection, stripping, and expansion."""

from pathlib import Path

from galaxy_tool_xml.binding import load_tool
from galaxy_tool_xml.macros import (
    MacroError,
    expand_from_path,
    expand_from_tree,
    has_macros,
    strip_macros,
)


def test_has_macros_true(data_dir: Path) -> None:
    document = load_tool(data_dir / "tool_with_macros.xml")
    assert has_macros(document.root)


def test_has_macros_false(data_dir: Path) -> None:
    document = load_tool(data_dir / "minimal_tool.xml")
    assert not has_macros(document.root)


def test_strip_macros_removes_constructs(data_dir: Path) -> None:
    document = load_tool(data_dir / "tool_with_macros.xml")
    stripped = strip_macros(document.tree)
    stripped_root = stripped.getroot()
    assert stripped_root.find("macros") is None
    assert stripped_root.find(".//expand") is None


def test_strip_macros_leaves_input_untouched(data_dir: Path) -> None:
    document = load_tool(data_dir / "tool_with_macros.xml")
    strip_macros(document.tree)
    assert document.root.find("macros") is not None
    assert document.root.find(".//expand") is not None


def test_expand_from_path_resolves_import_and_expand(data_dir: Path) -> None:
    tree, errors = expand_from_path(data_dir / "tool_with_macros.xml")
    assert errors == []
    assert tree is not None
    expanded_root = tree.getroot()
    assert expanded_root.find(".//expand") is None
    assert expanded_root.find(".//param") is not None


def test_expand_from_tree_round_trips_mutated_tree(data_dir: Path) -> None:
    document = load_tool(data_dir / "tool_with_macros.xml")
    document.root.set("version", "9.9.9")
    tree, errors = expand_from_tree(document.root, source_dir=data_dir)
    assert errors == []
    assert tree is not None
    assert tree.getroot().get("version") == "9.9.9"
    assert tree.getroot().find(".//param") is not None


def test_expand_undefined_macro_yields_macro_error(data_dir: Path) -> None:
    document = load_tool(data_dir / "tool_macro_error.xml")
    tree, errors = expand_from_tree(document.root, source_dir=data_dir)
    assert tree is None
    assert errors
    assert isinstance(errors[0], MacroError)


def test_expand_from_tree_without_source_dir_reports_import(data_dir: Path) -> None:
    document = load_tool(data_dir / "tool_with_macros.xml")
    _tree, errors = expand_from_tree(document.root, source_dir=None)
    assert any("import" in str(error) for error in errors)
