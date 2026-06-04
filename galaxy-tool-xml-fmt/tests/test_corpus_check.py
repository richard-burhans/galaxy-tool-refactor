"""Unit tests for the corpus runner's internal helpers.

``scripts/corpus_check.py`` is maintainer tooling, but the
``PROVENANCE.md`` round-trip — write entries with
``_append_provenance`` and re-discover them with
``_fmt_known_fixture_paths`` — is load-bearing for "don't re-retain
already-known fixtures". Locking it in here catches regressions
without needing a slow corpus sweep.
"""

from __future__ import annotations

from pathlib import Path

import scripts.corpus_check as corpus_check
from galaxy_tool_xml.profiles import latest_profile
from galaxy_tool_xml_codemod.catalog import coded_codemods

from galaxy_tool_xml_fmt.format import all_rules


def test_provenance_round_trip(tmp_path: Path) -> None:
    """Writing entries and re-parsing them must yield the same paths."""
    fake_regressions = tmp_path / "regressions"
    fake_regressions.mkdir()
    entries = [
        ("fixture-a", "repo-x", Path("tools/a/tool.xml"), "abc123def4567890", "sig:1"),
        ("fixture-b", "repo-y", Path("tools/b/tool.xml"), "789abcdef0123456", "sig:2"),
    ]
    corpus_check._append_provenance(entries, regressions_dir=fake_regressions)
    known = corpus_check._fmt_known_fixture_paths(regressions_dir=fake_regressions)
    assert known == {
        ("repo-x", "tools/a/tool.xml"),
        ("repo-y", "tools/b/tool.xml"),
    }


def test_provenance_handles_missing_file(tmp_path: Path) -> None:
    """A non-existent PROVENANCE.md returns the empty set, not an error."""
    fake_regressions = tmp_path / "regressions"
    fake_regressions.mkdir()
    known = corpus_check._fmt_known_fixture_paths(regressions_dir=fake_regressions)
    assert known == set()


def test_provenance_append_to_existing_does_not_duplicate(tmp_path: Path) -> None:
    """A second append after writing existing entries adds without rewriting."""
    fake_regressions = tmp_path / "regressions"
    fake_regressions.mkdir()
    corpus_check._append_provenance(
        [("fix-a", "repo-x", Path("a/t.xml"), "deadbeef0000", "sig:a")],
        regressions_dir=fake_regressions,
    )
    corpus_check._append_provenance(
        [("fix-b", "repo-x", Path("b/t.xml"), "deadbeef1111", "sig:b")],
        regressions_dir=fake_regressions,
    )
    known = corpus_check._fmt_known_fixture_paths(regressions_dir=fake_regressions)
    assert known == {("repo-x", "a/t.xml"), ("repo-x", "b/t.xml")}


def test_signature_includes_exception_type_and_deepest_frame() -> None:
    """``_signature`` must dedup crashes by exc type + deepest frame."""
    try:
        raise ValueError("boom")
    except ValueError as exc:
        signature = corpus_check._signature(exc)
    assert signature.startswith("ValueError @ ")
    assert "test_corpus_check.py" in signature


def _reference_table_codes() -> list[str]:
    """The rule codes listed in the generated reference table, in row order."""
    rows = corpus_check._fmt_format_rule_reference_table()
    return [line.split("|")[1].strip() for line in rows if line.startswith("| GTR")]


def test_reference_table_covers_every_rule_across_both_tiers() -> None:
    """Every fmt rule and every coded codemod appears in the reference table."""
    expected = {cls.meta.code for cls in all_rules()} | {
        cls.meta.code for cls in coded_codemods()
    }
    assert set(_reference_table_codes()) == expected


def test_gtr_codes_are_globally_unique_across_tiers() -> None:
    """A GTR code must identify exactly one rule across fmt + codemod."""
    codes = [cls.meta.code for cls in all_rules()]
    codes += [cls.meta.code for cls in coded_codemods()]
    assert len(codes) == len(set(codes))


def test_reference_table_sits_above_the_trigger_tables() -> None:
    """The glossary heading must precede the Pass 1 trigger heading."""
    rows = corpus_check._fmt_format_rule_reference_table()
    assert rows[0] == "## Rule reference"
    # codemod-tier rows are reference-only; the intro must say so.
    assert any("do not appear in the trigger tables" in line for line in rows)


