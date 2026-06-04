"""Tests for the concrete advisory checks."""

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
    assert "GTR021" in _codes(_tool(tests=""))
    assert "GTR021" not in _codes(_tool())


def test_iuc018_2_command_cdata_residual() -> None:
    # GTR018.2 (advisory) fires only on the residual the fix can't wrap: a
    # child-element mixed-content body. Pure text is GTR018.1's job.
    assert "GTR018.2" not in _codes(_tool(command="<command>foo</command>"))
    assert "GTR018.2" in _codes(_tool(command="<command>echo <a/> done</command>"))
    assert "GTR018.2" not in _codes(_tool())  # default is CDATA


def test_iuc003_bad_id_charset() -> None:
    assert "GTR023" in _codes(_tool(tool_id="Bad Id"))
    assert "GTR023" not in _codes(_tool(tool_id="ok_tool-1.2+x"))


def test_iuc004_version_not_pep440_and_no_macro() -> None:
    assert "GTR024" in _codes(_tool(version="not_a_version"))
    # A PEP 440 version and a @...@ macro both pass.
    assert "GTR024" not in _codes(_tool(version="1.2.3"))
    assert "GTR024" not in _codes(_tool(version="@TOOL_VERSION@+galaxy0"))


def test_iuc005_missing_requirements() -> None:
    assert "GTR025" in _codes(_tool(requirements=""))
    assert "GTR025" in _codes(_tool(requirements="<requirements/>"))
    assert "GTR025" not in _codes(_tool())


def test_iuc006_no_error_handling() -> None:
    # No <stdio> and the command has no detect_errors -> flagged.
    assert "GTR026" in _codes(_tool(stdio=""))
    # detect_errors on the command satisfies it without <stdio>.
    satisfied = _tool(
        stdio="",
        command='<command detect_errors="aggressive"><![CDATA[x]]></command>',
    )
    assert "GTR026" not in _codes(satisfied)


def test_iuc007_no_edam_or_xrefs() -> None:
    assert "GTR027" in _codes(_tool(edam=""))
    xrefs = '<xrefs><xref type="bio.tools">foo</xref></xrefs>'
    assert "GTR027" not in _codes(_tool(edam=xrefs))


def test_iuc008_missing_help() -> None:
    assert "GTR028" in _codes(_tool(help_=""))
    assert "GTR028" not in _codes(_tool())


def test_iuc009_missing_description() -> None:
    assert "GTR029" in _codes(_tool(description=""))
    assert "GTR029" not in _codes(_tool())


def test_iuc019_2_help_cdata_residual() -> None:
    # GTR019.2 (advisory) fires only on mixed-content help the fix can't wrap.
    assert "GTR019.2" not in _codes(_tool(help_="<help>plain text</help>"))
    assert "GTR019.2" in _codes(_tool(help_="<help>text <b/> more</help>"))
    assert "GTR019.2" not in _codes(_tool())


def test_iuc012_placeholder_never_fires() -> None:
    """GTR032 (&&-vs-lone-&) is a data-backed no-op stub (decisions D3)."""
    codes = _codes(_tool(command="<command><![CDATA[a & b && c]]></command>"))
    assert "GTR032" not in codes


def test_iuc013_flags_unpinned_package_requirements() -> None:
    """One GTR033 finding per package <requirement> without a version."""
    # The default tool pins its requirement, so GTR033 stays silent.
    assert "GTR033" not in _codes(_tool())
    unpinned = _tool(
        requirements=(
            "<requirements>"
            '<requirement type="package" version="1.0">pinned</requirement>'
            '<requirement type="package">loose</requirement>'
            '<requirement type="package" version="  ">blank</requirement>'
            "</requirements>"
        )
    )
    found = [v for v in detect_violations(load_tool(unpinned)) if v.code == "GTR033"]
    assert len(found) == 2  # loose + blank (pinned is fine)
    assert any("loose" in v.message for v in found)


def test_iuc013_ignores_non_package_and_flags_bare_default() -> None:
    """Non-package kinds carry no version; a bare <requirement> defaults to package."""
    env = _tool(
        requirements=(
            '<requirements><requirement type="set_environment">PATH'
            "</requirement></requirements>"
        )
    )
    assert "GTR033" not in _codes(env)  # set_environment isn't a package pin
    bare = _tool(
        requirements="<requirements><requirement>foo</requirement></requirements>"
    )
    assert "GTR033" in _codes(bare)  # no type= defaults to package -> flagged


def _iuc011(tool_bytes: bytes) -> list:
    return [v for v in detect_violations(load_tool(tool_bytes)) if v.code == "GTR020.2"]


def test_iuc020_2_residual_flags_only_non_provable_vars() -> None:
    """GTR020.2 (advisory) flags only the NON-provable unquoted vars; the provable
    ones (here $input, a data param) are GTR020.1's job."""
    tool = _tool(command="<command><![CDATA[prog --in $input --ref $ref]]></command>")
    found = _iuc011(tool)
    # $input resolves to a data param (provable -> fixed); $ref resolves to no input
    # (non-provable -> advisory residual).
    assert len(found) == 1
    assert found[0].message == (
        "unquoted Cheetah variable $ref in <command> — single-quote it as '$ref'"
    )


def test_iuc011_ignores_quoted_and_directive_vars() -> None:
    """Single/double-quoted vars and directive-line vars are not flagged."""
    # The default tool single-quotes its one var, so GTR020.2 stays silent.
    assert _iuc011(_tool()) == []
    quoted = _tool(command='<command><![CDATA[prog "$a" \'$b\']]></command>')
    assert _iuc011(quoted) == []
    directive = _tool(
        command="<command><![CDATA[#if $cond\nrun '$x'\n#end if]]></command>"
    )
    assert _iuc011(directive) == []


def test_violations_are_located() -> None:
    """Findings carry a source line and an xpath into the tool."""
    broken = _tool(tests="", command="<command>x</command>")
    violations = detect_violations(load_tool(broken))
    assert violations  # at least GTR021 (no tests); the pure-text command is fixable
    assert all(v.xpath.startswith("/tool") for v in violations)
    assert all(v.sourceline >= 1 for v in violations)


def test_iuc018_2_residual_is_child_element_mixed_content() -> None:
    """GTR018.2 (advisory) fires on mixed content the fix can't wrap as one section
    — a child *element* — not on a body the fix can losslessly wrap.
    """
    # A child element -> not wrappable -> advisory residual.
    child = "<command>echo <token><![CDATA[x]]></token></command>"
    assert "GTR018.2" in _codes(_tool(command=child))
    # Leading text + an inline CDATA (no child element) IS losslessly wrappable by
    # GTR018.1 (lxml exposes the body as one text run), so the advisory does not fire.
    inline = "<command>echo <![CDATA[hi]]></command>"
    assert "GTR018.2" not in _codes(_tool(command=inline))
    # Fully wrapped, even with leading whitespace, is fine.
    wrapped_ws = "<command>\n    <![CDATA[echo hi]]></command>"
    assert "GTR018.2" not in _codes(_tool(command=wrapped_ws))
