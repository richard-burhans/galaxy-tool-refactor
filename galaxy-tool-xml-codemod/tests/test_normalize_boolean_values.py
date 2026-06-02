"""Tests for the ``NormalizeBooleanValues`` repair codemod.

Like ``FixTypos`` it targets a tool that validates at no profile and, here,
normalizes Python-style boolean attribute values (``True``/``Yes``/…) on
schema-boolean attributes to canonical ``xs:boolean`` (``true``/``false``),
restoring validity. The rewrite is behaviour-preserving (Galaxy reads booleans
case-insensitively). It never touches ``profile=`` nor literal-string attributes,
and reverts to a byte-identical no-op when normalization does not restore
validity.
"""

from __future__ import annotations

from galaxy_tool_xml.binding import newest_valid_profile
from lxml import etree

from galaxy_tool_xml_codemod.codemods.normalize_boolean_values import (
    NormalizeBooleanValues,
)
from galaxy_tool_xml_codemod.parse import parse_module

# <data hidden="True"> fails XSD at every profile (`hidden` is strict xs:boolean);
# normalizing it to "true" makes the tool validate.
_BOOL_INVALID = (
    b'<tool id="m" name="M" version="1.0.0" profile="20.01">'
    b"<command><![CDATA[echo x]]></command><inputs/>"
    b'<outputs><data name="o" format="txt" hidden="True"/></outputs></tool>'
)

# Already validates — the guard must make the codemod a no-op (even though it
# carries a non-canonical boolean that the permissive newer schema accepts).
_ALREADY_VALID = (
    b'<tool id="m" name="M" version="1.0.0" profile="24.0">\n'
    b"    <command><![CDATA[echo x]]></command>\n"
    b'    <inputs><param name="p" type="boolean" checked="True"/></inputs>\n'
    b"    <outputs/>\n"
    b"</tool>"
)

# Globally invalid, with both a fixable boolean (`hidden`) and a literal
# value="True" on an <option> that must be left untouched.
_BOOL_PLUS_LITERAL = (
    b'<tool id="m" name="M" version="1.0.0" profile="20.01">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param name="p" type="select">'
    b'<option value="True">v</option></param></inputs>'
    b'<outputs><data name="o" format="txt" hidden="Yes"/></outputs></tool>'
)


def _apply(xml: bytes) -> tuple[bytes, etree._Element, str | None]:
    """Apply the codemod to *xml*; return (post-bytes, root, newest-valid-profile)."""
    module = parse_module(xml)
    NormalizeBooleanValues().apply(module)
    root = module.document.root
    return etree.tostring(root), root, newest_valid_profile(module.document)


def test_normalizes_boolean_to_restore_validity() -> None:
    _, root, nvp = _apply(_BOOL_INVALID)
    assert nvp is not None
    data = root.find(".//data")
    assert data is not None
    assert data.get("hidden") == "true"


def test_no_op_when_already_valid() -> None:
    before = _ALREADY_VALID
    after, _root, nvp = _apply(before)
    assert nvp is not None
    # Untouched: the permissive-schema "True" is left exactly as written.
    assert after == before


def test_leaves_literal_value_attribute_untouched() -> None:
    _, root, nvp = _apply(_BOOL_PLUS_LITERAL)
    assert nvp is not None
    option = root.find(".//option")
    assert option is not None
    assert option.get("value") == "True"  # literal value preserved
    data = root.find(".//data")
    assert data is not None
    assert data.get("hidden") == "true"  # boolean normalized


def test_idempotent() -> None:
    module = parse_module(_BOOL_INVALID)
    NormalizeBooleanValues().apply(module)
    once = etree.tostring(module.document.root)
    NormalizeBooleanValues().apply(module)
    assert etree.tostring(module.document.root) == once


def test_reverts_when_normalization_does_not_help() -> None:
    # Globally invalid for a non-boolean reason; the boolean rewrite alone can't
    # restore validity, so the codemod must revert to byte-identical.
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="20.01">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" format="txt" hidden="True"/><zzzzz/></outputs></tool>'
    )
    before = etree.tostring(parse_module(xml).document.root)
    after, _root, nvp = _apply(xml)
    assert nvp is None
    assert after == before
