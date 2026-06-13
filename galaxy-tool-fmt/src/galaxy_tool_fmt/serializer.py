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
    """Serialise *tree* to UTF-8 XML bytes with no XML declaration.

    The canonical output omits ``<?xml ...?>``: it is the IUC convention for
    tool XML (they remove the declaration even when an author wrote one), and
    it is optional anyway — XML with no declaration or BOM defaults to UTF-8,
    which is what Galaxy tool XML is. See ``docs/decisions.md`` §D21.

    The output ends with exactly one trailing newline: ``etree.tostring`` emits
    none (the bytes stop at the root's closing ``>``), but every tools-iuc tool
    XML ends with a ``\\n`` (the POSIX text-file convention), so canonical output
    must too. Appending one ``\\n`` is idempotent — a re-parse drops the trailing
    newline (it sits outside the root element), so re-serialising appends exactly
    one again. See ``docs/decisions.md`` §D22.
    """
    result: bytes = etree.tostring(tree, encoding="utf-8", xml_declaration=False)
    return result + b"\n"


def safe_set_text(element: etree._Element, value: str) -> None:
    """Write *value* to *element*.text only when it is absent or pure whitespace."""
    if not (element.text or "").strip():
        element.text = value


def safe_set_tail(element: etree._Element, value: str) -> None:
    """Write *value* to *element*.tail only when it is absent or pure whitespace.

    Caller contract (behaviour-preservation GTR001;
    ``../../docs/behavior_preservation.md``): the ``strip()`` guard treats *any*
    whitespace-only tail as rewritable, but a whitespace-only tail inside **mixed
    content** (``See <b>x</b> <i>y</i>``) or inside a payload element with children
    (``<command><expand/> <expand/></command>``) is significant — a rendered word
    separator / spliced script text — so callers must not target tails there. The
    indent rule enforces this with its mixed-content + payload-subtree skip
    (``rule_indent``); the blank-line rule only ever targets the root's direct
    children (element content by schema).
    """
    if not (element.tail or "").strip():
        element.tail = value
