"""Tests for ``DropRedundantParamName`` (GTR037).

When a `<param>` carries both ``argument`` and a ``name`` equal to the name Galaxy
*derives* from that argument (``argument.lstrip("-").replace("-", "_")`` —
``tool_util/parser/util.py:_parse_name``), the ``name`` is redundant: dropping it leaves
Galaxy computing the identical name, and ``param/@name`` is optional in every vendored
XSD that allows ``argument``, so validity is preserved too. Reimplements planemo's
`InputsNameRedundantArgument` linter (report-only) as a fixer.
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_codemod.codemods.drop_redundant_param_name import (
    DropRedundantParamName,
)
from galaxy_tool_codemod.parse import parse_module

_HEAD = b'<tool id="m" name="M" version="1.0.0" profile="21.09">'


def _tool(inputs: bytes) -> bytes:
    return _HEAD + b"<inputs>" + inputs + b"</inputs><outputs/></tool>"


def test_drops_name_equal_to_derived() -> None:
    module = parse_module(
        _tool(b'<param argument="--threads" name="threads" type="integer"/>')
    )
    changes = list(DropRedundantParamName().detect(module))
    assert len(changes) == 1 and changes[0].code == "GTR037"
    DropRedundantParamName().apply(module)
    param = module.document.root.find("inputs/param")
    assert param.get("name") is None and param.get("argument") == "--threads"


def test_drops_name_with_dash_to_underscore_derivation() -> None:
    module = parse_module(_tool(b'<param argument="--input-file" name="input_file"/>'))
    DropRedundantParamName().apply(module)
    assert module.document.root.find("inputs/param").get("name") is None


def test_keeps_name_that_differs_from_derived() -> None:
    # name carries information argument doesn't imply -> not redundant, keep it.
    module = parse_module(_tool(b'<param argument="--threads" name="num_threads"/>'))
    assert list(DropRedundantParamName().detect(module)) == []


def test_ignores_param_without_argument() -> None:
    module = parse_module(_tool(b'<param name="threads" type="integer"/>'))
    assert list(DropRedundantParamName().detect(module)) == []


def test_handles_nested_param_under_conditional() -> None:
    module = parse_module(
        _tool(
            b'<conditional name="c"><param name="sel" type="select"/>'
            b'<when value="x"><param argument="--threads" name="threads"/></when>'
            b"</conditional>"
        )
    )
    DropRedundantParamName().apply(module)
    nested = module.document.root.find("inputs/conditional/when/param")
    assert nested.get("name") is None


def test_does_not_touch_test_param() -> None:
    # a <test><param> is matched by name (not argument-derived) — never drop.
    module = parse_module(
        _HEAD + b'<inputs><param argument="--threads" name="threads"/></inputs>'
        b"<outputs/><tests><test>"
        b'<param name="threads" argument="--threads" value="4"/>'
        b"</test></tests></tool>"
    )
    DropRedundantParamName().apply(module)
    test_param = module.document.root.find("tests/test/param")
    assert test_param.get("name") == "threads"  # test param untouched


def test_is_idempotent() -> None:
    module = parse_module(_tool(b'<param argument="--threads" name="threads"/>'))
    DropRedundantParamName().apply(module)
    once = etree.tostring(module.document.root)
    DropRedundantParamName().apply(module)
    assert etree.tostring(module.document.root) == once
