"""Tests for reStructuredText validity + the surgical <help> repair."""

from __future__ import annotations

from galaxy_tool_xml.rst import repair_help_rst, rst_is_invalid


def test_valid_rst_is_not_invalid() -> None:
    assert not rst_is_invalid(
        "Title\n=====\n\nA paragraph with **bold**.\n\n- a\n- b\n"
    )


def test_invalid_rst_is_detected() -> None:
    assert rst_is_invalid("A paragraph.\n\n----\n")  # transition at end


def test_repair_is_none_on_valid_help() -> None:
    assert repair_help_rst("Title\n=====\n\nA paragraph.\n") is None


def test_repair_is_none_on_non_fixable() -> None:
    # Unclosed inline markup has no deterministic fix -> left for GTR089.2.
    assert repair_help_rst("text with **unclosed strong\n") is None


def test_repair_does_not_drop_a_trailing_transition() -> None:
    # docutils renders a trailing `----` as an <hr>, so dropping it would change the
    # rendered help — the behaviour gate vetoes it (left for the GTR089.2 residual).
    assert repair_help_rst("A paragraph.\n\n----\n") is None


def test_repair_title_underline_too_short() -> None:
    repaired = repair_help_rst("Section Title\n=====\n\nbody text here\n")
    assert repaired is not None
    assert "=============" in repaired  # extended to the 13-char title length
    assert not rst_is_invalid(repaired)


def test_repair_block_ends_without_blank_line() -> None:
    source = "Intro:\n\n    a quoted line\nnext paragraph at margin\n"
    repaired = repair_help_rst(source)
    assert repaired is not None
    assert not rst_is_invalid(repaired)


def test_repair_is_idempotent() -> None:
    source = "Section Title\n=====\n\nbody text here\n"
    once = repair_help_rst(source)
    assert once is not None
    # The repaired text is a fixpoint: repairing it again finds nothing to do.
    assert repair_help_rst(once) is None


def test_repair_preserves_content() -> None:
    repaired = repair_help_rst("Section Title\n=====\n\nbody text here\n")
    assert repaired is not None
    # The fix only touched the underline; the title and body text survive verbatim.
    assert "Section Title" in repaired
    assert "body text here" in repaired
