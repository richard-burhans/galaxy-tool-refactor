"""Tests for the ``galaxy-tool-xml-fmt`` CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from galaxy_tool_xml_fmt.cli import main
from galaxy_tool_xml_fmt.cli_support import is_macros_root, is_tool_root

_UNFORMATTED_TOOL = (
    b"<tool id='t' name='T' version='0.1'>"
    b"<inputs><param name='a' type='text'/></inputs>"
    b"</tool>"
)


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def test_reformats_file_in_place(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _UNFORMATTED_TOOL)
    result = CliRunner().invoke(main, [str(file)])
    assert result.exit_code == 0, result.output
    assert b'id="t"' in file.read_bytes()  # canonical double-quoted
    assert b"\n    <inputs" in file.read_bytes()  # canonical indent
    assert "reformatted" in result.output


def test_unchanged_file_exits_zero_and_says_so(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _UNFORMATTED_TOOL)
    # First pass canonicalises the file; second pass should be a no-op.
    CliRunner().invoke(main, [str(file)])
    result = CliRunner().invoke(main, [str(file)])
    assert result.exit_code == 0, result.output
    assert "unchanged" in result.output


def test_check_exits_non_zero_when_drift_detected(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _UNFORMATTED_TOOL)
    result = CliRunner().invoke(main, ["--check", str(file)])
    assert result.exit_code == 1, result.output
    assert "would reformat" in result.output
    assert file.read_bytes() == _UNFORMATTED_TOOL  # --check must not write


def test_check_exits_zero_on_canonical_input(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _UNFORMATTED_TOOL)
    CliRunner().invoke(main, [str(file)])  # canonicalise
    result = CliRunner().invoke(main, ["--check", str(file)])
    assert result.exit_code == 0, result.output


def test_diff_prints_unified_diff_and_does_not_write(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _UNFORMATTED_TOOL)
    result = CliRunner().invoke(main, ["--diff", str(file)])
    assert result.exit_code == 0, result.output
    assert "---" in result.output
    assert "+++" in result.output
    assert file.read_bytes() == _UNFORMATTED_TOOL  # --diff must not write


def test_quiet_suppresses_per_file_output(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _UNFORMATTED_TOOL)
    result = CliRunner().invoke(main, ["--quiet", str(file)])
    assert result.exit_code == 0, result.output
    assert "reformatted" not in result.output


def test_directory_path_recurses(tmp_path: Path) -> None:
    _write(tmp_path / "a.xml", _UNFORMATTED_TOOL)
    nested = tmp_path / "nested"
    nested.mkdir()
    _write(nested / "b.xml", _UNFORMATTED_TOOL)
    result = CliRunner().invoke(main, ["--check", str(tmp_path)])
    assert result.exit_code == 1, result.output
    assert "a.xml" in result.output
    assert "b.xml" in result.output


def test_non_tool_non_macro_xml_is_skipped(tmp_path: Path) -> None:
    # Neither a <tool> nor a <macros> root, so it is skipped and left untouched.
    original = b"<datatypes><datatype extension='txt'/></datatypes>"
    file = _write(tmp_path / "datatypes_conf.xml", original)
    result = CliRunner().invoke(main, [str(file)])
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output
    assert file.read_bytes() == original


def test_macro_file_is_formatted(tmp_path: Path) -> None:
    # A <macros> library is now formatted with the kind-applicable rules
    # (GTR001 indent, GTR004 shorthand) — not skipped.
    file = _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@TOOL_VERSION@">1.0</token></macros>',
    )
    result = CliRunner().invoke(main, [str(file)])
    assert result.exit_code == 0, result.output
    assert "reformatted" in result.output
    formatted = file.read_bytes()
    assert b'\n    <token name="@TOOL_VERSION@">1.0</token>\n' in formatted


def test_malformed_tool_xml_is_reported_as_error(tmp_path: Path) -> None:
    # Pre-check accepts it (starts with ``<tool``) but the parser rejects it.
    file = _write(tmp_path / "bad.xml", b"<tool id='t'><unclosed>")
    result = CliRunner().invoke(main, [str(file)])
    assert result.exit_code == 1, result.output
    assert "error" in result.output


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_flag(flag: str) -> None:
    result = CliRunner().invoke(main, [flag])
    assert result.exit_code == 0
    assert "format Galaxy tool and macro XML" in result.output


def test_root_pre_checks_distinguish_tool_macro_and_other() -> None:
    assert is_tool_root(b"<tool id='t'/>")
    assert not is_macros_root(b"<tool id='t'/>")
    assert is_macros_root(b"<macros/>")
    assert not is_tool_root(b"<macros/>")
    # A singular <macro> element is not a macro-*library* root.
    assert not is_macros_root(b"<macro/>")
    # Neither for unrelated config XML.
    assert not is_tool_root(b"<datatypes/>")
    assert not is_macros_root(b"<datatypes/>")
    # A leading declaration / comment is tolerated.
    assert is_macros_root(b"<?xml version='1.0'?>\n<!-- c -->\n<macros/>")


def test_cli_does_not_reorder_attributes(tmp_path: Path) -> None:
    """The cosmetic CLI must NOT reorder attributes — that's the app's job.

    Attribute reordering is a structural codemod (tier 2); fmt is cosmetic-only.
    A ``<param>`` with attributes already well-formed but in non-IUC order is
    left in that order by ``galaxy-tool-xml-fmt``.
    """
    param_out_of_order = (
        b"<tool id='t' name='T' version='0.1'>"
        b"<inputs><param value='v' type='text' name='a'/></inputs>"
        b"</tool>"
    )
    file = _write(tmp_path / "tool.xml", param_out_of_order)
    result = CliRunner().invoke(main, [str(file)])
    assert result.exit_code == 0, result.output
    # cosmetic formatting only: the <param>'s original order (value, type, name)
    # is preserved. Scope to the <param> element so the root <tool name=…>
    # doesn't confuse the attribute search.
    param = file.read_bytes().partition(b"<param")[2]
    assert param.index(b"value=") < param.index(b"type=") < param.index(b"name=")
