"""Tests for the concrete advisory IUC checks."""

from __future__ import annotations

from galaxy_tool_xml.binding import load_tool

from galaxy_tool_xml_check.detect import detect_violations


def _tool(
    *,
    tool_id: str = "good_tool",
    version: str = "1.0.0",
    description: str = "<description>Does a thing.</description>",
    edam: str = "<edam_topics><edam_topic>topic_0091</edam_topic></edam_topics>",
    requirements: str = (
        '<requirements><requirement type="package" version="1.0">foo'
        "</requirement></requirements>"
    ),
    stdio: str = '<stdio><exit_code range="1:" level="fatal"/></stdio>',
    command: str = "<command><![CDATA[foo --in '$input']]></command>",
    tests: str = '<tests><test><param name="input" value="x"/></test></tests>',
    help_: str = "<help><![CDATA[Some help text.]]></help>",
) -> bytes:
    """Build a tool that, with every default, passes all checks. Override one
    keyword to break exactly one practice."""
    return (
        f'<tool id="{tool_id}" name="Good" version="{version}" profile="24.0">'
        f"{description}{edam}{requirements}{stdio}{command}"
        '<inputs><param name="input" type="data" format="txt"/></inputs>'
        '<outputs><data name="out" format="txt"/></outputs>'
        f"{tests}{help_}</tool>"
    ).encode()


def _codes(tool_bytes: bytes) -> set[str]:
    return {v.code for v in detect_violations(load_tool(tool_bytes))}


def test_complete_tool_has_no_findings() -> None:
    """A tool that follows every detectable practice produces zero findings."""
    assert detect_violations(load_tool(_tool())) == []


def test_iuc001_missing_tests() -> None:
    assert "IUC001" in _codes(_tool(tests=""))
    assert "IUC001" not in _codes(_tool())


def test_iuc002_command_not_cdata() -> None:
    assert "IUC002" in _codes(_tool(command="<command>foo</command>"))
    assert "IUC002" not in _codes(_tool())


def test_iuc003_bad_id_charset() -> None:
    assert "IUC003" in _codes(_tool(tool_id="Bad Id"))
    assert "IUC003" not in _codes(_tool(tool_id="ok_tool-1.2+x"))


def test_iuc004_version_not_pep440_and_no_macro() -> None:
    assert "IUC004" in _codes(_tool(version="not_a_version"))
    # A PEP 440 version and a @...@ macro both pass.
    assert "IUC004" not in _codes(_tool(version="1.2.3"))
    assert "IUC004" not in _codes(_tool(version="@TOOL_VERSION@+galaxy0"))


def test_iuc005_missing_requirements() -> None:
    assert "IUC005" in _codes(_tool(requirements=""))
    assert "IUC005" in _codes(_tool(requirements="<requirements/>"))
    assert "IUC005" not in _codes(_tool())


def test_iuc006_no_error_handling() -> None:
    # No <stdio> and the command has no detect_errors -> flagged.
    assert "IUC006" in _codes(_tool(stdio=""))
    # detect_errors on the command satisfies it without <stdio>.
    satisfied = _tool(
        stdio="",
        command='<command detect_errors="aggressive"><![CDATA[x]]></command>',
    )
    assert "IUC006" not in _codes(satisfied)


def test_iuc007_no_edam_or_xrefs() -> None:
    assert "IUC007" in _codes(_tool(edam=""))
    xrefs = '<xrefs><xref type="bio.tools">foo</xref></xrefs>'
    assert "IUC007" not in _codes(_tool(edam=xrefs))


def test_iuc008_missing_help() -> None:
    assert "IUC008" in _codes(_tool(help_=""))
    assert "IUC008" not in _codes(_tool())


def test_iuc009_missing_description() -> None:
    assert "IUC009" in _codes(_tool(description=""))
    assert "IUC009" not in _codes(_tool())


def test_iuc010_help_not_cdata() -> None:
    assert "IUC010" in _codes(_tool(help_="<help>plain text</help>"))
    assert "IUC010" not in _codes(_tool())


def test_placeholders_never_fire() -> None:
    """The reserved Cheetah / && placeholders emit nothing on any tool."""
    codes = _codes(_tool(command="<command><![CDATA[$unquoted && a & b]]></command>"))
    assert "IUC011" not in codes
    assert "IUC012" not in codes


def test_violations_are_located() -> None:
    """Findings carry a source line and an xpath into the tool."""
    broken = _tool(tests="", command="<command>x</command>")
    violations = detect_violations(load_tool(broken))
    assert violations  # at least IUC001 and IUC002
    assert all(v.xpath.startswith("/tool") for v in violations)
    assert all(v.sourceline >= 1 for v in violations)


def test_iuc002_partial_or_child_cdata_is_flagged() -> None:
    """Only the command's own body being CDATA-wrapped clears IUC002.

    Leading unprotected text (`echo <![CDATA[...]]>`) or a CDATA-bearing *child*
    leaves the command body unprotected, so IUC002 must still fire.
    """
    assert "IUC002" in _codes(_tool(command="<command>echo <![CDATA[hi]]></command>"))
    child = "<command>echo <token><![CDATA[x]]></token></command>"
    assert "IUC002" in _codes(_tool(command=child))
    # Fully wrapped, even with leading whitespace, is fine.
    wrapped_ws = "<command>\n    <![CDATA[echo hi]]></command>"
    assert "IUC002" not in _codes(_tool(command=wrapped_ws))
