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

from galaxy_tool_xml_codemod.codemods.replace_output_element import (
    ReplaceOutputElement,
)
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


def test_collection_with_collection_type_now_rewrites() -> None:
    # The C3 widening: with collection_type present the Galaxy remap is exact
    # (unicodify(None) -> None settled the absent-source corner) — see the
    # dedicated collection tests below.
    module = parse_module(
        _tool(b'<output type="collection" collection_type="list" name="c"/>')
    )
    assert len(list(ReplaceOutputElement().detect(module))) == 1


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


def test_collection_output_remapped_to_collection_element() -> None:
    # Galaxy's deprecated-path remap (parser/xml.py:548-563): type takes
    # collection_type's value, type_source takes collection_type_source's, then
    # the element parses as a <collection>. The rewrite mirrors it exactly.
    module = parse_module(
        b'<tool id="m" name="M" version="1.0"><outputs>'
        b'<output type="collection" name="o" collection_type="list"'
        b' collection_type_source="src" label="L">'
        b'<data name="el" format="txt"/></output>'
        b"</outputs></tool>"
    )
    changes = list(ReplaceOutputElement().detect(module))
    assert len(changes) == 1 and changes[0].code == "GTR036"
    ReplaceOutputElement().apply(module)
    collection = module.document.root.find("outputs/collection")
    assert collection is not None
    assert collection.get("type") == "list"
    assert collection.get("type_source") == "src"
    assert collection.get("collection_type") is None
    assert collection.get("collection_type_source") is None
    assert collection.get("label") == "L"  # untouched attrs ride along
    assert collection.find("data").get("name") == "el"  # children preserved
    assert module.document.root.find(".//output") is None


def test_collection_output_without_source_attr() -> None:
    # Absent collection_type_source: the deprecated path stores
    # unicodify(None) -> None, which reads identically to an absent attribute
    # in the <collection> path — so no type_source is created.
    module = parse_module(
        b'<tool id="m" name="M" version="1.0"><outputs>'
        b'<output type="collection" name="o" collection_type="paired"/>'
        b"</outputs></tool>"
    )
    ReplaceOutputElement().apply(module)
    collection = module.document.root.find("outputs/collection")
    assert collection.get("type") == "paired"
    assert "type_source" not in collection.attrib


def test_collection_output_missing_collection_type_left() -> None:
    # Degenerate: the deprecated path would set type=None (unicodify(None));
    # there is no provable rewrite — left for the advisory check.
    module = parse_module(
        b'<tool id="m" name="M" version="1.0"><outputs>'
        b'<output type="collection" name="o"/>'
        b"</outputs></tool>"
    )
    assert list(ReplaceOutputElement().detect(module)) == []
