"""Tests for the ``UpdateProfile`` codemod.

``UpdateProfile`` sets the root ``<tool>``'s ``profile=`` to the newest vendored
profile the tool validates at: bumping a declared profile up to it, or adding the
declaration when absent. It is bump-up-only (never lowers a declared profile),
and a no-op when the profile is already correct, when the tool validates nowhere,
or when the declared profile is not a parseable version.
"""

from __future__ import annotations

from galaxy_tool_xml.binding import validate_tool
from lxml import etree

from galaxy_tool_xml_codemod.codemods.update_profile import UpdateProfile
from galaxy_tool_xml_codemod.parse import parse_module

_CMD = b"<command><![CDATA[echo x]]></command>"


def _tool(profile_attr: str | None) -> bytes:
    """A minimal well-formed tool, optionally carrying a ``profile=`` attribute."""
    attr = f' profile="{profile_attr}"'.encode() if profile_attr is not None else b""
    return (
        b'<tool id="m" name="M" version="1.0.0"' + attr + b">"
        + _CMD
        + b"<inputs/><outputs/></tool>"
    )


def _apply(xml: bytes) -> etree._Element:
    module = parse_module(xml)
    UpdateProfile().apply(module)
    return module.document.root


def test_bumps_declared_profile_up_to_newest_valid() -> None:
    """An old declared profile is bumped up to the newest validating version."""
    assert _apply(_tool("16.01")).get("profile") == "26.1"


def test_adds_profile_when_absent() -> None:
    """A tool with no declaration gains one set to the newest validating version."""
    assert _apply(_tool(None)).get("profile") == "26.1"


def test_added_profile_validates_at_that_version() -> None:
    """After adding ``profile=``, the tool validates at the version it now declares."""
    root = _apply(_tool(None))
    version = root.get("profile")
    assert version is not None
    assert validate_tool(etree.tostring(root), profile=version).valid


def test_noop_when_already_correct() -> None:
    """When the declared profile already equals newest-valid, nothing changes."""
    xml = _tool("26.1")
    module = parse_module(xml)
    before = etree.tostring(module.document.root)
    UpdateProfile().apply(module)
    assert etree.tostring(module.document.root) == before


def test_never_lowers_a_newer_declared_profile() -> None:
    """A declared profile newer than newest-valid is left untouched (bump-up only)."""
    assert _apply(_tool("99.0")).get("profile") == "99.0"


def test_leaves_unparseable_declared_profile_alone() -> None:
    """A non-version declaration (e.g. a macro placeholder) is never rewritten."""
    assert _apply(_tool("@PROFILE@")).get("profile") == "@PROFILE@"


def test_noop_when_tool_validates_nowhere() -> None:
    """With no valid profile to point at, the codemod is a byte-identical no-op."""
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="24.0">'
        + _CMD
        + b"<inputs/><outputs/><zzzzzzzzzz/></tool>"
    )
    module = parse_module(xml)
    before = etree.tostring(module.document.root)
    UpdateProfile().apply(module)
    assert etree.tostring(module.document.root) == before


def test_is_idempotent() -> None:
    """Applying twice equals applying once."""
    module = parse_module(_tool("16.01"))
    UpdateProfile().apply(module)
    once = etree.tostring(module.document.root)
    UpdateProfile().apply(module)
    assert etree.tostring(module.document.root) == once
