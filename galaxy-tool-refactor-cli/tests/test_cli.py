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


def test_upgrade_reports_behavior_preserving_pass(tmp_path: Path) -> None:
    """A tool that crosses no applicable behaviour code gets a clean-pass note."""
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1", param_fmt="BAM"))
    result = CliRunner().invoke(main, ["upgrade", str(file)])
    assert result.exit_code == 0, result.output
    assert "behavior-preserving" in result.output


def test_upgrade_resolves_imported_macros(tmp_path: Path) -> None:
    """An imported-macro tool upgrades correctly: the per-file load keeps the
    file's source_path so ``<import>`` resolves. Regression — loading from bytes
    dropped it, leaving the un-expanded ``<expand>`` tree XSD-invalid (no valid
    profile -> nothing to upgrade) and spewing 'macro expansion failed'."""
    _write(
        tmp_path / "macros.xml",
        b'<macros><xml name="reqs"><requirements>'
        b'<requirement type="package" version="1.0">foo</requirement>'
        b"</requirements></xml></macros>",
    )
    tool = _write(
        tmp_path / "tool.xml",
        b'<tool id="m" name="M" version="1.0.0" profile="20.01">'
        b"<macros><import>macros.xml</import></macros>"
        b'<expand macro="reqs"/>'
        b"<command><![CDATA[echo x]]></command>"
        b'<inputs/><outputs><data name="o"/></outputs></tool>',
    )
    result = CliRunner().invoke(main, ["upgrade", "--check", str(tool)])
    assert result.exit_code == 1, result.output
    assert "would upgrade" in result.output  # a valid profile was found via expansion
    assert "macro expansion failed" not in result.output


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


def test_upgrade_applies_runtime_gated_fix_at_reached_profile(tmp_path: Path) -> None:
    """End-to-end: crossing 21.09 strips a whitespace from_work_dir (GTX014)."""
    # Declares 20.09 (< 21.09), so the bump to latest CROSSES the 21.09 boundary.
    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="20.09">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>'
    )
    file = _write(tmp_path / "tool.xml", tool)
    result = CliRunner().invoke(main, ["upgrade", str(file)])
    assert result.exit_code == 0, result.output
    output = file.read_bytes()
    assert b'from_work_dir="out.txt"' in output
    assert b'from_work_dir=" out.txt "' not in output


def test_upgrade_rewrites_inline_profile_token(tmp_path: Path) -> None:
    """`upgrade` bumps a stale inline @PROFILE@ token, keeping the reference."""
    file = _write(
        tmp_path / "tool.xml",
        b'<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        b'<macros><token name="@PROFILE@">16.01</token></macros>'
        b"<command><![CDATA[echo x]]></command>"
        b'<inputs/><outputs><data name="o"/></outputs></tool>',
    )
    result = CliRunner().invoke(main, ["upgrade", str(file)])
    assert result.exit_code == 0, result.output
    output = file.read_bytes()
    assert b'profile="@PROFILE@"' in output  # reference preserved, not clobbered
    assert f">{latest_profile()}<".encode() in output  # token value bumped


def _imported_token_tool(tool_id: str) -> bytes:
    return (
        f'<tool id="{tool_id}" name="{tool_id}" version="1.0.0" profile="@PROFILE@">'
        "<macros><import>macros.xml</import></macros>"
        "<command><![CDATA[echo x]]></command>"
        '<inputs/><outputs><data name="o"/></outputs></tool>'
    ).encode()


def test_upgrade_bumps_shared_imported_profile_token(tmp_path: Path) -> None:
    """`upgrade` bumps a stale @PROFILE@ in a shared imported macro file."""
    _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@PROFILE@">16.01</token></macros>',
    )
    _write(tmp_path / "a.xml", _imported_token_tool("a"))
    _write(tmp_path / "b.xml", _imported_token_tool("b"))
    result = CliRunner().invoke(main, ["upgrade", str(tmp_path)])
    assert result.exit_code == 0, result.output
    macros = (tmp_path / "macros.xml").read_bytes()
    assert f">{latest_profile()}<".encode() in macros  # token bumped once
    # the tools keep the reference; the import is what advanced them
    assert b'profile="@PROFILE@"' in (tmp_path / "a.xml").read_bytes()
    assert "2 tool(s)" in result.output  # both importers drove the one edit


def test_upgrade_check_does_not_write_imported_token(tmp_path: Path) -> None:
    macros = _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@PROFILE@">16.01</token></macros>',
    )
    _write(tmp_path / "a.xml", _imported_token_tool("a"))
    result = CliRunner().invoke(main, ["upgrade", "--check", str(tmp_path)])
    assert result.exit_code == 1, result.output
    assert b"16.01" in macros.read_bytes()  # not written under --check
    assert "would upgrade @PROFILE@" in result.output


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


def test_non_tool_non_macro_xml_is_skipped(tmp_path: Path) -> None:
    original = b"<datatypes><datatype extension='txt'/></datatypes>"
    file = _write(tmp_path / "datatypes_conf.xml", original)
    result = CliRunner().invoke(main, ["format", str(file)])
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output
    assert file.read_bytes() == original