def test_rule_stats_fmt_table_renders_a_row() -> None:
    """The per-rule isolation fmt table renders code + counts, sorted by code."""
    sweeps = [
        corpus_check._FmtRuleSweep(code="GTR003", validated=10, touched=10, edits=42),
        corpus_check._FmtRuleSweep(
            code="GTR001", validated=10, touched=10, edits=99, non_idempotent=1
        ),
    ]
    table = corpus_check._rule_format_fmt_table(sweeps)
    codes = [line.split("|")[1].strip() for line in table if line.startswith("| GTR")]
    assert codes == ["GTR001", "GTR003"]  # sorted by code
    assert any("| GTR001 |" in line and "| 99 |" in line for line in table)


def test_rule_stats_page_has_reference_table_above_isolation_tables() -> None:
    """The GTR glossary must precede both isolated-rule tables."""
    lines = corpus_check._rule_stats_lines(
        profile="26.1",
        source="combined",
        fmt_sweeps=[corpus_check._FmtRuleSweep(code="GTR001", validated=1)],
        codemod_rows=[
            ("GTR002", "ReorderParamAttributes", corpus_check._CodemodSweepState())
        ],
        upgrade_state=None,
    )
    ref = lines.index("## Rule reference")
    fmt_tbl = lines.index("## fmt rules (isolated)")
    codemod_tbl = lines.index("## codemods (isolated)")
    assert ref < fmt_tbl < codemod_tbl
    expected = {cls.meta.code for cls in all_rules()} | {
        cls.meta.code for cls in coded_codemods()
    }
    glossary = "\n".join(lines[ref:fmt_tbl])
    assert all(code in glossary for code in expected)


def test_rule_stats_upgrade_discovery_lists_sticking_points() -> None:
    """UpgradeToLatest's isolated discovery shows reach + sticking-point rows."""
    from galaxy_tool_xml.profiles import latest_profile

    state = corpus_check._CodemodSweepState(eligible=5)
    state.final_profiles[latest_profile()] = 3
    state.final_profiles["24.1"] = 2
    state.upgrade_steps["24.1"] = 1
    lines = corpus_check._rule_format_upgrade_discovery(state)
    assert any("UpgradeToLatest" in line for line in lines)
    assert any("reached latest" in line for line in lines)
    assert any(line.startswith("| 24.1 |") for line in lines)


# --- fmt sweep population gate (_fmt_in_scope) ----------------------------------

_VALID_TOOL = (
    b'<tool id="m" name="M" version="1.0.0" profile="24.1">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs/><outputs><data name="o"/></outputs></tool>'
)
# Missing the required id/name/version: validates under no vendored profile.
_NEVER_VALID_TOOL = b"<tool><inputs/></tool>"


def test_fmt_in_scope_default_accepts_any_valid_profile(tmp_path: Path) -> None:
    file = tmp_path / "tool.xml"
    file.write_bytes(_VALID_TOOL)
    assert corpus_check._fmt_in_scope(file, profile=None) is True


def test_fmt_in_scope_default_rejects_never_valid(tmp_path: Path) -> None:
    file = tmp_path / "tool.xml"
    file.write_bytes(_NEVER_VALID_TOOL)
    assert corpus_check._fmt_in_scope(file, profile=None) is False


def test_fmt_in_scope_pinned_profile_uses_that_profile(tmp_path: Path) -> None:
    file = tmp_path / "tool.xml"
    file.write_bytes(_VALID_TOOL)
    assert corpus_check._fmt_in_scope(file, profile=latest_profile()) is True


def test_fmt_repos_section_lists_each_github_repo() -> None:
    repos = [("tools-iuc", "abc123", 5), ("pico_galaxy", "def456", 2)]
    out = corpus_check._fmt_format_repos_section(repos, source="github")
    assert any("| tools-iuc |" in line and "| 5 |" in line for line in out)
    assert any("| pico_galaxy |" in line and "| 2 |" in line for line in out)


