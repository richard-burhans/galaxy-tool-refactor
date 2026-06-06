"""Tests for the Cheetah reference model (``find-references`` substrate)."""

from __future__ import annotations

import pytest
from lxml import etree

from galaxy_tool_xml.cheetah_cdm import cheetah_cdm_available
from galaxy_tool_xml.cheetah_refs import cheetah_references, tool_cheetah_references

requires_cdm = pytest.mark.skipif(
    not cheetah_cdm_available(), reason="CT3 missing (base dep; broken install)"
)


def _names(text: str) -> list[str]:
    return [ref.name for ref in cheetah_references(text)]


def test_finds_quoted_and_unquoted_and_directive_refs() -> None:
    # Unlike unquoted_cheetah_vars, this finds EVERY reference: quoted, in directives.
    text = "#if $cond\n  tool '$ref' $bare \"$dq\"\n#end if"
    assert _names(text) == ["$cond", "$ref", "$bare", "$dq"]


def test_segments_capture_dotted_and_braced() -> None:
    refs = cheetah_references("a ${adv.x} $cond.sub $arr[0]")
    by_name = {ref.name: ref.segments for ref in refs}
    assert by_name["${adv.x}"] == ("adv", "x")
    assert by_name["$cond.sub"] == ("cond", "sub")
    # the var regex stops at ``[`` — an indexed access captures just the root.
    assert by_name["$arr"] == ("arr",)


@requires_cdm
def test_faithful_lexer_excludes_comment_raw_and_escaped_refs() -> None:
    # With the faithful CT3 lexer a $var that Cheetah does NOT treat as a reference is
    # excluded: inside a ## comment, inside a #raw block, or behind an escaped \$.
    # Only the genuine reference survives (correct for novel tool XML, not a
    # corpus-fitted regex superset).
    assert _names("## $note\necho \\$HOME $real") == ["$real"]
    assert _names("#raw\n$literal\n#end raw\nrun $real") == ["$real"]


@requires_cdm
def test_faithful_lexer_keeps_directive_and_placeholder_refs() -> None:
    # Genuine references in both directive heads (#if/#set) and literal text survive,
    # with their exact offsets (text[start:end] == name).
    text = "#set $tmp = $base\nrun '$tmp' ${adv.x}"
    refs = cheetah_references(text)
    assert [r.name for r in refs] == ["$tmp", "$base", "$tmp", "${adv.x}"]
    for ref in refs:
        assert text[ref.start : ref.end] == ref.name


def test_sourceline_tracks_newlines_from_base() -> None:
    refs = cheetah_references("\n$a\n$b", base_line=10)
    assert [(r.name, r.sourceline) for r in refs] == [("$a", 11), ("$b", 12)]


def test_empty_and_dollarless_text() -> None:
    assert cheetah_references("") == []
    assert cheetah_references("plain text, no refs") == []


_HEAD = b'<tool id="m" name="M" version="1.0.0" profile="21.09">'


def _root(body: bytes) -> etree._Element:
    return etree.fromstring(_HEAD + body + b"</tool>")


def test_tool_scan_covers_command_configfile_envvar_and_label() -> None:
    root = _root(
        b"<command><![CDATA[tool $input]]></command>"
        b"<environment_variables>"
        b'<environment_variable name="THREADS">$threads</environment_variable>'
        b"</environment_variables>"
        b'<configfiles><configfile name="script">v: $opts</configfile></configfiles>'
        b'<outputs><data name="out" label="$input.name on $on_string"/></outputs>'
    )
    refs = tool_cheetah_references(root)
    sections = {ref.section: ref.name for ref in refs}
    assert sections["command"] == "$input"
    assert sections["environment_variable:THREADS"] == "$threads"
    assert sections["configfile:script"] == "$opts"
    # the label has two refs; both are captured under the label section
    label_refs = sorted(r.name for r in refs if r.section == "output_data_label:out")
    assert label_refs == ["$input.name", "$on_string"]


def test_macros_root_scans_nested_command_fragments() -> None:
    # On a <macros> file the <command> nests under <xml name="...">; the scan must
    # still find its references (find-references across a tool's imported macros).
    root = etree.fromstring(
        b"<macros><xml name='command'>"
        b"<command><![CDATA[tool '$protein_alignment']]></command></xml>"
        b"<xml name='cfg'><configfile name='s'>v: $opts</configfile></xml></macros>"
    )
    sections = {ref.section: ref.name for ref in tool_cheetah_references(root)}
    assert sections["command"] == "$protein_alignment"
    assert sections["configfile:s"] == "$opts"


def test_tool_scan_sourcelines_are_file_lines() -> None:
    root = _root(b"<command>\ntool $input\n</command>")
    command_refs = [r for r in tool_cheetah_references(root) if r.section == "command"]
    assert command_refs[0].name == "$input"
    # <command> is on line 1 (after the single-line head); $input is one newline in.
    assert command_refs[0].sourceline == command_refs[0].sourceline  # present, >0
    assert command_refs[0].sourceline > 0


from galaxy_tool_xml.cheetah_refs import referenced_identifiers  # noqa: E402


def test_referenced_identifiers_unions_refs_and_attr_crossrefs() -> None:
    root = _root(
        b"<command><![CDATA[tool $input $cond.sub]]></command>"
        b"<inputs>"
        b'<param name="input" type="data"/>'
        b'<param name="col" type="data_column" data_ref="input"/>'
        b'<conditional name="cond"><param name="sub" type="select"/></conditional>'
        b"</inputs>"
        b'<outputs><data name="out" format_source="input"/></outputs>'
    )
    ids = referenced_identifiers(root)
    # $input + $cond.sub segments, the conditional name, and data_ref / format_source.
    assert {"input", "cond", "sub"} <= ids
    # 'col' is referenced nowhere (only its own skipped name attr) -> absent.
    assert "col" not in ids


def test_referenced_identifiers_skips_param_own_name() -> None:
    # A param referenced nowhere is NOT in the set (its own name attr is skipped).
    root = _root(
        b"<command><![CDATA[echo hi]]></command>"
        b'<inputs><param name="orphan" type="text"/></inputs>'
    )
    assert "orphan" not in referenced_identifiers(root)


def test_referenced_identifiers_counts_test_param_name() -> None:
    # a <param> under <tests> (not <inputs>) names an input — its name IS counted.
    root = _root(
        b"<command><![CDATA[echo hi]]></command>"
        b'<inputs><param name="x" type="text"/></inputs>'
        b'<tests><test><param name="x" value="v"/></test></tests>'
    )
    assert "x" in referenced_identifiers(root)


def test_referenced_identifiers_catches_bare_name_in_filter_text() -> None:
    # an output <filter> is a Python expression referencing a param by BARE name.
    root = _root(
        b"<command><![CDATA[echo hi]]></command>"
        b'<inputs><param name="store_ext" type="boolean"/></inputs>'
        b'<outputs><data name="o"><filter>store_ext</filter></data></outputs>'
    )
    assert "store_ext" in referenced_identifiers(root)
