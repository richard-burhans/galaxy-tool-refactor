"""Tests for the forward gate's suggest mode core (scripts/gate_suggest.py).

Synthetic and pure: the tricky, testable part is turning an original->canonical
line diff into GitHub one-click suggestions, posting only where the lines are
inside the PR's diff (eligible). The git/gh integration (collect/post_review) is
exercised live, not here.
"""

from __future__ import annotations

from scripts.gate_suggest import (
    Suggestion,
    _comment,
    build_suggestions,
    review_payload,
)


def test_replace_within_eligible_lines_makes_one_suggestion() -> None:
    original = "a\n  X\nb\n"   # line 2 is non-canonical
    canonical = "a\nX\nb\n"
    suggestions, skipped = build_suggestions(
        "tools/t/t.xml", original, canonical, eligible={1, 2, 3}
    )
    assert skipped == 0
    assert suggestions == [Suggestion("tools/t/t.xml", 2, 2, ["X"])]


def test_change_outside_the_diff_is_skipped_not_suggested() -> None:
    original = "a\n  X\nb\n"
    canonical = "a\nX\nb\n"
    # Line 2 changed, but it is not part of the PR's diff -> cannot be inlined.
    suggestions, skipped = build_suggestions(
        "tools/t/t.xml", original, canonical, eligible={1, 3}
    )
    assert suggestions == []
    assert skipped == 1


def test_deletion_yields_empty_suggestion() -> None:
    original = "a\nb\nc\n"
    canonical = "a\nc\n"  # line 2 deleted
    suggestions, _ = build_suggestions(
        "tools/t/t.xml", original, canonical, eligible={1, 2, 3}
    )
    assert suggestions == [Suggestion("tools/t/t.xml", 2, 2, [])]


def test_multiline_replace_spans_the_range() -> None:
    original = "a\nP\nQ\nd\n"
    canonical = "a\nX\nY\nZ\nd\n"  # lines 2-3 replaced by 3 lines
    suggestions, skipped = build_suggestions(
        "tools/t/t.xml", original, canonical, eligible={1, 2, 3, 4}
    )
    assert skipped == 0
    assert suggestions == [Suggestion("tools/t/t.xml", 2, 3, ["X", "Y", "Z"])]


def test_comment_single_vs_multiline_and_delete_body() -> None:
    single = _comment(Suggestion("p", 5, 5, ["new"]))
    assert single["line"] == 5 and "start_line" not in single
    assert single["body"] == "```suggestion\nnew\n```"

    multi = _comment(Suggestion("p", 2, 4, ["a", "b"]))
    assert multi["start_line"] == 2 and multi["line"] == 4
    assert multi["side"] == "RIGHT" and multi["start_side"] == "RIGHT"

    delete = _comment(Suggestion("p", 7, 7, []))
    assert delete["body"] == "```suggestion\n```"  # empty suggestion = delete


def test_review_payload_is_a_comment_review_with_fix_command() -> None:
    payload = review_payload(
        [Suggestion("tools/t/t.xml", 2, 2, ["X"])], 1, codes=frozenset({"GTR001"})
    )
    assert payload["event"] == "COMMENT"
    assert len(payload["comments"]) == 1
    body = payload["body"]
    assert "format --select GTR001" in body
    assert "Commit suggestion" in body
    assert "cannot be inlined" in body  # the skipped note
