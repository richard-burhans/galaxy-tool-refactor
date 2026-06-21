"""Tests for the facade ``bump_version_suffix`` entry point (N2).

N2 bumps a tool's integer ``+galaxy<N>`` revision suffix by one. Tool-local sites
(a literal ``version=`` suffix, or an inline ``@VERSION_SUFFIX@`` token) are bumped
in the tool itself; an imported-token suffix is bumped once in the shared macros
file under ``--scope suite``, moving every importer in lockstep, behind a
proof-by-execution gate. Identity-changing, so never wired into ``run``/``upgrade``.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_refactor_registry import facade

_LITERAL_TOOL = (
    b'<tool id="m" name="M" version="1.20+galaxy7" profile="24.0">'
    b"<command><![CDATA[echo x]]></command>"
    b'<requirements><requirement type="package" version="1.20">samtools'
    b"</requirement></requirements>"
    b'<inputs><param name="i" type="text"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)

_INLINE_TOKEN_TOOL = (
    b'<tool id="m" name="M" version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"'
    b' profile="24.0">'
    b'<macros>'
    b'<token name="@TOOL_VERSION@">1.20</token>'
    b'<token name="@VERSION_SUFFIX@">3</token>'
    b'</macros>'
    b"<command><![CDATA[echo x]]></command>"
    b'<requirements><requirement type="package" version="@TOOL_VERSION@">samtools'
    b"</requirement></requirements>"
    b'<inputs><param name="i" type="text"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)

_BARE_TOOL = (
    b'<tool id="m" name="M" version="1.20" profile="24.0">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param name="i" type="text"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)


def _shared_suite(tmp_path: Path, *, suffix: str = "4") -> tuple[Path, Path, Path]:
    """A directory with macros.xml + two tools importing its @VERSION_SUFFIX@."""
    macros = tmp_path / "macros.xml"
    macros.write_text(
        "<macros>\n"
        '    <token name="@TOOL_VERSION@">1.20</token>\n'
        f'    <token name="@VERSION_SUFFIX@">{suffix}</token>\n'
        "</macros>\n",
        encoding="utf-8",
    )
    body = (
        '<tool id="{id}" name="{id}" version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"'
        ' profile="24.0">\n'
        "    <macros><import>macros.xml</import></macros>\n"
        "    <command><![CDATA[echo x]]></command>\n"
        "    <requirements>\n"
        '        <requirement type="package" version="@TOOL_VERSION@">samtools'
        "</requirement>\n"
        "    </requirements>\n"
        '    <inputs><param name="i" type="text"/></inputs>\n'
        '    <outputs><data name="o"/></outputs>\n'
        "</tool>\n"
    )
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    a.write_text(body.format(id="a"), encoding="utf-8")
    b.write_text(body.format(id="b"), encoding="utf-8")
    return macros, a, b


# --------------------------------------------------------------------------- #
# Tool-local sites (both scopes identical)                                      #
# --------------------------------------------------------------------------- #


def test_bump_literal_suffix() -> None:
    result = facade.bump_version_suffix(_LITERAL_TOOL, scope="suite")
    assert result.bumped is True and result.skip_reason is None
    assert result.old_version == "1.20+galaxy7"
    assert result.new_version == "1.20+galaxy8"
    assert b'version="1.20+galaxy8"' in result.formatted
    assert result.affected_importers == ()


def test_bump_inline_token() -> None:
    result = facade.bump_version_suffix(_INLINE_TOKEN_TOOL, scope="per-tool")
    assert result.bumped is True
    assert b'<token name="@VERSION_SUFFIX@">4</token>' in result.formatted
    # the version= attribute stays the tokenized form
    assert b'version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"' in result.formatted


def test_bump_skips_bare_version() -> None:
    result = facade.bump_version_suffix(_BARE_TOOL, scope="suite")
    assert result.bumped is False
    assert result.skip_reason is not None
    assert "--adopt-suffix" in result.skip_reason


def test_bump_skips_non_integer_suffix() -> None:
    tool = _LITERAL_TOOL.replace(b"+galaxy7", b"+galaxyabc")
    result = facade.bump_version_suffix(tool, scope="suite")
    assert result.bumped is False
    assert result.skip_reason is not None and "not an integer" in result.skip_reason


def test_bump_writes_when_path_given(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_LITERAL_TOOL)
    result = facade.bump_version_suffix(tool, scope="suite", write_path=tool)
    assert result.bumped is True
    assert b'version="1.20+galaxy8"' in tool.read_bytes()


# --------------------------------------------------------------------------- #
# Imported token: per-tool skip, suite bump                                     #
# --------------------------------------------------------------------------- #


def test_imported_token_per_tool_skips(tmp_path: Path) -> None:
    _macros, a, _b = _shared_suite(tmp_path)
    result = facade.bump_version_suffix(a, scope="per-tool")
    assert result.bumped is False
    assert result.skip_reason is not None
    assert "macros.xml" in result.skip_reason
    assert "--scope suite" in result.skip_reason


def test_imported_token_suite_bumps_shared_file(tmp_path: Path) -> None:
    macros, a, b = _shared_suite(tmp_path, suffix="4")
    result = facade.bump_version_suffix(a, scope="suite", write_path=a)
    assert result.bumped is True, result.skip_reason
    # The shared macros file moved once, lifting every importer.
    assert b'<token name="@VERSION_SUFFIX@">5</token>' in macros.read_bytes()
    # Both importers are reported and the macros file is an affected path.
    assert set(result.affected_importers) == {a.resolve(), b.resolve()}
    assert macros.resolve() in result.affected_paths


def test_imported_token_suite_bails_when_not_inert(tmp_path: Path) -> None:
    # A third importer in the directory uses @VERSION_SUFFIX@ somewhere ELSE that the
    # bump would change beyond the +galaxy<N> segment -> the inert-except-suffix gate
    # must bail.
    macros, a, _b = _shared_suite(tmp_path, suffix="4")
    other = tmp_path / "c.xml"
    other.write_text(
        '<tool id="c" name="C" version="9.9+galaxy0" profile="24.0">\n'
        "    <macros><import>macros.xml</import></macros>\n"
        # references the shared suffix token in a place unrelated to +galaxy<N>
        "    <command><![CDATA[echo @VERSION_SUFFIX@]]></command>\n"
        '    <inputs><param name="i" type="text"/></inputs>\n'
        '    <outputs><data name="o"/></outputs>\n'
        "</tool>\n",
        encoding="utf-8",
    )
    result = facade.bump_version_suffix(a, scope="suite")
    assert result.bumped is False
    assert result.skip_reason is not None
    assert "c.xml" in result.skip_reason
