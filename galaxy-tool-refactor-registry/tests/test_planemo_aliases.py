"""Tests for the planemo-linter alias index and name-based selection."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from galaxy_tool_refactor_registry import facade
from galaxy_tool_refactor_registry.errors import UnknownRuleCode
from galaxy_tool_refactor_registry.planemo import planemo_index
from galaxy_tool_refactor_registry.resolve import resolve_codes

# Every Linter subclass in galaxy.tool_util.linters at the clone commit the parity
# roadmap is keyed to (c6e0ee3, 2026-06-01) — the canonical universe the aliases and
# the parity Summary count against. Regenerate by re-running the AST scan in
# docs/planemo_linter_parity.md's source note if the roadmap is re-keyed.
_CANONICAL_LINTERS = Path(__file__).resolve().parent / "data" / (
    "planemo_linters_c6e0ee3.txt"
)
_PARITY_DOC = (
    Path(__file__).resolve().parents[2] / "docs" / "planemo_linter_parity.md"
)

# Linters the parity roadmap marks HAVE with deliberately no metadata alias: XSD is
# covered by tier-1 ``validate_tool``, which is not a selectable rule.
_ALIAS_FREE_HAVE = frozenset({"XSD"})

# Aliased linters the roadmap does NOT count as HAVE. Empty since GTR098/GTR099
# (ValidDatatypes / DatatypesCustomConf) landed as faithful detect rules — both are
# now genuine HAVE (galaxy-tool-lint checks/datatypes.py).
_ALIASED_NOT_HAVE: frozenset[str] = frozenset()


def _canonical_names() -> frozenset[str]:
    lines = _CANONICAL_LINTERS.read_text(encoding="utf-8").splitlines()
    return frozenset(line for line in lines if line)


def test_index_maps_planemo_names_to_covering_codes() -> None:
    index = planemo_index()
    # A single-linter rule.
    assert index["outputsmissing"] == {"GTR048"}
    # A bundled rule: both planemo names of GTR028 resolve to it.
    assert index["helpmissing"] == {"GTR028"}
    assert index["helpempty"] == {"GTR028"}


def test_select_by_planemo_name() -> None:
    assert resolve_codes(select=["HelpMissing"]) == {"GTR028"}


def test_select_by_planemo_name_is_case_insensitive() -> None:
    assert resolve_codes(select=["helpmissing"]) == {"GTR028"}
    assert resolve_codes(select=["HELPMISSING"]) == {"GTR028"}


def test_select_a_bundle_name_selects_the_whole_covering_rule() -> None:
    # GTR027 covers EDAMTermsValid + BioToolsValid; either name selects GTR027.
    assert resolve_codes(select=["EDAMTermsValid"]) == {"GTR027"}
    assert resolve_codes(select=["BioToolsValid"]) == {"GTR027"}


def test_ignore_by_planemo_name_subtracts_from_the_base() -> None:
    strict = resolve_codes(rulesets=["strict"])
    assert "GTR027" in strict
    assert resolve_codes(rulesets=["strict"], ignore=["EDAMTermsValid"]) == strict - {
        "GTR027"
    }


def test_select_mixes_codes_and_planemo_names() -> None:
    assert resolve_codes(select=["GTR001", "HelpMissing"]) == {"GTR001", "GTR028"}


def test_unknown_planemo_name_raises() -> None:
    with pytest.raises(UnknownRuleCode):
        resolve_codes(select=["NotARealLinter"])


def test_rule_info_carries_planemo_linters() -> None:
    rules = {r.code: r for r in facade.list_rules()}
    assert rules["GTR028"].planemo_linters == ("HelpEmpty", "HelpMissing")
    # An own-rule with no planemo equivalent.
    assert rules["GTR001"].planemo_linters == ()


def test_every_alias_is_a_canonical_planemo_linter() -> None:
    """Typo guard: each ``planemo_linters`` name is a real planemo Linter class."""
    canonical_lower = {name.lower() for name in _canonical_names()}
    unknown = set(planemo_index()) - canonical_lower
    assert not unknown, f"aliases naming no planemo Linter class: {sorted(unknown)}"


def test_parity_summary_have_count_matches_metadata() -> None:
    """The hand-maintained Summary HAVE count is derivable from rule metadata.

    HAVE = aliased canonical linters − the aliased-but-not-HAVE exceptions + the
    alias-free HAVE allowlist. Fails when an alias lands without the Summary being
    updated (or vice versa), naming both figures.
    """
    canonical = _canonical_names()
    aliased = {name for name in canonical if name.lower() in planemo_index()}
    assert aliased >= _ALIASED_NOT_HAVE
    assert not _ALIAS_FREE_HAVE & aliased
    assert canonical >= _ALIAS_FREE_HAVE
    expected_have = len(aliased) - len(_ALIASED_NOT_HAVE) + len(_ALIAS_FREE_HAVE)

    text = _PARITY_DOC.read_text(encoding="utf-8")
    have_row = re.search(r"\| \*\*HAVE\*\* \| (\d+) \|", text)
    total_row = re.search(r"\| \*\*Total\*\* \| (\d+) \|", text)
    assert have_row is not None and total_row is not None, "Summary rows missing"
    assert int(total_row.group(1)) == len(canonical)
    assert int(have_row.group(1)) == expected_have, (
        f"parity Summary says HAVE={have_row.group(1)} but rule metadata derives "
        f"{expected_have} — update docs/planemo_linter_parity.md's Summary (or the "
        "exception sets in this test) when planemo_linters aliases change"
    )


def test_parity_summary_note_names_every_exception() -> None:
    """The Summary's derivation note must name each exception-set linter.

    The HAVE count test above pins the *number*; this pins the *prose* — the
    blockquote note explaining the derivation must mention every member of
    ``_ALIASED_NOT_HAVE`` / ``_ALIAS_FREE_HAVE``, so a reader can reconcile the
    count without opening this test file.
    """
    text = _PARITY_DOC.read_text(encoding="utf-8")
    note = re.search(
        r"^> \*\*Alias-reconciled[^\n]*(?:\n>[^\n]*)*",
        text,
        re.MULTILINE,
    )
    assert note is not None, "the Summary derivation note is missing"
    for name in sorted(_ALIASED_NOT_HAVE | _ALIAS_FREE_HAVE):
        assert f"`{name}`" in note.group(0), (
            f"the parity Summary derivation note no longer names the exception "
            f"{name!r} — update docs/planemo_linter_parity.md (or the exception "
            "sets in this test)"
        )
