"""Tests for GTR102 — BooleanGatesOtherOptions."""

from __future__ import annotations

from galaxy_tool_source.binding import load_tool

from galaxy_tool_lint.checks.tool import BooleanGatesOtherOptions


def _detect(command: str, inputs: str) -> list:
    src = (
        '<tool id="t" name="T" version="1.0">'
        f"<command><![CDATA[{command}]]></command>"
        f"<inputs>{inputs}</inputs><outputs/></tool>"
    ).encode()
    document = load_tool(src)
    return list(BooleanGatesOtherOptions().detect(document))


_BOOL = '<param name="strict" type="boolean" truevalue="--s" falsevalue=""/>'


def test_meta() -> None:
    meta = BooleanGatesOtherOptions.meta
    assert meta.code == "GTR102"
    assert meta.detect_only is True
    assert meta.rulesets == frozenset({"strict"})
    assert meta.cite
    assert meta.planemo_linters == frozenset()  # our own IUC rule, no planemo alias


def test_flags_boolean_gating_another_param() -> None:
    violations = _detect(
        "prog\n#if $strict\n  --thr $threshold\n#end if\n",
        _BOOL + '<param name="threshold" type="integer" value="1"/>',
    )
    assert len(violations) == 1
    assert violations[0].code == "GTR102"
    assert "strict" in violations[0].message
    assert violations[0].xpath == "/tool/command"


def test_does_not_flag_constant_flag_block() -> None:
    # #if $bool: --flag (the legitimate idiom) is not the anti-pattern.
    assert _detect("prog\n#if $strict\n  --enable-strict\n#end if\n", _BOOL) == []


def test_does_not_flag_non_boolean_conditional() -> None:
    violations = _detect(
        "prog\n#if $mode == 'x'\n  --thr $threshold\n#end if\n",
        '<param name="mode" type="select"/><param name="threshold" type="integer"/>',
    )
    assert violations == []


def test_one_violation_per_boolean_param() -> None:
    # the same boolean gating two different params -> a single GTR102 finding.
    violations = _detect(
        "prog\n#if $strict\n  --a $alpha --b $beta\n#end if\n",
        _BOOL
        + '<param name="alpha" type="integer"/>'
        + '<param name="beta" type="integer"/>',
    )
    assert len(violations) == 1
