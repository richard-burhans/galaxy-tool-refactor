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
    citations: str = '<citations><citation type="doi">10.1/x</citation></citations>',
    outputs: str = '<outputs><data name="out" format="txt"/></outputs>',
    profile: str = "24.0",
) -> bytes:
    """Build a tool that, with every default, passes all checks. Override one
    keyword to break exactly one practice."""
    return (
        f'<tool id="{tool_id}" name="Good" version="{version}" profile="{profile}">'
        f"{description}{edam}{requirements}{stdio}{command}"
        '<inputs><param name="input" type="data" format="txt"/></inputs>'
        f"{outputs}"
        f"{tests}{help_}{citations}</tool>"
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


def test_gtr038_citations_present() -> None:
    assert "GTR038" in _codes(_tool(citations=""))  # no <citations> at all
    # citations element present but the doi citation is empty -> flagged
    empty_doi = '<citations><citation type="doi"></citation></citations>'
    assert "GTR038" in _codes(_tool(citations=empty_doi))
    assert "GTR038" not in _codes(_tool())  # default has a non-empty doi citation


def test_gtr039_no_todo_text() -> None:
    todo_cmd = "<command><![CDATA[foo --in '$input' # TODO finish]]></command>"
    assert "GTR039" in _codes(_tool(command=todo_cmd))
    assert "GTR039" in _codes(_tool(help_="<help><![CDATA[TODO write help]]></help>"))
    assert "GTR039" not in _codes(_tool())  # default has no TODO


def test_gtr040_output_names_unique() -> None:
    dup = '<outputs><data name="out" format="txt"/><data name="out"/></outputs>'
    assert "GTR040" in _codes(_tool(outputs=dup))
    # a data and a collection sharing a name also collide
    dup_mixed = (
        '<outputs><data name="x"/><collection name="x" type="list"/></outputs>'
    )
    assert "GTR040" in _codes(_tool(outputs=dup_mixed))
    assert "GTR040" not in _codes(_tool())  # default has a single unique name


def test_gtr041_output_name_valid() -> None:
    bad = '<outputs><data name="out put" format="txt"/></outputs>'
    assert "GTR041" in _codes(_tool(outputs=bad))
    leading_digit = '<outputs><data name="1out" format="txt"/></outputs>'
    assert "GTR041" in _codes(_tool(outputs=leading_digit))
    assert "GTR041" not in _codes(_tool())  # 'out' is a valid placeholder


def test_gtr042_collection_type_declared() -> None:
    no_type = '<outputs><collection name="c"/></outputs>'
    assert "GTR042" in _codes(_tool(outputs=no_type))
    typed = '<outputs><collection name="c" type="list"/></outputs>'
    assert "GTR042" not in _codes(_tool(outputs=typed))
    # structure derived via structured_like is accepted (lenient vs planemo)
    derived = '<outputs><collection name="c" structured_like="x"/></outputs>'
    assert "GTR042" not in _codes(_tool(outputs=derived))


def test_gtr043_output_format_source_exclusive() -> None:
    clash = '<outputs><data name="o" format_source="input" format="txt"/></outputs>'
    assert "GTR043" in _codes(_tool(outputs=clash))
    ext_clash = '<outputs><data name="o" format_source="input" ext="bam"/></outputs>'
    assert "GTR043" in _codes(_tool(outputs=ext_clash))
    only_source = '<outputs><data name="o" format_source="input"/></outputs>'
    assert "GTR043" not in _codes(_tool(outputs=only_source))
    assert "GTR043" not in _codes(_tool())  # default sets only format


def test_gtr044_command_present() -> None:
    assert "GTR044" in _codes(_tool(command=""))  # no <command> at all
    assert "GTR044" in _codes(_tool(command="<command></command>"))  # empty
    assert "GTR044" in _codes(_tool(command="<command>   </command>"))  # whitespace
    assert "GTR044" not in _codes(_tool())  # default has a real command
    # A macro may inject the <command>: a top-level <expand> (or a <macros> block)
    # means we cannot prove the command absent on the raw tree -> skip, don't misfire.
    assert "GTR044" not in _codes(_tool(command='<expand macro="cmd"/>'))
    # An <expand> *child* supplies the body from a macro -> not really empty.
    expand_body = '<command><expand macro="cmd"/></command>'
    assert "GTR044" not in _codes(_tool(command=expand_body))


def test_gtr045_profile_format_valid() -> None:
    assert "GTR045" in _codes(_tool(profile="banana"))
    assert "GTR045" in _codes(_tool(profile="2024"))  # no dotted minor
    assert "GTR045" not in _codes(_tool(profile="21.09"))
    # a @...@ macro token resolves at expansion; we lint the raw tree, so skip it
    assert "GTR045" not in _codes(_tool(profile="@PROFILE@"))
    assert "GTR045" not in _codes(_tool())  # default 24.0 is valid


def test_gtr046_requirement_name_present() -> None:
    empty_name = (
        '<requirements><requirement type="package" version="1.0">'
        "</requirement></requirements>"
    )
    assert "GTR046" in _codes(_tool(requirements=empty_name))
    blank_name = (
        '<requirements><requirement type="package" version="1.0">  '
        "</requirement></requirements>"
    )
    assert "GTR046" in _codes(_tool(requirements=blank_name))
    assert "GTR046" not in _codes(_tool())  # default names its requirement


def test_gtr047_tool_version_whitespace() -> None:
    assert "GTR047" in _codes(_tool(version="1.0.0 "))
    assert "GTR047" in _codes(_tool(version=" 1.0.0"))
    assert "GTR047" not in _codes(_tool())  # default has no surrounding whitespace


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


def _refs_tool(
    *, inputs: bytes, command: bytes = b"echo hi", extra: bytes = b""
) -> bytes:
    return (
        b'<tool id="m" name="M" version="1.0.0" profile="21.09">'
        b"<command><![CDATA[" + command + b"]]></command>"
        b"<inputs>" + inputs + b"</inputs>" + extra
        + b'<outputs><data name="o"/></outputs></tool>'
    )


def test_gtr034_flags_orphan_param() -> None:
    tool = _refs_tool(inputs=b'<param name="orphan" type="text"/>')
    assert "GTR034" in _codes(tool)


def test_gtr034_not_flagged_when_dollar_referenced() -> None:
    tool = _refs_tool(
        inputs=b'<param name="used" type="text"/>', command=b"echo '$used'"
    )
    assert "GTR034" not in _codes(tool)


def test_gtr034_not_flagged_via_crossref_attribute() -> None:
    # data_ref names the data param without a $.
    tool = _refs_tool(
        inputs=(
            b'<param name="ds" type="data"/>'
            b'<param name="col" type="data_column" data_ref="ds"/>'
        ),
        command=b"echo '$col'",  # ds referenced only via data_ref
    )
    assert "GTR034" not in _codes(tool)


def test_gtr034_not_flagged_for_conditional_selector() -> None:
    # the selector param drives the <when> branches; never $-referenced here.
    tool = _refs_tool(
        inputs=(
            b'<conditional name="c">'
            b'<param name="sel" type="select"><option value="a">a</option></param>'
            b'<when value="a"><param name="x" type="text"/></when>'
            b"</conditional>"
        ),
        command=b"echo '$c.x'",
    )
    codes = _codes(tool)
    assert "GTR034" not in codes  # sel (selector) and x (used) both fine


def test_gtr034_not_flagged_when_referenced_only_via_macro_token() -> None:
    # $opts is reached only through a macro token (@OPTS@ -> $opts); the macro-expanded
    # scan sees the reference, so the param must not be flagged.
    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="21.09">'
        b'<macros><token name="@OPTS@">$opts</token></macros>'
        b"<command><![CDATA[tool @OPTS@]]></command>"
        b'<inputs><param name="opts" type="text"/></inputs>'
        b'<outputs><data name="o"/></outputs></tool>'
    )
    assert "GTR034" not in _codes(tool)


def test_gtr034_not_flagged_when_used_only_in_output_filter() -> None:
    # <filter>store_ext</filter> references the boolean by bare name (Python expr).
    tool = _refs_tool(
        inputs=b'<param name="store_ext" type="boolean" value="false"/>',
        extra=b'<outputs><data name="o2"><filter>store_ext</filter></data></outputs>',
    )
    assert "GTR034" not in _codes(tool)
