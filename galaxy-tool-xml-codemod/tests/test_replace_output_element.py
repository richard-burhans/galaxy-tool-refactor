"""Tests for ``ReplaceOutputElement`` (GTR036).

Replaces a deprecated ``<outputs><output type="data" …></outputs>`` with the modern
``<data …>`` — Galaxy parses ``<output type="data">`` identically to ``<data>``
(`tool_util/parser/xml.py`: an ``<output>`` with ``type="data"`` is routed to the same
``_parse`` as a ``<data>``), so the rename (dropping the now-redundant ``type``) is
behaviour-preserving. Reimplements planemo's `OutputsOutput` linter as a fixer.

Out of scope (left flagged, not rewritten): ``<output type="collection">`` (Galaxy
remaps ``collection_type``/``collection_type_source`` and fills a ``type_source`` via
``unicodify(None)`` when absent — pure equivalence is uncertain) and a ``<output>`` with
no ``type`` (an *expression* output, a different output kind). A ``<test><output>`` is a
test assertion, not an output definition — never touched (guarded on the parent tag).
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_xml_codemod.codemods.replace_output_element import ReplaceOutputElement
from galaxy_tool_xml_codemod.parse import parse_module

_HEAD = b'<tool id="m" name="M" version="1.0.0" profile="21.09">'


def _tool(outputs: bytes) -> bytes:
    return _HEAD + b"<inputs/><outputs>" + outputs + b"</outputs></tool>"


def test_replaces_output_type_data_with_data() -> None:
    module = parse_module(_tool(b'<output type="data" name="o" format="txt"/>'))
    changes = list(ReplaceOutputElement().detect(module))
    assert len(changes) == 1 and changes[0].code == "GTR036"
    ReplaceOutputElement().apply(module)
    data = module.document.root.find("outputs/data")
    assert data is not None
    assert data.get("name") == "o" and data.get("format") == "txt"
    assert data.get("type") is None  # the redundant type="data" is dropped
    assert module.document.root.find("outputs/output") is None


def test_skips_output_type_collection() -> None:
    # collection rewrite is deferred (Galaxy's collection_type/type_source remap +
    # unicodify(None) quirk make pure equivalence uncertain).
    module = parse_module(
        _tool(b'<output type="collection" collection_type="list" name="c"/>')
    )
    assert list(ReplaceOutputElement().detect(module)) == []


def test_skips_expression_output_without_type() -> None:
    # no type => an expression output, a different output kind — not a data rename.
    module = parse_module(_tool(b'<output name="o"/>'))
    assert list(ReplaceOutputElement().detect(module)) == []


def test_does_not_touch_test_output() -> None:
    # <output> under <test> is a test assertion, not an output definition.
    module = parse_module(
        _HEAD + b"<inputs/><outputs><data name=\"o\"/></outputs>"
        b'<tests><test><output name="o" file="exp.txt"/></test></tests></tool>'
    )
    assert list(ReplaceOutputElement().detect(module)) == []
    before = etree.tostring(module.document.root)
    ReplaceOutputElement().apply(module)
    assert etree.tostring(module.document.root) == before


def test_is_idempotent() -> None:
    module = parse_module(_tool(b'<output type="data" name="o"/>'))
    ReplaceOutputElement().apply(module)
    once = etree.tostring(module.document.root)
    ReplaceOutputElement().apply(module)
    assert etree.tostring(module.document.root) == once
