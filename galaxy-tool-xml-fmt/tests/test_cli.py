"""Tests for the ``galaxy-tool-xml-fmt`` CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from galaxy_tool_xml_fmt.cli import main

_UNFORMATTED_TOOL = (
    b"<tool id='t' name='T' version='0.1'>"
    b"<inputs><param name='a' type='text'/></inputs>"
    b"</tool>"
)

# Tool whose <param> attributes are in non-canonical order — only the
# canonical-pipeline (codemod extra) will reorder them. Used to pin
# that the CLI runs CANONICAL_CODEMODS when the codemod extra is
# installed.
_PARAM_OUT_OF_ORDER = (
    b"<tool id='t' name='T' version='0.1'>"
    b"<inputs><param value='v' type='text' name='a'/></inputs>"
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


def test_non_tool_xml_is_skipped(tmp_path: Path) -> None:
    file = _write(tmp_path / "macros.xml", b"<macros><token>x</token></macros>")
    result = CliRunner().invoke(main, [str(file)])
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output
    assert file.read_bytes() == b"<macros><token>x</token></macros>"


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
    assert "Format Galaxy tool XML" in result.output


def test_cli_runs_canonical_codemods_when_extra_is_installed(
    tmp_path: Path,
) -> None:
    """CLI reorders ``<param>`` attributes when the codemod extra is installed.

    In the workspace, codemod is always installed via uv sync, so this
    test pins the canonical-pipeline orchestration. fmt's cosmetic
    rules alone do NOT reorder attributes — only the structural codemod
    does.
    """
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, [str(file)])
    assert result.exit_code == 0, result.output
    output = file.read_bytes()
    # IUC canonical order on <param>: name, type, value
    name_idx = output.index(b"name=")
    type_idx = output.index(b"type=")
    value_idx = output.index(b"value=")
    assert name_idx < type_idx < value_idx


def test_cli_does_not_print_cosmetic_only_hint_when_extra_is_installed(
    tmp_path: Path,
) -> None:
    """In the workspace dev install, the cosmetic-only hint must not appear."""
    file = _write(tmp_path / "tool.xml", _UNFORMATTED_TOOL)
    result = CliRunner().invoke(main, [str(file)])
    assert "cosmetic rules only" not in result.output
    assert "cosmetic rules only" not in (result.stderr or "")
