"""Tests for the cosmetic detect (lint) phase, ``detect_tool_document``."""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_source.document import ToolDocument

from galaxy_tool_xml_fmt.detect import detect_tool_document
from galaxy_tool_xml_fmt.format import format_tool_document

_FLAT = (
    b"<tool id='t' name='T' version='0'>"
    b"<description>D</description>"
    b"<inputs><param name='p' type='text'/></inputs>"
    b"<outputs/>"
    b"</tool>"
)

_WITH_COMMENT = (
    b"<tool id='t' name='T' version='0'>"
    b"<!-- header --><description>D</description>"
    b"<inputs><param name='p' type='text'/></inputs>"
    b"</tool>"
)


def test_canonical_document_reports_no_violations(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """The key invariant: an already-canonical document has zero violations.

    Naively mapping each changing ``Edit`` to a violation over-reports here,
    because GTR001 rewrites top-level-child tails that GTR003 then overrides.
    The net-diff detector must stay silent.
    """
    canonical_bytes = format_tool_document(make_doc(_FLAT))
    assert detect_tool_document(make_doc(canonical_bytes)) == []


def test_flat_document_reports_indent_and_blank_line_violations(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """A flat, unformatted document flags GTR001 (indent) and GTR003 (blank line)."""
    violations = detect_tool_document(make_doc(_FLAT))
    codes = {violation.code for violation in violations}
    assert "GTR001" in codes
    assert "GTR003" in codes
    # Every violation is located on the source tree.
    assert all(violation.xpath.startswith("/tool") for violation in violations)
    assert all(violation.sourceline >= 1 for violation in violations)


def test_whitespace_only_leaf_reports_gtx004(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """A whitespace-only leaf is reported at its xpath, owned by GTR004.

    (The ``<tool>`` root also picks up a GTR001 child-indent violation; the leaf
    itself is the GTR004 one.)
    """
    payload = b"<tool id='t' name='T' version='0'><inputs>  </inputs></tool>"
    violations = detect_tool_document(make_doc(payload))
    by_xpath = {violation.xpath: violation for violation in violations}
    assert by_xpath["/tool/inputs"].code == "GTR004"


def test_detect_does_not_mutate_the_input(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """Detection works on a copy; the input document's tree is untouched."""
    document = make_doc(_FLAT)
    before = document.root.find("description").tail
    detect_tool_document(document)
    assert document.root.find("description").tail == before


def test_violation_message_is_the_owning_rules_summary(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """Each violation carries its owning rule's one-line summary as the message."""
    violations = detect_tool_document(make_doc(_FLAT))
    by_code = {violation.code: violation for violation in violations}
    assert by_code["GTR001"].message == "Canonical 4-space indentation; no tabs."
    assert (
        by_code["GTR003"].message
        == "One blank line between top-level children of <tool>."
    )


def test_canonical_document_with_comment_reports_no_violations(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """Comments must not false-positive on a canonical doc.

    GTR001/GTR003 rewrite a comment's *tail*, so a comment-bearing canonical
    document must still report zero violations (regression guard: detect once
    missed comment tails, disagreeing with format on bimib/cobraxy).
    """
    canonical_bytes = format_tool_document(make_doc(_WITH_COMMENT))
    assert detect_tool_document(make_doc(canonical_bytes)) == []


def test_detects_missing_blank_line_on_top_level_comment(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """A top-level comment lacking the blank line after it is flagged (GTR003)."""
    violations = detect_tool_document(make_doc(_WITH_COMMENT))
    comment_violations = [v for v in violations if "comment()" in v.xpath]
    assert comment_violations
    assert all(violation.code == "GTR003" for violation in comment_violations)
