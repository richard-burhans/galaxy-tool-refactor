"""Tests for the vendored Galaxy tool-profile upgrade-code catalogue."""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_xml.binding import load_tool
from packaging.version import Version

from galaxy_tool_xml_codemod.profile_semantics import (
    _DETECTORS,
    PROFILE_UPGRADE_CODES,
    _command_text_is_single_simple_statement,
    detect_codes_on_root,
    upgrade_codes_applicable,
    upgrade_codes_crossed,
)


def _applies(xml: bytes, code: str, /) -> bool:
    """Whether *code*'s detector fires for the tool *xml* (full-span bump)."""
    document = load_tool(xml)
    applicable = upgrade_codes_applicable(
        document=document, from_profile="16.01", to_profile="26.1"
    )
    return code in {change.code for change in applicable}


def test_catalogue_shape() -> None:
    codes = [change.code for change in PROFILE_UPGRADE_CODES]
    assert len(codes) == len(set(codes))  # unique code names
    for change in PROFILE_UPGRADE_CODES:
        Version(change.profile)  # every profile is a valid version
        assert change.level in {"must_fix", "consider"}  # the `ready` note is omitted
    # Galaxy's `ready` note and the two changes it doesn't catalogue are absent.
    assert "16_04_ready_interpreter" not in codes
    profiles = {change.profile for change in PROFILE_UPGRADE_CODES}
    assert "19.05" not in profiles and "25.1" not in profiles


def test_crossed_is_open_below_closed_above() -> None:
    """from < profile <= to: the from-profile isn't re-crossed; the target is."""
    crossed = {
        c.code
        for c in upgrade_codes_crossed(from_profile="20.05", to_profile="20.09")
    }
    assert "20_09_consider_set_e" in crossed  # closed at the top
    assert "20_09_consider_output_collection_order" in crossed
    assert not any(c.startswith("20_05") for c in crossed)  # open at the bottom


def test_full_span_from_no_profile_baseline_crosses_all() -> None:
    """A 16.01 (no-profile) tool bumped to latest crosses every catalogued code."""
    crossed = upgrade_codes_crossed(from_profile="16.01", to_profile="26.1")
    assert len(crossed) == len(PROFILE_UPGRADE_CODES)
    codes = {c.code for c in crossed}
    assert {"16_04_exit_code", "20_09_consider_set_e"} <= codes
    assert "24_2_fix_test_case_validation" in codes


def test_no_change_when_not_upward() -> None:
    assert upgrade_codes_crossed(from_profile="24.2", to_profile="24.2") == []
    assert upgrade_codes_crossed(from_profile="26.0", to_profile="24.0") == []


def test_additive_only_span_crosses_nothing() -> None:
    """24.2 -> 25.0 has no catalogued code (25.0 is additive)."""
    assert upgrade_codes_crossed(from_profile="24.2", to_profile="25.0") == []


def test_unparseable_profile_yields_no_codes() -> None:
    """A macro-token profile can't be placed, so it crosses nothing (no false alarm)."""
    assert upgrade_codes_crossed(from_profile="@PROFILE@", to_profile="26.1") == []
    assert upgrade_codes_crossed(from_profile="16.01", to_profile="@TOKEN@") == []


# --- per-tool detection (upgrade_codes_applicable) ------------------------------

# A tool with none of the trip conditions — every predicate but the unconditional
# 16.04 collection note should stay silent for it.
_INERT_TOOL = (
    b'<tool id="t" name="T"><command strict="true" use_shared_home="true">'
    b"echo hi</command><stdio/></tool>"
)


def test_every_code_has_a_detector() -> None:
    """No catalogue code may fall through the applicability filter undetected."""
    assert set(_DETECTORS) == {change.code for change in PROFILE_UPGRADE_CODES}


def test_applicable_is_a_subset_of_crossed() -> None:
    document = load_tool(_INERT_TOOL)
    crossed = {
        c.code
        for c in upgrade_codes_crossed(from_profile="16.01", to_profile="26.1")
    }
    applicable = {
        c.code
        for c in upgrade_codes_applicable(
            document=document, from_profile="16.01", to_profile="26.1"
        )
    }
    assert applicable <= crossed


