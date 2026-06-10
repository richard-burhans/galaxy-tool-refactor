"""Tests for the RST -> CommonMark <help> conversion + render-equivalence gate."""

from __future__ import annotations

from galaxy_tool_xml.rst_markdown import (
    conversion_is_render_equivalent,
    convert_help_rst,
    markdown_renderer_available,
    rst_to_commonmark,
)


def test_markdown_renderer_is_available_in_dev() -> None:
    # markdown-it-py is a dev dependency, so the gate is live in CI.
    assert markdown_renderer_available()


def test_rst_to_commonmark_converts_the_whitelist() -> None:
    markdown, bail = rst_to_commonmark(
        "Title\n=====\n\nSome *em* and ``code``.\n\n- a\n- b\n"
    )
    assert bail is None
    assert markdown is not None
    assert "# Title" in markdown
    assert "*em*" in markdown
    assert "`code`" in markdown
    assert "- a" in markdown


def test_rst_to_commonmark_converts_links_and_blocks() -> None:
    markdown, bail = rst_to_commonmark(
        "A `link <https://example.org>`_ here.\n\n::\n\n    literal block\n"
    )
    assert bail is None
    assert markdown is not None
    assert "[link](https://example.org)" in markdown
    assert "```" in markdown


def test_rst_to_commonmark_bails_on_non_commonmark_nodes() -> None:
    markdown, bail = rst_to_commonmark("A paragraph.\n\n:field: value\n")
    assert markdown is None
    assert bail == "field_list"
    markdown, bail = rst_to_commonmark("term\n   the definition\n")
    assert markdown is None
    assert bail == "definition_list"


def test_gate_accepts_a_faithful_conversion() -> None:
    rst = "Some **strong** text.\n"
    markdown, bail = rst_to_commonmark(rst)
    assert bail is None and markdown is not None
    assert conversion_is_render_equivalent(rst, markdown)


def test_gate_rejects_corrupted_conversions() -> None:
    """Negative control: semantically-different conversions must be rejected."""
    rst = "Some **strong** text.\n"
    markdown, _bail = rst_to_commonmark(rst)
    assert markdown is not None
    assert not conversion_is_render_equivalent(
        rst, markdown.replace("**strong**", "*strong*")
    )
    assert not conversion_is_render_equivalent(
        rst, markdown.replace("**strong** ", "")
    )
    assert not conversion_is_render_equivalent(
        rst, markdown.replace("**strong**", "strong")
    )


def test_convert_help_rst_valid_body() -> None:
    converted = convert_help_rst("Title\n=====\n\nA paragraph with **bold**.\n")
    assert converted is not None
    assert "# Title" in converted
    assert "**bold**" in converted


def test_convert_help_rst_returns_none_on_bail() -> None:
    # definition lists have no CommonMark form
    assert convert_help_rst("term\n   the definition\n") is None


def test_convert_help_rst_returns_none_on_gate_fail() -> None:
    # an RST literal containing a backtick cannot survive the single-backtick
    # CommonMark code span the converter emits -> renders differently -> rejected
    assert convert_help_rst("A paragraph with a ``lit`eral`` span.\n") is None


def test_convert_help_rst_repairs_then_converts() -> None:
    # invalid RST (short title underline) that the GTR089.1 repair can fix; the
    # conversion composes repair -> convert -> gate, so it succeeds.
    converted = convert_help_rst("Long Title\n====\n\nA paragraph.\n")
    assert converted is not None
    assert "# Long Title" in converted


def test_convert_help_rst_returns_none_on_unrepairable_invalid() -> None:
    # unclosed inline markup is not deterministically repairable
    assert convert_help_rst("some **unclosed strong text\n") is None
