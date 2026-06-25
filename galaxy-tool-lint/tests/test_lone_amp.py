"""Tests for the lone-``&`` classifier (GTR032's engine).

Pure string-in / counts-out, so every case is a synthetic command body.
"""

from __future__ import annotations

from galaxy_tool_lint.lone_amp import classify_lone_amps


def test_each_class_is_tagged() -> None:
    # redirect (2>&1), pipe (|&), quoted (literal & in '...'), background
    # (trailing &), joining (a & b — the GTR032 anti-pattern).
    assert classify_lone_amps("prog in 2>&1")["redirect"] == 1
    assert classify_lone_amps("a |& b")["pipe"] == 1
    assert classify_lone_amps("sed 's/&/x/' in")["quoted"] == 1
    assert classify_lone_amps("sleep 5 &")["background"] == 1
    assert classify_lone_amps("a & b")["joining"] == 1


def test_double_amp_is_not_a_lone_amp() -> None:
    assert classify_lone_amps("a && b") == {}


def test_redirect_both_streams_to_file() -> None:
    # &> targets a filename word (prev not <>, nxt is >) -> redirect, not joining.
    assert classify_lone_amps("prog &> out.log")["redirect"] == 1
    assert classify_lone_amps("prog &> out.log")["joining"] == 0


# --- escape handling -------------------------------------------------------------


def test_escaped_double_quote_does_not_open_a_quote() -> None:
    # A backslash-escaped " outside single quotes is a literal char and must not
    # toggle double-quote state; the later & joins two commands -> joining, not
    # mis-tagged as quoted. (The pre-escape scan saw in_double=True here.)
    counts = classify_lone_amps(r'foo \" bar & baz')
    assert counts["joining"] == 1
    assert counts["quoted"] == 0


def test_escaped_ampersand_is_literal_not_joining() -> None:
    # sed's literal \& (the matched text) is an escaped char, not a shell &.
    counts = classify_lone_amps(r"sed s/\&/X/ infile")
    assert counts["joining"] == 0
    assert counts["quoted"] == 0


def test_backslash_inside_single_quotes_is_not_an_escape() -> None:
    # Bash treats backslash literally inside '...'; the closing quote still ends
    # the string, so the trailing & is an outside-quotes joining &.
    counts = classify_lone_amps(r"echo '\' & foo")
    assert counts["joining"] == 1
    assert counts["quoted"] == 0
