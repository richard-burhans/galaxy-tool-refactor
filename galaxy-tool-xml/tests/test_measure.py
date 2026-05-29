"""Unit tests for measure.py measurement helpers."""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path

import pytest
from lxml import etree
from scripts.measure import (
    _COLLECTION_TYPE_MEMBERS,
    _MATCH_KEYS,
    _collection_type_patterns,
    _cross_source_key_matches,
    _measure_collection_type_normalization,
    _measure_param_types,
    _ParamTypesResult,
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
