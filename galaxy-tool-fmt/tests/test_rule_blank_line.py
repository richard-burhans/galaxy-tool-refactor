"""Tests for GTR003 (BlankLineBetweenSections), the PARKED blank-line rule.

GTR003 is suspended pending IUC input on whether the blank-line-between-top-level-
sections convention is wanted (fmt ``docs/decisions.md`` §D4;
``../../docs/iuc_conference_questions.md`` §4). It is **not** in ``all_rules()``, so
``format`` no longer emits blank lines. These tests apply the rule **in isolation**
(via the private ``_apply_rules``) so the implementation stays proven-working for a
one-line re-enable.
"""

from __future__ import annotations

from collections.abc import Callable

from galaxy_tool_source.document import ToolDocument

from galaxy_tool_fmt.format import _apply_rules, all_rules
from galaxy_tool_fmt.rule_blank_line import BlankLineBetweenSections


def _blank_line_only(document: ToolDocument) -> bytes:
    """Serialise *document* after applying ONLY the parked GTR003 rule."""
    return _apply_rules(document.tree, (BlankLineBetweenSections,))


def test_gtr003_is_parked_out_of_all_rules() -> None:
    # The guard for the suspension: format must not run the blank-line rule.
    assert BlankLineBetweenSections not in all_rules()


def test_rule_inserts_blank_line_between_top_level_children(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = (
        b"<tool id='t' name='T' version='0'>"
        b"<description>D</description>"
        b"<inputs><param name='p' type='text'/></inputs>"
        b"</tool>"
    )
    output = _blank_line_only(make_doc(payload))
    # The rule sets each non-last top-level child's tail to a blank line + indent.
    assert b"</description>\n\n    <inputs>" in output
    # Exactly one boundary here, so exactly one inserted blank line.
    assert output.count(b"\n\n") == 1


def test_rule_is_noop_for_single_top_level_child(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    payload = b"<tool id='t' name='T' version='0'><description>D</description></tool>"
    output = _blank_line_only(make_doc(payload))
    assert b"\n\n" not in output


def test_rule_skips_non_tool_root(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    output = _blank_line_only(make_doc(b"<other><child/><child/></other>"))
    assert b"\n\n" not in output
