"""Tests for the bashlex shell boundary oracle (the ``shell-oracle`` extra).

Exercises the general ``boundary_signature`` (argv partition + full fd topology), the
``quoting_context`` classifier (split / no-split / fd-dup), and the composed
``quote_is_behavior_preserving`` policy the GTR020.1 fixer and GTR020.2 check share.
Skipped wholesale when bashlex is not installed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("bashlex")

from galaxy_tool_xml.command_text import unquoted_cheetah_vars  # noqa: E402
from galaxy_tool_xml.command_vars import input_param_info  # noqa: E402
from galaxy_tool_xml.shell_oracle import (  # noqa: E402
    QuotingContext,
    boundary_signature,
    quote_is_behavior_preserving,
    quoting_context,
    shell_oracle_available,
)


def test_shell_oracle_available() -> None:
    assert shell_oracle_available() is True


def test_boundary_signature_argv_partition() -> None:
    sig = boundary_signature("samtools sort input.bam -o out.bam")
    assert sig is not None
    assert sig.words == ("samtools", "sort", "input.bam", "-o", "out.bam")
    assert sig.redirections == ()


def test_boundary_signature_full_fd_topology() -> None:
    sig = boundary_signature("tool < in > out 2>> err 3> custom 2>&1")
    assert sig is not None
    topology = [(r.src_fd, r.op, r.target, r.is_dup) for r in sig.redirections]
    assert topology == [
        (0, "<", "in", False),
        (1, ">", "out", False),
        (2, ">>", "err", False),
        (3, ">", "custom", False),
        (2, ">&", "&1", True),  # 2>&1 is a descriptor dup, not a file
    ]


def test_boundary_signature_does_not_expand_command_substitution() -> None:
    sig = boundary_signature("echo $(basename foo)")
    assert sig is not None
    # the $(...) interior stays inside its enclosing word, not a top-level arg
    assert sig.words == ("echo", "$(basename foo)")


def test_boundary_signature_unparseable_is_none() -> None:
    assert boundary_signature("[[ $x == y ]]") is None  # bashlex has no [[ ]]
    assert boundary_signature("tool $(( 1 +") is None  # malformed


def test_quoting_context_bare_word_is_split() -> None:
    assert quoting_context("tool --in $T", "T") is QuotingContext.SPLIT


def test_quoting_context_assignment_rhs_is_no_split() -> None:
    assert quoting_context("THREADS=$T", "T") is QuotingContext.NO_SPLIT


def test_quoting_context_fd_dup_target() -> None:
    assert quoting_context("tool 2>&$T", "T") is QuotingContext.DUP_TARGET


def test_quoting_context_redirect_file_target_is_split() -> None:
    # a redirect-to-file target word-splits like any word (safe only if space-free)
    assert quoting_context("tool > $T", "T") is QuotingContext.SPLIT


def test_quoting_context_inside_command_substitution_is_split() -> None:
    assert quoting_context("tool $(basename $T)", "T") is QuotingContext.SPLIT


def test_quoting_context_missing_or_unparseable_is_unknown() -> None:
    assert quoting_context("tool --in $OTHER", "T") is QuotingContext.UNKNOWN
    assert quoting_context("[[ $T == y ]]", "T") is QuotingContext.UNKNOWN


def _root(inputs: bytes) -> object:
    from lxml import etree

    return etree.fromstring(b"<tool><inputs>" + inputs + b"</inputs></tool>")


def _policy(body: str, *, inputs: bytes) -> list[tuple[str, bool]]:
    root = _root(inputs)
    kinds, structural = input_param_info(root)
    return [
        (
            occ.name,
            quote_is_behavior_preserving(
                body, occurrence=occ, kinds=kinds, structural=structural
            ),
        )
        for occ in unquoted_cheetah_vars(body)
    ]


def test_policy_does_not_widen_assignment_rhs() -> None:
    # $opts is a free-form text param. An assignment RHS is a no-split context for a
    # shell *expansion*, but Galaxy renders the Cheetah value as literal text, and a
    # literal `THREADS=foo bar` DOES split — so quoting is NOT behaviour-preserving and
    # the policy must defer to the value-domain rule (text -> not provable -> False).
    inputs = b'<param name="opts" type="text"/>'
    assert _policy("THREADS=$opts", inputs=inputs) == [("$opts", False)]


def test_policy_keeps_value_domain_for_split_position() -> None:
    # same residual text param as a bare command word: still not safe (may split).
    inputs = b'<param name="opts" type="text"/>'
    assert _policy("tool --opt $opts", inputs=inputs) == [("$opts", False)]


def test_policy_does_not_false_veto_glued_safe_var() -> None:
    # a value-domain-safe data param glued to a literal suffix (``${ds}.bam``) stays
    # fixable — the discarded "standalone word" heuristic would wrongly veto this,
    # but quoting a space-free value mid-word is behaviour-preserving.
    inputs = b'<param name="ds" type="data"/>'
    assert _policy("tool ${ds}.bam", inputs=inputs) == [("${ds}", True)]


def test_policy_narrows_fd_dup_even_when_value_domain_safe() -> None:
    inputs = b'<param name="fd" type="integer"/>'
    assert _policy("tool 2>&$fd", inputs=inputs) == [("$fd", False)]