def test_fmt_repos_section_rolls_up_combined_by_source() -> None:
    # toolshed display names carry an owner/ slash; github names do not.
    repos = [
        ("tools-iuc", "a", 5),
        ("pico_galaxy", "b", 2),
        ("owner/repo1", "c", 1),
        ("owner/repo2", "d", 3),
    ]
    out = corpus_check._fmt_format_repos_section(repos, source="combined")
    rows = {ln.split("|")[1].strip(): ln for ln in out if ln.startswith("| ")}
    assert "| 2 |" in rows["github"] and "| 7 |" in rows["github"]  # 2 repos, 5+2
    assert "| 2 |" in rows["toolshed"] and "| 4 |" in rows["toolshed"]  # 2 repos, 1+3
    # the giant per-repo list must NOT be present
    assert not any("| owner/repo1 |" in line for line in out)


def test_stat_tables_use_comma_thousands_separators() -> None:
    """Generated stat-table integers render with comma thousands separators."""
    state = corpus_check._FmtSweepState(parsed=12772, validated=8608, idempotent=8608)
    summary = "\n".join(corpus_check._fmt_format_summary_table(state))
    assert "12,772" in summary and "8,608" in summary
    assert "12 772" not in summary  # not space-separated, not bare
    sweeps = [
        corpus_check._FmtRuleSweep(
            code="GTR001", validated=8608, touched=8608, edits=863912
        )
    ]
    fmt_tbl = "\n".join(corpus_check._rule_format_fmt_table(sweeps))
    assert "8,608" in fmt_tbl and "863,912" in fmt_tbl


# --- check subcommand (unified-detect violation counts) ---------------------

_FLAT_TOOL = (
    b'<tool id="t" name="T" version="0.1" profile="24.1">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param value="v" type="text" name="a"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)


def test_check_rule_registry_spans_three_tiers() -> None:
    """The registry covers fmt + canonical codemods + advisory checks."""
    registry = corpus_check._check_rule_registry()
    assert {"GTR001", "GTR003", "GTR004"} <= set(registry)  # fmt
    assert {"GTR002", "GTR005", "GTR006", "GTR013"} <= set(registry)  # codemods
    # advisory checks: the flat ones + the partition .2 residual sub-rules.
    flat_advisory = {"GTR021", "GTR023", "GTR024", "GTR025", "GTR026", "GTR027",
                     "GTR028", "GTR029", "GTR032", "GTR033"}
    assert flat_advisory <= set(registry)
    assert {"GTR018.2", "GTR019.2", "GTR020.2"} <= set(registry)  # advisory residuals
    assert registry["GTR002"].detect_only is False
    assert registry["GTR021"].detect_only is True
    assert registry["GTR020.2"].detect_only is True
    assert registry["GTR002"].tier == "codemod"
    assert registry["GTR021"].tier == "check"


def test_check_detect_reports_fixable_and_advisory() -> None:
    """The unified detect yields both fixable and advisory findings."""
    from galaxy_tool_xml.binding import load_tool

    registry = corpus_check._check_rule_registry()
    codes = {v.code for v in corpus_check._check_detect(load_tool(_FLAT_TOOL))}
    assert "GTR002" in codes  # fixable: param attribute order
    # advisory present — identified by the rule's detect_only flag, not its prefix.
    assert any(code in registry and registry[code].detect_only for code in codes)


def test_check_process_path_tallies_per_code(tmp_path: Path) -> None:
    """One file rolls into the sweep's per-code and per-tool tallies."""
    file = tmp_path / "tool.xml"
    file.write_bytes(_FLAT_TOOL)
    state = corpus_check._CheckSweepState(registry=corpus_check._check_rule_registry())
    corpus_check._check_process_path(file, state=state)
    assert state.tools == 1
    assert state.flagged_tools == 1
    assert state.fixable_flagged_tools == 1
    assert state.advisory_flagged_tools == 1
    assert state.registry["GTR002"].flagged == 1
    assert state.registry["GTR002"].total == 1
    # GTR006 (FixTypos) does not fire on a valid tool.
    assert state.registry["GTR006"].flagged == 0


def test_check_process_path_skips_non_tool(tmp_path: Path) -> None:
    file = tmp_path / "macros.xml"
    file.write_bytes(b"<macros><token>x</token></macros>")
    state = corpus_check._CheckSweepState(registry=corpus_check._check_rule_registry())
    corpus_check._check_process_path(file, state=state)
    assert state.tools == 0
