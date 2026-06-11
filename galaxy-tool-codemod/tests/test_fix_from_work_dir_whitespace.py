"""Tests for the ``FixFromWorkDirWhitespace`` runtime-gated fix (GTR014).

From profile 21.09 Galaxy quotes `from_work_dir` output filenames, so surrounding
whitespace becomes literal (Galaxy's `21_09_fix_from_work_dir_whitespace` must-fix
code). The fix strips it — a deterministic, XSD-valid correctness fix (it does not
change `newest_valid_profile`), so it is a runtime-gated fix applied by `upgrade`,
not a validity-gated `upgrade_vN`.
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_codemod.codemods.fix_from_work_dir_whitespace import (
    FixFromWorkDirWhitespace,
)
from galaxy_tool_codemod.parse import parse_module


def _tool(outputs: bytes) -> bytes:
    return (
        b'<tool id="m" name="M" version="1.0.0" profile="26.0">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b"<outputs>" + outputs + b"</outputs></tool>"
    )


def test_strips_surrounding_whitespace_and_detects_it() -> None:
    module = parse_module(_tool(b'<data name="o" from_work_dir=" out.txt "/>'))
    changes = list(FixFromWorkDirWhitespace().detect(module))
    assert len(changes) == 1
    assert changes[0].code == "GTR014"
    # detect did not mutate
    assert module.document.root.find("outputs/data").get("from_work_dir") == " out.txt "
    FixFromWorkDirWhitespace().apply(module)
    assert module.document.root.find("outputs/data").get("from_work_dir") == "out.txt"


def test_strips_data_nested_in_collection() -> None:
    module = parse_module(
        _tool(
            b'<collection name="c" type="list">'
            b'<data name="d" from_work_dir="out.txt&#10;"/>'
            b"</collection>"
        )
    )
    FixFromWorkDirWhitespace().apply(module)
    nested = module.document.root.find("outputs/collection/data")
    assert nested.get("from_work_dir") == "out.txt"


def test_noop_when_already_clean() -> None:
    module = parse_module(_tool(b'<data name="o" from_work_dir="out.txt"/>'))
    assert not list(FixFromWorkDirWhitespace().detect(module))
    before = etree.tostring(module.document.root)
    FixFromWorkDirWhitespace().apply(module)
    assert etree.tostring(module.document.root) == before


def test_noop_when_no_from_work_dir() -> None:
    module = parse_module(_tool(b'<data name="o" format="txt"/>'))
    before = etree.tostring(module.document.root)
    FixFromWorkDirWhitespace().apply(module)
    assert etree.tostring(module.document.root) == before


def test_is_idempotent() -> None:
    module = parse_module(_tool(b'<data name="o" from_work_dir=" out.txt "/>'))
    FixFromWorkDirWhitespace().apply(module)
    once = etree.tostring(module.document.root)
    FixFromWorkDirWhitespace().apply(module)
    assert etree.tostring(module.document.root) == once


def test_introduced_at_2109() -> None:
    assert FixFromWorkDirWhitespace.introduced_profile == "21.09"
