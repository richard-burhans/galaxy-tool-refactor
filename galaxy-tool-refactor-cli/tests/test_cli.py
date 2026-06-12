"""Tests for the ``galaxy-tool-refactor`` app CLI (format + upgrade)."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest
from click.testing import CliRunner
from galaxy_tool_refactor_registry.deployment import DEPLOYMENT_CEILING
from galaxy_tool_refactor_registry.registry import advisory_codes
from galaxy_tool_source.profiles import latest_profile

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


def test_version_flag_prints_the_installed_version() -> None:
    """``--version`` exits 0 and prints the installed (lockstep) version."""
    expected = importlib.metadata.version("galaxy-tool-refactor-cli")
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0, result.output
    assert expected in result.output


def test_format_reorders_param_attributes(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["format", str(file)])
    assert result.exit_code == 0, result.output
    param = file.read_bytes().partition(b"<param")[2]
    # structural codemod ran: canonical order name, type, value
    assert param.index(b"name=") < param.index(b"type=") < param.index(b"value=")


def test_format_does_not_change_profile(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1"))
    result = CliRunner().invoke(main, ["format", str(file)])
    assert result.exit_code == 0, result.output
    assert b'profile="24.1"' in file.read_bytes()


def test_upgrade_modernize_bumps_profile_and_runs_migration(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1", param_fmt="BAM"))
    result = CliRunner().invoke(main, ["upgrade", "--modernize", str(file)])
    assert result.exit_code == 0, result.output
    output = file.read_bytes()
    # The walk lands on the deployment ceiling, not the (pre-release) latest.
    assert f'profile="{DEPLOYMENT_CEILING}"'.encode() in output
    assert b'format="bam"' in output  # the 24.1 -> 24.2 migration ran
    assert "upgraded past 24.1" in result.output
    assert "deployment ceiling" in result.output


def test_upgrade_default_keeps_a_valid_declared_profile(tmp_path: Path) -> None:
    """The minimal default: valid at the declared profile means no bump."""
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1", param_fmt="BAM"))
    result = CliRunner().invoke(main, ["upgrade", str(file)])
    assert result.exit_code == 0, result.output
    assert b'profile="24.1"' in file.read_bytes()
    assert "profile 24.1 kept" in result.output
    assert "--modernize" in result.output


def test_upgrade_default_bumps_to_the_minimum_valid_profile(tmp_path: Path) -> None:
    """Invalid at the declared profile: bump to the minimum valid one only."""
    tool = (
        b'<tool id="r" name="R" version="1.0.0" profile="20.09">'
        b'<required_files><include path="x.py"/></required_files>'
        b"<command><![CDATA[echo x]]></command>"
        b"<inputs/><outputs/></tool>"
    )
    file = _write(tmp_path / "tool.xml", tool)
    result = CliRunner().invoke(main, ["upgrade", str(file)])
    assert result.exit_code == 0, result.output
    output = file.read_bytes()
    assert b'profile="21.09"' in output
    assert f'profile="{latest_profile()}"'.encode() not in output
    assert "minimum" in result.output


def test_upgrade_allow_behavior_change_alone_is_an_error(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1"))
    result = CliRunner().invoke(
        main, ["upgrade", "--allow-behavior-change", str(file)]
    )
    assert result.exit_code != 0
    assert "modernize" in result.output


def test_upgrade_modernize_reports_behavior_preserving_pass(tmp_path: Path) -> None:
    """A walk that crosses no applicable behaviour code gets a clean-pass note."""
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1", param_fmt="BAM"))
    result = CliRunner().invoke(main, ["upgrade", "--modernize", str(file)])
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


def _tool_with_tests(*, profile: str) -> bytes:
    """A valid tool shipping a <test>, so 24.2's must_fix code applies on bump."""
    return (
        f'<tool id="m" name="M" version="1.0.0" profile="{profile}">'
        "<command><![CDATA[echo x]]></command>"
        '<inputs/><outputs><data name="o"/></outputs>'
        '<tests><test><param name="nosuch" value="1"/></test></tests></tool>'
    ).encode()


def test_upgrade_modernize_stops_at_a_behavior_boundary(tmp_path: Path) -> None:
    """A tool with tests stays at 24.1 under --modernize: 24.2 validates test
    cases, so the gated walk does not cross it."""
    file = _write(tmp_path / "tool.xml", _tool_with_tests(profile="24.1"))
    result = CliRunner().invoke(main, ["upgrade", "--modernize", str(file)])
    assert result.exit_code == 0, result.output
    assert b'profile="24.1"' in file.read_bytes()
    assert "stopped at 24.1" in result.output
    assert "24_2_fix_test_case_validation" in result.output
    assert "--allow-behavior-change" in result.output