def test_format_cosmetically_formats_a_macro_file(tmp_path: Path) -> None:
    # `format` cleans macro files cosmetically (no codemods — tool-only).
    file = _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@TOOL_VERSION@">1.0</token></macros>',
    )
    result = CliRunner().invoke(main, ["format", str(file)])
    assert result.exit_code == 0, result.output
    assert "reformatted" in result.output
    assert b'\n    <token name="@TOOL_VERSION@">1.0</token>\n' in file.read_bytes()


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


def test_check_default_preset_omits_advisory(tmp_path: Path) -> None:
    # Default preset is iuc (fixable only); advisory IUC checks are opt-in via
    # --preset strict, so a canonical tool reports nothing under the default.
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    CliRunner().invoke(main, ["format", str(file)])
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 0, result.output
    assert "IUC" not in result.output


def test_check_strict_preset_shows_advisory_without_failing(tmp_path: Path) -> None:
    # A canonical tool that merely lacks tests/requirements/help: advisory only.
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    CliRunner().invoke(main, ["format", str(file)])
    result = CliRunner().invoke(main, ["check", "--preset", "strict", str(file)])
    assert result.exit_code == 0, result.output
    assert "IUC" in result.output
    assert "(advisory)" in result.output
    assert "advisory finding(s)" in result.output


def test_check_strict_flag_fails_on_advisory(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    CliRunner().invoke(main, ["format", str(file)])
    result = CliRunner().invoke(
        main, ["check", "--preset", "strict", "--strict", str(file)]
    )
    assert result.exit_code == 1, result.output


def test_check_quiet_suppresses_per_finding_output(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["check", "--quiet", str(file)])
    assert result.exit_code == 1, result.output
    assert result.output == ""


def test_check_skips_non_tool_non_macro_xml(tmp_path: Path) -> None:
    file = _write(tmp_path / "datatypes_conf.xml", b"<datatypes/>")
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output


def test_check_reports_macro_file_cosmetic_drift(tmp_path: Path) -> None:
    # A non-canonical macro file is reported (fixable GTX001) and exits non-zero.
    file = _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@TOOL_VERSION@">1.0</token></macros>',
    )
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 1, result.output
    assert "GTX001" in result.output


def test_check_clean_macro_file_passes(tmp_path: Path) -> None:
    # Round trip: format canonicalises the macro file, then check finds it clean.
    file = _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@TOOL_VERSION@">1.0</token></macros>',
    )
    CliRunner().invoke(main, ["format", str(file)])
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 0, result.output
    assert "clean" in result.output


def test_check_reports_malformed_as_error(tmp_path: Path) -> None:
    file = _write(tmp_path / "bad.xml", b"<tool id='t'><unclosed>")
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 1, result.output
    assert "error" in result.output


def test_group_help_lists_check() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "check" in result.output


def test_format_cosmetic_preset_does_not_reorder_params(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["format", "--preset", "cosmetic", str(file)])
    assert result.exit_code == 0, result.output
    param = file.read_bytes().partition(b"<param")[2]
    # cosmetic-only: the source attribute order (value, type, name) is preserved.
    assert param.index(b"value=") < param.index(b"type=") < param.index(b"name=")


def test_format_ignore_drops_a_rule(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(
        main, ["format", "--ignore", "GTX002", str(file)]
    )
    assert result.exit_code == 0, result.output
    param = file.read_bytes().partition(b"<param")[2]
    # GTX002 (param reorder) ignored, so source order is preserved.
    assert param.index(b"value=") < param.index(b"type=") < param.index(b"name=")


def test_format_strict_preset_emits_advisory_notes(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["format", "--preset", "strict", str(file)])
    assert result.exit_code == 0, result.output
    assert "(advisory)" in result.output  # advisory findings surfaced as notes


def test_unknown_code_is_clean_error(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["format", "--select", "GTX999", str(file)])
    assert result.exit_code != 0
    assert "GTX999" in result.output
    assert "Traceback" not in result.output


def test_unknown_preset_is_clean_error(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["check", "--preset", "nope", str(file)])
    assert result.exit_code != 0
    assert "nope" in result.output


def test_upgrade_rejects_preset(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1"))
    result = CliRunner().invoke(main, ["upgrade", "--preset", "iuc", str(file)])
    assert result.exit_code != 0
    assert "preset" in result.output.lower()


def test_presets_subcommand_lists_presets() -> None:
    result = CliRunner().invoke(main, ["presets"])
    assert result.exit_code == 0, result.output
    assert "iuc (default)" in result.output
    assert "cosmetic" in result.output
    assert "strict" in result.output


def test_rules_subcommand_lists_rules() -> None:
    result = CliRunner().invoke(main, ["rules"])
    assert result.exit_code == 0, result.output
    assert "GTX002" in result.output
    assert "IUC001" in result.output
    assert "GTX012" not in result.output  # upgrade-only excluded by default
    with_upgrade = CliRunner().invoke(main, ["rules", "--include-upgrade"])
    assert "GTX012" in with_upgrade.output
