"""Tests for the ``Upgrade19_01`` codemod (single-step 19.01 -> 19.05).

19.05 made ``name`` required on output ``<data>`` elements. ``Upgrade19_01``
synthesizes a deterministic, collision-free ``name`` (``output``, ``output2``,
…) on every unnamed output ``<data>``. These are unreferenced placeholder
identities — the corpus tools that need this never reference the output name in
their command or tests — so the synthesis breaks nothing and carries the tool to
the latest profile. See ``docs/decisions.md`` §14.
"""

from __future__ import annotations

from galaxy_tool_source.binding import newest_valid_profile
from lxml import etree

from galaxy_tool_codemod.codemods.upgrade_19_01 import Upgrade19_01
from galaxy_tool_codemod.parse import parse_module

_STUCK = (
    b'<tool id="m" name="M" version="1.0.0" profile="19.01">'
    b"<command><![CDATA[echo x]]></command><inputs/>"
    b'<outputs><data from_work_dir="out.txt" format="txt"/></outputs></tool>'
)


def test_synthesizes_name_and_unsticks() -> None:
    module = parse_module(_STUCK)
    Upgrade19_01().apply(module)
    data = module.document.root.find("outputs/data")
    assert data is not None
    assert data.get("name") == "output"
    # the from_work_dir it was derived alongside is untouched
    assert data.get("from_work_dir") == "out.txt"
    assert newest_valid_profile(module.document) not in (None, "19.01")


def test_multiple_unnamed_get_distinct_names() -> None:
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="19.01">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data from_work_dir="a"/><data from_work_dir="b"/></outputs>'
        b"</tool>"
    )
    module = parse_module(xml)
    Upgrade19_01().apply(module)
    names = [d.get("name") for d in module.document.root.findall("outputs/data")]
    assert names == ["output", "output2"]


def test_avoids_collision_with_existing_name() -> None:
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="19.01">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="output" format="txt"/>'
        b'<data from_work_dir="b"/></outputs></tool>'
    )
    module = parse_module(xml)
    Upgrade19_01().apply(module)
    names = [d.get("name") for d in module.document.root.findall("outputs/data")]
    assert names == ["output", "output2"]


def test_avoids_collision_with_collection_name() -> None:
    """Output identifiers share one namespace: don't mint a name a <collection> uses.

    A bare <data> next to <collection name="output"> must not be synthesised as
    "output" (that would be a duplicate output identifier); it gets "output2".
    """
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="19.01">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><collection name="output" type="list"/>'
        b'<data from_work_dir="b"/></outputs></tool>'
    )
    module = parse_module(xml)
    Upgrade19_01().apply(module)
    data = module.document.root.find("outputs/data")
    assert data is not None
    assert data.get("name") == "output2"


def test_leaves_collection_nested_unnamed_data_out_of_scope() -> None:
    """Only direct <outputs> children are named (documented scope).

    A <data> nested inside a <collection> is also name-required at 19.05, but the
    codemod deliberately scopes to top-level outputs (no corpus tool needs the
    nested case). Pin that boundary so a future change to it is deliberate.
    """
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="19.01">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><collection name="c" type="list">'
        b'<data from_work_dir="x"/></collection></outputs></tool>'
    )
    module = parse_module(xml)
    Upgrade19_01().apply(module)
    nested = module.document.root.find("outputs/collection/data")
    assert nested is not None
    assert nested.get("name") is None


def test_noop_when_all_outputs_named() -> None:
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="19.01">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" format="txt"/></outputs></tool>'
    )
    module = parse_module(xml)
    before = etree.tostring(module.document.root)
    Upgrade19_01().apply(module)
    assert etree.tostring(module.document.root) == before


def test_noop_when_no_outputs() -> None:
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="19.01">'
        b"<command><![CDATA[echo x]]></command><inputs/></tool>"
    )
    module = parse_module(xml)
    before = etree.tostring(module.document.root)
    Upgrade19_01().apply(module)
    assert etree.tostring(module.document.root) == before


def test_is_idempotent() -> None:
    module = parse_module(_STUCK)
    Upgrade19_01().apply(module)
    once = etree.tostring(module.document.root)
    Upgrade19_01().apply(module)
    assert etree.tostring(module.document.root) == once
