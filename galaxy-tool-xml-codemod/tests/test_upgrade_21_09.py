"""Tests for the ``Upgrade21_09`` codemod (single-step 21.09 -> 22.01 upgrade).

The 21.09 -> 22.01 schema delta is ``collection_type`` gaining pattern facets:
``CollectionTypeList`` (``<param>``) requires ``(list|paired)`` tokens joined by
``,``/``:`` with no whitespace. Galaxy's runtime strips each comma-separated
token (``DataCollectionToolParameter``: ``[t.strip() for t in
collection_types.split(",")]``), so comma-adjacent whitespace is runtime-
insignificant — stripping it is a no-op that unsticks validation. Colon-inner
whitespace is NOT runtime-stripped (``type_description.py`` splits ``:`` raw),
and the single-value ``CollectionType`` sites (output ``<collection type=>``)
have no strip either, so those stay untouched. ``collection_type=""`` is
droppable (``if collection_types:`` is falsy — same as absent); whitespace-only
is NOT (stripping it would flip a matches-nothing restriction into none).
"""

from __future__ import annotations

from galaxy_tool_xml.binding import newest_valid_profile
from lxml import etree

from galaxy_tool_xml_codemod.codemods.upgrade_21_09 import Upgrade21_09
from galaxy_tool_xml_codemod.parse import parse_module


def _tool(*, collection_type: str, output: str = '<data name="o"/>') -> bytes:
    return (
        '<tool id="m" name="M" version="1.0.0" profile="21.09">'
        "<command><![CDATA[echo x]]></command>"
        f'<inputs><param name="i" type="data_collection"'
        f' collection_type="{collection_type}"/></inputs>'
        f"<outputs>{output}</outputs></tool>"
    ).encode()


def _apply(xml: bytes) -> etree._Element:
    module = parse_module(xml)
    Upgrade21_09().apply(module)
    return module.document.root


def test_strips_comma_whitespace_and_unsticks() -> None:
    root = _apply(_tool(collection_type="list, list:paired"))
    param = root.find(".//param")
    assert param is not None
    assert param.get("collection_type") == "list,list:paired"
    assert newest_valid_profile(etree.tostring(root)) not in (None, "21.09")


def test_valid_value_untouched() -> None:
    root = _apply(_tool(collection_type="list,list:paired"))
    assert root.find(".//param").get("collection_type") == "list,list:paired"


def test_colon_inner_whitespace_left() -> None:
    # type_description.py splits ":" without strip — colon-inner whitespace is
    # runtime-significant, so there is no provable rewrite.
    root = _apply(_tool(collection_type="list : paired"))
    assert root.find(".//param").get("collection_type") == "list : paired"


def test_still_invalid_after_strip_left() -> None:
    # case is not coerced (runtime comparison is exact); the strip alone leaves
    # the value pattern-invalid, so nothing is written.
    root = _apply(_tool(collection_type="List, paired"))
    assert root.find(".//param").get("collection_type") == "List, paired"


def test_empty_value_dropped_whitespace_only_left() -> None:
    # "" is falsy at runtime (same as absent) -> droppable; " " strips to [""]
    # (a matches-nothing restriction) -> dropping/stripping would CHANGE behaviour.
    root = _apply(_tool(collection_type=""))
    assert root.find(".//param").get("collection_type") is None
    root = _apply(_tool(collection_type="   "))
    assert root.find(".//param").get("collection_type") == "   "


def test_output_collection_type_left() -> None:
    # The single-value CollectionType sites have no runtime strip — out of scope.
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="21.09">'
        b"<command><![CDATA[echo x]]></command>"
        b'<inputs><param name="i" type="text"/></inputs>'
        b'<outputs><collection name="o" type="list "><data name="d"/></collection>'
        b"</outputs></tool>"
    )
    root = _apply(xml)
    assert root.find(".//collection").get("type") == "list "


def test_is_idempotent() -> None:
    module = parse_module(_tool(collection_type="list, paired"))
    Upgrade21_09().apply(module)
    once = etree.tostring(module.document.root)
    Upgrade21_09().apply(module)
    assert etree.tostring(module.document.root) == once


def test_meta() -> None:
    assert Upgrade21_09.meta.code == "GTR093"
    assert Upgrade21_09.meta.rulesets == frozenset()
