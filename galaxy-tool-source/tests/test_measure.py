"""Unit tests for measure.py measurement helpers."""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path

import pytest
from lxml import etree
from scripts._shared import sha256_of
from scripts.measure import (
    _COLLECTION_TYPE_MEMBERS,
    _MATCH_KEYS,
    _PROFILE_NONE,
    _baseline_bucket,
    _cheetah_feature_flags,
    _classify_command_language,
    _classify_command_vars,
    _classify_lone_amps,
    _collection_type_patterns,
    _count_unquoted_vars,
    _cross_source_key_matches,
    _ExpansionGapResult,
    _facts_from_macro_container,
    _measure_cheetah_cdm_bails,
    _measure_cheetah_cdm_coverage,
    _measure_cheetah_command_complexity,
    _measure_collection_type_normalization,
    _measure_command_iuc_heuristics,
    _measure_command_language,
    _measure_element_cardinality,
    _measure_help_formats,
    _measure_help_rst_errors,
    _measure_help_rst_features,
    _measure_help_rst_md_convert,
    _measure_help_rst_to_markdown,
    _measure_interpreter_buckets,
    _measure_iuc011_fixability,
    _measure_macro_expansion_detection_gap,
    _measure_macro_fmt_idempotence,
    _measure_macro_profile_ownership,
    _measure_macro_profile_tokens,
    _measure_macro_token_residual,
    _measure_macro_topology,
    _measure_output_format_input,
    _measure_param_types,
    _measure_rename_coverage,
    _measure_rename_macro_spread,
    _measure_select_quoting_safety,
    _measure_semantic_upgrade_boundaries,
    _measure_shell_oracle_quoting,
    _measure_test_case_validation_truth,
    _measure_upgrade_behavior_blocks,
    _measure_upgrade_headroom,
    _measure_version_tokenization,
    _measure_xsd_tightenings,
    _normalize_validation_error,
    _ParamTypesResult,
    _render_behavior_block_page,
    _render_macro_stats_page,
    _render_profile_ownership_page,
    _render_profile_shift_page,
    _tally_applicability,
    _tally_behavior_blocks,
    _tally_expansion_gap,
    _tally_profile_shift,
    _version_tuple,
)

from galaxy_tool_source.cheetah_cdm import cheetah_cdm_available
from galaxy_tool_source.shell_oracle import shell_oracle_available


@pytest.fixture()
def corpus_root(tmp_path: Path) -> Path:
    """Synthetic corpus with two tools and known param types."""
    repo = tmp_path / "owner" / "some-repo"
    repo.mkdir(parents=True)
    (repo / "tool_a.xml").write_text(
        "<tool><inputs>"
        '<param type="text" name="a"/>'
        '<param type="integer" name="b"/>'
        '<param type="text" name="c"/>'
        "</inputs></tool>",
        encoding="utf-8",
    )
    (repo / "tool_b.xml").write_text(
        "<tool><inputs>"
        '<param type="select" name="d"/>'
        "</inputs></tool>",
        encoding="utf-8",
    )
    (repo / "not_a_tool.xml").write_text("<data/>", encoding="utf-8")
    return tmp_path


def test_param_types_counts_correctly(corpus_root: Path) -> None:
    result = _measure_param_types(corpus_root=corpus_root)
    assert isinstance(result, _ParamTypesResult)
    assert result.type_counts["text"] == 2
    assert result.type_counts["integer"] == 1
    assert result.type_counts["select"] == 1
    assert result.n_tools_parsed == 2
    assert result.n_params_total == 4


def test_param_types_skips_non_tool_roots(corpus_root: Path) -> None:
    result = _measure_param_types(corpus_root=corpus_root)
    assert result.n_tools_parsed == 2


def test_param_types_empty_corpus(tmp_path: Path) -> None:
    result = _measure_param_types(corpus_root=tmp_path)
    assert result.n_tools_parsed == 0
    assert result.n_params_total == 0
    assert len(result.type_counts) == 0


# --- select-quoting-safety -------------------------------------------------------


@pytest.fixture()
def select_quoting_corpus(tmp_path: Path) -> Path:
    """Synthetic corpus exercising every select/drill_down safety class + scope."""
    repo = tmp_path / "owner" / "select-repo"
    repo.mkdir(parents=True)
    # provable: every option value a single token; bare-referenced in <command>.
    (repo / "provable.xml").write_text(
        '<tool id="t_prov"><inputs>'
        '<param name="fmt" type="select">'
        '<option value="-b">b</option><option value="-h">h</option></param>'
        "</inputs><command><![CDATA[run $fmt]]></command></tool>",
        encoding="utf-8",
    )
    # multiflag: an option value word-splits; referenced -> unsound before the fix.
    (repo / "multiflag.xml").write_text(
        '<tool id="t_mf"><inputs>'
        '<param name="opt" type="select"><option value="-b -h">x</option></param>'
        "</inputs><command><![CDATA[run $opt]]></command></tool>",
        encoding="utf-8",
    )
    # metachar: a glob value expands unquoted; referenced -> unsound.
    (repo / "metachar.xml").write_text(
        '<tool id="t_mc"><inputs>'
        '<param name="g" type="select"><option value="*.bam">x</option></param>'
        "</inputs><command><![CDATA[run $g]]></command></tool>",
        encoding="utf-8",
    )
    # dynamic: runtime-sourced values; referenced -> unsound.
    (repo / "dynamic.xml").write_text(
        '<tool id="t_dyn"><inputs>'
        '<param name="src" type="select"><options from_dataset="d"/></param>'
        "</inputs><command><![CDATA[run $src]]></command></tool>",
        encoding="utf-8",
    )
    # drill_down with a whitespace value, NOT referenced -> counted, not in scope.
    (repo / "drilldown.xml").write_text(
        '<tool id="t_dd"><inputs>'
        '<param name="tree" type="drill_down"><options>'
        '<option name="A" value="a b"/></options></param>'
        "</inputs><command><![CDATA[run nothing]]></command></tool>",
        encoding="utf-8",
    )
    # multiple= select: a deliberate splat -> excluded from the population entirely.
    (repo / "multiple.xml").write_text(
        '<tool id="t_multi"><inputs>'
        '<param name="m" type="select" multiple="true">'
        '<option value="-b">b</option></param>'
        "</inputs><command><![CDATA[run $m]]></command></tool>",
        encoding="utf-8",
    )
    (repo / "not_a_tool.xml").write_text("<data/>", encoding="utf-8")
    return tmp_path


def test_select_quoting_safety_buckets_and_scope(select_quoting_corpus: Path) -> None:
    result = _measure_select_quoting_safety(corpus_root=select_quoting_corpus)
    # fmt, opt, g, src, tree -> 5 non-multiple option-valued params (m excluded).
    assert result.n_params == 5
    assert dict(result.per_class) == {
        "provable": 1,
        "multiflag": 2,  # opt + the unreferenced drill_down tree
        "metachar": 1,
        "dynamic": 1,
    }
    # Bare-referenced in <command>: fmt, opt, g, src (tree not referenced, m excluded).
    assert result.n_referenced == 4
    assert dict(result.referenced_per_class) == {
        "provable": 1,
        "multiflag": 1,
        "metachar": 1,
        "dynamic": 1,
    }
    # Old GTR020.1 would have mis-quoted opt, g, src -> 3 tools.
    assert result.n_tools_unsound_before == 3


def test_select_quoting_safety_empty_corpus(tmp_path: Path) -> None:
    result = _measure_select_quoting_safety(corpus_root=tmp_path)
    assert result.n_params == 0
    assert result.n_referenced == 0
    assert result.n_tools_unsound_before == 0


# --- help-formats ----------------------------------------------------------------


@pytest.fixture()
def help_formats_corpus(tmp_path: Path) -> Path:
    """Synthetic corpus exercising every <help> format bucket + sha dedup."""
    repo = tmp_path / "owner" / "help-repo"
    repo.mkdir(parents=True)
    (repo / "no_help.xml").write_text(
        '<tool id="t_nohelp"><inputs/></tool>', encoding="utf-8"
    )
    (repo / "implicit.xml").write_text(
        '<tool id="t_implicit"><help>plain rst</help></tool>', encoding="utf-8"
    )
    (repo / "blank_format.xml").write_text(
        '<tool id="t_blank"><help format="  ">still rst</help></tool>',
        encoding="utf-8",
    )
    (repo / "rst.xml").write_text(
        '<tool id="t_rst"><help format="restructuredtext">x</help></tool>',
        encoding="utf-8",
    )
    md_xml = '<tool id="t_md"><help format="markdown">x</help></tool>'
    (repo / "md.xml").write_text(md_xml, encoding="utf-8")
    # Case-insensitive normalisation: "Markdown" buckets with "markdown".
    (repo / "md_upper.xml").write_text(
        '<tool id="t_md2"><help format="Markdown">x</help></tool>', encoding="utf-8"
    )
    (repo / "plain.xml").write_text(
        '<tool id="t_plain"><help format="plain_text">x</help></tool>',
        encoding="utf-8",
    )
    # Byte-identical to md.xml -> deduped by sha256 (not double-counted).
    (repo / "md_dup.xml").write_text(md_xml, encoding="utf-8")
    (repo / "not_a_tool.xml").write_text("<data/>", encoding="utf-8")
    return tmp_path


def test_help_formats_buckets(help_formats_corpus: Path) -> None:
    result = _measure_help_formats(corpus_root=help_formats_corpus)
    # 7 unique tool roots: no_help, implicit, blank_format, rst, md, md2, plain.
    # md_dup is byte-identical to md (sha dedup); not_a_tool is not a <tool>.
    assert result.n_unique_tools == 7
    assert result.n_without_help == 1
    # implicit (no attr) and blank (whitespace-only attr) both count as rst.
    assert result.n_help_implicit_rst == 2
    assert dict(result.explicit_format_buckets) == {
        "markdown": 2,
        "restructuredtext": 1,
        "plain_text": 1,
    }
    assert set(result.markdown_example_ids) == {"t_md", "t_md2"}


def test_help_formats_empty_corpus(tmp_path: Path) -> None:
    result = _measure_help_formats(corpus_root=tmp_path)
    assert result.n_unique_tools == 0
    assert result.n_without_help == 0
    assert result.n_help_implicit_rst == 0
    assert result.explicit_format_buckets == []
    assert result.markdown_example_ids == []


# --- cross-source match-key sanity check (§10.11 / §6) ---------------------------
#
# repo with a "/" reads as toolshed, otherwise github (see _shared.row_source).
def _row(
    *,
    repo: str,
    tool_id: str,
    path: str,
    sha256: str,
    failing: bool = False,
) -> dict[str, object]:
    row: dict[str, object] = {
        "repo": repo,
        "tool_id": tool_id,
        "path": path,
        "sha256": sha256,
    }
    if failing:
        row["no_valid_reason"] = "XSD does not declare attribute used by tool"
    return row


