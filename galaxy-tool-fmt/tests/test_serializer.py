"""Tests for the bytes serialiser.

The canonical output carries **no** XML declaration: the IUC convention is to
omit `<?xml ...?>` on tool XML (they remove it even when an author included
it), and the declaration is optional — XML defaults to UTF-8 with no
declaration or BOM, which is what Galaxy tool XML is. See `docs/decisions.md`
§D21.
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_fmt.serializer import to_bytes


def _tree(source: bytes) -> etree._ElementTree:
    return etree.ElementTree(etree.fromstring(source))


def test_to_bytes_emits_no_xml_declaration() -> None:
    """The serialised bytes begin with the root element, not `<?xml ...?>`."""
    out = to_bytes(_tree(b"<tool id='t'/>"))
    assert not out.lstrip().startswith(b"<?xml")
    assert out.startswith(b"<tool")


def test_to_bytes_drops_a_declaration_present_on_input() -> None:
    """An author-supplied declaration is removed (IUC removes it even when present)."""
    out = to_bytes(_tree(b"<?xml version='1.0' encoding='UTF-8'?>\n<tool id='t'/>"))
    assert b"<?xml" not in out


def test_to_bytes_round_trips_without_a_declaration() -> None:
    """A declaration-free document is still well-formed UTF-8 XML that reparses."""
    out = to_bytes(_tree(b"<tool id='t'><inputs/></tool>"))
    root = etree.fromstring(out)
    assert root.tag == "tool"
    assert root.find("inputs") is not None


def test_to_bytes_ends_with_exactly_one_trailing_newline() -> None:
    """The serialised bytes end with a single ``\\n`` (POSIX text-file convention;
    every tools-iuc tool XML ends with a newline). ``etree.tostring`` emits none."""
    out = to_bytes(_tree(b"<tool id='t'/>"))
    assert out.endswith(b">\n")
    assert not out.endswith(b"\n\n")


def test_to_bytes_trailing_newline_is_idempotent() -> None:
    """Reparsing output (whose trailing ``\\n`` sits outside the root) and
    re-serialising yields the same bytes — one newline, not two."""
    once = to_bytes(_tree(b"<tool id='t'><inputs/></tool>"))
    twice = to_bytes(etree.ElementTree(etree.fromstring(once)))
    assert once == twice
    assert once.endswith(b"\n")
    assert not once.endswith(b"\n\n")
