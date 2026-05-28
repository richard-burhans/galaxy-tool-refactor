"""Unit tests for measure.py measurement helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.measure import _ParamTypesResult, _measure_param_types


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