def test_upgrade_allow_behavior_change_walks_past_the_gate(tmp_path: Path) -> None:
    """The flag lifts the behaviour gate; the deployment ceiling still caps."""
    file = _write(tmp_path / "tool.xml", _tool_with_tests(profile="24.1"))
    result = CliRunner().invoke(
        main, ["upgrade", "--modernize", "--allow-behavior-change", str(file)]
    )
    assert result.exit_code == 0, result.output
    assert f'profile="{DEPLOYMENT_CEILING}"'.encode() in file.read_bytes()
    assert "profile-behaviour" in result.output  # the review warning remains


def test_upgrade_target_profile_may_exceed_the_deployment_ceiling(
    tmp_path: Path,
) -> None:
    """An explicit target expresses intent: it wins over the deployment cap."""
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1"))
    result = CliRunner().invoke(
        main, ["upgrade", "--target-profile", latest_profile(), str(file)]
    )
    assert result.exit_code == 0, result.output
    assert f'profile="{latest_profile()}"'.encode() in file.read_bytes()
    assert "deployment ceiling" in result.output  # informed, never silent


def test_upgrade_target_profile_caps_the_walk(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="19.01"))
    result = CliRunner().invoke(
        main, ["upgrade", "--target-profile", "20.09", str(file)]
    )
    assert result.exit_code == 0, result.output
    assert b'profile="20.09"' in file.read_bytes()


def test_upgrade_rejects_an_unknown_target_profile(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1"))
    result = CliRunner().invoke(
        main, ["upgrade", "--target-profile", "99.99", str(file)]
    )
    assert result.exit_code != 0
    assert "unknown profile" in result.output


def test_upgrade_modernize_gates_a_shared_imported_profile_token(
    tmp_path: Path,
) -> None:
    """The whole-run @PROFILE@ bump honors the gate: importers with tests agree
    on the 24.1 ceiling, so the shared token lands there, not at latest."""
    _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@PROFILE@">19.01</token></macros>',
    )
    for tool_id in ("a", "b"):
        _write(
            tmp_path / f"{tool_id}.xml",
            (
                f'<tool id="{tool_id}" name="{tool_id}" version="1.0.0"'
                ' profile="@PROFILE@">'
                "<macros><import>macros.xml</import></macros>"
                "<command><![CDATA[echo x]]></command>"
                '<inputs/><outputs><data name="o"/></outputs>'
                '<tests><test><param name="nosuch" value="1"/></test></tests></tool>'
            ).encode(),
        )
    result = CliRunner().invoke(main, ["upgrade", "--modernize", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert b">24.1<" in (tmp_path / "macros.xml").read_bytes()


def test_upgrade_default_keeps_a_valid_imported_profile_token(
    tmp_path: Path,
) -> None:
    """The minimal default leaves a shared token its importers validate at."""
    macros = _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@PROFILE@">19.01</token></macros>',
    )
    _write(tmp_path / "a.xml", _imported_token_tool("a"))
    result = CliRunner().invoke(main, ["upgrade", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert b">19.01</token>" in macros.read_bytes()  # kept: valid at its value


def test_upgrade_modernize_applies_runtime_gated_fix(tmp_path: Path) -> None:
    """End-to-end: crossing 21.09 strips a whitespace from_work_dir (GTR014)."""
    # Declares 20.09 (< 21.09), so the walk to latest CROSSES the 21.09 boundary.
    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="20.09">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>'
    )
    file = _write(tmp_path / "tool.xml", tool)
    result = CliRunner().invoke(main, ["upgrade", "--modernize", str(file)])
    assert result.exit_code == 0, result.output
    output = file.read_bytes()
    assert b'from_work_dir="out.txt"' in output
    assert b'from_work_dir=" out.txt "' not in output


def test_upgrade_modernize_rewrites_inline_profile_token(tmp_path: Path) -> None:
    """--modernize bumps a stale inline @PROFILE@ token, keeping the reference."""
    file = _write(
        tmp_path / "tool.xml",
        b'<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        b'<macros><token name="@PROFILE@">16.01</token></macros>'
        b"<command><![CDATA[echo x]]></command>"
        b'<inputs/><outputs><data name="o"/></outputs></tool>',
    )
    result = CliRunner().invoke(main, ["upgrade", "--modernize", str(file)])
    assert result.exit_code == 0, result.output
    output = file.read_bytes()
    assert b'profile="@PROFILE@"' in output  # reference preserved, not clobbered
    assert f">{DEPLOYMENT_CEILING}<".encode() in output  # token value bumped


def _imported_token_tool(tool_id: str) -> bytes:
    return (
        f'<tool id="{tool_id}" name="{tool_id}" version="1.0.0" profile="@PROFILE@">'
        "<macros><import>macros.xml</import></macros>"
        "<command><![CDATA[echo x]]></command>"
        '<inputs/><outputs><data name="o"/></outputs></tool>'
    ).encode()


def test_upgrade_modernize_bumps_shared_imported_profile_token(
    tmp_path: Path,
) -> None:
    """--modernize bumps a stale @PROFILE@ in a shared imported macro file."""
    _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@PROFILE@">16.01</token></macros>',
    )
    _write(tmp_path / "a.xml", _imported_token_tool("a"))
    _write(tmp_path / "b.xml", _imported_token_tool("b"))
    result = CliRunner().invoke(main, ["upgrade", "--modernize", str(tmp_path)])
    assert result.exit_code == 0, result.output
    macros = (tmp_path / "macros.xml").read_bytes()
    assert f">{DEPLOYMENT_CEILING}<".encode() in macros  # token bumped once
    # the tools keep the reference; the import is what advanced them
    assert b'profile="@PROFILE@"' in (tmp_path / "a.xml").read_bytes()
    assert "2 tool(s)" in result.output  # both importers drove the one edit


def test_upgrade_check_does_not_write_imported_token(tmp_path: Path) -> None:
    macros = _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@PROFILE@">16.01</token></macros>',
    )
    _write(tmp_path / "a.xml", _imported_token_tool("a"))
    result = CliRunner().invoke(
        main, ["upgrade", "--modernize", "--check", str(tmp_path)]
    )
    assert result.exit_code == 1, result.output
    assert b"16.01" in macros.read_bytes()  # not written under --check
    assert "would upgrade @PROFILE@" in result.output


