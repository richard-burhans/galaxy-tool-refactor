"""Bytes serialisation and the CDATA-safe whitespace helper.

lxml exposes CDATA content as a plain ``str`` from ``.text`` — there is
no API to distinguish CDATA text from regular text at the Python level.
Assigning a plain string to ``.text`` permanently destroys the CDATA
wrapper; ``etree.tostring`` will subsequently emit escaped text instead
of ``<![CDATA[...]]>``. ``safe_set_text`` exists so any edit that wants
to write whitespace into ``.text`` (canonical indentation, etc.) can do
so without trampling element content that may be CDATA.
"""

from __future__ import annotations

from lxml import etree


def to_bytes(tree: etree._ElementTree) -> bytes:
    """Serialise *tree* to UTF-8 XML bytes with an XML declaration."""
    result: bytes = etree.tostring(tree, encoding="utf-8", xml_declaration=True)
    return result


def safe_set_text(element: etree._Element, value: str) -> None:
    """Write *value* to *element*.text only when it is absent or pure whitespace."""
    if not (element.text or "").strip():
        element.text = value


def safe_set_tail(element: etree._Element, value: str) -> None:
    """Write *value* to *element*.tail only when it is absent or pure whitespace.

    Known limitation (behaviour-preservation GTR001;
    ``../../docs/behavior_preservation.md``): the ``strip()`` guard treats *any*
    whitespace-only tail as rewritable, but a whitespace-only tail inside **mixed
    content** (text interspersed with child elements, e.g. ``See <b>x</b> <i>y</i>``)
    is a *significant* word separator — XML 1.0 calls inter-element whitespace
    non-significant only for *element* content, not mixed content. Rewriting it to
    newline+indent would change the rendered text. This has **zero corpus incidence**
    (no real tool indents inside a mixed-content body), so it is left as a documented
    limitation rather than guarded; revisit (skip ws-tail rewrite when the parent
    holds mixed content) if a real case appears.
    """
    if not (element.tail or "").strip():
        element.tail = value
