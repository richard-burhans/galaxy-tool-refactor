"""Tests for the faithful Cheetah lexer (CT3, a base dependency).

Exercises ``cheetah_spans`` — the disjoint, ordered placeholder / directive / comment
span model harvested by the CT3 ``Parser`` subclass — covering round-trip fidelity,
the ``##`` / ``#raw`` / escaped-``\\$`` constructs it must *not* mistake for live
references, the directive heads that swallow their own ``$vars``, and the bail-to-None
contract on a parse failure or an absent extra. Skipped wholesale when CT3 is not
installed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("Cheetah")

from galaxy_tool_xml.cheetah_cdm import (  # noqa: E402
    CheetahSpan,
    SpanKind,
    cheetah_cdm_available,
    cheetah_spans,
)


def _reserialize(text: str, spans: list[CheetahSpan]) -> str:
    """Reconstruct *text* from the literal gaps between *spans* and each span's text."""
    out: list[str] = []
    cursor = 0
    for span in spans:
        out.append(text[cursor : span.start])  # literal gap
        out.append(span.text)
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out)


def test_cheetah_cdm_available() -> None:
    # The importorskip above guarantees CT3 is present in this run.
    assert cheetah_cdm_available() is True


def test_plain_vars_are_placeholders() -> None:
    text = "samtools sort $input -o ${out.bam}"
    spans = cheetah_spans(text)
    assert spans is not None
    assert [(s.kind, s.text) for s in spans] == [
        (SpanKind.PLACEHOLDER, "$input"),
        (SpanKind.PLACEHOLDER, "${out.bam}"),
    ]
    # Offsets are exact slices.
    assert all(text[s.start : s.end] == s.text for s in spans)


@pytest.mark.parametrize(
    "text",
    [
        "samtools sort $input -o ${out.bam}",
        "#if $paired\n  bwa mem '$ref' $reads\n#end if",
        "## $note is a comment\necho $real",
        "#raw\n$notavar #notadirective\n#end raw\necho $x",
        "echo \\$HOME and $realvar",
        "#set $tmp = $base\n#for $f in $files\n  cat $f >> $tmp\n#end for",
    ],
)
def test_round_trip_fidelity(text: str) -> None:
    spans = cheetah_spans(text)
    assert spans is not None
    # Disjoint and ordered.
    for earlier, later in zip(spans, spans[1:], strict=False):
        assert earlier.end <= later.start
    # Every span is an exact source slice, and the gaps + spans reproduce the input.
    assert all(text[s.start : s.end] == s.text for s in spans)
    assert _reserialize(text, spans) == text


def test_comment_hides_dollar_var() -> None:
    spans = cheetah_spans("## $note is a comment\necho $real")
    assert spans is not None
    # The $note lives inside a comment span; only $real is a live placeholder.
    assert [(s.kind, s.text) for s in spans] == [
        (SpanKind.COMMENT, "## $note is a comment\n"),
        (SpanKind.PLACEHOLDER, "$real"),
    ]


def test_raw_block_hides_constructs() -> None:
    spans = cheetah_spans("#raw\n$notavar #notadirective\n#end raw\necho $x")
    assert spans is not None
    placeholders = [s.text for s in spans if s.kind is SpanKind.PLACEHOLDER]
    assert placeholders == ["$x"]  # $notavar inside #raw is not a reference
    assert any(s.kind is SpanKind.DIRECTIVE and s.directive == "raw" for s in spans)


def test_escaped_dollar_is_literal() -> None:
    spans = cheetah_spans("echo \\$HOME and $realvar")
    assert spans is not None
    assert [(s.kind, s.text) for s in spans] == [(SpanKind.PLACEHOLDER, "$realvar")]


def test_directive_head_swallows_its_vars() -> None:
    spans = cheetah_spans("#if $paired\n  bwa mem '$ref' $reads\n#end if")
    assert spans is not None
    # The #if head ($paired) is a directive span, not a standalone placeholder.
    placeholders = [s.text for s in spans if s.kind is SpanKind.PLACEHOLDER]
    assert placeholders == ["$ref", "$reads"]
    head = spans[0]
    assert head.kind is SpanKind.DIRECTIVE
    assert head.directive == "if"
    assert head.text == "#if $paired\n"
    # The closing tag is a directive named "end".
    assert spans[-1].kind is SpanKind.DIRECTIVE
    assert spans[-1].directive == "end"


def test_set_for_locals_are_directives() -> None:
    text = "#set $tmp = $base\n#for $f in $files\n  cat $f >> $tmp\n#end for"
    spans = cheetah_spans(text)
    assert spans is not None
    directives = [s.directive for s in spans if s.kind is SpanKind.DIRECTIVE]
    assert directives == ["set", "for", "end"]
    placeholders = [s.text for s in spans if s.kind is SpanKind.PLACEHOLDER]
    # Only the loop-body references are placeholders; #set/#for heads swallow theirs.
    assert placeholders == ["$f", "$tmp"]


def test_parse_failure_returns_none() -> None:
    # An unterminated #if cannot compile -> bail to None (caller falls back to regex).
    assert cheetah_spans("#if $x\n echo hi\n") is None


def test_unavailable_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    import galaxy_tool_xml.cheetah_cdm as cdm

    monkeypatch.setattr(cdm, "cheetah_cdm_available", lambda: False)
    assert cdm.cheetah_spans("echo $x") is None
