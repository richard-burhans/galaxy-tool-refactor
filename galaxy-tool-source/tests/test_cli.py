"""Tests for the click command-line interface."""

from pathlib import Path

from click.testing import CliRunner

from galaxy_tool_source.cli import main


def test_validate_valid_tool(data_dir: Path) -> None:
    result = CliRunner().invoke(main, ["validate", str(data_dir / "minimal_tool.xml")])
    assert result.exit_code == 0
    assert "valid" in result.output


def test_validate_schema_invalid_tool(data_dir: Path) -> None:
    result = CliRunner().invoke(main, ["validate", str(data_dir / "invalid_tool.xml")])
    assert result.exit_code == 1


def test_validate_malformed_tool(data_dir: Path) -> None:
    result = CliRunner().invoke(
        main, ["validate", str(data_dir / "malformed_tool.xml")]
    )
    assert result.exit_code == 1


def test_validate_on_missing_exact(data_dir: Path) -> None:
    result = CliRunner().invoke(
        main,
        [
            "validate",
            "--profile",
            "99.9",
            "--on-missing",
            "exact",
            str(data_dir / "minimal_tool.xml"),
        ],
    )
    assert result.exit_code == 1


def test_validate_macro_handling_expand(data_dir: Path) -> None:
    result = CliRunner().invoke(
        main, ["validate", str(data_dir / "tool_with_macros.xml")]
    )
    assert result.exit_code == 0


def test_validate_macro_handling_off(data_dir: Path) -> None:
    result = CliRunner().invoke(
        main,
        ["validate", "--macro-handling", "off", str(data_dir / "tool_with_macros.xml")],
    )
    assert result.exit_code == 1


def test_suggest_reports_typos(data_dir: Path) -> None:
    result = CliRunner().invoke(
        main, ["suggest", str(data_dir / "tool_with_typos.xml")]
    )
    assert result.exit_code == 1
    assert "did you mean" in result.output


def test_suggest_clean_tool(data_dir: Path) -> None:
    result = CliRunner().invoke(main, ["suggest", str(data_dir / "minimal_tool.xml")])
    assert result.exit_code == 0


def test_profiles_lists_versions_with_latest_marked() -> None:
    result = CliRunner().invoke(main, ["profiles"])
    assert result.exit_code == 0
    assert "26.0" in result.output
    assert "(latest)" in result.output
