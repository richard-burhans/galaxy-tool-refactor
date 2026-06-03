"""Tests for the GTR-coded codemod catalog."""

from __future__ import annotations

from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS
from galaxy_tool_xml_codemod.catalog import coded_codemods

_EXPECTED_CODES = {
    "GTR002",  # ReorderParamAttributes
    "GTR005",  # ReorderToolAttributes
    "GTR006",  # FixTypos
    "GTR007",  # UpdateProfile
    "GTR008",  # Upgrade19_01
    "GTR009",  # Upgrade24_0
    "GTR010",  # Upgrade24_1
    "GTR011",  # Upgrade25_1
    "GTR012",  # UpgradeToLatest
    "GTR013",  # ReorderToolChildren
    "GTR014",  # FixFromWorkDirWhitespace (runtime-gated)
    "GTR015",  # FixOutputFormatInput (runtime-gated)
    "GTR016",  # FixInterpreter (runtime-gated)
    "GTR017",  # NormalizeBooleanValues
    "GTR018",  # WrapCommandCdata
    "GTR019",  # WrapHelpCdata
    "GTR020",  # SingleQuoteCommandVars
}


def test_every_coded_codemod_carries_a_gtr_code() -> None:
    codes = [cls.meta.code for cls in coded_codemods()]
    assert all(code.startswith("GTR") for code in codes)


def test_catalog_codes_match_expected_set() -> None:
    assert {cls.meta.code for cls in coded_codemods()} == _EXPECTED_CODES


def test_catalog_codes_are_unique() -> None:
    codes = [cls.meta.code for cls in coded_codemods()]
    assert len(codes) == len(set(codes))


def test_catalog_is_sorted_by_code() -> None:
    codes = [cls.meta.code for cls in coded_codemods()]
    assert codes == sorted(codes)


def test_every_canonical_codemod_is_in_the_catalog() -> None:
    catalog = set(coded_codemods())
    assert set(CANONICAL_CODEMODS) <= catalog


def test_every_codemod_is_tool_only() -> None:
    """Codemods run on tool files only (`applies_to={"tool"}`). Macro handling is
    cosmetic-only in v1 (ARCHITECTURE.md §9; codemod `docs/decisions.md` §20), so a
    macro-applicable codemod must opt in *explicitly* — this guards against one
    landing on the `RuleMeta` default and silently mutating macro files."""
    for cls in coded_codemods():
        assert cls.meta.applies_to == frozenset({"tool"}), cls.meta.code
