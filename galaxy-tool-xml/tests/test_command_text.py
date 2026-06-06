"""Tests for the read-only command-text lexer (GTR020.2 substrate)."""

from __future__ import annotations

import pytest

from galaxy_tool_xml.cheetah_cdm import cheetah_cdm_available
from galaxy_tool_xml.command_text import unquoted_cheetah_vars

requires_cdm = pytest.mark.skipif(
    not cheetah_cdm_available(), reason="needs the cheetah-cdm extra (CT3)"
)


def _names(text: str) -> list[str]:
    return [var.name for var in unquoted_cheetah_vars(text)]


@requires_cdm
def test_faithful_lexer_excludes_non_placeholder_dollar_runs() -> None:
    # When the faithful CT3 lexer is available it narrows away $-runs the regex
    # scanner wrongly treats as shell vars: a $var inside a #raw block, inside a
    # #* … *# block comment, and an escaped \$ are all NOT genuine placeholders.
    assert _names("#raw\n$x\n#end raw\nrun $real") == ["$real"]
    assert _names("echo $a #* $b *#") == ["$a"]
    assert _names("run \\$x $real") == ["$real"]


@requires_cdm
def test_faithful_lexer_keeps_genuine_placeholders() -> None:
    # Genuine shell-argument placeholders survive the filter unchanged (offsets too).
    text = "samtools sort $input -o ${out.x}"
    vars_ = unquoted_cheetah_vars(text)
    assert [(v.name, v.start, v.end) for v in vars_] == [
        ("$input", 14, 20),
        ("${out.x}", 24, 32),
    ]


def test_flags_only_fully_unquoted_shell_vars() -> None:
    assert _names("samtools sort $input") == ["$input"]
    assert _names("samtools sort '$input'") == []  # single-quoted is correct
    assert _names('samtools sort "$input"') == []  # double-quoted: lesser concern
    assert _names("run ${x.y}") == ["${x.y}"]  # ${...} form
    # $1 / $(...) are not Cheetah vars.
    assert _names("echo $(date) $1") == []


def test_skips_cheetah_directive_lines() -> None:
    assert _names("#if $cond\nrun $real\n#end if") == ["$real"]
    assert _names("## $note\necho $x") == ["$x"]
    assert _names("#set $tmp = $other\nuse $tmp") == ["$tmp"]


def test_tracks_quotes_across_newlines() -> None:
    # A single-quoted span crossing a newline keeps $inside quoted; $after is bare.
    text = "echo 'a\n$inside\nb' $after"
    assert _names(text) == ["$after"]
    # A '#'-leading line INSIDE a quote is literal text, not a directive.
    text2 = "echo 'start\n#notadirective $x\nend' $y"
    assert _names(text2) == ["$y"]


def test_line_offsets_are_zero_based_newline_counts() -> None:
    text = "\nsamtools sort $input\nbwa $ref"
    vars_ = unquoted_cheetah_vars(text)
    assert [(v.name, v.line_offset) for v in vars_] == [
        ("$input", 1),
        ("$ref", 2),
    ]


def test_empty_and_directive_only() -> None:
    assert unquoted_cheetah_vars("") == []
    assert unquoted_cheetah_vars("#if $x\n#end if") == []


def test_spans_bound_exactly_the_reference() -> None:
    # start/end are absolute offsets into the scanned text; text[start:end] == name.
    text = "samtools sort $input -o ${out.x}"
    vars_ = unquoted_cheetah_vars(text)
    assert [(v.name, v.start, v.end) for v in vars_] == [
        ("$input", 14, 20),
        ("${out.x}", 24, 32),
    ]
    for var in vars_:
        assert text[var.start : var.end] == var.name
