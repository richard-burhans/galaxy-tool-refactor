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
    _classify_command_language,
    _collection_type_patterns,
    _count_unquoted_vars,
    _cross_source_key_matches,
    _facts_from_macro_container,
    _measure_collection_type_normalization,
    _measure_command_iuc_heuristics,
    _measure_command_language,
    _measure_element_cardinality,
    _measure_macro_fmt_idempotence,
    _measure_macro_profile_ownership,
    _measure_macro_profile_tokens,
    _measure_macro_topology,
    _measure_output_format_input,
    _measure_param_types,
    _measure_semantic_upgrade_boundaries,
    _measure_upgrade_headroom,
    _measure_version_tokenization,
    _ParamTypesResult,
    _render_macro_stats_page,
    _render_profile_ownership_page,
    _version_tuple,
)


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
    from galaxy_tool_xml.profiles import latest_profile

    schema_dir = importlib.resources.files("galaxy_tool_xml") / "schema"
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
    # needs qualified ref: single data input nested in a conditional
    (repo / "nested.xml").write_text(
        '<tool><inputs><conditional name="c">'
        '<param type="data" name="i"/></conditional></inputs>'
        '<outputs><data name="o" format="input"/></outputs></tool>',
        encoding="utf-8",
    )
    # not counted: no format="input"
    (repo / "clean.xml").write_text(
        '<tool><inputs><param type="data" name="i"/></inputs>'
        '<outputs><data name="o" format="txt"/></outputs></tool>',
        encoding="utf-8",
    )
    result = _measure_output_format_input(corpus_root=tmp_path)
    assert result.n_tools_parsed == 4
    assert result.n_tools_with_format_input == 3
    assert result.n_auto_fixable == 1  # auto.xml only
    buckets = result.by_data_input_bucket
    assert buckets["1 top-level (auto-fixable)"] == 1
    assert buckets["2+ data inputs"] == 1
    assert buckets["1 nested (needs qualified ref)"] == 1


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


def test_version_tuple_equates_zero_padded_versions() -> None:
    assert _version_tuple("20.5") == _version_tuple("20.05") == (20, 5)
    assert _version_tuple("@PROFILE@") is None
    assert _version_tuple(None) is None


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


def test_render_macro_stats_page_smoke(macro_corpus: Path) -> None:
    topology = _measure_macro_topology(corpus_root=macro_corpus)
    profile_tokens = _measure_macro_profile_tokens(
        rows=[_ptrow("a", "@PROFILE@", "19.01", "24.2")]
    )
    page = _render_macro_stats_page(topology, profile_tokens=profile_tokens)
    assert page.startswith("# Macro corpus statistics")
    assert "## Shared macro files (blast-radius input)" in page
    assert "## Stale macro-token profiles (token-aware upgrade target)" in page


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


# --- command-iuc-heuristics (IUC011 / IUC012 sizing) ----------------------------


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
