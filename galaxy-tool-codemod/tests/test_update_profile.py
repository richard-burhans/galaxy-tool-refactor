"""Tests for the ``UpdateProfile`` codemod.

``UpdateProfile`` sets the root ``<tool>``'s ``profile=`` to the newest vendored
profile the tool validates at: bumping a declared profile up to it, or adding the
declaration when absent. It is bump-up-only (never lowers a declared profile),
and a no-op when the profile is already correct or the tool validates nowhere.
A ``@TOKEN@`` profile whose token is defined inline is upgraded by rewriting the
token value; an imported (or unresolved) token is left untouched.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_source.binding import validate_tool
from lxml import etree

from galaxy_tool_codemod.codemods.update_profile import UpdateProfile
from galaxy_tool_codemod.parse import parse_module

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


def test_ceiling_caps_the_declared_profile() -> None:
    """With a ceiling, the declaration never rises above it."""
    module = parse_module(_tool(None))
    UpdateProfile(ceiling="24.1").apply(module)
    assert module.document.root.get("profile") == "24.1"


def test_ceiling_never_lowers_a_declared_profile() -> None:
    """The ceiling caps the bump; it never takes a declaration backwards."""
    module = parse_module(_tool("25.1"))
    UpdateProfile(ceiling="24.1").apply(module)
    assert module.document.root.get("profile") == "25.1"


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


def _tool_inline_token(token_value: bytes) -> bytes:
    """A tool whose ``profile=`` is an inline ``@PROFILE@`` token."""
    return (
        b'<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        b'<macros><token name="@PROFILE@">' + token_value + b"</token></macros>"
        + _CMD
        + b"<inputs/><outputs/></tool>"
    )


def test_rewrites_stale_inline_profile_token() -> None:
    """A stale inline @PROFILE@ token is bumped; the reference is preserved."""
    root = _apply(_tool_inline_token(b"16.01"))
    assert root.get("profile") == "@PROFILE@"  # reference kept, not clobbered
    token = root.find('macros/token[@name="@PROFILE@"]')
    assert token is not None
    assert token.text == "26.1"


def test_inline_profile_token_already_current_is_noop() -> None:
    module = parse_module(_tool_inline_token(b"26.1"))
    before = etree.tostring(module.document.root)
    UpdateProfile().apply(module)
    assert etree.tostring(module.document.root) == before


def test_leaves_imported_profile_token_untouched(tmp_path: Path) -> None:
    """An @PROFILE@ token defined in an imported macro file is left alone (3a).

    The cross-file edit is the bundle-aware step; here neither the tool's
    reference nor the macro file is changed.
    """
    macros = tmp_path / "macros.xml"
    macros.write_bytes(b'<macros><token name="@PROFILE@">16.01</token></macros>')
    tool = tmp_path / "tool.xml"
    tool.write_bytes(
        b'<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        b"<macros><import>macros.xml</import></macros>" + _CMD
        + b"<inputs/><outputs/></tool>"
    )
    module = parse_module(tool)
    before_tool = etree.tostring(module.document.root)
    UpdateProfile().apply(module)
    assert module.document.root.get("profile") == "@PROFILE@"
    assert etree.tostring(module.document.root) == before_tool
    assert macros.read_bytes() == (
        b'<macros><token name="@PROFILE@">16.01</token></macros>'
    )