def test_inert_tool_trips_only_the_unconditional_code() -> None:
    """An inert tool applies just the always-on 16.04 extra-file-collection note."""
    document = load_tool(_INERT_TOOL)
    applicable = {
        c.code
        for c in upgrade_codes_applicable(
            document=document, from_profile="16.01", to_profile="26.1"
        )
    }
    assert applicable == {"16_04_consider_implicit_extra_file_collection"}


def test_applicable_respects_the_crossed_range() -> None:
    """A code only applies when its profile is actually crossed by the bump."""
    document = load_tool(
        b'<tool id="t" name="T" tool_type="data_source"><command>x</command></tool>'
    )
    # data_source trips 21_09 + 24_0 codes, but a bump that stops at 20.09 crosses
    # neither, so they must not appear.
    applicable = {
        c.code
        for c in upgrade_codes_applicable(
            document=document, from_profile="16.10", to_profile="20.09"
        )
    }
    assert not any(c.startswith(("21_09", "24_0")) for c in applicable)


def test_detects_output_format_input() -> None:
    trips = (
        b'<tool id="t" name="T"><outputs><data name="o" format="input"/>'
        b"</outputs></tool>"
    )
    misses = (
        b'<tool id="t" name="T"><outputs><data name="o" format="txt"/>'
        b"</outputs></tool>"
    )
    assert _applies(trips, "16_04_fix_output_format")
    assert not _applies(misses, "16_04_fix_output_format")


def test_detects_interpreter() -> None:
    trips = b'<tool id="t" name="T"><command interpreter="python">s.py</command></tool>'
    assert _applies(trips, "16_04_fix_interpreter")
    assert not _applies(_INERT_TOOL, "16_04_fix_interpreter")


def test_detects_exit_code_when_no_error_handling() -> None:
    bare = b'<tool id="t" name="T"><command>echo</command></tool>'
    has_stdio = b'<tool id="t" name="T"><command>echo</command><stdio/></tool>'
    detect_errs = (
        b'<tool id="t" name="T"><command detect_errors="exit_code">x</command></tool>'
    )
    assert _applies(bare, "16_04_exit_code")
    assert not _applies(has_stdio, "16_04_exit_code")
    assert not _applies(detect_errs, "16_04_exit_code")


def test_macro_supplied_stdio_does_not_over_flag_exit_code(tmp_path: Path) -> None:
    """Detection mirrors Galaxy's post-expansion view: a ``<stdio>`` reached only
    through an imported ``<expand macro="stdio"/>`` must NOT over-flag
    ``16_04_exit_code`` — even though it is absent from the raw tool tree."""
    (tmp_path / "macros.xml").write_text(
        '<macros><xml name="stdio">'
        '<stdio><exit_code range="1:" level="fatal"/></stdio></xml></macros>',
        encoding="utf-8",
    )
    (tmp_path / "tool.xml").write_text(
        '<tool id="t" name="T"><macros><import>macros.xml</import></macros>'
        '<command>echo</command><expand macro="stdio"/></tool>',
        encoding="utf-8",
    )
    document = load_tool(tmp_path / "tool.xml")
    applicable = {
        change.code
        for change in upgrade_codes_applicable(
            document=document, from_profile="16.01", to_profile="26.1"
        )
    }
    assert "16_04_exit_code" not in applicable  # macro-supplied <stdio> is seen
    # The raw tree alone would over-flag it — the bug this port fixes.
    assert "16_04_exit_code" in detect_codes_on_root(document.root)


def test_unresolvable_macro_falls_back_to_raw_detection() -> None:
    """When expansion can't run (unresolvable import, no source path), detection
    falls back to the raw tree — a conservative over-report, never silent."""
    xml = (
        b'<tool id="t" name="T"><macros><import>missing.xml</import></macros>'
        b"<command>echo</command></tool>"
    )
    assert _applies(xml, "16_04_exit_code")  # raw fallback still flags the no-stdio


