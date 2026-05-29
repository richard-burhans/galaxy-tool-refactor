"""Unit tests for measure.py measurement helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.measure import (
    _MATCH_KEYS,
    _cross_source_key_matches,
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
