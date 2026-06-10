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

from galaxy_tool_source.binding import newest_valid_profile
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


def _stdio_tool(stdio: str, /) -> bytes:
    return (
        '<tool id="m" name="M" version="1.0.0" profile="21.09">'
        "<command><![CDATA[echo x]]></command>"
        f"<stdio>{stdio}</stdio>"
        '<inputs><param name="i" type="text"/></inputs>'
        '<outputs><data name="o"/></outputs></tool>'
    ).encode()


def test_exit_code_value_alias_renamed_to_range() -> None:
    # Galaxy reads range first and falls back to value (xml.py:1248-1250) —
    # the attributes are runtime aliases, and 22.01 requires range.
    root = _apply(_stdio_tool('<exit_code value="1:" level="fatal"/>'))
    exit_code = root.find(".//exit_code")
    assert exit_code is not None
    assert exit_code.get("range") == "1:"
    assert exit_code.get("value") is None
    assert newest_valid_profile(etree.tostring(root)) not in (None, "21.09")


def test_exit_code_with_range_keeps_it_and_drops_dead_value() -> None:
    # With range present the value attribute is never read — a dead attribute.
    root = _apply(_stdio_tool('<exit_code range="1:" value="2:"/>'))
    exit_code = root.find(".//exit_code")
    assert exit_code.get("range") == "1:"
    assert exit_code.get("value") is None


def test_exit_code_with_neither_attr_is_deleted() -> None:
    # Runtime logs "must have a range or value" and skips the element — dead.
    root = _apply(_stdio_tool('<exit_code level="fatal"/>'))
    assert root.find(".//exit_code") is None
    assert root.find("stdio") is not None  # the container itself stays


def test_exit_code_with_blank_range_is_deleted() -> None:
    # range="" (and whitespace-only): the runtime strips whitespace, then the
    # singular int("") path logs and skips — dead either way.
    root = _apply(_stdio_tool('<exit_code range=""/><exit_code range="  "/>'))
    assert root.find(".//exit_code") is None


def test_regex_without_match_is_deleted_with_match_kept() -> None:
    # xml.py:1318-1324: a <regex> without match= is logged and skipped — dead.
    root = _apply(
        _stdio_tool('<regex match="error" level="fatal"/><regex level="warning"/>')
    )
    regexes = root.findall(".//regex")
    assert len(regexes) == 1
    assert regexes[0].get("match") == "error"


def test_stdio_repair_is_idempotent() -> None:
    module = parse_module(
        _stdio_tool('<exit_code value="1:"/><regex level="warning"/>')
    )
    Upgrade21_09().apply(module)
    once = etree.tostring(module.document.root)
    Upgrade21_09().apply(module)
    assert etree.tostring(module.document.root) == once


def _has_size_tool(attrs: str, /) -> bytes:
    return (
        '<tool id="m" name="M" version="1.0.0" profile="21.09">'
        "<command><![CDATA[echo x]]></command>"
        '<inputs><param name="i" type="text"/></inputs>'
        '<outputs><data name="o"/></outputs>'
        '<tests><test><output name="o"><assert_contents>'
        f"<has_size {attrs}/>"
        "</assert_contents></output></test></tests></tool>"
    ).encode()


def _has_size_of(root: etree._Element) -> etree._Element:
    element = root.find(".//has_size")
    assert element is not None
    return element


def test_has_size_whitespace_value_stripped_and_unsticks() -> None:
    # parse_bytesize int()-tolerates surrounding whitespace; the 22.01 Bytes
    # pattern does not — stripping is a runtime no-op.
    root = _apply(_has_size_tool('value=" 100 "'))
    assert _has_size_of(root).get("value") == "100"
    assert newest_valid_profile(etree.tostring(root)) not in (None, "21.09")


def test_has_size_inner_space_and_suffix_case_normalized() -> None:
    # "100 Mi" and "100MI" both parse at runtime (upper() + suffix table); the
    # pattern wants the canonical "100Mi".
    root = _apply(_has_size_tool('value="100 Mi" delta="2MI"'))
    has_size = _has_size_of(root)
    assert has_size.get("value") == "100Mi"
    assert has_size.get("delta") == "2Mi"


def test_has_size_integral_scientific_becomes_exact_integer() -> None:
    # "129e6" parses to the float 129000000.0 — integral, so the exact integer
    # string is runtime-identical and pattern-valid.
    root = _apply(_has_size_tool('value="129e6"'))
    assert _has_size_of(root).get("value") == "129000000"


def test_has_size_valid_and_unparseable_values_untouched() -> None:
    root = _apply(_has_size_tool('value="129M" delta="12 cars"'))
    has_size = _has_size_of(root)
    assert has_size.get("value") == "129M"  # already pattern-valid
    assert has_size.get("delta") == "12 cars"  # never runtime-working: leave

    # a non-integral parse compares as a float at runtime — no integer string
    # is runtime-identical, so it is left (and stays stuck + reported).
    root = _apply(_has_size_tool('value="1.5"'))
    assert _has_size_of(root).get("value") == "1.5"
