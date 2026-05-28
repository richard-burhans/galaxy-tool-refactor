"""Tests for the ``FixTypos`` repair codemod.

``FixTypos`` targets a tool that is well-formed but validates at no profile,
and rewrites near-miss typos (attribute names, element tags, enum values) so it
validates — iterating profiles newest-to-oldest and stopping at the first that
validates. It never touches ``profile=``, and if no profile validates after
fixes it reverts to a byte-identical no-op.
"""

from __future__ import annotations

from galaxy_tool_xml.binding import newest_valid_profile
from lxml import etree

from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.parse import parse_module

_HEAD = b'<tool id="m" name="M" version="1.0.0" profile="24.0">'
_CMD = b"<command><![CDATA[echo x]]></command>"

_ATTR_TYPO = (
    _HEAD + _CMD
    + b'<inputs><param name="x" typ="text" label="L"/></inputs><outputs/></tool>'
)
_ELEM_TYPO = _HEAD + _CMD + b"<inputss/><outputs/></tool>"
_ENUM_TYPO = (
    _HEAD + _CMD
    + b'<inputs><param name="x" type="interger" label="L"/></inputs><outputs/></tool>'
)

# A genuinely-disallowed element no near-miss can repair (difflib < 0.8 cutoff).
_STRUCTURAL = (
    b'<tool id="m" name="M" version="1.0.0" profile="24.0">\n'
    b"    <!-- keep this comment -->\n"
    b"    <command><![CDATA[echo x && run]]></command>\n"
    b"    <inputs/>\n"
    b"    <outputs/>\n"
    b"    <zzzzzzzzzz/>\n"
    b"</tool>"
)

# Already validates at 24.0 — the guard must make FixTypos a no-op.
_ALREADY_VALID = (
    b'<tool id="m" name="M" version="1.0.0" profile="24.0">\n'
    b"    <command><![CDATA[echo x]]></command>\n"
    b"    <inputs/>\n"
    b"    <outputs/>\n"
    b"</tool>"
)


def _apply(xml: bytes) -> tuple[bytes, etree._Element, str | None]:
    """Apply ``FixTypos`` to *xml*; return (post-bytes, root, newest-valid-profile)."""
    module = parse_module(xml)
    FixTypos().apply(module)
    root = module.document.root
    return etree.tostring(root), root, newest_valid_profile(module.document)


def test_fixes_attribute_name_typo() -> None:
    """A misspelled attribute name is renamed in place, restoring validity."""
    _, root, nvp = _apply(_ATTR_TYPO)
    assert nvp is not None
    param = root.find(".//param")
    assert param is not None
    assert "typ" not in param.attrib
    assert param.get("type") == "text"
    # Position preserved: the renamed slot stays where ``typ`` was.
    assert tuple(param.attrib) == ("name", "type", "label")


def test_fixes_element_name_typo() -> None:
    """A misspelled child element tag is renamed, restoring validity."""
    _, root, nvp = _apply(_ELEM_TYPO)
    assert nvp is not None
    assert root.find("inputss") is None
    assert root.find("inputs") is not None


def test_fixes_enum_value_typo() -> None:
    """A misspelled enumerated attribute value is corrected, restoring validity."""
    _, root, nvp = _apply(_ENUM_TYPO)
    assert nvp is not None
    param = root.find(".//param")
    assert param is not None
    assert param.get("type") == "integer"


def test_non_typo_structural_error_is_byte_identical_noop() -> None:
    """An unrepairable structural error leaves the document byte-identical."""
    after, _, nvp = _apply(_STRUCTURAL)
    assert after == _STRUCTURAL
    assert nvp is None


def test_already_valid_tool_is_byte_identical_noop() -> None:
    """A tool that already validates is left untouched by the guard."""
    after, _, nvp = _apply(_ALREADY_VALID)
    assert after == _ALREADY_VALID
    assert nvp is not None


def test_repair_is_idempotent() -> None:
    """Applying twice repairs once; the second pass is a byte no-op."""
    module = parse_module(_ATTR_TYPO)
    FixTypos().apply(module)
    first = etree.tostring(module.document.root)
    FixTypos().apply(module)
    second = etree.tostring(module.document.root)
    assert second == first


def test_atomic_revert_preserves_cdata_comments_and_attr_order() -> None:
    """The atomic revert restores CDATA, comments, and attribute order verbatim."""
    after, _, _ = _apply(_STRUCTURAL)
    assert after == _STRUCTURAL
    assert b"<![CDATA[echo x && run]]>" in after
    assert b"<!-- keep this comment -->" in after


def test_profile_attribute_is_never_modified() -> None:
    """``profile=`` is left untouched on every fixture, repaired or not."""
    for xml in (_ATTR_TYPO, _ELEM_TYPO, _ENUM_TYPO, _STRUCTURAL):
        _, root, _ = _apply(xml)
        assert root.get("profile") == "24.0"
