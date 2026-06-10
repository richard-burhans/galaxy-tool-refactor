"""Schema-derived element content knowledge: which tags may carry text.

The fmt tier's whitespace guards (GTR004's content-bearing denylist, GTR001's
payload-subtree skip) need the set of element tags whose body text can be
*meaningful* — script/template payload (``<command>``, ``<configfile>``,
``<token>``), rendered text (``<help>``, ``<option>`` labels), or evaluated
expressions (``<filter>``). Hand-maintaining that set risks silently missing a
tag; the schema already knows it: an element is **text-bearing** iff its
resolved type admits character content —

- a complexType with ``xs:simpleContent`` (the tool schema's idiom for
  string-bodied elements), or ``mixed="true"``;
- an XSD builtin (``xs:string``, ``xs:anyType``, ``xs:integer``, …); or
- a named simpleType.

Element-only and empty (attributes-only) content models are not text-bearing —
their internal whitespace is layout by XML 1.0's element-content rule.

``text_bearing_tags()`` unions the answer across **every vendored XSD** (a tag
text-bearing in any Galaxy release is treated as text-bearing — the conservative
direction for a guard) and resolves unknown type references conservatively (to
text-bearing). Derived once, cached; behaviour-preservation ledger
(``../../docs/behavior_preservation.md``, the GTR004 derivation proposal,
applied 2026-06-10).
"""

from __future__ import annotations

import importlib.resources
from functools import cache

from lxml import etree

_XS = "{http://www.w3.org/2001/XMLSchema}"
_BUILTIN_PREFIX = "xs:"


def _named_type_maps(
    root: etree._Element, /
) -> tuple[dict[str, etree._Element], frozenset[str]]:
    """Top-level complexTypes by name + the set of named simpleType names."""
    complex_types = {
        name: ct
        for ct in root.findall(f"{_XS}complexType")
        if (name := ct.get("name")) is not None
    }
    simple_types = frozenset(
        name
        for st in root.findall(f"{_XS}simpleType")
        if (name := st.get("name")) is not None
    )
    return complex_types, simple_types


def _complex_type_is_text_bearing(complex_type: etree._Element, /) -> bool:
    """A complexType admits text iff it is mixed or has simpleContent."""
    if complex_type.get("mixed") == "true":
        return True
    return complex_type.find(f"{_XS}simpleContent") is not None


def _element_is_text_bearing(
    element: etree._Element,
    /,
    *,
    complex_types: dict[str, etree._Element],
    simple_types: frozenset[str],
) -> bool:
    type_name = element.get("type")
    if type_name is None:
        inline_complex = element.find(f"{_XS}complexType")
        if inline_complex is not None:
            return _complex_type_is_text_bearing(inline_complex)
        # An inline simpleType — or no type at all (anyType semantics): text.
        return True
    if type_name.startswith(_BUILTIN_PREFIX):
        return True  # every builtin (string/anyType/integer/…) is character data
    if type_name in simple_types:
        return True
    named = complex_types.get(type_name)
    if named is not None:
        return _complex_type_is_text_bearing(named)
    return True  # unknown reference: conservative for a guard


@cache
def text_bearing_tags() -> frozenset[str]:
    """Element tags whose content model admits text, in any vendored XSD."""
    schema_dir = importlib.resources.files("galaxy_tool_xml") / "schema"
    tags: set[str] = set()
    with importlib.resources.as_file(schema_dir) as directory:
        for path in sorted(directory.glob("galaxy-*.xsd")):
            root = etree.parse(str(path)).getroot()
            complex_types, simple_types = _named_type_maps(root)
            for element in root.iter(f"{_XS}element"):
                name = element.get("name")
                if name is None:
                    continue  # a ref= element resolves at its declaration
                if _element_is_text_bearing(
                    element, complex_types=complex_types, simple_types=simple_types
                ):
                    tags.add(name)
    return frozenset(tags)