def test_upgrade_diff_reflects_pending_imported_token(tmp_path: Path) -> None:
    """`--diff` is a preview mode too: a pending macro bump must exit non-zero
    and write nothing (cli D6) — regression for the --diff-only exit-code gap."""
    macros = _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@PROFILE@">16.01</token></macros>',
    )
    _write(tmp_path / "a.xml", _imported_token_tool("a"))
    result = CliRunner().invoke(
        main, ["upgrade", "--modernize", "--diff", str(tmp_path)]
    )
    assert result.exit_code == 1, result.output
    assert b"16.01" in macros.read_bytes()  # not written under --diff


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
    # structural finding (param attr order) is reported with its GTR code
    assert "GTR002" in result.output
    assert f"{file}:" in result.output
    assert "finding(s)" in result.output


def test_check_does_not_modify_the_file(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    CliRunner().invoke(main, ["check", str(file)])
    assert file.read_bytes() == _PARAM_OUT_OF_ORDER


def test_check_formatted_file_has_no_fixable_findings(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    # Canonicalise first; the formatted file then has no *fixable* findings,
    # so check exits 0 even though advisory suggestions remain.
    assert CliRunner().invoke(main, ["format", str(file)]).exit_code == 0
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 0, result.output
    assert "GTR" not in result.output  # no rule findings left to report


def test_check_default_ruleset_omits_advisory(tmp_path: Path) -> None:
    # Default ruleset is 'default' (fixable only); advisory checks are opt-in via
    # --ruleset strict, so a canonical tool reports nothing under the default.
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    CliRunner().invoke(main, ["format", str(file)])
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 0, result.output
    assert not any(code in result.output for code in advisory_codes())


def test_check_strict_ruleset_shows_advisory_without_failing(tmp_path: Path) -> None:
    # A canonical tool that merely lacks tests/requirements/help: advisory only.
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    CliRunner().invoke(main, ["format", str(file)])
    result = CliRunner().invoke(main, ["check", "--ruleset", "strict", str(file)])
    assert result.exit_code == 0, result.output
    assert any(code in result.output for code in advisory_codes())
    assert "(advisory)" in result.output
    assert "advisory finding(s)" in result.output


def test_check_strict_flag_fails_on_advisory(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    CliRunner().invoke(main, ["format", str(file)])
    result = CliRunner().invoke(
        main, ["check", "--ruleset", "strict", "--strict", str(file)]
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
    # A non-canonical macro file is reported (fixable GTR001) and exits non-zero.
    file = _write(
        tmp_path / "macros.xml",
        b'<macros><token name="@TOOL_VERSION@">1.0</token></macros>',
    )
    result = CliRunner().invoke(main, ["check", str(file)])
    assert result.exit_code == 1, result.output
    assert "GTR001" in result.output


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


def test_format_cosmetic_ruleset_does_not_reorder_params(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["format", "--ruleset", "cosmetic", str(file)])
    assert result.exit_code == 0, result.output
    param = file.read_bytes().partition(b"<param")[2]
    # cosmetic-only: the source attribute order (value, type, name) is preserved.
    assert param.index(b"value=") < param.index(b"type=") < param.index(b"name=")


def test_format_ignore_drops_a_rule(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(
        main, ["format", "--ignore", "GTR002", str(file)]
    )
    assert result.exit_code == 0, result.output
    param = file.read_bytes().partition(b"<param")[2]
    # GTR002 (param reorder) ignored, so source order is preserved.
    assert param.index(b"value=") < param.index(b"type=") < param.index(b"name=")


def test_format_strict_ruleset_emits_advisory_notes(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["format", "--ruleset", "strict", str(file)])
    assert result.exit_code == 0, result.output
    assert "(advisory)" in result.output  # advisory findings surfaced as notes


def test_unknown_code_is_clean_error(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["format", "--select", "GTR999", str(file)])
    assert result.exit_code != 0
    assert "GTR999" in result.output
    assert "Traceback" not in result.output


def test_unknown_ruleset_is_clean_error(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["check", "--ruleset", "nope", str(file)])
    assert result.exit_code != 0
    assert "nope" in result.output


def test_upgrade_rejects_ruleset(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _valid_tool(profile="24.1"))
    result = CliRunner().invoke(main, ["upgrade", "--ruleset", "default", str(file)])
    assert result.exit_code != 0
    assert "ruleset" in result.output.lower()


def test_rulesets_subcommand_lists_rulesets() -> None:
    result = CliRunner().invoke(main, ["rulesets"])
    assert result.exit_code == 0, result.output
    assert "default (default)" in result.output
    assert "cosmetic" in result.output
    assert "strict" in result.output


def test_rules_subcommand_lists_rules() -> None:
    result = CliRunner().invoke(main, ["rules"])
    assert result.exit_code == 0, result.output
    assert "GTR002" in result.output
    assert "GTR021" in result.output
    assert "GTR012" not in result.output  # upgrade-only excluded by default
    with_upgrade = CliRunner().invoke(main, ["rules", "--include-upgrade"])
    assert "GTR012" in with_upgrade.output


def test_rules_subcommand_shows_planemo_names() -> None:
    result = CliRunner().invoke(main, ["rules"])
    assert result.exit_code == 0, result.output
    assert "planemo:HelpEmpty,HelpMissing" in result.output  # GTR028 bundle


def test_select_by_planemo_name_matches_the_covering_code(tmp_path: Path) -> None:
    # `--select <planemo name>` selects exactly the covering GTR rule.
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    by_name = CliRunner().invoke(
        main, ["check", "--strict", "--select", "HelpMissing", str(file)]
    )
    by_code = CliRunner().invoke(
        main, ["check", "--strict", "--select", "GTR028", str(file)]
    )
    assert by_name.output == by_code.output
    assert "GTR028" in by_name.output


def test_unknown_planemo_name_is_clean_error(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _PARAM_OUT_OF_ORDER)
    result = CliRunner().invoke(main, ["check", "--select", "NotALinter", str(file)])
    assert result.exit_code != 0
    assert "NotALinter" in result.output


# --- normalize-macros (Phase 2a: macro-library format/ftype normalization) ---------


def test_normalize_macros_lowercases_macro_file(tmp_path: Path) -> None:
    macros = tmp_path / "macros.xml"
    macros.write_bytes(
        b'<macros><xml name="o"><data name="x" format="GTiff"/></xml></macros>'
    )
    result = CliRunner().invoke(main, ["normalize-macros", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert b'format="gtiff"' in macros.read_bytes()
    assert "normalized" in result.output


def test_normalize_macros_check_writes_nothing(tmp_path: Path) -> None:
    macros = tmp_path / "macros.xml"
    original = b'<macros><xml name="o"><data name="x" format="GTiff"/></xml></macros>'
    macros.write_bytes(original)
    result = CliRunner().invoke(main, ["normalize-macros", "--check", str(macros)])
    assert result.exit_code == 0, result.output
    assert "would normalize" in result.output
    assert macros.read_bytes() == original  # --check writes nothing


def test_normalize_macros_ignores_non_macro_files(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_valid_tool(profile="24.2"))
    result = CliRunner().invoke(main, ["normalize-macros", str(tool)])
    assert result.exit_code == 0, result.output
    assert "no macro-library files needed normalization" in result.output


_REFS_TOOL_BYTES = (
    b'<tool id="m" name="M" version="1.0.0" profile="21.09">'
    b"<command><![CDATA[tool $input --opt $opts]]></command>"
    b'<outputs><data name="o" label="$input.name"/></outputs></tool>'
)


def test_find_references_reports_occurrences(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _REFS_TOOL_BYTES)
    result = CliRunner().invoke(main, ["find-references", "input", str(file)])
    assert result.exit_code == 0, result.output
    assert "[command]  $input" in result.output
    assert "[output_data_label:o]  $input.name" in result.output
    assert "2 reference(s) to 'input'" in result.output


def test_find_references_absent_name_is_zero(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _REFS_TOOL_BYTES)
    result = CliRunner().invoke(main, ["find-references", "absent", str(file)])
    assert result.exit_code == 0, result.output
    assert "0 reference(s) to 'absent'" in result.output


def test_rename_param_rewrites_and_writes(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _REFS_TOOL_BYTES)
    result = CliRunner().invoke(main, ["rename-param", "input", "sample", str(file)])
    assert result.exit_code == 0, result.output
    assert "renamed" in result.output
    written = file.read_bytes()
    assert b"$sample" in written and b"$input" not in written


def test_rename_param_check_does_not_write(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _REFS_TOOL_BYTES)
    result = CliRunner().invoke(
        main, ["rename-param", "input", "sample", "--check", str(file)]
    )
    assert result.exit_code == 1  # --check exits non-zero when a file would change
    assert "would rename" in result.output
    assert file.read_bytes() == _REFS_TOOL_BYTES  # unchanged


def test_rename_param_skips_with_reason(tmp_path: Path) -> None:
    shadow = (
        b'<tool id="m" name="M" version="1.0.0" profile="21.09">'
        b"<command><![CDATA[#set $input = 1\ntool $input]]></command></tool>"
    )
    file = _write(tmp_path / "tool.xml", shadow)
    result = CliRunner().invoke(main, ["rename-param", "input", "sample", str(file)])
    assert result.exit_code == 0, result.output
    assert "skip" in result.output and "shadowed" in result.output
    assert file.read_bytes() == shadow  # unchanged


def test_rename_param_rejects_invalid_name(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _REFS_TOOL_BYTES)
    result = CliRunner().invoke(main, ["rename-param", "input", "not valid", str(file)])
    assert result.exit_code != 0
    assert "identifier" in result.output


# --- cross-file (bundle) rename + find-references --------------------------------


def _pal2nal_bundle(directory: Path) -> Path:
    """A tool whose param reference lives only in a sole-owned imported macro."""
    _write(
        directory / "macros.xml",
        b"<macros><xml name='command'>"
        b"<command><![CDATA[pal2nal '$protein_alignment']]></command></xml></macros>",
    )
    return _write(
        directory / "pal2nal.xml",
        b"<tool id='pal2nal' name='P' version='1.0.0' profile='21.09'>"
        b"<macros><import>macros.xml</import></macros>"
        b"<inputs><param name='protein_alignment' type='data'/></inputs>"
        b"<expand macro='command'/></tool>",
    )


def test_find_references_spans_imported_macro(tmp_path: Path) -> None:
    tool = _pal2nal_bundle(tmp_path)
    result = CliRunner().invoke(
        main, ["find-references", "protein_alignment", str(tool)]
    )
    assert result.exit_code == 0, result.output
    assert "macros.xml" in result.output  # the reference is reported in the macro file
    assert "$protein_alignment" in result.output
    assert "1 reference(s) to 'protein_alignment'" in result.output


def test_rename_into_macro_without_repo_root_skips(tmp_path: Path) -> None:
    tool = _pal2nal_bundle(tmp_path)
    result = CliRunner().invoke(
        main, ["rename-param", "protein_alignment", "aln", str(tool)]
    )
    assert result.exit_code == 0, result.output
    assert "--repo-root" in result.output  # tells the user how to proceed
    assert b"protein_alignment" in tool.read_bytes()  # nothing written


def test_rename_into_sole_owned_macro_with_repo_root(tmp_path: Path) -> None:
    tool = _pal2nal_bundle(tmp_path)
    result = CliRunner().invoke(
        main,
        ["rename-param", "protein_alignment", "aln", "--repo-root", str(tmp_path),
         str(tool)],
    )
    assert result.exit_code == 0, result.output
    assert "across 2 file(s)" in result.output
    macro_text = (tmp_path / "macros.xml").read_text(encoding="utf-8")
    assert "$aln" in macro_text and "$protein_alignment" not in macro_text
    assert "name=\"aln\"" in tool.read_text(encoding="utf-8")


def test_rename_into_shared_macro_is_reported(tmp_path: Path) -> None:
    _write(
        tmp_path / "shared.xml",
        b"<macros><xml name='command'>"
        b"<command><![CDATA[run '$old']]></command></xml></macros>",
    )
    common = (
        b"<macros><import>shared.xml</import></macros>"
        b"<inputs><param name='old' type='data'/></inputs>"
        b"<expand macro='command'/></tool>"
    )
    tool_a = _write(
        tmp_path / "a.xml",
        b"<tool id='a' name='A' version='1.0.0' profile='21.09'>" + common,
    )
    _write(
        tmp_path / "b.xml",
        b"<tool id='b' name='B' version='1.0.0' profile='21.09'>" + common,
    )
    result = CliRunner().invoke(
        main,
        ["rename-param", "old", "new", "--repo-root", str(tmp_path), str(tool_a)],
    )
    assert result.exit_code == 0, result.output
    assert "shared" in result.output
    assert "b.xml" in result.output  # the other importer is named
    assert b"old" in tool_a.read_bytes()  # not applied


def test_rename_repo_root_not_covering_tool_skips(tmp_path: Path) -> None:
    # --repo-root pointed at a dir that does not contain the tool: the macro is absent
    # from the importer map, so ownership can't be proven and the rename fails CLOSED.
    tool = _pal2nal_bundle(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = CliRunner().invoke(
        main,
        ["rename-param", "protein_alignment", "aln", "--repo-root", str(elsewhere),
         str(tool)],
    )
    assert result.exit_code == 0, result.output
    assert "cannot prove" in result.output and "sole-owned" in result.output
    assert b"protein_alignment" in tool.read_bytes()  # not applied


def _shared_importers(tmp_path: Path, b_body: bytes | None = None) -> tuple[Path, Path]:
    """Two tools importing a shared macro that references `$old`; return (a, b)."""
    _write(
        tmp_path / "shared.xml",
        b"<macros><xml name='command'>"
        b"<command><![CDATA[run '$old']]></command></xml></macros>",
    )
    common = (
        b"<macros><import>shared.xml</import></macros>"
        b"<inputs><param name='old' type='data'/></inputs>"
        b"<expand macro='command'/></tool>"
    )
    tool_a = _write(
        tmp_path / "a.xml",
        b"<tool id='a' name='A' version='1.0.0' profile='21.09'>" + common,
    )
    tool_b = _write(
        tmp_path / "b.xml",
        b_body or (b"<tool id='b' name='B' version='1.0.0' profile='21.09'>" + common),
    )
    return tool_a, tool_b


def test_rename_across_importers_renames_the_group(tmp_path: Path) -> None:
    tool_a, tool_b = _shared_importers(tmp_path)
    result = CliRunner().invoke(
        main,
        ["rename-param", "old", "new", "--repo-root", str(tmp_path),
         "--across-importers", str(tool_a)],
    )
    assert result.exit_code == 0, result.output
    assert "renamed across importers" in result.output
    assert b'name="new"' in tool_a.read_bytes()
    assert b'name="new"' in tool_b.read_bytes()  # the co-importer renamed in lockstep
    macro_text = (tmp_path / "shared.xml").read_text(encoding="utf-8")
    assert "$new" in macro_text and "$old" not in macro_text


def test_across_importers_requires_repo_root(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _REFS_TOOL_BYTES)
    result = CliRunner().invoke(
        main, ["rename-param", "input", "x", "--across-importers", str(file)]
    )
    assert result.exit_code != 0
    assert "repo-root" in result.output


def test_across_importers_dissent_skips_the_group(tmp_path: Path) -> None:
    # tool_b shadows the param in its own command -> no consensus -> nothing written.
    b_body = (
        b"<tool id='b' name='B' version='1.0.0' profile='21.09'>"
        b"<macros><import>shared.xml</import></macros>"
        b"<inputs><param name='old' type='data'/></inputs>"
        b"<command>#set $old = 1\nrun $old</command></tool>"
    )
    tool_a, _tool_b = _shared_importers(tmp_path, b_body=b_body)
    result = CliRunner().invoke(
        main,
        ["rename-param", "old", "new", "--repo-root", str(tmp_path),
         "--across-importers", str(tool_a)],
    )
    assert result.exit_code == 0, result.output
    assert "cannot rename" in result.output
    assert "b.xml" in result.output and "shadowed" in result.output  # names dissenter
    assert b"old" in tool_a.read_bytes()  # the agreeing tool is not written either


# --- --backup -------------------------------------------------------------------


def test_format_backup_writes_bak(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _REFS_TOOL_BYTES)
    result = CliRunner().invoke(main, ["format", "--backup", str(file)])
    assert result.exit_code == 0, result.output
    backup = tmp_path / "tool.xml.bak"
    assert backup.read_bytes() == _REFS_TOOL_BYTES  # the pristine original is preserved
    assert file.read_bytes() != _REFS_TOOL_BYTES  # the real file was reformatted


def test_rename_backup_covers_every_written_member(tmp_path: Path) -> None:
    tool = _pal2nal_bundle(tmp_path)
    macro_before = (tmp_path / "macros.xml").read_bytes()
    tool_before = tool.read_bytes()
    result = CliRunner().invoke(
        main,
        ["rename-param", "protein_alignment", "aln", "--repo-root", str(tmp_path),
         "--backup", str(tool)],
    )
    assert result.exit_code == 0, result.output
    # Both written members got a .bak holding their pre-rename content.
    assert (tmp_path / "macros.xml.bak").read_bytes() == macro_before
    assert (tmp_path / "pal2nal.xml.bak").read_bytes() == tool_before


def test_check_makes_no_backup(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _REFS_TOOL_BYTES)
    CliRunner().invoke(main, ["format", "--check", "--backup", str(file)])
    assert not (tmp_path / "tool.xml.bak").exists()  # --check writes nothing


_CONVERTIBLE_TOOL = (
    b"<tool id='x' name='X' version='1.0' profile='24.2'>"
    b"<command><![CDATA[echo hi]]></command>"
    b"<help>Title\n=====\n\nSome **bold** text.\n</help></tool>"
)
_OLD_PROFILE_TOOL = (
    b"<tool id='x' name='X' version='1.0'>"
    b"<command><![CDATA[echo hi]]></command>"
    b"<help>Title\n=====\n\nSome **bold** text.\n</help></tool>"
)


def test_convert_help_converts_in_place(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _CONVERTIBLE_TOOL)
    result = CliRunner().invoke(main, ["convert-help", str(file)])
    assert result.exit_code == 0, result.output
    assert "converted" in result.output
    written = file.read_bytes()
    assert b'format="markdown"' in written
    assert b"# Title" in written


def test_convert_help_check_writes_nothing(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _CONVERTIBLE_TOOL)
    result = CliRunner().invoke(main, ["convert-help", "--check", str(file)])
    assert result.exit_code == 0, result.output
    assert "would convert" in result.output
    assert file.read_bytes() == _CONVERTIBLE_TOOL


def test_convert_help_reports_profile_skip(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _OLD_PROFILE_TOOL)
    result = CliRunner().invoke(main, ["convert-help", str(file)])
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output and "upgrade" in result.output
    assert file.read_bytes() == _OLD_PROFILE_TOOL


def test_convert_help_backup(tmp_path: Path) -> None:
    file = _write(tmp_path / "tool.xml", _CONVERTIBLE_TOOL)
    result = CliRunner().invoke(main, ["convert-help", "--backup", str(file)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "tool.xml.bak").read_bytes() == _CONVERTIBLE_TOOL


def test_tokenize_version_command(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(
        b'<tool id="m" name="M" version="1.20+galaxy0" profile="24.0">'
        b"<command><![CDATA[echo x]]></command>"
        b'<requirements><requirement type="package" version="1.20">samtools'
        b"</requirement></requirements>"
        b'<inputs><param name="i" type="text"/></inputs>'
        b'<outputs><data name="o"/></outputs></tool>'
    )
    result = CliRunner().invoke(main, ["tokenize-version", str(tool)])
    assert result.exit_code == 0, result.output
    assert "tokenized" in result.output
    written = tool.read_bytes()
    assert b'version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"' in written
    assert b'<token name="@TOOL_VERSION@">1.20</token>' in written


def test_tokenize_version_check_mode_writes_nothing(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    payload = (
        b'<tool id="m" name="M" version="2.1+galaxy3" profile="24.0">'
        b"<command><![CDATA[echo x]]></command>"
        b'<requirements><requirement type="package" version="2.1">x'
        b"</requirement></requirements>"
        b'<inputs><param name="i" type="text"/></inputs>'
        b'<outputs><data name="o"/></outputs></tool>'
    )
    tool.write_bytes(payload)
    result = CliRunner().invoke(main, ["tokenize-version", "--check", str(tool)])
    assert result.exit_code == 0
    assert "would tokenize" in result.output
    assert tool.read_bytes() == payload


def test_tokenize_version_reports_skip_reason(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(
        b'<tool id="m" name="M" version="1.20" profile="24.0">'
        b"<command><![CDATA[echo x]]></command>"
        b'<inputs><param name="i" type="text"/></inputs>'
        b'<outputs><data name="o"/></outputs></tool>'
    )
    result = CliRunner().invoke(main, ["tokenize-version", str(tool)])
    assert result.exit_code == 0
    assert "skipped" in result.output and "+galaxy" in result.output


_TOKENIZABLE_TOOL = (
    b'<tool id="m" name="M" version="1.20+galaxy0" profile="24.0">'
    b"<command><![CDATA[echo x]]></command>"
    b'<requirements><requirement type="package" version="1.20">samtools'
    b"</requirement></requirements>"
    b'<inputs><param name="i" type="text"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)


def test_tokenize_version_macros_file_creates_separate_file(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_TOKENIZABLE_TOOL)
    result = CliRunner().invoke(
        main, ["tokenize-version", "--macros-file", "macros.xml", str(tool)]
    )
    assert result.exit_code == 0, result.output
    assert "tokenized" in result.output and "macros.xml" in result.output
    written = tool.read_bytes()
    assert b"<import>macros.xml</import>" in written
    assert b'<token name="@TOOL_VERSION@">' not in written  # not inline
    macros = tmp_path / "macros.xml"
    assert macros.exists()
    assert b'<token name="@TOOL_VERSION@">1.20</token>' in macros.read_bytes()


def test_tokenize_version_macros_file_named(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_TOKENIZABLE_TOOL)
    result = CliRunner().invoke(
        main, ["tokenize-version", "--macros-file", "version_macros.xml", str(tool)]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "version_macros.xml").exists()
    assert b"<import>version_macros.xml</import>" in tool.read_bytes()


def test_tokenize_version_macros_file_check_writes_nothing(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_TOKENIZABLE_TOOL)
    result = CliRunner().invoke(
        main, ["tokenize-version", "--check", "--macros-file", "macros.xml", str(tool)]
    )
    assert result.exit_code == 0, result.output
    assert "would tokenize" in result.output
    assert tool.read_bytes() == _TOKENIZABLE_TOOL
    assert not (tmp_path / "macros.xml").exists()


def test_tokenize_version_macros_file_merges_existing(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_TOKENIZABLE_TOOL)
    (tmp_path / "macros.xml").write_text(
        '<macros><token name="@CITE@">ref</token></macros>', encoding="utf-8"
    )
    result = CliRunner().invoke(
        main, ["tokenize-version", "--macros-file", "macros.xml", str(tool)]
    )
    assert result.exit_code == 0, result.output
    assert "tokenized" in result.output and "updated macros.xml" in result.output
    macros = (tmp_path / "macros.xml").read_bytes()
    assert b'<token name="@CITE@">ref</token>' in macros  # kept
    assert b'<token name="@TOOL_VERSION@">1.20</token>' in macros  # added
    assert b"<import>macros.xml</import>" in tool.read_bytes()


_BARE_VERSION_TOOL = (
    b'<tool id="m" name="M" version="1.20" profile="24.0">'
    b"<command><![CDATA[echo x]]></command>"
    b'<requirements><requirement type="package" version="1.20">samtools'
    b"</requirement></requirements>"
    b'<inputs><param name="i" type="text"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)


def test_tokenize_version_adopt_suffix(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_BARE_VERSION_TOOL)
    result = CliRunner().invoke(main, ["tokenize-version", "--adopt-suffix", str(tool)])
    assert result.exit_code == 0, result.output
    assert "adopted" in result.output and "published version changed" in result.output
    written = tool.read_bytes()
    assert b'version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"' in written
    assert b'<token name="@VERSION_SUFFIX@">0</token>' in written


def test_tokenize_version_adopt_suffix_check_writes_nothing(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_BARE_VERSION_TOOL)
    result = CliRunner().invoke(
        main, ["tokenize-version", "--adopt-suffix", "--check", str(tool)]
    )
    assert result.exit_code == 0, result.output
    assert "would adopt" in result.output
    assert tool.read_bytes() == _BARE_VERSION_TOOL


def test_tokenize_version_adopt_suffix_rejects_macros_file(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_BARE_VERSION_TOOL)
    result = CliRunner().invoke(
        main,
        ["tokenize-version", "--adopt-suffix", "--macros-file", "m.xml", str(tool)],
    )
    assert result.exit_code == 1
    assert "cannot be combined" in result.output


def test_tokenize_version_macros_file_consensus(tmp_path: Path) -> None:
    # Two tools sharing the same version in one directory tokenize together into one
    # created macros.xml.
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    a.write_bytes(_TOKENIZABLE_TOOL.replace(b'id="m"', b'id="a"'))
    b.write_bytes(_TOKENIZABLE_TOOL.replace(b'id="m"', b'id="b"'))
    result = CliRunner().invoke(
        main, ["tokenize-version", "--macros-file", "macros.xml", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "2 tokenized" in result.output
    assert (tmp_path / "macros.xml").exists()
    for tool in (a, b):
        assert b"<import>macros.xml</import>" in tool.read_bytes()
        assert b'version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"' in tool.read_bytes()
