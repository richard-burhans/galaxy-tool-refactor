"""Tests for the auto-fix gate-eligibility classification (gate_eligibility.py).

Covers the classification logic (detect-only → advisory; each fixable rule's
bucket; the guard that an unclassified fixable rule raises) and a freshness guard
that the committed ``docs/gate_eligibility.md`` block equals the generated output.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from galaxy_tool_refactor_registry.gate_eligibility import (
    _FIXABLE_BUCKETS,
    ADVISORY_ONLY,
    BEGIN_MARKER,
    BLOCKED_PENDING_IUC,
    BUCKET_ORDER,
    BULK_ELIGIBLE_ONLY,
    END_MARKER,
    GATE_ELIGIBLE,
    classify,
    eligibility_groups,
    render_eligibility_table,
)
from galaxy_tool_refactor_registry.registry import registry

_DOC = Path(__file__).resolve().parents[2] / "docs" / "gate_eligibility.md"


def test_every_registered_rule_classifies() -> None:
    # eligibility_groups() classifies every rule without raising, and partitions
    # them exactly (each code in one bucket, totals add up).
    groups = eligibility_groups()
    assert set(groups) == set(BUCKET_ORDER)
    all_codes = [code for bucket in BUCKET_ORDER for code in groups[bucket]]
    assert sorted(all_codes) == sorted(registry())
    assert len(all_codes) == len(set(all_codes))  # no code in two buckets


def test_detect_only_rules_are_advisory() -> None:
    for handle in registry().values():
        if handle.meta.detect_only:
            assert classify(handle) == ADVISORY_ONLY


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("GTR001", GATE_ELIGIBLE),  # cited whitespace
        ("GTR020.1", GATE_ELIGIBLE),  # cited quoting
        ("GTR006", GATE_ELIGIBLE),  # uncited validity repair
        ("GTR017", GATE_ELIGIBLE),  # uncited validity repair
        ("GTR004", BULK_ELIGIBLE_ONLY),  # uncited style
        ("GTR002", BLOCKED_PENDING_IUC),  # contested param attrs
        ("GTR005", BLOCKED_PENDING_IUC),  # contested tool attrs
    ],
)
def test_fixable_rule_buckets(code: str, expected: str) -> None:
    assert classify(registry()[code]) == expected


def test_fixable_buckets_cover_exactly_the_fixable_rules() -> None:
    # Every fixable rule is classified and no stale entries linger: the data-level
    # invariant behind the classify() guard.
    fixable = {code for code, handle in registry().items() if handle.fixable}
    assert set(_FIXABLE_BUCKETS) == fixable


def test_unclassified_fixable_rule_raises() -> None:
    # A fixable rule with no entry in _FIXABLE_BUCKETS must raise, so nothing
    # silently defaults into a half of the auto-fix system.
    handle = SimpleNamespace(meta=SimpleNamespace(detect_only=False, code="GTR999"))
    with pytest.raises(KeyError):
        classify(handle)


def test_eligibility_table_block_is_fresh() -> None:
    text = _DOC.read_text(encoding="utf-8")
    assert BEGIN_MARKER in text and END_MARKER in text, "markers missing"
    begin = text.index(BEGIN_MARKER)
    end = text.index(END_MARKER) + len(END_MARKER)
    committed = text[begin:end]
    expected = f"{BEGIN_MARKER}\n{render_eligibility_table()}\n{END_MARKER}"
    assert committed == expected, (
        "docs/gate_eligibility.md table is stale — regenerate with "
        "`uv run python -m scripts.gen_gate_eligibility`"
    )
