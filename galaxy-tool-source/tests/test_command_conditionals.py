"""Tests for command_conditionals.command_boolean_conditionals."""

from __future__ import annotations

from galaxy_tool_source.binding import load_tool
from galaxy_tool_source.command_conditionals import (
    CONSTANT_ONLY,
    GATES_OTHER_PARAMS,
    OTHER,
    command_boolean_conditionals,
)


def _tool(command: str, inputs: str) -> object:
    src = (
        '<tool id="t" name="T" version="1.0">'
        f"<command><![CDATA[{command}]]></command>"
        f"<inputs>{inputs}</inputs><outputs/></tool>"
    ).encode()
    return load_tool(src).root


_BOOL = '<param name="strict" type="boolean" truevalue="--s" falsevalue=""/>'


def test_gates_other_params() -> None:
    root = _tool(
        "prog\n#if $strict\n  --thr $threshold\n#end if\n",
        _BOOL + '<param name="threshold" type="integer" value="1"/>',
    )
    findings = command_boolean_conditionals(root)
    assert [(f.param, f.klass) for f in findings] == [("strict", GATES_OTHER_PARAMS)]


def test_constant_only() -> None:
    root = _tool("prog\n#if $strict\n  --enable-strict\n#end if\n", _BOOL)
    findings = command_boolean_conditionals(root)
    assert [(f.param, f.klass) for f in findings] == [("strict", CONSTANT_ONLY)]


def test_other_references_only_the_bool() -> None:
    root = _tool("prog\n#if $strict\n  --mode=$strict\n#end if\n", _BOOL)
    findings = command_boolean_conditionals(root)
    assert [f.klass for f in findings] == [OTHER]


def test_non_boolean_if_is_ignored() -> None:
    root = _tool(
        "prog\n#if $mode == 'x'\n  --thr $threshold\n#end if\n",
        '<param name="mode" type="select"/><param name="threshold" type="integer"/>',
    )
    assert command_boolean_conditionals(root) == []


def test_nested_ref_bubbles_to_enclosing_boolean_if() -> None:
    root = _tool(
        "prog\n#if $strict\n  #if $verbose\n    --thr $threshold\n  #end if\n#end if\n",
        _BOOL
        + '<param name="verbose" type="boolean" truevalue="-v" falsevalue=""/>'
        + '<param name="threshold" type="integer"/>',
    )
    findings = command_boolean_conditionals(root)
    # both booleans are gating $threshold (the inner directly, the outer transitively)
    assert {f.param for f in findings} == {"strict", "verbose"}
    assert all(f.klass == GATES_OTHER_PARAMS for f in findings)


def test_line_is_reported() -> None:
    root = _tool("prog\n#if $strict\n  --thr $threshold\n#end if\n", _BOOL)
    finding = command_boolean_conditionals(root)[0]
    assert finding.line > 0


def test_missing_or_mixed_content_command_is_empty() -> None:
    no_command = load_tool(
        b'<tool id="t" name="T" version="1.0"><inputs/><outputs/></tool>'
    ).root
    assert command_boolean_conditionals(no_command) == []


def test_no_boolean_param_is_empty() -> None:
    root = _tool(
        "prog\n#if $threshold\n  --x\n#end if\n",
        '<param name="threshold" type="integer"/>',
    )
    assert command_boolean_conditionals(root) == []
