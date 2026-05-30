"""Tests for macro detection, stripping, and expansion."""

from pathlib import Path

from galaxy_tool_xml.binding import load_tool
from galaxy_tool_xml.macros import (
    MacroError,
    TokenDefinition,
    expand_from_path,
    expand_from_tree,
    has_macros,
    imported_macro_paths,
    strip_macros,
    token_definitions,
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


def test_imported_macro_paths_single(data_dir: Path) -> None:
    document = load_tool(data_dir / "tool_with_macros.xml")
    assert imported_macro_paths(document) == [(data_dir / "macros.xml").resolve()]


def test_imported_macro_paths_transitive(data_dir: Path) -> None:
    # tool -> nested_macros.xml -> nested_macros_inner.xml, in import order.
    document = load_tool(data_dir / "tool_nested_macros.xml")
    assert imported_macro_paths(document) == [
        (data_dir / "nested_macros.xml").resolve(),
        (data_dir / "nested_macros_inner.xml").resolve(),
    ]


def test_imported_macro_paths_none_for_macro_free_tool(data_dir: Path) -> None:
    document = load_tool(data_dir / "minimal_tool.xml")
    assert imported_macro_paths(document) == []


def test_imported_macro_paths_accepts_a_path(data_dir: Path) -> None:
    assert imported_macro_paths(data_dir / "tool_with_macros.xml") == [
        (data_dir / "macros.xml").resolve()
    ]


def test_imported_macro_paths_empty_without_source(data_dir: Path) -> None:
    # A document parsed from bytes has no source directory to resolve against.
    document = load_tool((data_dir / "tool_with_macros.xml").read_bytes())
    assert document.source_path is None
    assert imported_macro_paths(document) == []


def test_token_definitions_inline(data_dir: Path) -> None:
    definitions = token_definitions(load_tool(data_dir / "tool_inline_tokens.xml"))
    assert definitions == [
        TokenDefinition(
            name="@TOOL_VERSION@", value="2.0.0", source=None, sourceline=3
        )
    ]


def test_token_definitions_imported(data_dir: Path) -> None:
    definitions = token_definitions(load_tool(data_dir / "tool_imported_tokens.xml"))
    macro_file = (data_dir / "token_macros.xml").resolve()
    assert {(d.name, d.value, d.source) for d in definitions} == {
        ("@TOOL_VERSION@", "1.2.3", macro_file),
        ("@PROFILE@", "21.05", macro_file),
    }
    # The profile token (the @PROFILE@ upgrade target) is resolvable to its file.
    profile = next(d for d in definitions if d.name == "@PROFILE@")
    assert profile.source == macro_file
    assert profile.value == "21.05"


def test_token_definitions_none_for_tokenless_tool(data_dir: Path) -> None:
    assert token_definitions(load_tool(data_dir / "minimal_tool.xml")) == []
