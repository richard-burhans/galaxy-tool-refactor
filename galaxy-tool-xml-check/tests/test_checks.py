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
    tests: str = (
        '<tests><test expect_num_outputs="1">'
        '<param name="input" value="x"/></test></tests>'
    ),
    help_: str = "<help><![CDATA[Some help text.]]></help>",
    citations: str = '<citations><citation type="doi">10.1/x</citation></citations>',
    outputs: str = '<outputs><data name="out" format="txt"/></outputs>',
    profile: str = "24.0",
    inputs: str = '<inputs><param name="input" type="data" format="txt"/></inputs>',
) -> bytes:
    """Build a tool that, with every default, passes all checks. Override one
    keyword to break exactly one practice."""
    return (
        f'<tool id="{tool_id}" name="Good" version="{version}" profile="{profile}">'
        f"{description}{edam}{requirements}{stdio}{command}"
        f"{inputs}"
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


def test_gtr048_outputs_present() -> None:
    assert "GTR048" in _codes(_tool(outputs=""))  # no <outputs> at all
    assert "GTR048" not in _codes(_tool())  # default has an <outputs>
    # A macro may inject the <outputs>; can't prove absence on the raw tree -> skip.
    assert "GTR048" not in _codes(_tool(outputs='<expand macro="outputs"/>'))


def test_gtr049_output_format_defined() -> None:
    no_fmt = '<outputs><data name="o"/></outputs>'
    assert "GTR049" in _codes(_tool(outputs=no_fmt))
    # format / ext / format_source / auto_format all satisfy it
    assert "GTR049" not in _codes(_tool())  # default sets format="txt"
    assert "GTR049" not in _codes(
        _tool(outputs='<outputs><data name="o" ext="bam"/></outputs>')
    )
    assert "GTR049" not in _codes(
        _tool(outputs='<outputs><data name="o" auto_format="true"/></outputs>')
    )
    # a child <action type="format"> defines it
    action = (
        '<outputs><data name="o"><actions>'
        '<action type="format"><option type="from_param"/></action>'
        "</actions></data></outputs>"
    )
    assert "GTR049" not in _codes(_tool(outputs=action))
    # a discover_datasets pattern that captures the ext defines it
    discover = (
        '<outputs><data name="o">'
        r'<discover_datasets pattern="(?P&lt;designation&gt;.+)\.(?P&lt;ext&gt;.+)"/>'
        "</data></outputs>"
    )
    assert "GTR049" not in _codes(_tool(outputs=discover))
    # a tool that writes galaxy.json provides formats at runtime -> whole tool exempt
    meta_cmd = '<command><![CDATA[run > galaxy.json]]></command>'
    assert "GTR049" not in _codes(_tool(outputs=no_fmt, command=meta_cmd))
    # a macro may inject format-defining structure into the output -> skip
    expand_out = '<outputs><data name="o"><expand macro="fmt"/></data></outputs>'
    assert "GTR049" not in _codes(_tool(outputs=expand_out))


def test_gtr050_output_labels_distinct() -> None:
    dup = (
        '<outputs><data name="a" label="result"/>'
        '<data name="b" label="result"/></outputs>'
    )
    assert "GTR050" in _codes(_tool(outputs=dup))
    # distinct explicit labels are fine
    distinct = (
        '<outputs><data name="a" label="one"/>'
        '<data name="b" label="two"/></outputs>'
    )
    assert "GTR050" not in _codes(_tool(outputs=distinct))
    # outputs without an explicit label share Galaxy's default -> not flagged
    # (low-noise narrowing of planemo, which flags the default collision too)
    no_label = '<outputs><data name="a"/><data name="b"/></outputs>'
    assert "GTR050" not in _codes(_tool(outputs=no_label))


def test_gtr051_container_shape_recognized() -> None:
    bad = (
        '<requirements><container type="docker">'
        "not a shape!</container></requirements>"
    )
    assert "GTR051" in _codes(_tool(requirements=bad))
    quay = (
        '<requirements><container type="docker">'
        "quay.io/biocontainers/samtools:1.0</container></requirements>"
    )
    assert "GTR051" not in _codes(_tool(requirements=quay))
    hub = (
        '<requirements><container type="docker">'
        "biocontainers/samtools:1.0</container></requirements>"
    )
    assert "GTR051" not in _codes(_tool(requirements=hub))
    # an unexpanded @…@ macro token cannot be checked on the raw tree -> skip
    token = (
        '<requirements><container type="docker">'
        "@CONTAINER@</container></requirements>"
    )
    assert "GTR051" not in _codes(_tool(requirements=token))
    assert "GTR051" not in _codes(_tool())  # default has no <container>


def test_gtr052_output_filter_valid() -> None:
    bad = '<outputs><data name="o" format="txt"><filter>1 +</filter></data></outputs>'
    assert "GTR052" in _codes(_tool(outputs=bad))
    good = (
        '<outputs><data name="o" format="txt">'
        "<filter>genome == 'hg19'</filter></data></outputs>"
    )
    assert "GTR052" not in _codes(_tool(outputs=good))
    # a filter carrying a macro token is skipped (unprovable on the raw tree)
    token = (
        '<outputs><data name="o" format="txt"><filter>@FOO@</filter></data></outputs>'
    )
    assert "GTR052" not in _codes(_tool(outputs=token))
    assert "GTR052" not in _codes(_tool())  # default has no <filter>


def test_gtr053_stdio_regex_valid() -> None:
    bad = '<stdio><regex match="["/></stdio>'
    assert "GTR053" in _codes(_tool(stdio=bad))
    good = '<stdio><regex match="error|fatal"/></stdio>'
    assert "GTR053" not in _codes(_tool(stdio=good))
    assert "GTR053" not in _codes(_tool())  # default stdio has no <regex>


def test_gtr054_param_name_present() -> None:
    nameless = '<inputs><param type="data" format="txt"/></inputs>'
    assert "GTR054" in _codes(_tool(inputs=nameless))
    # an 'argument' supplies the name -> fine
    arg = '<inputs><param argument="--in" type="data" format="txt"/></inputs>'
    assert "GTR054" not in _codes(_tool(inputs=arg))
    assert "GTR054" not in _codes(_tool())  # default param has a name


def test_gtr055_param_name_valid() -> None:
    empty = '<inputs><param name="" type="data" format="txt"/></inputs>'
    assert "GTR055" in _codes(_tool(inputs=empty))
    bad = '<inputs><param name="in put" type="data" format="txt"/></inputs>'
    assert "GTR055" in _codes(_tool(inputs=bad))
    leading_digit = '<inputs><param name="1in" type="data" format="txt"/></inputs>'
    assert "GTR055" in _codes(_tool(inputs=leading_digit))
    assert "GTR055" not in _codes(_tool())  # 'input' is a valid placeholder


def test_gtr056_param_names_unique() -> None:
    dup = (
        '<inputs><param name="x" type="text"/>'
        '<param name="x" type="text"/></inputs>'
    )
    assert "GTR056" in _codes(_tool(inputs=dup))
    # the same name in disjoint <when> branches is allowed (qualified path differs)
    cond = (
        '<inputs><conditional name="c"><param name="sel" type="select">'
        '<option value="a">a</option><option value="b">b</option></param>'
        '<when value="a"><param name="x" type="text"/></when>'
        '<when value="b"><param name="x" type="text"/></when>'
        "</conditional></inputs>"
    )
    assert "GTR056" not in _codes(_tool(inputs=cond))
    assert "GTR056" not in _codes(_tool())  # single param, unique


def test_gtr057_input_output_names_distinct() -> None:
    clash = '<inputs><param name="out" type="text"/></inputs>'
    # default output is named "out" -> collides with the input
    assert "GTR057" in _codes(_tool(inputs=clash))
    assert "GTR057" not in _codes(_tool())  # input 'input' != output 'out'


def test_gtr058_select_options_defined() -> None:
    none = '<inputs><param name="s" type="select"/></inputs>'
    assert "GTR058" in _codes(_tool(inputs=none))  # zero ways to define options
    both = (
        '<inputs><param name="s" type="select"><option value="a">A</option>'
        '<options from_data_table="t"/></param></inputs>'
    )
    assert "GTR058" in _codes(_tool(inputs=both))  # two ways at once
    static = (
        '<inputs><param name="s" type="select">'
        '<option value="a">A</option></param></inputs>'
    )
    assert "GTR058" not in _codes(_tool(inputs=static))
    dynamic = '<inputs><param name="s" type="select" dynamic_options="f()"/></inputs>'
    assert "GTR058" not in _codes(_tool(inputs=dynamic))
    # a conditional select must use <option> children, not <options>/dynamic
    cond_bad = (
        '<inputs><conditional name="c">'
        '<param name="s" type="select"><options from_data_table="t"/></param>'
        "</conditional></inputs>"
    )
    assert "GTR058" in _codes(_tool(inputs=cond_bad))
    # a macro <expand> may inject the options -> skip (raw-tree boundary)
    macro = (
        '<inputs><param name="s" type="select">'
        '<expand macro="opts"/></param></inputs>'
    )
    assert "GTR058" not in _codes(_tool(inputs=macro))


def test_gtr059_select_option_value_present() -> None:
    missing = (
        '<inputs><param name="s" type="select">'
        "<option>A</option></param></inputs>"
    )
    assert "GTR059" in _codes(_tool(inputs=missing))
    ok = (
        '<inputs><param name="s" type="select">'
        '<option value="a">A</option></param></inputs>'
    )
    assert "GTR059" not in _codes(_tool(inputs=ok))


def test_gtr060_select_options_distinct() -> None:
    dup_value = (
        '<inputs><param name="s" type="select">'
        '<option value="a">A</option><option value="a">B</option></param></inputs>'
    )
    assert "GTR060" in _codes(_tool(inputs=dup_value))
    dup_text = (
        '<inputs><param name="s" type="select">'
        '<option value="a">Same</option><option value="b">Same</option>'
        "</param></inputs>"
    )
    assert "GTR060" in _codes(_tool(inputs=dup_text))
    distinct = (
        '<inputs><param name="s" type="select">'
        '<option value="a">A</option><option value="b">B</option></param></inputs>'
    )
    assert "GTR060" not in _codes(_tool(inputs=distinct))


def test_gtr061_select_options_single() -> None:
    two = (
        '<inputs><param name="s" type="select">'
        '<options from_data_table="t"/><options from_data_table="u"/>'
        "</param></inputs>"
    )
    assert "GTR061" in _codes(_tool(inputs=two))
    one = (
        '<inputs><param name="s" type="select">'
        '<options from_data_table="t"/></param></inputs>'
    )
    assert "GTR061" not in _codes(_tool(inputs=one))


def test_gtr062_select_options_have_source() -> None:
    empty = '<inputs><param name="s" type="select"><options/></param></inputs>'
    assert "GTR062" in _codes(_tool(inputs=empty))
    sourced = (
        '<inputs><param name="s" type="select">'
        '<options from_data_table="t"/></param></inputs>'
    )
    assert "GTR062" not in _codes(_tool(inputs=sourced))
    # a filter that adds values counts as a source
    add_filter = (
        '<inputs><param name="s" type="select"><options>'
        '<filter type="add_value" value="x"/></options></param></inputs>'
    )
    assert "GTR062" not in _codes(_tool(inputs=add_filter))
    # a macro <expand> in <options> may inject the source -> skip
    macro = (
        '<inputs><param name="s" type="select"><options>'
        '<expand macro="opt_source"/></options></param></inputs>'
    )
    assert "GTR062" not in _codes(_tool(inputs=macro))


def test_gtr063_select_options_source_coherent() -> None:
    both = (
        '<inputs><param name="s" type="select">'
        '<options from_dataset="d" from_data_table="t"/></param></inputs>'
    )
    assert "GTR063" in _codes(_tool(inputs=both))
    meta_no_dataset = (
        '<inputs><param name="s" type="select">'
        '<options from_data_table="t" meta_file_key="k"/></param></inputs>'
    )
    assert "GTR063" in _codes(_tool(inputs=meta_no_dataset))
    ok = (
        '<inputs><param name="s" type="select">'
        '<options from_dataset="d" meta_file_key="k"/></param></inputs>'
    )
    assert "GTR063" not in _codes(_tool(inputs=ok))


def test_gtr064_select_options_not_deprecated() -> None:
    dyn = '<inputs><param name="s" type="select" dynamic_options="f()"/></inputs>'
    assert "GTR064" in _codes(_tool(inputs=dyn))
    dep_attr = (
        '<inputs><param name="s" type="select">'
        '<options from_file="f.txt"/></param></inputs>'
    )
    assert "GTR064" in _codes(_tool(inputs=dep_attr))
    ok = (
        '<inputs><param name="s" type="select">'
        '<options from_data_table="t"/></param></inputs>'
    )
    assert "GTR064" not in _codes(_tool(inputs=ok))


def test_gtr065_validator_type_compatible() -> None:
    # regex validator is incompatible with an integer param type
    bad_type = (
        '<inputs><param name="x" type="integer" value="1">'
        "<validator type=\"regex\">.*</validator></param></inputs>"
    )
    assert "GTR065" in _codes(_tool(inputs=bad_type))
    # 'min' attribute is incompatible with a regex validator
    bad_attr = (
        '<inputs><param name="x" type="text">'
        '<validator type="regex" min="1">.*</validator></param></inputs>'
    )
    assert "GTR065" in _codes(_tool(inputs=bad_attr))
    ok = (
        '<inputs><param name="x" type="integer" value="1">'
        '<validator type="in_range" min="0"/></param></inputs>'
    )
    assert "GTR065" not in _codes(_tool(inputs=ok))


def test_gtr066_validator_text_presence() -> None:
    # a regex validator needs text
    no_text = (
        '<inputs><param name="x" type="text">'
        '<validator type="regex"/></param></inputs>'
    )
    assert "GTR066" in _codes(_tool(inputs=no_text))
    # a non-expression validator should not carry text
    has_text = (
        '<inputs><param name="x" type="data" format="txt">'
        '<validator type="metadata" check="x">stray</validator></param></inputs>'
    )
    assert "GTR066" in _codes(_tool(inputs=has_text))
    ok = (
        '<inputs><param name="x" type="text">'
        "<validator type=\"regex\">.*</validator></param></inputs>"
    )
    assert "GTR066" not in _codes(_tool(inputs=ok))


def test_gtr067_validator_expression_valid() -> None:
    bad = (
        '<inputs><param name="x" type="text">'
        '<validator type="regex">[</validator></param></inputs>'
    )
    assert "GTR067" in _codes(_tool(inputs=bad))
    ok = (
        '<inputs><param name="x" type="text">'
        '<validator type="regex">ab+c</validator></param></inputs>'
    )
    assert "GTR067" not in _codes(_tool(inputs=ok))
    # a macro-token validator body is skipped (raw-tree boundary)
    macro = (
        '<inputs><param name="x" type="text">'
        '<validator type="regex">@PATTERN@</validator></param></inputs>'
    )
    assert "GTR067" not in _codes(_tool(inputs=macro))


def test_gtr068_validator_required_attributes() -> None:
    no_range = (
        '<inputs><param name="x" type="integer" value="1">'
        '<validator type="in_range"/></param></inputs>'
    )
    assert "GTR068" in _codes(_tool(inputs=no_range))
    with_min = (
        '<inputs><param name="x" type="integer" value="1">'
        '<validator type="in_range" min="0"/></param></inputs>'
    )
    assert "GTR068" not in _codes(_tool(inputs=with_min))
    no_check = (
        '<inputs><param name="x" type="data" format="txt">'
        '<validator type="metadata"/></param></inputs>'
    )
    assert "GTR068" in _codes(_tool(inputs=no_check))
    no_table = (
        '<inputs><param name="x" type="text">'
        '<validator type="value_in_data_table"/></param></inputs>'
    )
    assert "GTR068" in _codes(_tool(inputs=no_table))
    # dataset_metadata_equal needs (value|value_json) AND metadata_name
    meta_equal_missing = (
        '<inputs><param name="x" type="data" format="txt">'
        '<validator type="dataset_metadata_equal"/></param></inputs>'
    )
    assert "GTR068" in _codes(_tool(inputs=meta_equal_missing))
    # ...and must not set both value and value_json
    meta_equal_both = (
        '<inputs><param name="x" type="data" format="txt">'
        '<validator type="dataset_metadata_equal" value="a" value_json="b"'
        ' metadata_name="m"/></param></inputs>'
    )
    assert "GTR068" in _codes(_tool(inputs=meta_equal_both))
    meta_equal_ok = (
        '<inputs><param name="x" type="data" format="txt">'
        '<validator type="dataset_metadata_equal" value="a" metadata_name="m"/>'
        "</param></inputs>"
    )
    assert "GTR068" not in _codes(_tool(inputs=meta_equal_ok))


def test_gtr069_conditional_test_param_type() -> None:
    text_first = (
        '<inputs><conditional name="c">'
        '<param name="p" type="text"/></conditional></inputs>'
    )
    assert "GTR069" in _codes(_tool(inputs=text_first))  # must be select/boolean
    boolean_first = (
        '<inputs><conditional name="c"><param name="p" type="boolean"/>'
        '<when value="true"/><when value="false"/></conditional></inputs>'
    )
    assert "GTR069" in _codes(_tool(inputs=boolean_first))  # boolean discouraged
    select_first = (
        '<inputs><conditional name="c">'
        '<param name="p" type="select"><option value="a">A</option></param>'
        '<when value="a"/></conditional></inputs>'
    )
    assert "GTR069" not in _codes(_tool(inputs=select_first))


def test_gtr070_conditional_test_param_attributes() -> None:
    optional = (
        '<inputs><conditional name="c">'
        '<param name="p" type="select" optional="true">'
        '<option value="a">A</option></param>'
        '<when value="a"/></conditional></inputs>'
    )
    assert "GTR070" in _codes(_tool(inputs=optional))
    assert "GTR070" not in _codes(_tool(inputs=(
        '<inputs><conditional name="c">'
        '<param name="p" type="select"><option value="a">A</option></param>'
        '<when value="a"/></conditional></inputs>'
    )))


def test_gtr071_conditional_whens_match_options() -> None:
    missing_when = (
        '<inputs><conditional name="c"><param name="p" type="select">'
        '<option value="a">A</option><option value="b">B</option></param>'
        '<when value="a"/></conditional></inputs>'
    )
    assert "GTR071" in _codes(_tool(inputs=missing_when))  # option 'b' has no when
    matched = (
        '<inputs><conditional name="c"><param name="p" type="select">'
        '<option value="a">A</option><option value="b">B</option></param>'
        '<when value="a"/><when value="b"/></conditional></inputs>'
    )
    assert "GTR071" not in _codes(_tool(inputs=matched))
    # a macro <expand> may supply the whens/options -> skip (raw-tree boundary)
    macro = (
        '<inputs><conditional name="c"><param name="p" type="select">'
        '<option value="a">A</option></param>'
        '<expand macro="whens"/></conditional></inputs>'
    )
    assert "GTR071" not in _codes(_tool(inputs=macro))


def test_gtr072_inputs_present() -> None:
    assert "GTR072" in _codes(_tool(inputs="<inputs></inputs>"))  # no params
    assert "GTR072" not in _codes(_tool())  # default has a param
    # a macro <expand> may inject the params -> skip (raw-tree boundary)
    macro = "<inputs><expand macro=\"params\"/></inputs>"
    assert "GTR072" not in _codes(_tool(inputs=macro))


def test_gtr073_param_type_child_combination() -> None:
    # <options> is only valid for data/select/drill_down params
    bad = (
        '<inputs><param name="x" type="integer" value="1">'
        '<options from_data_table="t"/></param></inputs>'
    )
    assert "GTR073" in _codes(_tool(inputs=bad))
    # a select with <options> is fine
    ok = (
        '<inputs><param name="x" type="select">'
        '<options from_data_table="t"/></param></inputs>'
    )
    assert "GTR073" not in _codes(_tool(inputs=ok))


def test_gtr074_data_options_valid() -> None:
    multiple = (
        '<inputs><param name="x" type="data" format="txt">'
        '<options><filter type="data_meta" key="dbkey" ref="r"/></options>'
        '<options><filter type="data_meta" key="dbkey" ref="r"/></options>'
        "</param></inputs>"
    )
    assert "GTR074" in _codes(_tool(inputs=multiple))  # multiple <options>
    bad_attr = (
        '<inputs><param name="x" type="data" format="txt">'
        '<options from_data_table="t"/></param></inputs>'
    )
    assert "GTR074" in _codes(_tool(inputs=bad_attr))  # invalid options attribute
    bad_filter = (
        '<inputs><param name="x" type="data" format="txt">'
        '<options><filter type="static_value" column="1" value="x"/></options>'
        "</param></inputs>"
    )
    assert "GTR074" in _codes(_tool(inputs=bad_filter))  # not dbkey/data_meta, no ref
    ok = (
        '<inputs><param name="x" type="data" format="txt">'
        '<options><filter type="data_meta" key="dbkey" ref="r"/></options>'
        "</param></inputs>"
    )
    assert "GTR074" not in _codes(_tool(inputs=ok))


def test_gtr075_boolean_values_distinct() -> None:
    same = (
        '<inputs><param name="b" type="boolean" '
        'truevalue="x" falsevalue="x"/></inputs>'
    )
    assert "GTR075" in _codes(_tool(inputs=same))  # identical true/false values
    swapped = (
        '<inputs><param name="b" type="boolean" truevalue="false"/></inputs>'
    )
    assert "GTR075" in _codes(_tool(inputs=swapped))  # truevalue looks false
    ok = (
        '<inputs><param name="b" type="boolean" '
        'truevalue="--flag" falsevalue=""/></inputs>'
    )
    assert "GTR075" not in _codes(_tool(inputs=ok))


def test_gtr076_select_display_consistent() -> None:
    checkboxes_single = (
        '<inputs><param name="s" type="select" display="checkboxes">'
        '<option value="a">A</option></param></inputs>'
    )
    assert "GTR076" in _codes(_tool(inputs=checkboxes_single))  # not multiple
    radio_multiple = (
        '<inputs><param name="s" type="select" display="radio" multiple="true">'
        '<option value="a">A</option></param></inputs>'
    )
    assert "GTR076" in _codes(_tool(inputs=radio_multiple))
    checkboxes_ok = (
        '<inputs><param name="s" type="select" display="checkboxes" multiple="true">'
        '<option value="a">A</option></param></inputs>'
    )
    assert "GTR076" not in _codes(_tool(inputs=checkboxes_ok))
    radio_ok = (
        '<inputs><param name="s" type="select" display="radio">'
        '<option value="a">A</option></param></inputs>'
    )
    assert "GTR076" not in _codes(_tool(inputs=radio_ok))


def test_gtr077_option_filter_attributes() -> None:
    missing_required = (
        '<inputs><param name="s" type="select"><options from_data_table="t">'
        '<filter type="data_meta" ref="r"/></options></param></inputs>'
    )
    assert "GTR077" in _codes(_tool(inputs=missing_required))  # data_meta needs key
    remove_value_bad = (
        '<inputs><param name="s" type="select"><options from_data_table="t">'
        '<filter type="remove_value" value="x" ref="y"/></options></param></inputs>'
    )
    assert "GTR077" in _codes(_tool(inputs=remove_value_bad))  # value AND ref
    ok = (
        '<inputs><param name="s" type="select"><options from_data_table="t">'
        '<filter type="data_meta" ref="r" key="dbkey"/></options></param></inputs>'
    )
    assert "GTR077" not in _codes(_tool(inputs=ok))


def test_gtr078_option_filter_expression() -> None:
    bad = (
        '<inputs><param name="s" type="select"><options from_data_table="t">'
        '<filter type="regexp" column="1" value="["/></options></param></inputs>'
    )
    assert "GTR078" in _codes(_tool(inputs=bad))
    good = (
        '<inputs><param name="s" type="select"><options from_data_table="t">'
        '<filter type="regexp" column="1" value="ab+"/></options></param></inputs>'
    )
    assert "GTR078" not in _codes(_tool(inputs=good))


def test_gtr079_option_filter_references() -> None:
    ghost = (
        '<inputs><param name="s" type="select"><options from_data_table="t">'
        '<filter type="data_meta" ref="ghost" key="dbkey"/></options></param></inputs>'
    )
    assert "GTR079" in _codes(_tool(inputs=ghost))  # ref to a non-existent param
    resolved = (
        '<inputs><param name="d" type="data" format="txt"/>'
        '<param name="s" type="select"><options from_data_table="t">'
        '<filter type="data_meta" ref="d" key="dbkey"/></options></param></inputs>'
    )
    assert "GTR079" not in _codes(_tool(inputs=resolved))


def test_gtr080_test_assertions_well_formed() -> None:
    two_stdout = (
        "<tests><test><assert_stdout><has_line line=\"a\"/></assert_stdout>"
        "<assert_stdout><has_line line=\"b\"/></assert_stdout></test></tests>"
    )
    assert "GTR080" in _codes(_tool(tests=two_stdout))  # >1 assert_stdout
    no_quant = (
        "<tests><test><assert_stdout><has_n_lines/></assert_stdout></test></tests>"
    )
    assert "GTR080" in _codes(_tool(tests=no_quant))  # has_n_lines needs n/min/max
    size_both = (
        '<tests><test><output name="out"><assert_contents>'
        '<has_size value="5" size="5"/></assert_contents></output></test></tests>'
    )
    assert "GTR080" in _codes(_tool(tests=size_both))  # value and size
    ok = (
        '<tests><test><output name="out"><assert_contents>'
        '<has_size value="5"/></assert_contents></output></test></tests>'
    )
    assert "GTR080" not in _codes(_tool(tests=ok))
    assert "GTR080" not in _codes(_tool())  # default test has no assertions


def test_gtr081_test_output_compare_attributes() -> None:
    bad = (
        '<tests><test><output name="out" sort="true" compare="contains"/>'
        "</test></tests>"
    )
    assert "GTR081" in _codes(_tool(tests=bad))  # sort needs diff/re_match
    ok = '<tests><test><output name="out" sort="true"/></test></tests>'
    assert "GTR081" not in _codes(_tool(tests=ok))  # compare defaults to diff


def test_gtr082_test_output_named() -> None:
    no_name = "<tests><test><output/></test></tests>"
    assert "GTR082" in _codes(_tool(tests=no_name))
    named = '<tests><test><output name="out"/></test></tests>'
    assert "GTR082" not in _codes(_tool(tests=named))


def test_gtr083_test_outputs_correspond() -> None:
    ghost = '<tests><test><output name="ghost"/></test></tests>'
    assert "GTR083" in _codes(_tool(tests=ghost))  # not a declared output
    # a test <output> referencing a <collection> output is the wrong kind
    mismatch = _tool(
        outputs='<outputs><collection name="c" type="list"/></outputs>',
        tests='<tests><test><output name="c"/></test></tests>',
    )
    assert "GTR083" in _codes(mismatch)
    ok = '<tests><test><output name="out"/></test></tests>'
    assert "GTR083" not in _codes(_tool(tests=ok))  # 'out' is a <data> output


def test_gtr084_test_discovered_outputs_checked() -> None:
    discover = "<discover_datasets pattern=\"__name__\"/>"
    data_unchecked = _tool(
        outputs=f'<outputs><data name="out" format="txt">{discover}</data></outputs>',
        tests='<tests><test><output name="out"/></test></tests>',
    )
    assert "GTR084" in _codes(data_unchecked)  # discovers datasets, not asserted
    data_checked = _tool(
        outputs=f'<outputs><data name="out" format="txt">{discover}</data></outputs>',
        tests='<tests><test><output name="out" count="1"/></test></tests>',
    )
    assert "GTR084" not in _codes(data_checked)
    coll_unchecked = _tool(
        outputs=(
            f'<outputs><collection name="c" type="list">{discover}'
            "</collection></outputs>"
        ),
        tests='<tests><test><output_collection name="c"/></test></tests>',
    )
    assert "GTR084" in _codes(coll_unchecked)  # collection discovers, not asserted
    # a plain output without discover_datasets is never required to assert counts
    assert "GTR084" not in _codes(
        _tool(tests='<tests><test><output name="out" count="1"/></test></tests>')
    )


def test_gtr085_test_params_in_inputs() -> None:
    ghost = (
        '<tests><test expect_num_outputs="1">'
        '<param name="nope" value="x"/></test></tests>'
    )
    assert "GTR085" in _codes(_tool(tests=ghost))  # 'nope' is not an input
    # the default input is named 'input'; a test param matching it is fine
    ok = (
        '<tests><test expect_num_outputs="1">'
        '<param name="input" value="x"/></test></tests>'
    )
    assert "GTR085" not in _codes(_tool(tests=ok))
    # a test param matching an input's argument (dash/underscore variants) resolves
    arg_inputs = '<inputs><param argument="--my-flag" type="text"/></inputs>'
    arg_test = (
        '<tests><test expect_num_outputs="1">'
        '<param name="my_flag" value="x"/></test></tests>'
    )
    assert "GTR085" not in _codes(_tool(inputs=arg_inputs, tests=arg_test))


def test_gtr086_test_expect_failure_coherent() -> None:
    with_output = (
        '<tests><test expect_failure="true">'
        '<output name="out"/></test></tests>'
    )
    assert "GTR086" in _codes(_tool(tests=with_output))  # failure test w/ output
    with_num = '<tests><test expect_failure="true" expect_num_outputs="1"/></tests>'
    assert "GTR086" in _codes(_tool(tests=with_num))  # failure test w/ expect_num
    ok = '<tests><test expect_failure="true"/></tests>'
    assert "GTR086" not in _codes(_tool(tests=ok))


def test_gtr087_test_expect_num_outputs() -> None:
    filtered_outputs = (
        '<outputs><data name="out" format="txt">'
        "<filter>x</filter></data></outputs>"
    )
    filtered = _tool(
        outputs=filtered_outputs,
        tests='<tests><test><param name="input" value="x"/></test></tests>',
    )
    assert "GTR087" in _codes(filtered)  # filtered output, no expect_num_outputs
    ok = _tool(
        outputs=filtered_outputs,
        tests=(
            '<tests><test expect_num_outputs="1">'
            '<param name="input" value="x"/></test></tests>'
        ),
    )
    assert "GTR087" not in _codes(ok)


def test_gtr088_test_has_expectations() -> None:
    empty = '<tests><test><param name="input" value="x"/></test></tests>'
    assert "GTR088" in _codes(_tool(tests=empty))  # asserts nothing
    assert "GTR088" not in _codes(_tool())  # default sets expect_num_outputs


def test_gtr089_help_rst_valid() -> None:
    bad = "<help><![CDATA[See `missing`_ for details.]]></help>"
    assert "GTR089" in _codes(_tool(help_=bad))  # undefined RST reference target
    assert "GTR089" not in _codes(_tool())  # default help is valid RST
    # markdown help is not RST and is skipped even if it isn't valid RST
    markdown = '<help format="markdown"><![CDATA[See `missing`_]]></help>'
    assert "GTR089" not in _codes(_tool(help_=markdown))


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
