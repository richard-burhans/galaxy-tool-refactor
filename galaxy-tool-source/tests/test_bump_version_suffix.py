"""Tests for the tier-1 ``bump-version-suffix`` (N2) primitives.

N2 is the identity-changing sibling of ``--adopt-suffix``: it bumps the integer
``+galaxy<N>`` revision suffix by one (``+galaxy7`` -> ``+galaxy8``), author-invoked.
This module owns the *decision* (``bump_suffix_skip_reason``), the *resolver*
(``current_suffix`` -> the integer and where it is defined), and the *tool-local
tree mutation* (``bump_suffix_tree``). The imported-macros-file case is handled in
the registry, not here.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_source.binding import load_tool, parse_tool
from galaxy_tool_source.version_tokens import (
    SuffixSiteKind,
    bump_suffix_skip_reason,
    bump_suffix_tree,
    current_suffix,
)

_LITERAL_TOOL = """\
<tool id="x" name="X" version="1.20+galaxy7" profile="22.05">
    <requirements>
        <requirement type="package" version="1.20">samtools</requirement>
    </requirements>
    <command><![CDATA[samtools --version]]></command>
</tool>
"""

_INLINE_TOKEN_TOOL = """\
<tool id="x" name="X" version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@" profile="22.05">
    <macros>
        <token name="@TOOL_VERSION@">1.20</token>
        <token name="@VERSION_SUFFIX@">3</token>
    </macros>
    <requirements>
        <requirement type="package" version="@TOOL_VERSION@">samtools</requirement>
    </requirements>
    <command><![CDATA[samtools --version]]></command>
</tool>
"""

_LITERAL_TOKEN_BASE_TOOL = """\
<tool id="x" name="X" version="@TOOL_VERSION@+galaxy5" profile="22.05">
    <macros>
        <token name="@TOOL_VERSION@">1.20</token>
    </macros>
    <requirements>
        <requirement type="package" version="@TOOL_VERSION@">samtools</requirement>
    </requirements>
    <command><![CDATA[samtools --version]]></command>
</tool>
"""

_BARE_TOOL = """\
<tool id="x" name="X" version="1.20" profile="22.05">
    <command><![CDATA[echo x]]></command>
</tool>
"""

_NON_INT_TOOL = """\
<tool id="x" name="X" version="1.20+galaxyabc" profile="22.05">
    <command><![CDATA[echo x]]></command>
</tool>
"""


def _document(xml: str):
    return parse_tool(xml.encode("utf-8")).document


# --------------------------------------------------------------------------- #
# bump_suffix_skip_reason                                                       #
# --------------------------------------------------------------------------- #


def test_skip_reason_none_for_literal_suffix() -> None:
    assert bump_suffix_skip_reason(_document(_LITERAL_TOOL)) is None


def test_skip_reason_none_for_inline_token() -> None:
    assert bump_suffix_skip_reason(_document(_INLINE_TOKEN_TOOL)) is None


def test_skip_reason_no_version() -> None:
    xml = '<tool id="x" name="X" profile="22.05"><command>echo</command></tool>'
    reason = bump_suffix_skip_reason(_document(xml))
    assert reason is not None and "no version=" in reason


def test_skip_reason_no_galaxy_suffix_points_to_adopt() -> None:
    reason = bump_suffix_skip_reason(_document(_BARE_TOOL))
    assert reason is not None
    assert "no +galaxy suffix" in reason
    assert "--adopt-suffix" in reason


def test_skip_reason_non_integer_suffix() -> None:
    reason = bump_suffix_skip_reason(_document(_NON_INT_TOOL))
    assert reason is not None
    assert "not an integer" in reason
    assert "abc" in reason


# --------------------------------------------------------------------------- #
# current_suffix (the resolver + its three site kinds)                          #
# --------------------------------------------------------------------------- #


def test_current_suffix_version_literal() -> None:
    found = current_suffix(_document(_LITERAL_TOOL))
    assert found is not None
    value, site = found
    assert value == 7
    assert site.kind is SuffixSiteKind.VERSION_LITERAL
    assert site.macro_file is None


def test_current_suffix_inline_token() -> None:
    found = current_suffix(_document(_INLINE_TOKEN_TOOL))
    assert found is not None
    value, site = found
    assert value == 3
    assert site.kind is SuffixSiteKind.INLINE_TOKEN
    assert site.macro_file is None


def test_current_suffix_literal_with_tokenized_base() -> None:
    # version="@TOOL_VERSION@+galaxy5" -> the suffix is still a literal in version=.
    found = current_suffix(_document(_LITERAL_TOKEN_BASE_TOOL))
    assert found is not None
    value, site = found
    assert value == 5
    assert site.kind is SuffixSiteKind.VERSION_LITERAL


def test_current_suffix_imported_token(tmp_path: Path) -> None:
    macros = tmp_path / "macros.xml"
    macros.write_text(
        '<macros>\n'
        '    <token name="@TOOL_VERSION@">1.20</token>\n'
        '    <token name="@VERSION_SUFFIX@">4</token>\n'
        '</macros>\n',
        encoding="utf-8",
    )
    tool = tmp_path / "tool.xml"
    tool.write_text(
        '<tool id="x" name="X" version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"'
        ' profile="22.05">\n'
        '    <macros><import>macros.xml</import></macros>\n'
        '    <requirements>\n'
        '        <requirement type="package" version="@TOOL_VERSION@">samtools'
        '</requirement>\n'
        '    </requirements>\n'
        '    <command><![CDATA[samtools]]></command>\n'
        '</tool>\n',
        encoding="utf-8",
    )
    found = current_suffix(load_tool(tool))
    assert found is not None
    value, site = found
    assert value == 4
    assert site.kind is SuffixSiteKind.IMPORTED_TOKEN
    assert site.macro_file == macros.resolve()


# --------------------------------------------------------------------------- #
# bump_suffix_tree (tool-local mutation)                                        #
# --------------------------------------------------------------------------- #


def test_bump_tree_literal_rewrites_version() -> None:
    document = _document(_LITERAL_TOOL)
    bump_suffix_tree(document.root, new_suffix=8)
    assert document.root.get("version") == "1.20+galaxy8"


def test_bump_tree_literal_with_tokenized_base() -> None:
    document = _document(_LITERAL_TOKEN_BASE_TOOL)
    bump_suffix_tree(document.root, new_suffix=6)
    assert document.root.get("version") == "@TOOL_VERSION@+galaxy6"


def test_bump_tree_inline_token_rewrites_token_text() -> None:
    document = _document(_INLINE_TOKEN_TOOL)
    bump_suffix_tree(document.root, new_suffix=4)
    # version= attribute unchanged (still the tokenized form)
    assert document.root.get("version") == "@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"
    token = document.root.find('macros/token[@name="@VERSION_SUFFIX@"]')
    assert token is not None
    assert (token.text or "").strip() == "4"
