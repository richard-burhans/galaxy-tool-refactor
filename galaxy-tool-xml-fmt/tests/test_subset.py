"""Tests for the per-rule subset variants of format / detect.

The rule-selection facade (``galaxy-tool-refactor-registry``) drives a single
fmt rule at a time through ``format_tool_document_subset`` /
``detect_tool_document_subset``; the whole-pipeline functions are these called
with ``all_rules()``.
"""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_source.binding import load_macros
from galaxy_tool_source.document import ToolDocument

from galaxy_tool_xml_fmt.detect import (
    detect_tool_document,
    detect_tool_document_subset,
)
from galaxy_tool_xml_fmt.format import (
    all_rules,
    format_macro_document,
    format_tool_document,
    format_tool_document_subset,
    rules_for_kind,
)
from galaxy_tool_xml_fmt.rule_blank_line import BlankLineBetweenSections
from galaxy_tool_xml_fmt.rule_empty_element import EmptyElementShorthand
from galaxy_tool_xml_fmt.rule_indent import CanonicalIndent
from galaxy_tool_xml_fmt.serializer import to_bytes

_FLAT = (
    b"<tool id='t' name='T' version='0'>"
    b"<description>D</description>"
    b"<inputs><param name='p' type='text'/></inputs>"
    b"<outputs/>"
    b"</tool>"
)


def test_subset_with_all_rules_equals_whole_pipeline(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """The full subset reproduces ``format_tool_document`` byte-for-byte."""
    whole = format_tool_document(make_doc(_FLAT))
    subset = format_tool_document_subset(make_doc(_FLAT), rule_classes=all_rules())
    assert subset == whole


def test_empty_subset_serialises_unchanged(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """No rules selected → only serialisation, no whitespace rewrite."""
    doc = make_doc(_FLAT)
    # Serialising the untouched tree is what an empty selection must equal.
    expected = to_bytes(doc.tree)
    out = format_tool_document_subset(make_doc(_FLAT), rule_classes=())
    assert out == expected


def test_subset_runs_in_meta_order_regardless_of_input_order(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """Passing rules out of order yields the same bytes as in-order (order-locked)."""
    ordered = format_tool_document_subset(
        make_doc(_FLAT), rule_classes=(CanonicalIndent, BlankLineBetweenSections)
    )
    reversed_ = format_tool_document_subset(
        make_doc(_FLAT), rule_classes=(BlankLineBetweenSections, CanonicalIndent)
    )
    assert ordered == reversed_


def test_detect_subset_with_all_rules_equals_whole_pipeline(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """The full detect subset reproduces ``detect_tool_document``."""
    whole = detect_tool_document(make_doc(_FLAT))
    subset = detect_tool_document_subset(make_doc(_FLAT), rule_classes=all_rules())
    assert subset == whole


def test_detect_single_rule_subset_reports_only_that_code(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """Selecting only the blank-line rule reports GTR003 and not GTR001."""
    violations = detect_tool_document_subset(
        make_doc(_FLAT), rule_classes=(BlankLineBetweenSections,)
    )
    codes = {violation.code for violation in violations}
    assert codes == {"GTR003"}


def test_rules_for_kind_filters_by_applies_to() -> None:
    # Every active rule applies to tools; macros get the generic XML rules only
    # (GTR001 indent, GTR004 shorthand) — not the tool-only blank-line rule.
    assert set(rules_for_kind("tool")) == set(all_rules())
    assert set(rules_for_kind("macro")) == {CanonicalIndent, EmptyElementShorthand}
    assert BlankLineBetweenSections not in rules_for_kind("macro")


def test_format_macro_document_indents_and_shorthands() -> None:
    document = load_macros(
        b'<macros><token name="@TOOL_VERSION@">1.0</token><thing></thing></macros>'
    )
    out = format_macro_document(document)
    # GTR001: children indented under <macros>.
    assert b'\n    <token name="@TOOL_VERSION@">1.0</token>\n' in out
    # GTR004: the empty <thing></thing> collapses to <thing/>.
    assert b"<thing/>" in out
