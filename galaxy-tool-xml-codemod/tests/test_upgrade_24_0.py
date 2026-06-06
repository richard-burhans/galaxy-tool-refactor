"""Tests for the ``Upgrade24_0`` codemod (single-step 24.0 -> 24.1).

24.1 stopped allowing ``<filter>`` inside a ``<collection>``'s child
``<data>`` (only ``actions`` / ``change_format`` remain). When every child
``<data>`` of a collection carries the *same* filter, that is an all-or-nothing
condition on the whole collection, so ``Upgrade24_0`` hoists one filter to the
``<collection>`` level and drops the per-``<data>`` ones — semantics-preserving.
Mixed or partial per-element filters can't be hoisted, so they are left for the
discovery sweep to report. See ``docs/decisions.md`` §14.
"""

from __future__ import annotations

import pytest
from galaxy_tool_xml.binding import newest_valid_profile
from lxml import etree

from galaxy_tool_xml_codemod.codemods.upgrade_24_0 import Upgrade24_0
from galaxy_tool_xml_codemod.parse import parse_module


def _tool(outputs: bytes) -> bytes:
    return (
        b'<tool id="m" name="M" version="1.0.0" profile="24.0">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b"<outputs>" + outputs + b"</outputs></tool>"
    )


_STUCK = _tool(
    b'<collection name="c" type="paired">'
    b'<data name="forward" format="txt"><filter>cond</filter></data>'
    b'<data name="reverse" format="txt"><filter>cond</filter></data>'
    b"</collection>"
)


def test_hoists_identical_filters_and_unsticks() -> None:
    module = parse_module(_STUCK)
    Upgrade24_0().apply(module)
    collection = module.document.root.find("outputs/collection")
    assert collection is not None
    # one filter now lives on the collection; the children have none.
    coll_filters = collection.findall("filter")
    assert [f.text for f in coll_filters] == ["cond"]
    assert all(d.find("filter") is None for d in collection.findall("data"))
    assert newest_valid_profile(module.document) not in (None, "24.0")


@pytest.mark.xfail(
    strict=True,
    reason="behavior-preservation bug GTR009: the hoisted collection <filter> is built "
    "from Element.text, which stops at the first child node, so text after a comment "
    "is dropped; see docs/behavior_preservation.md. Fix: rebuild via itertext().",
)
def test_hoisted_filter_preserves_text_after_a_comment() -> None:
    # Per-child filters that read identically by .text but carry text after a comment
    # child get hoisted; the hoisted filter must preserve the FULL condition, not just
    # the run before the comment.
    module = parse_module(
        _tool(
            b'<collection name="c" type="list">'
            b'<data name="d1" format="txt">'
            b"<filter>cond_one <!-- x --> and cond_two</filter></data>"
            b'<data name="d2" format="txt">'
            b"<filter>cond_one <!-- y --> and cond_two</filter></data>"
            b"</collection>"
        )
    )
    Upgrade24_0().apply(module)
    hoisted = module.document.root.find("outputs/collection/filter")
    assert hoisted is not None
    assert "and cond_two" in "".join(hoisted.itertext())


def test_leaves_top_level_data_filters_untouched() -> None:
    # A <filter> on a top-level output <data> is still valid at 24.1 — untouched.
    module = parse_module(
        _tool(b'<data name="o" format="txt"><filter>keep</filter></data>')
    )
    before = etree.tostring(module.document.root)
    Upgrade24_0().apply(module)
    assert etree.tostring(module.document.root) == before


def test_skips_when_child_filters_differ() -> None:
    module = parse_module(
        _tool(
            b'<collection name="c" type="list">'
            b'<data name="a" format="txt"><filter>x</filter></data>'
            b'<data name="b" format="txt"><filter>y</filter></data>'
            b"</collection>"
        )
    )
    before = etree.tostring(module.document.root)
    Upgrade24_0().apply(module)
    assert etree.tostring(module.document.root) == before


def test_skips_when_not_all_children_filtered() -> None:
    module = parse_module(
        _tool(
            b'<collection name="c" type="list">'
            b'<data name="a" format="txt"><filter>x</filter></data>'
            b'<data name="b" format="txt"/>'
            b"</collection>"
        )
    )
    before = etree.tostring(module.document.root)
    Upgrade24_0().apply(module)
    assert etree.tostring(module.document.root) == before


def test_skips_when_collection_already_has_filter() -> None:
    module = parse_module(
        _tool(
            b'<collection name="c" type="paired">'
            b"<filter>own</filter>"
            b'<data name="forward" format="txt"><filter>cond</filter></data>'
            b'<data name="reverse" format="txt"><filter>cond</filter></data>'
            b"</collection>"
        )
    )
    before = etree.tostring(module.document.root)
    Upgrade24_0().apply(module)
    assert etree.tostring(module.document.root) == before


def test_handles_each_collection_independently() -> None:
    """Two collections in one tool: the hoistable one is hoisted, the mixed one left."""
    module = parse_module(
        _tool(
            b'<collection name="ok" type="paired">'
            b'<data name="forward" format="txt"><filter>cond</filter></data>'
            b'<data name="reverse" format="txt"><filter>cond</filter></data>'
            b"</collection>"
            b'<collection name="mixed" type="list">'
            b'<data name="a" format="txt"><filter>x</filter></data>'
            b'<data name="b" format="txt"><filter>y</filter></data>'
            b"</collection>"
        )
    )
    Upgrade24_0().apply(module)
    ok = module.document.root.find("outputs/collection[@name='ok']")
    mixed = module.document.root.find("outputs/collection[@name='mixed']")
    assert ok is not None and mixed is not None
    # hoistable collection: filter hoisted, children cleared
    assert [f.text for f in ok.findall("filter")] == ["cond"]
    assert all(d.find("filter") is None for d in ok.findall("data"))
    # mixed collection: untouched (per-element filters differ)
    assert mixed.find("filter") is None
    assert [d.find("filter").text for d in mixed.findall("data")] == ["x", "y"]


def test_is_idempotent() -> None:
    module = parse_module(_STUCK)
    Upgrade24_0().apply(module)
    once = etree.tostring(module.document.root)
    Upgrade24_0().apply(module)
    assert etree.tostring(module.document.root) == once