_MATCH_ROWS = [
    # tool A: both sources, different bytes, same basename — passing.
    _row(repo="tools-iuc", tool_id="A", path="tools/a/a.xml", sha256="s1"),
    _row(repo="owner/repo", tool_id="A", path="owner/repo/a.xml", sha256="s2"),
    # tool B: both sources, byte-identical, same basename — failing.
    _row(
        repo="tools-iuc", tool_id="B", path="tools/b/b.xml", sha256="s3", failing=True
    ),
    _row(
        repo="owner/repo",
        tool_id="B",
        path="owner/repo/b.xml",
        sha256="s3",
        failing=True,
    ),
    # tool C: github only, failing — must never count as a cross-source match.
    _row(
        repo="tools-iuc", tool_id="C", path="tools/c/c.xml", sha256="s4", failing=True
    ),
]


def test_tool_id_matches_count_both_sources() -> None:
    # A and B appear in both sources; C is github-only. B is the only failing
    # tool_id present in both sources. Result is (all-corpus, failure-subset).
    assert _cross_source_key_matches(_MATCH_ROWS, key=_MATCH_KEYS["tool_id"]) == (2, 1)


def test_tool_id_basename_matches_track_tool_id() -> None:
    key = _MATCH_KEYS["(tool_id, basename)"]
    assert _cross_source_key_matches(_MATCH_ROWS, key=key) == (2, 1)


def test_sha256_matches_only_byte_identical() -> None:
    # Only tool B is byte-identical across sources (s3); A's copies differ.
    assert _cross_source_key_matches(_MATCH_ROWS, key=_MATCH_KEYS["sha256"]) == (1, 1)


# --- collection-type-normalization (codemod docs/decisions.md §14) ---------------

_XS = "{http://www.w3.org/2001/XMLSchema}"


def _latest_xsd_pattern(simple_type: str) -> str:
    """Return the ``xs:pattern`` value of a named simpleType in the latest XSD."""
    from galaxy_tool_source.profiles import latest_profile

    schema_dir = importlib.resources.files("galaxy_tool_source") / "schema"
    manifest = json.loads((schema_dir / "manifest.json").read_text(encoding="utf-8"))
    xsd_file = manifest["schemas"][latest_profile()]["file"]
    root = etree.fromstring((schema_dir / xsd_file).read_bytes())
    pattern = root.find(f"{_XS}simpleType[@name='{simple_type}']//{_XS}pattern")
    assert pattern is not None, f"no pattern under simpleType {simple_type!r}"
    value = pattern.get("value")
    assert value is not None
    return value


def test_collection_type_grammar_matches_latest_xsd() -> None:
    # Drift guard: if a schema regen changes the collection-type grammar, the
    # _COLLECTION_TYPE_MEMBERS constant (and this measurement) must be updated.
    patterns = _collection_type_patterns()
    # The compiled patterns differ from the XSD's only by the ^...$ anchors.
    assert _latest_xsd_pattern("CollectionType") == patterns["type"].pattern.strip("^$")
    assert (
        _latest_xsd_pattern("CollectionTypeList")
        == patterns["collection_type"].pattern.strip("^$")
    )
    # And the member set the constant encodes is exactly the XSD's.
    members = "|".join(_COLLECTION_TYPE_MEMBERS)
    assert f"({members})" in _latest_xsd_pattern("CollectionType")


@pytest.fixture()
def collection_corpus(tmp_path: Path) -> Path:
    """Synthetic corpus exercising every collection-type classification bucket."""
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # Whitespace-fixable: comma value with a stray space (the qiime2 shape).
    (repo / "fixable.xml").write_text(
        '<tool><inputs><param collection_type="list, list:paired" name="a"/>'
        "</inputs></tool>",
        encoding="utf-8",
    )
    # Already valid: paired_or_unpaired (25.0+ member) on a <collection type>,
    # and a bare list on a param collection_type.
    (repo / "valid.xml").write_text(
        '<tool><outputs><collection type="paired_or_unpaired" name="c"/></outputs>'
        '<inputs><param collection_type="list" name="b"/></inputs></tool>',
        encoding="utf-8",
    )
    # Other violation: a datatype where a collection structure belongs.
    (repo / "other.xml").write_text(
        '<tool><tests><test><output_collection type="pdf" name="d"/></test>'
        "</tests></tool>",
        encoding="utf-8",
    )
    # Skipped value: an unexpanded macro token is not a literal grammar value.
    (repo / "template.xml").write_text(
        '<tool><inputs><param collection_type="@COLLECTION_TYPE@" name="e"/>'
        "</inputs></tool>",
        encoding="utf-8",
    )
    # Skipped file: non-<tool> root.
    (repo / "not_a_tool.xml").write_text("<data/>", encoding="utf-8")
    return tmp_path


def test_collection_type_normalization_buckets(collection_corpus: Path) -> None:
    result = _measure_collection_type_normalization(corpus_root=collection_corpus)
    assert result.n_unique_tools == 4  # fixable, valid, other, template
    assert result.n_unparseable_skipped == 1  # not_a_tool.xml
    assert result.n_already_valid == 2  # paired_or_unpaired + bare list
    assert result.n_whitespace_fixable == 1
    assert result.n_other_violation == 1  # pdf
    assert result.n_values_total == 4
    assert result.fixable_exemplars[0][2:] == ("list, list:paired", "list,list:paired")
    assert result.other_violation_values[0] == (("output_collection", "type", "pdf"), 1)


# --- upgrade-headroom -----------------------------------------------------------


def _hrow(sha: str, newest: object, declared: object) -> dict[str, object]:
    """One synthetic combined row; valid_* columns make latest == 26.0."""
    return {
        "valid_19.01": 0,
        "valid_24.0": 0,
        "valid_26.0": 0,
        "sha256": sha,
        "newest_valid": newest,
        "profile_expanded": declared,
    }


def _headroom_rows() -> list[dict[str, object]]:
    return [
        _hrow("a", "26.0", "26.0"),
        _hrow("b", "26.0", "20.01"),
        _hrow("c", "24.0", "24.0"),
        _hrow("d", _PROFILE_NONE, None),
        _hrow("e", "26.0", None),
        _hrow("f", "26.0", "@PROFILE@"),
    ]


def test_upgrade_headroom_declaration_buckets() -> None:
    result = _measure_upgrade_headroom(rows=_headroom_rows())
    buckets = dict(result.declaration_buckets)
    assert result.latest_profile == "26.0"
    assert result.n_unique_tools == 6
    assert buckets["accurate (declaration unchanged)"] == 2  # a, c
    assert buckets["understated (declaration bumped up)"] == 1  # b
    assert buckets["no declaration (would be added)"] == 1  # e
    assert buckets["macro-placeholder declaration (left as-is)"] == 1  # f
    assert buckets["no valid profile (repair first)"] == 1  # d


def test_upgrade_headroom_structural_split() -> None:
    result = _measure_upgrade_headroom(rows=_headroom_rows())
    assert result.n_with_valid_profile == 5  # a, b, c, e, f
    assert result.n_at_latest == 4  # a, b, e, f
    assert result.n_below_latest == 1  # c


def _semantic_rows() -> list[dict[str, object]]:
    # (sha, newest_valid target, declared profile_expanded)
    return [
        _hrow("a", "26.1", "26.1"),  # at latest: crosses nothing
        _hrow("b", "26.1", "19.01"),  # 8 boundaries (19.05..25.1)
        _hrow("c", "26.1", _PROFILE_NONE),  # no profile= -> baseline 16.01 -> all 12
        _hrow("d", "24.2", "24.1"),  # 24.2 only (not pinnable)
        _hrow("e", "26.1", "@PROFILE@"),  # macro token -> unplaceable, excluded
        _hrow("f", _PROFILE_NONE, "19.01"),  # validates nowhere -> excluded
        _hrow("g", "17.09", "17.05"),  # 17.09 only (cleanly pinnable)
        _hrow("h", "26.1", "(expansion failed)"),  # unplaceable -> excluded
    ]


