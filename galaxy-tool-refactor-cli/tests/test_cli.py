"""Tests for the ``galaxy-tool-refactor`` app CLI (format + upgrade)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from galaxy_tool_xml.profiles import latest_profile

from galaxy_tool_refactor_cli.cli import main


def _valid_tool(*, profile: str, param_fmt: str | None = None) -> bytes:
    """A minimal valid Galaxy tool (mirrors the codemod upgrade-test template)."""
    param = (
        f'<param name="i" type="data" format="{param_fmt}"/>'
        if param_fmt is not None
        else ""
    )
    return (
        f'<tool id="m" name="M" version="1.0.0" profile="{profile}">'
        "<command><![CDATA[echo x]]></command>"
        f'<inputs>{param}</inputs><outputs><data name="o"/></outputs></tool>'
    ).encode()


_PARAM_OUT_OF_ORDER = (
    b'<tool id="t" name="T" version="0.1" profile="24.1">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param value="v" type="text" name="a"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def test_format_reorders_param_attributes(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["format", str(file)])
    assert result.exit_code == 0, result.output
    param = file.read_bytes().partition(b"<param")[2]
    # structural codemod ran: IUC order name, type, value
    assert param.index(b"name=") < param.index(b"type=") < param.index(b"value=")


def test_format_does_not_change_profile(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1"))
    result = CliRunner().invoke(main, ["format", str(file)])
    assert result.exit_code == 0, result.output
    assert b'profile="24.1"' in file.read_bytes()


def test_upgrade_bumps_profile_and_runs_migration(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1", param_fmt="BAM"))
    result = CliRunner().invoke(main, ["upgrade", str(file)])
    assert result.exit_code == 0, result.output
    output = file.read_bytes()
    assert f'profile="{latest_profile()}"'.encode() in output
    assert b'format="bam"' in output  # the 24.1 -> 24.2 migration ran
    assert "upgraded past 24.1" in result.output


def test_upgrade_check_reports_and_does_not_write(tmp_path: Path) -> None:
    original = _valid_tool(profile="24.1", param_fmt="BAM")
    file = _write(tmp_path / "tool.xml", original)
    result = CliRunner().invoke(main, ["upgrade", "--check", str(file)])
    assert result.exit_code == 1, result.output
    assert "would upgrade" in result.output
    assert file.read_bytes() == original


def test_upgrade_keeps_latest_profile(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _valid_tool(profile=latest_profile()))
    result = CliRunner().invoke(main, ["upgrade", str(file)])
    assert result.exit_code == 0, result.output
    assert f'profile="{latest_profile()}"'.encode() in file.read_bytes()


def test_format_diff_does_not_write(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["format", "--diff", str(file)])
    assert result.exit_code == 0, result.output
    assert "---" in result.output
    assert "+++" in result.output
    assert file.read_bytes() == _PARAM_OUT_OF_ORDER


def test_quiet_suppresses_per_file_output(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["format", "--quiet", str(file)])
    assert result.exit_code == 0, result.output
    assert "reformatted" not in result.output


def test_non_tool_xml_is_skipped(tmp_path: Path) -> None:
    file = _write(tmp_path / "macros.xml", b"<macros><token>x</token></macros>")
    result = CliRunner().invoke(main, ["format", str(file)])
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output
    assert file.read_bytes() == b"<macros><token>x</token></macros>"


def test_malformed_tool_is_reported_as_error(tmp_path: Path) -> None:
    file = _write(tmp_path / "bad.xml", b"<tool id='t'><unclosed>")
    result = CliRunner().invoke(main, ["upgrade", str(file)])
    assert result.exit_code == 1, result.output
    assert "error" in result.output


def test_group_help_lists_both_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "format" in result.output
    assert "upgrade" in result.output


@pytest.mark.parametrize("command", ["format", "upgrade"])
def test_subcommand_help(command: str) -> None:
    result = CliRunner().invoke(main, [command, "--help"])
    assert result.exit_code == 0
    assert "PATHS" in result.output


def test_check_reports_findings_and_exits_nonzero(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 1, result.output
    # structural finding (param attr order) is reported with its GTX code
    assert "GTX002" in result.output
    assert f"{file}:" in result.output
    assert "finding(s)" in result.output


def test_check_does_not_modify_the_file(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    CliRunner().invoke(main, ["check", str(file)])
    assert file.read_bytes() == _PARAM_OUT_OF_ORDER


def test_check_formatted_file_has_no_fixable_findings(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    # Canonicalise first; the formatted file then has no *fixable* (GTX) findings,
    # so check exits 0 even though advisory (IUC) suggestions remain.
    assert CliRunner().invoke(main, ["format", str(file)]).exit_code == 0
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 0, result.output
    assert "GTX" not in result.output  # nothing left to fix


def test_check_advisory_findings_do_not_fail_by_default(tmp_path: Path) -> None:
    # A canonical tool that merely lacks tests/requirements/help: advisory only.
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    CliRunner().invoke(main, ["format", str(file)])
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 0, result.output
    assert "IUC" in result.output
    assert "(advisory)" in result.output
    assert "advisory finding(s)" in result.output


def test_check_strict_fails_on_advisory(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    CliRunner().invoke(main, ["format", str(file)])
    result = CliRunner().invoke(main, ["check", "--strict", str(file)])
    assert result.exit_code == 1, result.output


def test_check_quiet_suppresses_per_finding_output(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["check", "--quiet", str(file)])
    assert result.exit_code == 1, result.output
    assert result.output == ""


def test_check_skips_non_tool_xml(tmp_path: Path) -> None:
    file = _write(tmp_path / "macros.xml", b"<macros><token>x</token></macros>")
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output


def test_check_reports_malformed_as_error(tmp_path: Path) -> None:
    file = _write(tmp_path / "bad.xml", b"<tool id='t'><unclosed>")
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 1, result.output
    assert "error" in result.output


def test_group_help_lists_check() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "check" in result.output