def test_detects_tool_type_python_environment_codes() -> None:
    data_source = (
        b'<tool id="t" name="T" tool_type="data_source"><command>x</command></tool>'
    )
    assert _applies(data_source, "21_09_consider_python_environment")
    assert _applies(data_source, "24_0_request_cleaning")
    assert not _applies(data_source, "24_0_consider_python_environment")  # async only
    manage = (
        b'<tool id="t" name="T" tool_type="manage_data"><command>x</command></tool>'
    )
    assert _applies(manage, "18_09_consider_python_environment")
    assert not _applies(_INERT_TOOL, "21_09_consider_python_environment")


def test_detects_from_work_dir_whitespace() -> None:
    dirty = (
        b'<tool id="t" name="T"><outputs><data name="o" from_work_dir=" out.txt "/>'
        b"</outputs></tool>"
    )
    clean = (
        b'<tool id="t" name="T"><outputs><data name="o" from_work_dir="out.txt"/>'
        b"</outputs></tool>"
    )
    assert _applies(dirty, "21_09_fix_from_work_dir_whitespace")
    assert not _applies(clean, "21_09_fix_from_work_dir_whitespace")


def test_detects_optional_text_and_set_e() -> None:
    text_param = (
        b'<tool id="t" name="T"><command>x</command>'
        b'<inputs><param name="p" type="text"/></inputs></tool>'
    )
    assert _applies(text_param, "23_0_consider_optional_text")
    optional_text = (
        b'<tool id="t" name="T"><command>x</command>'
        b'<inputs><param name="p" type="text" optional="true"/></inputs></tool>'
    )
    assert not _applies(optional_text, "23_0_consider_optional_text")
    # set -e (20.09) only affects a SEQUENCE: a multi-statement command without
    # strict= applies; a single simple command is suppressed; strict= never trips
    # (codemod decisions §28).
    chained = b'<tool id="t" name="T"><command>a &amp;&amp; b</command></tool>'
    assert _applies(chained, "20_09_consider_set_e")
    single_cmd = b'<tool id="t" name="T"><command>x</command></tool>'
    assert not _applies(single_cmd, "20_09_consider_set_e")
    assert not _applies(_INERT_TOOL, "20_09_consider_set_e")


def _tool_with_command(body: bytes, /) -> bytes:
    return b'<tool id="t" name="T"><command><![CDATA[' + body + b"]]></command></tool>"


def test_set_e_tightening_suppresses_provably_single_commands() -> None:
    """The §28 tightening: a lone command can't be changed by set -e, so no note."""
    suppressed = (
        b"samtools sort in.bam",
        b"## go\nsamtools sort in.bam",  # comment line + one real statement
    )
    for body in suppressed:
        assert not _applies(_tool_with_command(body), "20_09_consider_set_e")
    kept = (
        b"a | b",  # pipeline
        b"a\nb",  # two statement lines
        b"#if $x\nrun\n#end if",  # Cheetah control flow can expand to many commands
    )
    for body in kept:
        assert _applies(_tool_with_command(body), "20_09_consider_set_e")


def test_24_2_is_a_necessary_condition_on_having_tests() -> None:
    """No port of Galaxy's test-case validator, so we approximate: no tests, no trip."""
    with_tests = (
        b'<tool id="t" name="T"><command>x</command>'
        b'<tests><test><param name="p" value="1"/></test></tests></tool>'
    )
    no_tests = b'<tool id="t" name="T"><command>x</command></tool>'
    assert _applies(with_tests, "24_2_fix_test_case_validation")
    assert not _applies(no_tests, "24_2_fix_test_case_validation")


def test_command_text_single_simple_statement_predicate() -> None:
    """The §28 set_e suppression predicate: pure string -> bool, conservative."""
    simple = _command_text_is_single_simple_statement
    # Provably single simple commands -> suppress (set -e can't change them).
    assert simple("samtools sort in.bam")
    assert simple("\n## comment\nsamtools sort in.bam\n")  # comment + 1 statement
    assert simple("samtools sort \\\n  -o out.bam in.bam")  # line-continuation
    # Anything that could sequence/expand to >1 command -> keep the note.
    for kept in (
        "a && b",
        "a ; b",
        "a | b",
        "a || b",
        "server &",
        "echo $(date)",
        "echo `date`",
        "cp a b\ncp c d",
        "#if $x\nrun a\n#end if",
        "#for $i in $r\nrun $i\n#end for",
    ):
        assert not simple(kept), kept
