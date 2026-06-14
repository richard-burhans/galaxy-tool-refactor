"""Tests for ``.lint_skip`` parsing and the provable-removal coverage gate."""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_refactor_registry.lint_skip import (
    LintSkipLine,
    _complete_coverage_codes,
    covering_codes,
    is_completely_covered,
    lint_skip_path,
    parse_lint_skip,
)


def test_parse_preserves_every_line_and_classifies_names() -> None:
    text = "# a comment\nTestsMissing\n\nCitationsMissing  # inline\n   \n"
    lines = parse_lint_skip(text)
    assert lines == [
        LintSkipLine(raw="# a comment", name=None),
        LintSkipLine(raw="TestsMissing", name="TestsMissing"),
        LintSkipLine(raw="", name=None),
        LintSkipLine(raw="CitationsMissing  # inline", name="CitationsMissing"),
        LintSkipLine(raw="   ", name=None),
    ]


def test_parse_round_trips_unknown_lines_verbatim() -> None:
    # A name we do not recognise is still a name-line (raw preserved for rewrite).
    lines = parse_lint_skip("SomeFutureLinter\n")
    assert lines == [LintSkipLine(raw="SomeFutureLinter", name="SomeFutureLinter")]


def test_lint_skip_path_is_the_dir_sidecar() -> None:
    assert lint_skip_path(Path("tools/vg/view.xml")) == Path("tools/vg/.lint_skip")


def test_covering_codes_is_case_insensitive() -> None:
    assert covering_codes("helpinvalidrst") == covering_codes("HelpInvalidRST")
    assert covering_codes("HelpInvalidRST")  # non-empty: we cover it


def test_uncovered_name_is_not_completely_covered() -> None:
    # TestsCaseValidation is bound (GTR101) behind the opt-in [test-validation]
    # extra, so it is *covered* (selectable by name) but NOT a proof-of-clean for
    # suppression removal — its clean state is conditional on the extra being
    # installed, so is_completely_covered must stay False.
    assert covering_codes("TestsCaseValidation") == frozenset({"GTR101"})
    assert not is_completely_covered("TestsCaseValidation")


def test_check_tier_and_canonical_codes_are_complete() -> None:
    # CitationsNoValid -> GTR038 (check-tier port); HelpInvalidRST -> GTR089.1
    # (canonical codemod) + GTR089.2 (check residual). Both faithfully covered.
    assert is_completely_covered("CitationsNoValid")
    assert is_completely_covered("HelpInvalidRST")
    assert is_completely_covered("XMLOrder")  # GTR013 canonical
    # The datatypes pair landed as faithful check-tier ports (GTR098/GTR099).
    assert is_completely_covered("ValidDatatypes")
    assert is_completely_covered("DatatypesCustomConf")


def test_incidental_upgrade_codemod_coverage_is_not_complete() -> None:
    # OutputsFormatInput is covered only by GTR015, a runtime-gated upgrade codemod
    # that reaches only the single-top-level-data-input case (so it does not prove
    # the linter passes) — never provably removable.
    assert "GTR015" in covering_codes("OutputsFormatInput")
    assert "GTR015" not in _complete_coverage_codes()
    assert not is_completely_covered("OutputsFormatInput")