def test_output_format_input_buckets(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "r"
    repo.mkdir(parents=True)
    # auto-fixable: format="input" output + single top-level data input
    (repo / "auto.xml").write_text(
        '<tool><inputs><param type="data" name="i"/></inputs>'
        '<outputs><data name="o" format="input"/></outputs></tool>',
        encoding="utf-8",
    )
    # needs-intent: two data inputs
    (repo / "multi.xml").write_text(
        '<tool><inputs><param type="data" name="i"/><param type="data" name="j"/>'
        '</inputs><outputs><data name="o" format="input"/></outputs></tool>',
        encoding="utf-8",
    )
    # nested but addressable (qualified format_source): auto-fixable since the
    # 2026-06-10 widening (codemod decisions §40)
    (repo / "nested.xml").write_text(
        '<tool><inputs><conditional name="c">'
        '<param type="data" name="i"/></conditional></inputs>'
        '<outputs><data name="o" format="input"/></outputs></tool>',
        encoding="utf-8",
    )
    # repeat-nested: instance-indexed runtime prefix -> still needs author intent
    (repo / "repeat.xml").write_text(
        '<tool><inputs><repeat name="r">'
        '<param type="data" name="i"/></repeat></inputs>'
        '<outputs><data name="o" format="input"/></outputs></tool>',
        encoding="utf-8",
    )
    # not counted: no format="input"
    (repo / "clean.xml").write_text(
        '<tool><inputs><param type="data" name="i"/></inputs>'
        '<outputs><data name="o" format="txt"/></outputs></tool>',
        encoding="utf-8",
    )
    # co-present format_source, NOT auto-fixable (no data inputs): GTR015's guard
    # skips it, and it does not land in the auto-fixable subset.
    (repo / "copresent_nonauto.xml").write_text(
        '<tool><inputs/>'
        '<outputs><data name="o" format="input" format_source="x"/></outputs></tool>',
        encoding="utf-8",
    )
    # co-present format_source AND auto-fixable: the guard-relevant subset.
    (repo / "copresent_auto.xml").write_text(
        '<tool><inputs><param type="data" name="i"/></inputs>'
        '<outputs><data name="o" format="input" format_source="i"/></outputs></tool>',
        encoding="utf-8",
    )
    # auto-fixable but ALREADY declares profile >= 16.04: the crossing-gate skips it.
    (repo / "autofix_past_1604.xml").write_text(
        '<tool profile="21.09"><inputs><param type="data" name="i"/></inputs>'
        '<outputs><data name="o" format="input"/></outputs></tool>',
        encoding="utf-8",
    )
    result = _measure_output_format_input(corpus_root=tmp_path)
    assert result.n_tools_parsed == 8
    assert result.n_tools_with_format_input == 7
    # auto + copresent_auto + autofix_past_1604 + nested (addressable since §40)
    assert result.n_auto_fixable == 4
    buckets = result.by_data_input_bucket
    assert buckets["1 top-level (auto-fixable)"] == 3
    assert buckets["1 nested, addressable (auto-fixable)"] == 1
    assert buckets["1 under repeat / unnamed (needs author intent)"] == 1
    assert buckets["2+ data inputs"] == 1
    # the format_source guard breakdown (codemod decisions §24)
    assert result.n_format_input_with_format_source == 2  # both copresent_* files
    assert result.n_auto_fixable_with_format_source == 1  # copresent_auto.xml only
    # the crossing-gate breakdown: only autofix_past_1604.xml declares >= 16.04
    # (auto.xml/copresent_auto.xml have no profile -> 16.01 default, below 16.04)
    assert result.n_auto_fixable_already_at_16_04 == 1


def test_semantic_boundaries_population_split() -> None:
    result = _measure_semantic_upgrade_boundaries(rows=_semantic_rows())
    assert result.n_unique_tools == 8
    assert result.n_no_valid_profile == 1  # f
    assert result.n_unplaceable_baseline == 2  # e, h
    assert result.n_considered == 5  # a, b, c, d, g
    assert result.n_no_declaration_baseline == 1  # c (the _PROFILE_NONE sentinel)
    assert result.n_cross_any == 4  # b, c, d, g
    assert result.n_cross_none == 1  # a


def test_semantic_boundaries_per_code_and_pinnability() -> None:
    result = _measure_semantic_upgrade_boundaries(rows=_semantic_rows())
    per = result.per_code
    assert per["24_2_fix_test_case_validation"] == 3  # b, c, d
    assert per["20_09_consider_set_e"] == 2  # b, c
    assert per["17_09_consider_provided_metadata_style"] == 2  # c, g
    assert per["16_04_exit_code"] == 1  # c only (no-profile baseline)
    assert per["21_09_fix_from_work_dir_whitespace"] == 2  # b, c
    # codes crossed: a=0, d & g =1, b=9, c=17 (every catalogued code)
    assert dict(result.distribution) == {0: 1, 1: 2, 9: 1, 17: 1}
    assert result.total_crossing_events == 28  # 0 + 9 + 17 + 1 + 1
    # CLEAN events: 16_04_exit_code(c) + 17_09(c,g) + 18_01_home(c) + 20_09_set_e(b,c)
    assert result.pinnable_clean_events == 6
    # only g crosses solely cleanly-pinnable codes (17.09); d's 24.2 has no knob
    assert result.n_fully_pinnable_tools == 1  # g


def test_applicability_tally_narrows_crossed_to_tripped() -> None:
    # baseline 16.01 -> 26.1 crosses all 17 codes; only the tripped ones apply.
    samples = [
        # trips just set -e and the always-on extra-file note (a 20.09 + a 16.04)
        ("16.01", "26.1", frozenset({"20_09_consider_set_e"})),
        # at-latest: crosses nothing, so applies nothing regardless of tripped
        ("26.1", "26.1", frozenset({"20_09_consider_set_e"})),
        # 24.1 -> 24.2 crosses only 24_2; the tool trips it
        ("24.1", "24.2", frozenset({"24_2_fix_test_case_validation"})),
        # 24.1 -> 24.2 crosses only 24_2; the tool does NOT trip it (no warning)
        ("24.1", "24.2", frozenset()),
    ]
    result = _tally_applicability(samples=samples)
    assert result.n_considered == 4
    assert result.n_warn_range == 3  # all but the at-latest sample cross something
    assert result.n_warn_applicable == 2  # only the two tripping a crossed code
    # 24_2 is crossed by the full-span sample too (it crosses all 17 codes).
    assert result.per_code_crossed["24_2_fix_test_case_validation"] == 3
    assert result.per_code_applicable["24_2_fix_test_case_validation"] == 1
    assert result.per_code_applicable["20_09_consider_set_e"] == 1
    # applicable is always a subset of crossed
    assert result.total_applicable_events <= result.total_crossed_events


def test_baseline_bucket_defaults_and_buckets() -> None:
    assert _baseline_bucket(None) == "16.01"  # no profile -> Galaxy default
    assert _baseline_bucket("21.05") == "21.05"  # literal -> itself
    assert _baseline_bucket("@PROFILE@") == "(macro/unparseable)"


def test_profile_shift_tally_summarises_advance_and_distributions() -> None:
    samples = [
        ("16.01", "26.1"),  # no-profile default, advanced to latest
        ("24.1", "26.1"),  # advanced (a stuck tool climbed past its ceiling)
        ("26.1", "26.1"),  # already at latest, unchanged
        ("(macro/unparseable)", "26.1"),  # token baseline -> still reaches latest
        ("20.05", "(none)"),  # broke / validates nowhere after upgrade
    ]
    result = _tally_profile_shift(samples=samples, latest="26.1")
    assert result.n_tools == 5
    assert result.n_at_latest_before == 1  # only the 26.1 sample
    assert result.n_at_latest_after == 4  # all but the "(none)" one
    assert result.n_advanced == 2  # 16.01->26.1 and 24.1->26.1
    assert result.n_unchanged == 1  # 26.1->26.1
    assert result.n_unplaceable_baseline == 1  # the macro-token baseline
    assert result.n_after_validates_nowhere == 1  # the 20.05 -> (none)
    assert result.before["16.01"] == 1
    assert result.after["26.1"] == 4


def test_render_profile_shift_page_smoke() -> None:
    result = _tally_profile_shift(
        samples=[("16.01", "26.1"), ("24.1", "26.1"), ("20.05", "(none)")],
        latest="26.1",
    )
    page = _render_profile_shift_page(result)
    assert "# Upgrade profile-shift statistics" in page
    assert "Declared (defaulted) profile distribution — before" in page
    assert "Reached profile distribution — after `upgrade`" in page
    assert "| 16.01 | 1 |" in page  # a before-row
    assert "| 26.1 | 2 |" in page  # an after-row
    assert "| (none) | 1 |" in page  # validates-nowhere bucket sorts last


def test_version_tuple_equates_zero_padded_versions() -> None:
    assert _version_tuple("20.5") == _version_tuple("20.05") == (20, 5)
    assert _version_tuple("@PROFILE@") is None
    assert _version_tuple(None) is None


# --- upgrade-behavior-blocks ----------------------------------------------------


def _puc(code: str, profile: str, level: str) -> object:
    """A synthetic ``ProfileUpgradeCode`` for the pure-tally tests."""
    from galaxy_tool_codemod.profile_semantics import ProfileUpgradeCode

    return ProfileUpgradeCode(
        code=code, profile=profile, level=level, niche=False, message="", url=None
    )


def test_tally_behavior_blocks_picks_lowest_blocker_per_policy() -> None:
    samples = [
        # a must_fix at 16.04 dominates a later consider under both policies
        (_puc("mf16", "16.04", "must_fix"), _puc("c20", "20.09", "consider")),
        # consider-only: reaches latest under must_fix-only, stuck under both
        (_puc("c17", "17.09", "consider"),),
        # nothing applicable/unfixable: reaches latest under either policy
        (),
        # first blocker differs by policy: consider@18.01 (both) vs must_fix@24.2
        (_puc("c18", "18.01", "consider"), _puc("mf24", "24.2", "must_fix")),
    ]
    result = _tally_behavior_blocks(samples=samples, n_excluded=2, latest="26.1")  # type: ignore[arg-type]
    assert result.n_considered == 4
    assert result.n_excluded == 2
    assert result.latest == "26.1"

    # must_fix-only: c17-only and the empty sample both reach latest.
    assert result.must_fix.reached_latest == 2
    assert result.must_fix.stuck_total == 2
    assert result.must_fix.per_code == {"mf16": 1, "mf24": 1}

    # must_fix + consider: only the empty sample reaches latest.
    assert result.must_fix_and_consider.reached_latest == 1
    assert result.must_fix_and_consider.stuck_total == 3
    assert result.must_fix_and_consider.per_code == {"mf16": 1, "c17": 1, "c18": 1}


def test_render_behavior_block_page_smoke() -> None:
    result = _tally_behavior_blocks(
        samples=[
            (_puc("16_04_fix_interpreter", "16.04", "must_fix"),),
            (),
        ],  # type: ignore[arg-type]
        n_excluded=1,
        latest="26.1",
    )
    page = _render_behavior_block_page(result)
    assert "# Upgrade behavior-block statistics" in page
    assert "Blocking on `must_fix` only" in page
    assert "Blocking on `must_fix` + `consider`" in page
    assert "`16_04_fix_interpreter`" in page


@pytest.fixture()
def behavior_corpus(tmp_path: Path) -> Path:
    """Synthetic corpus exercising the behavior-block stop + auto-fix subtraction."""
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # No profile -> baseline 16.01. An interpreter command is a must_fix at 16.04
    # with no auto-fix -> stuck on 16_04_fix_interpreter.
    (repo / "interp.xml").write_text(
        '<tool><command interpreter="python">run</command>'
        "<inputs/><outputs/></tool>",
        encoding="utf-8",
    )
    # profile 21.05 -> the only crossed applicable code is the 21.09 from_work_dir
    # whitespace must_fix, which GTR014 auto-fixes -> reaches latest (both policies).
    (repo / "workdir.xml").write_text(
        '<tool profile="21.05"><command>run</command>'
        '<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>',
        encoding="utf-8",
    )
    # No profile + format="input" output + a sole top-level data input -> GTR015
    # auto-fixes the must_fix; <stdio/> silences the 16.04 exit-code consider, so
    # under must_fix-only it reaches latest, and under both it stalls on the
    # unconditional 16_04_consider_implicit_extra_file_collection.
    (repo / "fmt_sole.xml").write_text(
        '<tool><inputs><param type="data" name="inp"/></inputs>'
        '<outputs><data name="o" format="input"/></outputs><stdio/></tool>',
        encoding="utf-8",
    )
    # Two data inputs -> GTR015 cannot pick one, so 16_04_fix_output_format remains
    # a must_fix blocker.
    (repo / "fmt_multi.xml").write_text(
        '<tool><inputs><param type="data" name="a"/><param type="data" name="b"/>'
        '</inputs><outputs><data name="o" format="input"/></outputs><stdio/></tool>',
        encoding="utf-8",
    )
    # A macro-token profile cannot be ranged -> excluded.
    (repo / "macro.xml").write_text(
        '<tool profile="@PROFILE@"><inputs/></tool>', encoding="utf-8"
    )
    return tmp_path


def test_measure_behavior_blocks_applies_autofix_and_stop(
    behavior_corpus: Path,
) -> None:
    result = _measure_upgrade_behavior_blocks(corpus_root=behavior_corpus)
    assert result.n_considered == 4  # interp, workdir, fmt_sole, fmt_multi
    assert result.n_excluded == 1  # the @PROFILE@ tool

    # must_fix-only: workdir (GTR014) and fmt_sole (GTR015) reach latest; interp and
    # fmt_multi stall on their unfixable must_fix codes.
    must_fix = result.must_fix
    assert must_fix.reached_latest == 2
    assert must_fix.per_code == {
        "16_04_fix_interpreter": 1,
        "16_04_fix_output_format": 1,
    }

    # must_fix + consider: only workdir (baseline 21.05, no applicable consider)
    # reaches latest; the three 16.01-baseline tools stall at 16.04.
    both = result.must_fix_and_consider
    assert both.reached_latest == 1
    assert both.per_code["16_04_fix_interpreter"] == 1
    assert both.per_code["16_04_consider_implicit_extra_file_collection"] == 2


# --- test-case-validation-truth ---------------------------------------------------


def test_normalize_validation_error_buckets() -> None:
    assert (
        _normalize_validation_error("Invalid parameter name found nosuch")
        == "unknown-parameter"
    )
    assert (
        _normalize_validation_error("Invalid conditional test value (x) for ...")
        == "invalid-conditional-test-value"
    )
    assert (
        _normalize_validation_error("1 validation error for PydanticModelFor[t]")
        == "type-or-value-mismatch"
    )
    assert _normalize_validation_error("something novel") == "other"


_CHECKED_OUTPUT = (
    '<output name="o"><assert_contents><has_text text="x"/></assert_contents>'
    "</output>"
)


@pytest.fixture()
def truth_corpus(tmp_path: Path) -> Path:
    """Synthetic corpus exercising every test-case-validation-truth bucket."""
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # A valid test case: counts clean (would NOT block at 24.2).
    (repo / "clean.xml").write_text(
        '<tool id="clean" name="C" version="1.0"><command>echo</command>'
        '<inputs><param name="i" type="integer" value="1"/></inputs>'
        '<outputs><data name="o" format="txt"/></outputs>'
        f'<tests><test><param name="i" value="2"/>{_CHECKED_OUTPUT}</test></tests>'
        "</tool>",
        encoding="utf-8",
    )
    # An unknown test parameter: strict validation fails (a TRUE blocker).
    (repo / "invalid.xml").write_text(
        '<tool id="invalid" name="I" version="1.0"><command>echo</command>'
        '<inputs><param name="i" type="integer" value="1"/></inputs>'
        '<outputs><data name="o" format="txt"/></outputs>'
        '<tests><test><param name="nosuch" value="2"/>'
        f"{_CHECKED_OUTPUT}</test></tests></tool>",
        encoding="utf-8",
    )
    # Galaxy's own test parser rejects an output with nothing to check: the
    # validator call raises, so the tool lands in the retained error bucket.
    (repo / "raises.xml").write_text(
        '<tool id="raises" name="R" version="1.0"><command>echo</command>'
        '<inputs><param name="i" type="integer" value="1"/></inputs>'
        '<outputs><data name="o" format="txt"/></outputs>'
        '<tests><test><param name="i" value="2"/><output name="o"/></test></tests>'
        "</tool>",
        encoding="utf-8",
    )
    # No <test>: outside the detector's population entirely.
    (repo / "no_tests.xml").write_text(
        '<tool id="n" name="N" version="1.0"><command>echo</command>'
        '<inputs/><outputs><data name="o" format="txt"/></outputs></tool>',
        encoding="utf-8",
    )
    return tmp_path


def test_measure_test_case_validation_truth_buckets(truth_corpus: Path) -> None:
    result = _measure_test_case_validation_truth(corpus_root=truth_corpus)
    assert result.n_with_tests == 3  # clean, invalid, raises; no_tests excluded
    assert result.n_clean == 1
    assert result.n_invalid == 1
    assert result.error_kinds == {"unknown-parameter": 1}
    assert result.n_validator_error == 1
    assert len(result.retained) == 1
    assert result.retained[0]["path"].endswith("raises.xml")
    # Parity: our checker proves clean.xml only (invalid.xml carries the
    # unknown param; raises.xml carries the nothing-to-check output our
    # output-bail rejects), so every suppression agrees with Galaxy.
    assert result.n_ours_clean == 1
    assert result.n_unsound == 0
    assert result.n_suppressed == 1
    assert result.n_headroom == 0
    assert result.n_clean_galaxy_raised == 0
    assert result.unsound_examples == []
    assert result.raised_examples == []


# --- cheetah-command-complexity -------------------------------------------------


def test_cheetah_feature_flags_detects_constructs() -> None:
    flags = _cheetah_feature_flags(
        "#if $cond\n"
        "#for $i in $items\n"
        "python '$__tool_directory__/x.py' ${input.ext} $x[0] $foo(1) "
        "$GALAXY_SLOTS ## a comment\n"
        "echo \\$LITERAL @TOOL_VERSION@\n"
        "#end for\n#end if"
    )
    # directives
    assert "directive:if" in flags
    assert "directive:for" in flags
    # shapes
    assert "shape:braced" in flags  # ${input.ext}
    assert "shape:dotted" in flags  # input.ext
    assert "shape:indexed" in flags  # $x[0]
    assert "shape:call" in flags  # $foo(1)
    assert "shape:special" in flags  # $__tool_directory__
    assert "shape:env" in flags  # $GALAXY_SLOTS
    # hazards + macro
    assert "hazard:comment" in flags  # ##
    assert "hazard:escaped" in flags  # \$LITERAL
    assert "macro:token" in flags  # @TOOL_VERSION@


def test_cheetah_feature_flags_trivial_command_has_no_directives() -> None:
    flags = _cheetah_feature_flags("mytool --in '$input' --out '$output'")
    assert not any(f.startswith("directive:") for f in flags)
    assert "shape:braced" not in flags  # bare $var only


def test_measure_cheetah_complexity_counts_tools(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # Trivial command: no directive.
    (repo / "trivial.xml").write_text(
        "<tool><command>mytool '$input' '$output'</command></tool>",
        encoding="utf-8",
    )
    # Directive in command + an inline configfile (also Cheetah) + an <expand>.
    (repo / "complex.xml").write_text(
        "<tool>"
        "<command><![CDATA[\n#for $i in $reps\n"
        "Rscript '$__tool_directory__/r.R' $i\n#end for\n]]></command>"
        "<expand macro='requirements'/>"
        "<configfiles><configfile name='script'>"
        "#if $flag\nx <- 1\n#end if</configfile></configfiles>"
        "</tool>",
        encoding="utf-8",
    )
    # No <command> at all.
    (repo / "nocmd.xml").write_text("<tool><inputs/></tool>", encoding="utf-8")

    result = _measure_cheetah_command_complexity(corpus_root=tmp_path)
    assert result.n_tools == 3
    assert result.n_with_command == 2
    assert result.n_command_trivial == 1  # trivial.xml
    assert result.n_command_with_directive == 1  # complex.xml (#for)
    assert result.n_with_configfile == 1  # complex.xml
    assert result.n_with_expand == 1  # complex.xml
    assert result.n_with_cheetah_text == 2
    assert result.feature_counts.get("directive:for", 0) == 1
    assert result.feature_counts.get("directive:if", 0) == 1  # from the configfile
    assert result.feature_counts.get("shape:special", 0) == 1


# --- cheetah-cdm-coverage -------------------------------------------------------


@pytest.mark.skipif(
    not cheetah_cdm_available(), reason="CT3 missing (base dep; broken install)"
)
def test_measure_cheetah_cdm_coverage_counts(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # Clean, directive + a #for local (rename scope hazard), two placeholders.
    (repo / "locals.xml").write_text(
        "<tool><command>#for $f in $files\ncat '$f'\n#end for</command></tool>",
        encoding="utf-8",
    )
    # Clean, a bare placeholder, no directive.
    (repo / "plain.xml").write_text(
        "<tool><command>mytool $input</command></tool>", encoding="utf-8"
    )
    # Bail: an unterminated #if cannot compile.
    (repo / "bail.xml").write_text(
        "<tool><command>#if $x\necho hi\n</command></tool>", encoding="utf-8"
    )
    # Skipped: no $ or # in the body.
    (repo / "trivial.xml").write_text(
        "<tool><command>echo done</command></tool>", encoding="utf-8"
    )
    # Skipped: mixed content (child element) is not a pure-text body.
    (repo / "mixed.xml").write_text(
        "<tool><command>run $x <inputs/></command></tool>", encoding="utf-8"
    )

    result = _measure_cheetah_cdm_coverage(corpus_root=tmp_path)
    assert result.cdm_available is True
    assert result.n_bodies == 3  # locals + plain + bail (trivial/mixed skipped)
    assert result.n_clean == 2  # locals + plain
    assert result.n_bail == 1  # bail.xml
    assert result.n_with_directive == 1  # locals.xml (#for/#end)
    assert result.n_with_locals == 1  # locals.xml (#for)
    assert result.n_placeholders == 2  # $f (loop body) + $input


# --- cheetah-cdm-bails ----------------------------------------------------------


@pytest.mark.skipif(
    not cheetah_cdm_available(), reason="CT3 missing (base dep; broken install)"
)
def test_measure_cheetah_cdm_bails_collects_only_bail_bodies(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # Bail: an unterminated #if cannot compile -> retained for later testing.
    (repo / "bail.xml").write_text(
        '<tool id="t_bail"><command>#if $x\necho hi\n</command></tool>',
        encoding="utf-8",
    )
    # Clean body -> compiles, not retained.
    (repo / "clean.xml").write_text(
        '<tool id="t_clean"><command>mytool $input</command></tool>', encoding="utf-8"
    )
    # No $ or # -> skipped before the lexer.
    (repo / "trivial.xml").write_text(
        '<tool id="t_triv"><command>echo done</command></tool>', encoding="utf-8"
    )
    cases = _measure_cheetah_cdm_bails(corpus_root=tmp_path)
    assert [(c.tool_id, c.body) for c in cases] == [("t_bail", "#if $x\necho hi\n")]
    assert cases[0].source.endswith("bail.xml")


def _sharing_tool(tool_id: str, version: str, req: str, macros: str) -> str:
    return (
        f'<tool id="{tool_id}" name="{tool_id}" version="{version}" profile="24.0">'
        f"<macros><import>{macros}</import></macros>"
        "<command><![CDATA[echo x]]></command>"
        f'<requirements><requirement type="package" version="{req}">pkg'
        "</requirement></requirements>"
        "<inputs/><outputs><data name=\"o\"/></outputs></tool>"
    )


def test_measure_version_token_sharing_consensus_and_divergence(tmp_path: Path) -> None:
    from scripts.measure import _measure_version_token_sharing

    # Consensus directory: two tools at the same version share one macros file.
    con = tmp_path / "owner" / "consensus"
    con.mkdir(parents=True)
    (con / "macros.xml").write_text(
        '<macros><token name="@CITE@">r</token></macros>', encoding="utf-8"
    )
    (con / "a.xml").write_text(
        _sharing_tool("a", "1.20+galaxy0", "1.20", "macros.xml"), encoding="utf-8"
    )
    (con / "b.xml").write_text(
        _sharing_tool("b", "1.20+galaxy0", "1.20", "macros.xml"), encoding="utf-8"
    )
    # Divergent directory: two tokenizable tools disagree on the version.
    div = tmp_path / "owner" / "divergent"
    div.mkdir(parents=True)
    (div / "macros.xml").write_text("<macros/>", encoding="utf-8")
    (div / "c.xml").write_text(
        _sharing_tool("c", "1.20+galaxy0", "1.20", "macros.xml"), encoding="utf-8"
    )
    (div / "d.xml").write_text(
        _sharing_tool("d", "2.0+galaxy0", "2.0", "macros.xml"), encoding="utf-8"
    )

    result = _measure_version_token_sharing(corpus_root=tmp_path)
    assert result.tokenizable == 4
    assert result.full_consensus == 1 and result.consensus_tools == 2
    assert result.divergent == 1
    assert result.errors == []  # the planner ran clean on the synthetic corpus


# --- rename-coverage ------------------------------------------------------------


@pytest.mark.skipif(
    not cheetah_cdm_available(), reason="CT3 missing (base dep; broken install)"
)
def test_measure_rename_coverage_classifies(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # Two cleanly-renameable params (a + b): four sites (the def + $ref of each).
    (repo / "clean.xml").write_text(
        "<tool><inputs><param name='a'/><param name='b'/></inputs>"
        "<command>run $a $b</command></tool>",
        encoding="utf-8",
    )
    # One param shadowed by a #set local -> bail.
    (repo / "shadow.xml").write_text(
        "<tool><inputs><param name='s'/></inputs>"
        "<command>#set $s = 1\nrun $s</command></tool>",
        encoding="utf-8",
    )
    # A param whose body carries XML entities (&amp;) and a CDATA section with leading
    # whitespace: the body walker relocates the span, so BOTH paths apply (agree).
    (repo / "entity.xml").write_text(
        "<tool><inputs><param name='e'/></inputs>"
        "<command>\n  <![CDATA[echo a &amp;&amp; run $e]]></command></tool>",
        encoding="utf-8",
    )
    # A Latin-1 (non-UTF-8) tool: the tree mutator parses + applies, but the offset
    # path's bytes convenience bails `encoding` — a sound stricter bail (no mismatch).
    (repo / "latin1.xml").write_bytes(
        "<?xml version='1.0' encoding='ISO-8859-1'?>"
        "<tool><inputs><param name='p' label='café'/></inputs>"
        "<command>run $p</command></tool>".encode("latin-1")
    )
    # No <inputs> -> skipped entirely.
    (repo / "noinputs.xml").write_text(
        "<tool><command>run</command></tool>", encoding="utf-8"
    )

    result = _measure_rename_coverage(corpus_root=tmp_path)
    assert result.cdm_available is True
    assert result.n_tools == 4  # clean + shadow + entity + latin1 (noinputs skipped)
    assert result.n_attempts == 5  # a, b, s, e, p
    assert result.n_success == 4  # a, b, e, p (tree mutator)
    assert result.n_sites == 8  # ($a,def a), ($b,def b), ($e,def e), ($p,def p)
    assert result.bail_counts.get("shadowed") == 1
    assert result.n_tools_all_clean == 3  # clean + entity + latin1 (all tree-clean)
    # Tier-B parity: a, b, s, e agree (e via the body walker); p is the stricter
    # offset-only bail (non-UTF-8 bytes); 0 mismatch.
    assert result.n_plan_agree == 4
    assert result.n_plan_stricter == 1
    assert result.plan_stricter_counts.get("encoding") == 1
    assert result.n_plan_mismatch == 0


def test_measure_rename_macro_spread_classifies(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # pal2nal shape: param defined in the tool, referenced only in a SOLE-OWNED macro.
    (repo / "sole_macros.xml").write_text(
        "<macros><xml name='command'>"
        "<command><![CDATA[run '$pa']]></command></xml></macros>",
        encoding="utf-8",
    )
    (repo / "pal.xml").write_text(
        "<tool id='pal'><macros><import>sole_macros.xml</import></macros>"
        "<inputs><param name='pa' type='data'/></inputs>"
        "<expand macro='command'/></tool>",
        encoding="utf-8",
    )
    # Tool-only: param defined and referenced in the tool itself.
    (repo / "internal.xml").write_text(
        "<tool id='int'><inputs><param name='x'/></inputs>"
        "<command>run $x</command></tool>",
        encoding="utf-8",
    )
    # Shared macro: imported by a.xml AND b.xml, each renaming 'sp' would touch it.
    (repo / "shared.xml").write_text(
        "<macros><xml name='command'>"
        "<command><![CDATA[run '$sp']]></command></xml></macros>",
        encoding="utf-8",
    )
    for tool_id in ("a", "b"):
        (repo / f"{tool_id}.xml").write_text(
            f"<tool id='{tool_id}'><macros><import>shared.xml</import></macros>"
            "<inputs><param name='sp' type='data'/></inputs>"
            "<expand macro='command'/></tool>",
            encoding="utf-8",
        )

    result = _measure_rename_macro_spread(corpus_root=tmp_path)
    assert result.cdm_available is True
    assert result.n_tools == 4  # pal + internal + a + b
    assert result.n_attempts == 4  # pa, x, sp(a), sp(b)
    assert result.n_tool_only == 1  # x
    assert result.n_spills_sole == 1  # pa -> sole_macros.xml
    assert result.n_spills_shared == 2  # sp from a and from b -> shared.xml
    # Every spill here is over a tool that DEFINES the param, so the old single-file
    # rename would have "succeeded" while dangling the macro ref: all 3 silent breaks.
    assert result.n_silent_break_today == 3


# --- xsd-tightenings --------------------------------------------------------------


def test_measure_xsd_tightenings_classifies(tmp_path: Path) -> None:
    xs = "http://www.w3.org/2001/XMLSchema"
    (tmp_path / "galaxy-1.0.xsd").write_text(
        f"""<xs:schema xmlns:xs="{xs}">
  <xs:simpleType name="Color"><xs:restriction base="xs:string">
    <xs:enumeration value="red"/><xs:enumeration value="blue"/>
  </xs:restriction></xs:simpleType>
  <xs:simpleType name="Range"><xs:restriction base="xs:string">
    <xs:pattern value="loose"/>
  </xs:restriction></xs:simpleType>
  <xs:simpleType name="Mood"><xs:restriction base="xs:string">
    <xs:enumeration value="happy"/>
  </xs:restriction></xs:simpleType>
  <xs:complexType name="Thing">
    <xs:attribute name="size" type="xs:string"/>
    <xs:attribute name="name" type="xs:string"/>
  </xs:complexType>
</xs:schema>""",
        encoding="utf-8",
    )
    (tmp_path / "galaxy-2.0.xsd").write_text(
        f"""<xs:schema xmlns:xs="{xs}">
  <xs:simpleType name="Color"><xs:restriction base="xs:string">
    <xs:enumeration value="red"/>
  </xs:restriction></xs:simpleType>
  <xs:simpleType name="Range"><xs:restriction base="xs:string">
    <xs:pattern value="tight"/>
  </xs:restriction></xs:simpleType>
  <xs:simpleType name="Mood"><xs:restriction base="xs:string">
    <xs:enumeration value="happy"/><xs:enumeration value="calm"/>
  </xs:restriction></xs:simpleType>
  <xs:simpleType name="Size"><xs:restriction base="xs:string">
    <xs:pattern value="[0-9]+"/>
  </xs:restriction></xs:simpleType>
  <xs:complexType name="Thing">
    <xs:attribute name="size" type="Size"/>
    <xs:attribute name="name" type="xs:string" use="required"/>
  </xs:complexType>
</xs:schema>""",
        encoding="utf-8",
    )
    result = _measure_xsd_tightenings(schema_dir=tmp_path)
    assert result.versions == ["1.0", "2.0"]
    kinds = {(kind, site) for _, _, kind, site, _ in result.rows}
    assert ("enums-removed", "Color") in kinds  # blue removed = narrowing
    assert ("pattern-changed", "Range") in kinds
    assert ("typed", "Thing.size") in kinds
    assert ("required", "Thing.name") in kinds
    # Mood only GAINED an enum (a widening) -> no row for it.
    assert not any(site == "Mood" for _, _, _, site, _ in result.rows)
    assert len(result.rows) == 4


# --- interpreter-bucket-split ---------------------------------------------------


def test_measure_interpreter_buckets_classifies(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # Bucket A: standard interpreter + literal leading script that exists.
    (repo / "a.xml").write_text(
        '<tool><command interpreter="python">run.py $in</command></tool>',
        encoding="utf-8",
    )
    (repo / "run.py").write_text("print(1)\n", encoding="utf-8")
    # A-missing: same shape but the script is not co-located.
    (repo / "a_missing.xml").write_text(
        '<tool><command interpreter="perl">absent.pl $in</command></tool>',
        encoding="utf-8",
    )
    # B: leading Cheetah directive -> script not statically first.
    (repo / "b.xml").write_text(
        '<tool><command interpreter="python">#if $c\nx.py\n#end if</command></tool>',
        encoding="utf-8",
    )
    # Multi-token interpreter is bucket A since the verbatim-composition widening
    # (here A: the jar is co-located).
    (repo / "c.xml").write_text(
        '<tool><command interpreter="java -jar">app.jar</command></tool>',
        encoding="utf-8",
    )
    (repo / "app.jar").write_bytes(b"")
    # Empty interpreter: legacy-ignored -> its own bucket, never rewritten.
    (repo / "empty.xml").write_text(
        '<tool><command interpreter="">run.py $in</command></tool>',
        encoding="utf-8",
    )
    # No interpreter attribute -> not counted in the population.
    (repo / "plain.xml").write_text(
        "<tool><command>tool $in</command></tool>", encoding="utf-8"
    )

    result = _measure_interpreter_buckets(corpus_root=tmp_path)
    assert result.n_tools == 6
    assert result.n_with_interpreter == 5
    assert result.bucket_a == 2
    assert result.bucket_a_missing == 1
    assert result.bucket_b == 1
    assert result.bucket_empty == 1
    assert result.interpreter_values["python"] == 2
    assert result.interpreter_values["java -jar"] == 1


# --- element-cardinality --------------------------------------------------------


def test_element_cardinality_counts_per_tag(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    (repo / "a.xml").write_text(
        "<tool><requirements><requirement>r</requirement></requirements>"
        "<inputs><conditional name='c'/></inputs>"
        "<tests><test/><test/></tests></tool>",
        encoding="utf-8",
    )
    (repo / "b.xml").write_text(
        "<tool><outputs><collection name='o'/></outputs></tool>",
        encoding="utf-8",
    )
    result = _measure_element_cardinality(corpus_root=tmp_path)
    per_tag = {row[0]: row[1:] for row in result.per_tag}
    assert result.n_unique_tools == 2
    assert per_tag["test"] == (1, 2, 2)
    assert per_tag["requirement"] == (1, 1, 1)
    assert per_tag["conditional"] == (1, 1, 1)
    assert per_tag["collection"] == (1, 1, 1)


def test_element_cardinality_dedups_identical_tools(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    body = "<tool><tests><test/></tests></tool>"
    (repo / "a.xml").write_text(body, encoding="utf-8")
    (repo / "dup.xml").write_text(body, encoding="utf-8")
    result = _measure_element_cardinality(corpus_root=tmp_path)
    assert result.n_unique_tools == 1


# --- command-language -----------------------------------------------------------


def test_classify_command_language_precedence() -> None:
    assert _classify_command_language("python '$__tool_directory__/x.py'") == "python"
    assert _classify_command_language("Rscript foo.R") == "Rscript"
    assert _classify_command_language("perl foo.pl") == "perl"
    assert _classify_command_language("bash -c 'echo hi'") == "shell"
    assert _classify_command_language("samtools view in.bam") == "other"


def test_command_language_buckets_and_missing(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    (repo / "py.xml").write_text(
        "<tool><command><![CDATA[python run.py]]></command></tool>", encoding="utf-8"
    )
    (repo / "sh.xml").write_text(
        "<tool><command>bash do.sh</command></tool>", encoding="utf-8"
    )
    (repo / "none.xml").write_text("<tool><inputs/></tool>", encoding="utf-8")
    result = _measure_command_language(corpus_root=tmp_path)
    buckets = dict(result.buckets)
    assert result.n_unique_tools == 3
    assert result.n_without_command == 1
    assert buckets["python"] == 1
    assert buckets["shell"] == 1


# --- macro-profile-tokens (token-aware profile upgrade target) ------------------


def _ptrow(
    sha: str, raw: object, expanded: object, newest: object
) -> dict[str, object]:
    """One synthetic combined row for the macro-profile-tokens measurement."""
    return {
        "sha256": sha,
        "path": f"{sha}.xml",
        "profile_raw": raw,
        "profile_expanded": expanded,
        "newest_valid": newest,
    }


def test_macro_profile_tokens_buckets() -> None:
    rows = [
        _ptrow("a", "@PROFILE@", "19.01", "24.2"),  # upgradeable
        _ptrow("b", "@P@", "24.2", "24.2"),  # current
        _ptrow("c", "@P@", "24.2", "22.01"),  # token ahead of validity
        _ptrow("d", "@P@", "19.01", _PROFILE_NONE),  # validates nowhere
        _ptrow("e", "@P@", "notaversion", "24.2"),  # unparseable expanded
        _ptrow("f", "24.2", "24.2", "24.2"),  # not a token — ignored
        _ptrow("g", "@P@", "19.1", "19.01"),  # 19.1 == 19.01 -> current
    ]
    result = _measure_macro_profile_tokens(rows=rows)
    assert result.n_unique_tools == 7
    assert result.n_profile_is_token == 6  # f excluded
    assert result.n_upgradeable == 1  # a
    assert result.n_current == 2  # b, g (19.1 == 19.01)
    assert result.n_token_ahead == 1  # c
    assert result.n_validates_nowhere == 1  # d
    assert result.n_unparseable_versions == 1  # e
    assert result.exemplars[0] == ("a.xml", "@PROFILE@", "19.01", "24.2")


# --- macro-topology -------------------------------------------------------------


def test_facts_from_macro_container() -> None:
    macros = etree.fromstring(
        b'<macros><token name="@TOOL_VERSION@">1.0</token>'
        b'<macro name="m"><yield/></macro>'
        b'<xml name="x"><yield name="extra"/></xml></macros>'
    )
    facts = _facts_from_macro_container(macros)
    assert facts.token_names == frozenset({"@TOOL_VERSION@"})
    assert facts.has_yield is True
    assert facts.has_named_yield is True
    assert facts.defines_macro is True


@pytest.fixture()
def macro_corpus(tmp_path: Path) -> Path:
    """Synthetic corpus exercising the macro-topology buckets.

    One macro library imported by two tools (shared), an inline-only tool, a
    macro-free tool, and non-<tool> XML that must be skipped.
    """
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    (repo / "macros.xml").write_text(
        '<macros><token name="@PROFILE@">19.01</token>'
        '<macro name="m"><yield/></macro></macros>',
        encoding="utf-8",
    )
    (repo / "tool1.xml").write_text(
        '<tool profile="@PROFILE@"><macros><import>macros.xml</import></macros>'
        '<expand macro="m"/></tool>',
        encoding="utf-8",
    )
    (repo / "tool2.xml").write_text(
        "<tool><macros><import>macros.xml</import></macros></tool>",
        encoding="utf-8",
    )
    (repo / "inline.xml").write_text(
        '<tool version="@TOOL_VERSION@+galaxy0">'
        '<macros><token name="@TOOL_VERSION@">1.0</token></macros></tool>',
        encoding="utf-8",
    )
    (repo / "plain.xml").write_text("<tool><inputs/></tool>", encoding="utf-8")
    (repo / "not_a_tool.xml").write_text("<data/>", encoding="utf-8")
    return tmp_path


def test_macro_topology_buckets(macro_corpus: Path) -> None:
    result = _measure_macro_topology(corpus_root=macro_corpus)
    assert result.n_unique_tools == 4  # tool1, tool2, inline, plain
    assert result.n_unparseable_skipped == 2  # macros.xml (non-tool root) + not_a_tool
    assert result.n_no_macros == 1  # plain
    assert result.n_inline_only == 1  # inline
    assert result.n_with_imports == 2  # tool1, tool2
    assert result.n_unresolved_imports == 0


def test_macro_topology_sharing_and_yield(macro_corpus: Path) -> None:
    result = _measure_macro_topology(corpus_root=macro_corpus)
    # macros.xml is imported by tool1 and tool2 -> one shared file, 2 importers.
    assert result.n_macro_files == 1
    assert result.n_shared_macro_files == 1
    assert result.max_importers == 2
    assert result.importer_histogram == [(2, 1)]
    # tool1 + tool2 import the shared macros.xml; inline + plain do not.
    assert result.n_imports_shared_macro == 2
    assert result.n_no_shared_macro == 2
    # The shared macro library defines <macro> with a <yield/>.
    assert result.n_uses_yield == 2  # tool1, tool2 (via the imported library)
    assert result.n_named_yield == 0
    assert result.n_defines_macro == 2
    assert result.n_uses_expand == 1  # tool1


def test_macro_topology_token_location(macro_corpus: Path) -> None:
    result = _measure_macro_topology(corpus_root=macro_corpus)
    # tool1's profile=@PROFILE@ is defined in the imported macros.xml, not inline.
    assert result.n_profile_is_token == 1
    assert result.n_profile_token_imported == 1
    assert result.n_profile_token_inline == 0
    assert result.n_profile_token_unresolved == 0
    # inline.xml's version is a token.
    assert result.n_version_is_token == 1
    token_counts = dict(result.top_token_names)
    assert token_counts["@PROFILE@"] == 2  # tool1 + tool2 import it
    assert token_counts["@TOOL_VERSION@"] == 1  # inline.xml


def test_macro_topology_imports_per_tool_flat(macro_corpus: Path) -> None:
    result = _measure_macro_topology(corpus_root=macro_corpus)
    # tool1 + tool2 each import a single (un-nested) macros.xml; inline + plain
    # pull in nothing.
    assert result.n_tools_importing == 2
    assert result.transitive_import_histogram == [(1, 2)]
    assert result.max_transitive_imports == 1
    assert result.n_tools_multi_import == 0
    assert result.n_nested_import_tools == 0


@pytest.fixture()
def nested_macro_corpus(tmp_path: Path) -> Path:
    """Synthetic corpus exercising imports-per-tool bundle sizes.

    A leaf macro file (``base``), a mid file that imports the leaf (``mid``), and
    three tools: one importing the mid file (transitive bundle 2 > direct 1, i.e.
    a nested import), one importing both files directly (bundle 2, not nested),
    and one importing only the leaf (bundle 1).
    """
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    (repo / "base.xml").write_text(
        '<macros><token name="@X@">1</token></macros>', encoding="utf-8"
    )
    (repo / "mid.xml").write_text(
        '<macros><import>base.xml</import><token name="@Y@">2</token></macros>',
        encoding="utf-8",
    )
    (repo / "tool_nested.xml").write_text(
        "<tool><macros><import>mid.xml</import></macros></tool>", encoding="utf-8"
    )
    (repo / "tool_two.xml").write_text(
        "<tool><macros><import>base.xml</import>"
        "<import>mid.xml</import></macros></tool>",
        encoding="utf-8",
    )
    (repo / "tool_single.xml").write_text(
        "<tool><macros><import>base.xml</import></macros></tool>", encoding="utf-8"
    )
    (repo / "plain.xml").write_text("<tool><inputs/></tool>", encoding="utf-8")
    return tmp_path


def test_macro_topology_imports_per_tool_nested(nested_macro_corpus: Path) -> None:
    result = _measure_macro_topology(corpus_root=nested_macro_corpus)
    # Three tools import >=1 macro file (plain imports nothing).
    assert result.n_tools_importing == 3
    # tool_single -> {base} (1); tool_nested -> {mid, base} (2); tool_two ->
    # {base, mid} (2, base deduped).
    assert result.transitive_import_histogram == [(1, 1), (2, 2)]
    assert result.max_transitive_imports == 2
    assert result.n_tools_multi_import == 2  # tool_nested, tool_two
    # Only tool_nested's transitive bundle (2) exceeds its direct imports (1).
    assert result.n_nested_import_tools == 1


def test_render_macro_stats_page_smoke(macro_corpus: Path) -> None:
    topology = _measure_macro_topology(corpus_root=macro_corpus)
    profile_tokens = _measure_macro_profile_tokens(
        rows=[_ptrow("a", "@PROFILE@", "19.01", "24.2")]
    )
    page = _render_macro_stats_page(topology, profile_tokens=profile_tokens)
    assert page.startswith("# Macro corpus statistics")
    assert "## Shared macro files (blast-radius input)" in page
    assert "## Stale macro-token profiles (token-aware upgrade target)" in page


# --- macro-expansion-detection-gap ----------------------------------------------


def test_tally_expansion_gap_classifies_directions() -> None:
    samples = [
        ("unparseable", frozenset(), frozenset()),
        ("no_macros", frozenset(), frozenset()),
        ("expansion_failed", frozenset({"X"}), frozenset()),
        # raw {A, B} vs expanded {B, C}: A over-flags, C under-reports, B agrees.
        ("compared", frozenset({"A", "B"}), frozenset({"B", "C"})),
        ("compared", frozenset({"A"}), frozenset({"A"})),  # A agrees, no divergence
    ]
    result = _tally_expansion_gap(samples=samples)
    assert isinstance(result, _ExpansionGapResult)
    assert result.n_unique_tools == 4  # excludes the unparseable sample
    assert result.n_unparseable == 1
    assert result.n_no_macros == 1
    assert result.n_expansion_failed == 1
    assert result.n_compared == 2
    assert result.over_flag == {"A": 1}
    assert result.under_report == {"C": 1}
    assert result.agree_positive == {"B": 1, "A": 1}
    assert result.n_tools_over_flag == 1
    assert result.n_tools_under_report == 1
    assert result.n_tools_divergent == 1


@pytest.fixture()
def expansion_gap_corpus(tmp_path: Path) -> Path:
    """Corpus where an imported macro supplies the ``<stdio>`` the raw tree lacks.

    ``tool_macro`` ships no literal error handling, so ``16_04_exit_code`` ("no
    error handling") fires on its raw tree; the imported ``<expand macro="stdio"/>``
    injects a ``<stdio>`` post-expansion, so it must NOT fire there — an over-flag.
    ``plain`` is macro-free; ``macros.xml`` + ``not_a_tool`` are non-``<tool>`` XML.
    """
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    (repo / "macros.xml").write_text(
        '<macros><xml name="stdio">'
        '<stdio><exit_code range="1:" level="fatal"/></stdio>'
        "</xml></macros>",
        encoding="utf-8",
    )
    (repo / "tool_macro.xml").write_text(
        "<tool><macros><import>macros.xml</import></macros>"
        '<command>run</command><expand macro="stdio"/></tool>',
        encoding="utf-8",
    )
    (repo / "plain.xml").write_text(
        "<tool><command>run</command></tool>", encoding="utf-8"
    )
    (repo / "not_a_tool.xml").write_text("<data/>", encoding="utf-8")
    return tmp_path


def test_macro_expansion_detection_gap_over_flags_stdio(
    expansion_gap_corpus: Path,
) -> None:
    result = _measure_macro_expansion_detection_gap(corpus_root=expansion_gap_corpus)
    assert result.n_unique_tools == 2  # tool_macro, plain
    assert result.n_unparseable == 2  # macros.xml (non-tool root) + not_a_tool
    assert result.n_no_macros == 1  # plain
    assert result.n_expansion_failed == 0
    assert result.n_compared == 1  # tool_macro
    # 16_04_exit_code fires on the raw tree (no literal <stdio>) but not after the
    # macro injects one -> a raw-only over-flag, never an under-report.
    assert result.over_flag.get("16_04_exit_code") == 1
    assert result.under_report.get("16_04_exit_code", 0) == 0
    assert result.n_tools_over_flag == 1


# --- macro-profile-ownership ----------------------------------------------------

_PROFILE_MACROS = b'<macros><token name="@PROFILE@">19.01</token></macros>'


def _importing_tool(tool_id: str) -> str:
    return (
        f'<tool id="{tool_id}" profile="@PROFILE@">'
        "<macros><import>macros.xml</import></macros></tool>"
    )


@pytest.fixture()
def ownership_corpus(tmp_path: Path) -> tuple[Path, list[dict[str, object]]]:
    """Synthetic corpus exercising every ownership bucket, plus matching rows.

    A shared file whose two profile-using importers AGREE on the target; a
    shared file whose importers DIVERGE; a sole-owned file; and an inline token.
    Each tool's ``newest_valid`` is joined by content sha, so the fixture builds
    the rows from the files it writes.
    """
    repo = tmp_path / "owner" / "repo"
    layout = {
        "agree": (_PROFILE_MACROS, {"a.xml": "26.1", "b.xml": "26.1"}),
        "diverge": (_PROFILE_MACROS, {"c.xml": "24.2", "e.xml": "26.1"}),
        "solo": (_PROFILE_MACROS, {"solo.xml": "26.1"}),
    }
    rows: list[dict[str, object]] = []
    for subdir, (macros, tools) in layout.items():
        directory = repo / subdir
        directory.mkdir(parents=True)
        (directory / "macros.xml").write_bytes(macros)
        for filename, newest in tools.items():
            path = directory / filename
            path.write_text(_importing_tool(path.stem), encoding="utf-8")
            rows.append({"sha256": sha256_of(path), "newest_valid": newest})
    inline = repo / "inline.xml"
    inline.write_text(
        '<tool id="inline" profile="@PROFILE@">'
        '<macros><token name="@PROFILE@">19.01</token></macros></tool>',
        encoding="utf-8",
    )
    rows.append({"sha256": sha256_of(inline), "newest_valid": "26.1"})
    return tmp_path, rows


def test_profile_ownership_placement(
    ownership_corpus: tuple[Path, list[dict[str, object]]],
) -> None:
    corpus_root, rows = ownership_corpus
    result = _measure_macro_profile_ownership(corpus_root=corpus_root, rows=rows)
    assert result.n_unique_tools == 6  # a, b, c, e, solo, inline
    assert result.n_profile_token_tools == 6
    assert result.n_inline == 1  # inline.xml
    assert result.n_imported_direct == 5  # a, b, c, e, solo
    assert result.n_imported_deeper == 0
    assert result.n_unresolved == 0
    assert result.n_defining_same_dir == 5  # every macros.xml is beside its tools


def test_profile_ownership_sharedness_and_agreement(
    ownership_corpus: tuple[Path, list[dict[str, object]]],
) -> None:
    corpus_root, rows = ownership_corpus
    result = _measure_macro_profile_ownership(corpus_root=corpus_root, rows=rows)
    # solo is sole-owned; a, b, c, e import a shared file.
    assert result.n_defining_sole_owned == 1
    assert result.n_defining_shared == 4
    # Two shared defining files, both with >=2 profile users: agree/ and diverge/.
    assert result.n_shared_defining_files == 2
    assert result.n_shared_multi_user == 2
    assert result.n_shared_agree == 1
    assert result.n_shared_diverge == 1
    assert result.n_shared_indeterminate == 0
    assert [path.split("/")[-2] for path, _ in result.diverge_exemplars] == ["diverge"]


def test_profile_ownership_scan_soundness(
    ownership_corpus: tuple[Path, list[dict[str, object]]],
) -> None:
    corpus_root, rows = ownership_corpus
    result = _measure_macro_profile_ownership(corpus_root=corpus_root, rows=rows)
    assert result.n_import_stmts == 5  # a, b, c, e, solo each import macros.xml
    assert result.n_import_dotdot == 0
    assert result.n_import_absolute == 0


def test_render_profile_ownership_page_smoke(
    ownership_corpus: tuple[Path, list[dict[str, object]]],
) -> None:
    corpus_root, rows = ownership_corpus
    result = _measure_macro_profile_ownership(corpus_root=corpus_root, rows=rows)
    page = _render_profile_ownership_page(result)
    assert page.startswith("# Macro profile-token ownership")
    assert "## Do shared files' importers agree on the target profile?" in page


# --- command-iuc-heuristics (GTR020.2 / GTR032 sizing) ----------------------------


def test_count_unquoted_vars_quote_heuristic() -> None:
    # $x is preceded by a space (unquoted); '$y' is preceded by a quote.
    assert _count_unquoted_vars("echo $x and '$y'") == 1
    assert _count_unquoted_vars("'$a' '${b}'") == 0  # both single-quoted
    assert _count_unquoted_vars("$a $b ${c}") == 3  # none quoted


def test_command_iuc_heuristics_counts(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # One unquoted $x, one quoted '$y'; one lone & and one && (not lone).
    (repo / "tool.xml").write_text(
        "<tool><command><![CDATA[echo $x && cat '$y' & wait]]></command></tool>",
        encoding="utf-8",
    )
    (repo / "no_command.xml").write_text("<tool><inputs/></tool>", encoding="utf-8")
    (repo / "not_a_tool.xml").write_text("<data/>", encoding="utf-8")
    result = _measure_command_iuc_heuristics(corpus_root=tmp_path)
    assert result.n_unique_tools == 2  # tool, no_command
    assert result.n_with_command == 1
    assert result.n_tools_unquoted_var == 1
    assert result.n_unquoted_var_findings == 1  # $x only ('$y' is quoted)
    assert result.n_tools_lone_amp == 1
    assert result.n_lone_amp_findings == 1  # the standalone & (&& is not lone)


# --- macro-fmt-idempotence ------------------------------------------------------


def test_macro_fmt_idempotence_sweep(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # A non-canonical macro file (odd indentation) -> would change, idempotent.
    (repo / "macros.xml").write_text(
        '<macros>\n      <token name="@X@">1.0</token>\n</macros>',
        encoding="utf-8",
    )
    # A non-<macros> file is not a macro file and must be skipped.
    (repo / "tool.xml").write_text("<tool><inputs/></tool>", encoding="utf-8")
    result = _measure_macro_fmt_idempotence(corpus_root=tmp_path)
    assert result.n_macro_files == 1
    assert result.n_would_change == 1
    assert result.n_idempotent == 1
    assert result.n_non_idempotent == 0


# --- version-tokenization (Phase-3c @TOOL_VERSION@ sizing) ----------------------


def test_version_tokenization_buckets(tmp_path: Path) -> None:
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # Clean candidate, no <macros> -> need one created.
    (repo / "candidate.xml").write_text(
        '<tool version="1.2.3+galaxy0"><requirements>'
        '<requirement type="package" version="1.2.3">pkg</requirement>'
        "</requirements></tool>",
        encoding="utf-8",
    )
    # Clean candidate that already has a <macros> block.
    (repo / "candidate_macros.xml").write_text(
        '<tool version="2.0+galaxy1"><macros/><requirements>'
        '<requirement type="package" version="2.0">pkg</requirement>'
        "</requirements></tool>",
        encoding="utf-8",
    )
    # Already tokenized.
    (repo / "tokenized.xml").write_text(
        '<tool version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"></tool>',
        encoding="utf-8",
    )
    # version == req literal, no +galaxy suffix.
    (repo / "no_suffix.xml").write_text(
        '<tool version="3.1"><requirements>'
        '<requirement type="package" version="3.1">pkg</requirement>'
        "</requirements></tool>",
        encoding="utf-8",
    )
    # Other literal: version unrelated to any requirement.
    (repo / "other.xml").write_text('<tool version="0.1"></tool>', encoding="utf-8")
    # No version attribute.
    (repo / "no_version.xml").write_text("<tool><inputs/></tool>", encoding="utf-8")
    result = _measure_version_tokenization(corpus_root=tmp_path)
    assert result.n_unique_tools == 6
    assert result.n_already_tokenized == 1
    assert result.n_missing_version == 1
    assert result.n_candidates == 2
    assert result.n_candidates_need_macros == 1  # candidate.xml
    assert result.n_candidates_have_macros == 1  # candidate_macros.xml
    assert result.n_version_equals_req_no_suffix == 1
    assert result.n_other_literal == 1


def test_classify_lone_amps_buckets() -> None:
    """The GTR032 lone-& classifier separates the anti-pattern from look-alikes."""
    classify = _classify_lone_amps
    # Redirections are not command joining.
    assert classify("samtools view a 2>&1")["redirect"] == 1
    assert classify("prog &> log")["redirect"] == 1
    assert classify("exec 3<&0")["redirect"] == 1
    # |& is a pipe operator, not joining.
    assert classify("a |& b")["pipe"] == 1
    # A literal & inside a quoted argument (sed/awk "matched text").
    assert classify("sed 's/^x/&!/' f")["quoted"] == 1
    assert classify('echo "a & b"')["quoted"] == 1
    # The genuine cases.
    assert classify("cmd1 & cmd2")["joining"] == 1  # the GTR032 anti-pattern
    assert classify("server &\nwait")["background"] == 1  # trailing background
    # && is logical-and, never a lone &.
    assert classify("a && b") == {}


def test_classify_command_vars_buckets() -> None:
    """The GTR020.2 classifier separates shell-arg $vars from Cheetah directives."""
    classify = _classify_command_vars
    # A directive line's $vars are template logic, not shell args.
    assert classify("#if $cond\nrun") == {"directive": 1}
    assert classify("## $note") == {"directive": 1}
    # Shell-line quote state.
    assert classify("echo '$a'")["single_quoted"] == 1
    assert classify('echo "$b"')["double_quoted"] == 1
    assert classify("echo $c")["unquoted"] == 1
    assert classify("echo ${d}")["unquoted"] == 1  # ${...} form
    # A realistic mix: directive excluded, one quoted + one unquoted on the shell.
    counts = classify("#set $x = 1\nsamtools sort '$input' -o $output")
    assert counts["directive"] == 1  # $x
    assert counts["single_quoted"] == 1  # '$input'
    assert counts["unquoted"] == 1  # $output
    # $(...) and $1 are not Cheetah vars.
    assert classify("echo $(date) $1") == {}


def test_measure_iuc011_fixability_buckets_and_option_b(tmp_path: Path) -> None:
    """The walker buckets each unquoted var and separates the Option-A floor (safe
    bare params) from the Option-B provable set (+ path built-ins / space-free
    attrs), so a whole-tool count reflects exactly the GTR020 auto-fix population."""
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # Tool A: every unquoted var is provable, and one is a non-safe provable class
    # ($__tool_directory__ -> builtin_path), so Option B "newly unlocks" it.
    (repo / "a.xml").write_text(
        '<tool id="a" name="A"><inputs><param name="ds" type="data"/></inputs>'
        "<command><![CDATA[python $__tool_directory__/s.py $ds]]></command></tool>",
        encoding="utf-8",
    )
    # Tool B: a free-form text param ($opts) keeps it out of the whole-tool set,
    # even though $ds.ext is a provable space-free attr.
    (repo / "b.xml").write_text(
        '<tool id="b" name="B"><inputs>'
        '<param name="opts" type="text"/><param name="ds" type="data"/></inputs>'
        "<command><![CDATA[run $opts $ds.ext]]></command></tool>",
        encoding="utf-8",
    )

    result = _measure_iuc011_fixability(corpus_root=tmp_path)
    assert result.n_tools_flagged == 2
    assert result.n_occurrences == 4
    assert result.per_class == {
        "safe": 1,  # $ds
        "builtin_path": 1,  # $__tool_directory__
        "text": 1,  # $opts
        "attr_safe": 1,  # $ds.ext
    }
    assert result.n_tools_all_provable == 1  # only tool A
    assert result.n_tools_beyond_safe == 1  # tool A has a builtin_path var


@pytest.mark.skipif(
    not shell_oracle_available(), reason="needs the shell-oracle extra (bashlex)"
)
def test_measure_shell_oracle_quoting_narrows_only(tmp_path: Path) -> None:
    """The oracle does NOT widen (assignment-RHS is unsound for Cheetah-rendered
    literals); its only sound delta vs the value-domain rule is the fd-dup narrowing."""
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)
    # NOT widened: $opts is a free-form text param in an assignment RHS. The shell-
    # expansion no-split rule does not apply to a Cheetah-rendered literal, so the
    # oracle leaves it to the value-domain rule (text -> not provable -> not quoted).
    (repo / "no_widen.xml").write_text(
        '<tool id="w" name="W"><inputs><param name="opts" type="text"/></inputs>'
        "<command><![CDATA[THREADS=$opts]]></command></tool>",
        encoding="utf-8",
    )
    # Narrow: $fd is an integer (value-domain safe), but in a >&-dup position the
    # oracle declines it.
    (repo / "narrow.xml").write_text(
        '<tool id="n" name="N"><inputs><param name="fd" type="integer"/></inputs>'
        "<command><![CDATA[run 2>&$fd]]></command></tool>",
        encoding="utf-8",
    )
    result = _measure_shell_oracle_quoting(corpus_root=tmp_path)
    assert result.oracle_available is True
    assert result.widened_occurrences == 0 and result.widened_tools == 0
    assert result.narrowed_occurrences == 1 and result.narrowed_tools == 1


def test_measure_macro_token_residual_detects_imported_token(tmp_path: Path) -> None:
    """A tool stuck at 24.1 only because an imported token supplies an uppercase
    datatype is counted, and a tool whose token is already lowercase is not — so a
    corpus-wide 0 means "no such tool", not a broken measure."""
    repo = tmp_path / "owner" / "repo"
    repo.mkdir(parents=True)

    def _tool(*, fmt_token: str) -> str:
        return (
            '<tool id="m" name="M" version="1.0.0" profile="24.1">'
            f"<macros><import>{fmt_token}_macros.xml</import></macros>"
            "<command><![CDATA[echo x]]></command>"
            "<inputs/>"
            '<outputs><data name="o" format="@FMT@"/></outputs>'
            "</tool>"
        )

    # Coercible imported token (GTiff) — expanded format trips the 24.2 pattern.
    (repo / "up.xml").write_text(_tool(fmt_token="up"), encoding="utf-8")
    (repo / "up_macros.xml").write_text(
        '<macros><token name="@FMT@">GTiff</token></macros>', encoding="utf-8"
    )
    # Already-lowercase token — nothing to coerce, must not be counted.
    (repo / "ok.xml").write_text(_tool(fmt_token="ok"), encoding="utf-8")
    (repo / "ok_macros.xml").write_text(
        '<macros><token name="@FMT@">bam</token></macros>', encoding="utf-8"
    )

    result = _measure_macro_token_residual(corpus_root=tmp_path)
    assert result.n_token_datatype == 1  # only the GTiff tool is a coercible candidate
    assert result.residual_tools == 1
    assert result.imported_involved == 1
    assert result.inline_only == 0


# --- RST <help> investigation measures (help-rst-errors/features/to-markdown) ----


@pytest.fixture()
def rst_help_corpus(tmp_path: Path) -> Path:
    """Synthetic corpus exercising the RST-help eligibility + classification."""
    repo = tmp_path / "owner" / "help-repo"
    repo.mkdir(parents=True)

    def _tool(name: str, help_attr: str, body: str) -> None:
        (repo / name).write_text(
            f"<tool id='{name}'><help{help_attr}>{body}</help></tool>",
            encoding="utf-8",
        )

    # valid RST, only CommonMark-expressible nodes -> valid + convertible
    _tool("valid.xml", "", "\nTitle\n=====\n\nA paragraph with **bold**.\n\n- a\n- b\n")
    # invalid RST (unclosed inline strong = WARNING/level-2), otherwise simple shape
    _tool("invalid.xml", "", "\nsome **unclosed strong text\n")
    # valid RST using a definition list (no CommonMark equivalent) -> valid + complex
    _tool("complex.xml", "", "\nterm\n   the definition\n")
    # invalid RST, deterministically fixable (transition at end of document)
    _tool("fixable.xml", "", "\nA paragraph.\n\n----\n")
    # excluded: markdown format
    _tool("markdown.xml", " format='markdown'", "\n# A heading\n")
    # excluded: macro token in the body
    _tool("macro.xml", "", "\n@HELP_OVERVIEW@\n")
    # excluded: no <help> at all
    (repo / "nohelp.xml").write_text("<tool id='nohelp'/>", encoding="utf-8")
    return tmp_path


def test_help_rst_errors_classifies_and_excludes(rst_help_corpus: Path) -> None:
    result = _measure_help_rst_errors(corpus_root=rst_help_corpus)
    # markdown / macro / no-help bodies are excluded; 4 RST bodies remain.
    assert result.n_rst_tools == 4
    assert result.n_parse_fail == 0
    assert result.n_invalid == 2  # unclosed-strong + transition-at-end
    # only the transition tool's errors are all in the deterministic-fix set.
    assert result.n_fully_fixable == 1
    classes = {cls for cls, _occ, _tools in result.class_buckets}
    assert any("strong" in cls for cls in classes)
    assert "Transition at the end of the document." in classes


def test_help_rst_features_flags_definition_list(rst_help_corpus: Path) -> None:
    result = _measure_help_rst_features(corpus_root=rst_help_corpus)
    assert result.n_rst_tools == 4
    # valid, invalid (problematic ignored), and transition are convertible; complex not.
    assert result.n_convertible_shape == 3
    blocking = {name for name, _count in result.blocking_features}
    assert "definition_list" in blocking


def test_help_rst_to_markdown_2x2(rst_help_corpus: Path) -> None:
    result = _measure_help_rst_to_markdown(corpus_root=rst_help_corpus)
    assert result.n_rst_tools == 4
    assert result.valid_convertible == 1  # the simple valid tool
    assert result.invalid_convertible == 2  # unclosed-strong + transition (both simple)
    assert result.valid_complex == 1  # the definition-list tool
    assert result.invalid_complex == 0


def test_help_rst_measures_empty_corpus(tmp_path: Path) -> None:
    assert _measure_help_rst_errors(corpus_root=tmp_path).n_rst_tools == 0
    assert _measure_help_rst_features(corpus_root=tmp_path).n_rst_tools == 0
    assert _measure_help_rst_to_markdown(corpus_root=tmp_path).n_rst_tools == 0
    assert _measure_help_rst_md_convert(corpus_root=tmp_path).n_rst_tools == 0


# --- RST -> CommonMark converter + render-equivalence gate (help-rst-md-convert) --


@pytest.fixture()
def rst_md_convert_corpus(tmp_path: Path) -> Path:
    """Synthetic corpus pinning each ``help-rst-md-convert`` verdict class."""
    repo = tmp_path / "owner" / "convert-repo"
    repo.mkdir(parents=True)

    def _tool(name: str, body: str) -> None:
        (repo / name).write_text(
            f"<tool id='{name}'><help>{body}</help></tool>", encoding="utf-8"
        )

    # Whitelist-only nodes; renders identically both sides -> CONVERT + gate PASS.
    _tool(
        "pass.xml",
        "\nTitle\n=====\n\nA paragraph with **bold** and a "
        "`link &lt;https://example.org&gt;`_.\n\n- item one\n- item two\n",
    )
    # A definition list has no CommonMark form -> converter BAIL.
    _tool("bail.xml", "\nterm\n   the definition\n")
    # An RST literal may contain a backtick; the single-backtick CommonMark code
    # span the converter emits cannot -> renders differently -> gate FAIL.
    _tool("gatefail.xml", "\nA paragraph with a ``lit`eral`` span.\n")
    return tmp_path


def test_help_rst_md_convert_verdict_classes(rst_md_convert_corpus: Path) -> None:
    result = _measure_help_rst_md_convert(corpus_root=rst_md_convert_corpus)
    assert result.n_rst_tools == 3
    assert result.n_pass == 1
    assert result.n_bail == 1
    assert result.n_gate_fail == 1
    assert result.bail_classes == [("definition_list", 1)]
