"""Unit tests for the corpus-stats fine-grained emitter helpers.

End-to-end behaviour is covered by a full ``scripts/corpus_check.py``
sweep, but the per-source vs combined column shape, the per-profile
validity flags, and the TSV escaping are each small enough to be worth
covering in isolation so a schema regression surfaces without paying
for a multi-minute sweep.
"""

from __future__ import annotations

import json
from collections import Counter as _Counter
from pathlib import Path

import pytest
import scripts.corpus_check as corpus_check
from scripts.corpus_check import (
    ToolStats,
    _failure_slug,
    _format_presence_failures,
    _make_row,
    _stamp_presence,
    _tool_source_url,
    _tsv_safe,
    _write_corpus_data,
    _write_failure_details,
)

from galaxy_tool_source.profiles import available_profiles


def _stats(
    *,
    validity: list[bool] | None = None,
    has_macros: bool = True,
    expansion_failure_reason: str | None = None,
    no_valid_reason: str | None = None,
) -> ToolStats:
    """Build a ToolStats with a default-everything-False validity vector."""
    profiles = available_profiles()
    return ToolStats(
        profile_raw="@PROFILE@",
        profile_expanded="25.0",
        tool_id="kegalign",
        newest_valid="26.1",
        validity=validity if validity is not None else [False] * len(profiles),
        has_macros=has_macros,
        contiguous=False,
        expansion_failure_reason=expansion_failure_reason,
        no_valid_reason=no_valid_reason,
    )


def _row(**overrides: object) -> dict[str, str | int | None]:
    """Build one fully-populated combined-schema row with overridable fields."""
    defaults: dict[str, object] = {
        "display_name": "richard-burhans/kegalign",
        "version": "f885abcfe3a0",
        "path": Path("/repo/tool.xml"),
        "repo_dir": Path("/repo"),
        "sha": "abc",
        "stats": _stats(),
    }
    defaults.update(overrides)
    return _make_row(**defaults)  # type: ignore[arg-type]


def test_make_row_carries_the_full_combined_schema() -> None:
    profiles = available_profiles()
    row = _row()
    assert list(row.keys())[:12] == [
        "repo",
        "version",
        "path",
        "tool_id",
        "sha256",
        "profile_raw",
        "profile_expanded",
        "newest_valid",
        "has_macros",
        "expansion_failure_reason",
        "no_valid_reason",
        "source",
    ]
    assert len(row) == 12 + len(profiles)
    for profile in profiles:
        assert f"valid_{profile}" in row


def test_make_row_source_column_reflects_repo_kind() -> None:
    # toolshed repos carry an owner/ slash; github repos do not.
    assert _row(display_name="tools-iuc")["source"] == "github"
    assert _row(display_name="owner/repo")["source"] == "toolshed"


def test_make_row_failure_reason_columns_default_to_none() -> None:
    row = _row()
    # _stats() builds a ToolStats with no failure reasons set; these flow
    # through as JSON null and TSV empty-string.
    assert row["expansion_failure_reason"] is None
    assert row["no_valid_reason"] is None


def test_make_row_failure_reason_columns_propagate_from_stats() -> None:
    row = _row(
        stats=_stats(
            expansion_failure_reason="undefined macro reference in <expand>",
            no_valid_reason="(macro expansion failed)",
        )
    )
    assert row["expansion_failure_reason"] == "undefined macro reference in <expand>"
    assert row["no_valid_reason"] == "(macro expansion failed)"


def test_make_row_path_is_relative_to_repo_dir() -> None:
    row = _row(path=Path("/repo/tools/sub/tool.xml"), repo_dir=Path("/repo"))
    assert row["path"] == "tools/sub/tool.xml"


def test_make_row_propagates_identifying_fields() -> None:
    row = _row(display_name="some/repo", version="abcdef012345", sha="dead")
    assert row["repo"] == "some/repo"
    assert row["version"] == "abcdef012345"
    assert row["sha256"] == "dead"
    assert row["tool_id"] == "kegalign"


def test_make_row_validity_flags_are_int_zero_or_one() -> None:
    profiles = available_profiles()
    pattern = [bool(i % 2) for i in range(len(profiles))]
    row = _row(stats=_stats(validity=pattern))
    for profile, ok in zip(profiles, pattern, strict=True):
        value = row[f"valid_{profile}"]
        assert isinstance(value, int)
        assert value == (1 if ok else 0)


def test_make_row_has_macros_is_int_zero_or_one() -> None:
    assert _row(stats=_stats(has_macros=True))["has_macros"] == 1
    assert _row(stats=_stats(has_macros=False))["has_macros"] == 0


def test_tsv_safe_replaces_tab_newline_cr_with_space() -> None:
    assert _tsv_safe("a\tb") == "a b"
    assert _tsv_safe("a\nb") == "a b"
    assert _tsv_safe("a\rb") == "a b"
    assert _tsv_safe("a\t\n\rb") == "a   b"
    assert _tsv_safe("ordinary value") == "ordinary value"


def _two_rows() -> list[dict[str, str | int | None]]:
    profiles = available_profiles()
    rows = [
        _row(sha="sha_a", stats=_stats(validity=[True] * len(profiles))),
        _row(
            display_name="other/repo",
            version="aaaaaaaaaaaa",
            path=Path("/repo/b.xml"),
            sha="sha_b",
            stats=_stats(validity=[False] * len(profiles)),
        ),
    ]
    corpus_check._stamp_presence(rows)
    return rows


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``_CORPUS_DATA_DIR`` at the module level for one test."""
    monkeypatch.setattr(corpus_check, "_CORPUS_DATA_DIR", tmp_path)
    return tmp_path


def test_write_corpus_data_per_source_omits_profile_columns(
    isolated_data_dir: Path,
) -> None:
    _write_corpus_data(rows=_two_rows(), source="github", include_profile_columns=False)
    data = json.loads(
        (isolated_data_dir / "corpus_data.json").read_text(encoding="utf-8")
    )
    assert len(data) == 2
    assert list(data[0].keys()) == ["repo", "version", "path", "tool_id", "sha256"]


def test_write_corpus_data_combined_includes_validity_flags(
    isolated_data_dir: Path,
) -> None:
    _write_corpus_data(
        rows=_two_rows(), source="combined", include_profile_columns=True
    )
    data = json.loads(
        (isolated_data_dir / "combined_corpus_data.json").read_text(encoding="utf-8")
    )
    profiles = available_profiles()
    assert len(data[0]) == 12 + len(profiles)
    assert data[0]["source"] in ("github", "toolshed")
    # Row 0 was built with validity=[True, ...]; row 1 with [False, ...].
    for profile in profiles:
        assert data[0][f"valid_{profile}"] == 1
        assert data[1][f"valid_{profile}"] == 0


def test_write_corpus_data_combined_tsv_has_header_plus_one_row_per_record(
    isolated_data_dir: Path,
) -> None:
    _write_corpus_data(
        rows=_two_rows(), source="combined", include_profile_columns=True
    )
    lines = (
        (isolated_data_dir / "combined_corpus_data.tsv")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    profiles = available_profiles()
    expected_columns = 12 + len(profiles)
    assert len(lines) == 3  # header + 2 data rows
    assert lines[0].split("\t")[0] == "repo"
    assert len(lines[0].split("\t")) == expected_columns
    for value in lines[1].split("\t")[12:]:
        assert value == "1"
    for value in lines[2].split("\t")[12:]:
        assert value == "0"


def test_write_corpus_data_tsv_sanitizes_field_values_containing_tabs(
    isolated_data_dir: Path,
) -> None:
    profiles = available_profiles()
    stats = ToolStats(
        profile_raw="(none)",
        profile_expanded="(none)",
        tool_id="bad\ttool\nid",
        newest_valid="(none)",
        validity=[False] * len(profiles),
        has_macros=False,
        contiguous=True,
    )
    row = _row(stats=stats)
    _write_corpus_data(rows=[row], source="github", include_profile_columns=False)
    lines = (
        (isolated_data_dir / "corpus_data.tsv").read_text(encoding="utf-8").splitlines()
    )
    assert len(lines[1].split("\t")) == 5  # tabs in tool_id did not split the row
    tool_id_value = lines[1].split("\t")[3]
    assert "\t" not in tool_id_value
    assert "\n" not in tool_id_value
    assert tool_id_value == "bad tool id"


def test_write_corpus_data_json_uses_native_integers_for_validity_flags(
    isolated_data_dir: Path,
) -> None:
    _write_corpus_data(
        rows=_two_rows(), source="combined", include_profile_columns=True
    )
    raw = (isolated_data_dir / "combined_corpus_data.json").read_text(encoding="utf-8")
    # JSON ints (no surrounding quotes) — verify by string search and by
    # round-tripping back through json.loads.
    for profile in available_profiles():
        assert f'"valid_{profile}": 1' in raw or f'"valid_{profile}": 0' in raw
    data = json.loads(raw)
    sample = next(value for key, value in data[0].items() if key.startswith("valid_"))
    assert isinstance(sample, int)


def test_write_corpus_data_tsv_renders_none_failure_reasons_as_empty_string(
    isolated_data_dir: Path,
) -> None:
    _write_corpus_data(
        rows=_two_rows(), source="combined", include_profile_columns=True
    )
    lines = (
        (isolated_data_dir / "combined_corpus_data.tsv")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    header = lines[0].split("\t")
    expansion_idx = header.index("expansion_failure_reason")
    no_valid_idx = header.index("no_valid_reason")
    # _stats() leaves both reasons None; TSV should render them as "".
    for row in lines[1:]:
        cells = row.split("\t")
        assert cells[expansion_idx] == ""
        assert cells[no_valid_idx] == ""


def test_failure_slug_renders_filesystem_safe() -> None:
    assert _failure_slug("undefined macro reference in <expand>") == (
        "undefined-macro-reference-in-expand"
    )
    assert _failure_slug("invalid boolean ('True'/'False' vs 'true'/'false')") == (
        "invalid-boolean-true-false-vs-true-false"
    )
    assert _failure_slug("(macro expansion failed)") == "macro-expansion-failed"
    # Edge case: a reason with no alphanumerics produces a non-empty fallback.
    assert _failure_slug("???") == "unknown"


def test_tool_source_url_constructs_toolshed_link() -> None:
    # Toolshed hgweb routes are 403 behind nginx, so we link to the
    # public `/view/<owner>/<name>` browse page only — the file path and
    # changeset are rendered in adjacent table columns.
    url = _tool_source_url("richard-burhans/kegalign", "f885abcfe3a0", "kegalign.xml")
    assert url == "https://toolshed.g2.bx.psu.edu/view/richard-burhans/kegalign"


def test_tool_source_url_constructs_github_link() -> None:
    url = _tool_source_url("tools-iuc", "abc123def456", "tools/foo/foo.xml")
    # tools-iuc is in corpus_sources.json pointing at github.com.
    assert url is not None
    assert url.startswith(
        "https://github.com/galaxyproject/tools-iuc/blob/abc123def456/"
    )
    assert url.endswith("tools/foo/foo.xml")


def test_tool_source_url_constructs_gitlab_link() -> None:
    url = _tool_source_url("einonm-galaxy-tools", "deadbeef0001", "some/path.xml")
    # einonm-galaxy-tools is in corpus_sources.json pointing at gitlab.com.
    assert url is not None
    assert url.startswith("https://gitlab.com/einonm/galaxy-tools/-/blob/deadbeef0001/")


def test_tool_source_url_returns_none_for_unknown_repo() -> None:
    assert _tool_source_url("no-such-repo", "deadbeef", "x.xml") is None


def test_tool_source_url_returns_none_for_unknown_version_sentinel() -> None:
    # `fetch_toolshed.py` writes "unknown" for clones predating the manifest;
    # building a URL with that sentinel would 404. _tool_source_url refuses.
    assert _tool_source_url("iuc/some-tool", "unknown", "tool.xml") is None
    assert _tool_source_url("tools-iuc", "unknown", "tool.xml") is None


def test_write_failure_details_writes_index_and_per_reason_files(
    tmp_path: Path,
) -> None:
    rows: list[dict[str, str | int | None]] = [
        _row(
            sha="sha_a",
            stats=_stats(
                expansion_failure_reason="undefined macro reference in <expand>",
                no_valid_reason="(macro expansion failed)",
            ),
        ),
        _row(
            display_name="tools-iuc",
            version="abc123def4567890",
            path=Path("/repo/tools/foo/foo.xml"),
            sha="sha_b",
            stats=_stats(no_valid_reason="XSD does not declare attribute used by tool"),
        ),
        # A duplicate of sha_a should be deduplicated.
        _row(
            display_name="some-other-repo",
            sha="sha_a",
            stats=_stats(
                expansion_failure_reason="undefined macro reference in <expand>",
            ),
        ),
        # A tool with no failure reason should not appear in any failure file.
        _row(sha="sha_c", stats=_stats()),
    ]
    _write_failure_details(rows=rows, output_dir=tmp_path)

    index = (tmp_path / "README.md").read_text(encoding="utf-8")
    # All three reason categories should appear in the index — the Group A
    # tool lands in both its sub-category file and the umbrella page so
    # links from the combined stats markdown resolve.
    assert "undefined-macro-reference-in-expand.md" in index
    assert "macro-expansion-failed.md" in index
    assert "xsd-does-not-declare-attribute-used-by-tool.md" in index
    # The dedup should leave just one entry under the macro sub-category file.
    macro_page = (tmp_path / "undefined-macro-reference-in-expand.md").read_text(
        encoding="utf-8"
    )
    assert macro_page.count("| richard-burhans/kegalign |") == 1
    # And the same tool appears in the umbrella page (also deduped).
    umbrella_page = (tmp_path / "macro-expansion-failed.md").read_text(encoding="utf-8")
    assert umbrella_page.count("| richard-burhans/kegalign |") == 1
    # The Group B category file got the tools-iuc tool with a github link.
    xsd_page = (tmp_path / "xsd-does-not-declare-attribute-used-by-tool.md").read_text(
        encoding="utf-8"
    )
    assert "https://github.com/galaxyproject/tools-iuc/blob/abc123def456" in xsd_page


def test_stamp_presence_marks_github_only_toolshed_only_and_both() -> None:
    profiles = available_profiles()
    rows: list[dict[str, str | int | None]] = [
        # tool_id "alpha" exists in github only
        _row(
            display_name="tools-iuc",
            sha="sha_a",
            stats=_stats(validity=[True] * len(profiles)),
        ),
        # tool_id "beta" exists in toolshed only — override tool_id
        _row(
            display_name="owner/repo",
            sha="sha_b",
            stats=_stats(validity=[True] * len(profiles)),
        ),
        # tool_id "kegalign" exists in BOTH (this is the default _stats id)
        _row(
            display_name="tools-iuc",
            sha="sha_c",
            stats=_stats(validity=[True] * len(profiles)),
        ),
        _row(
            display_name="other/repo",
            sha="sha_d",
            stats=_stats(validity=[True] * len(profiles)),
        ),
    ]
    # Make the first two have distinct tool_ids so we exercise *_only.
    rows[0]["tool_id"] = "alpha"
    rows[1]["tool_id"] = "beta"
    _stamp_presence(rows)
    assert rows[0]["presence"] == "github_only"
    assert rows[1]["presence"] == "toolshed_only"
    assert rows[2]["presence"] == "both"
    assert rows[3]["presence"] == "both"


def test_stamp_presence_handles_empty_tool_id() -> None:
    profiles = available_profiles()
    rows: list[dict[str, str | int | None]] = [
        _row(sha="sha_a", stats=_stats(validity=[True] * len(profiles))),
    ]
    rows[0]["tool_id"] = ""
    _stamp_presence(rows)
    assert rows[0]["presence"] == ""


def test_format_presence_failures_emits_two_subtables() -> None:
    profiles = available_profiles()
    rows: list[dict[str, str | int | None]] = [
        # github failure, tool_id seen in github only → github-only
        _row(
            display_name="tools-iuc",
            sha="sha_a",
            stats=_stats(
                no_valid_reason="XSD does not declare attribute used by tool",
                validity=[False] * len(profiles),
            ),
        ),
        # toolshed failure, tool_id NOT seen in github → toolshed-only
        _row(
            display_name="owner/repo",
            sha="sha_b",
            stats=_stats(
                no_valid_reason="XSD does not declare attribute used by tool",
                validity=[False] * len(profiles),
            ),
        ),
        # toolshed failure whose tool_id IS also in github → both
        _row(
            display_name="other/repo",
            sha="sha_c",
            stats=_stats(
                no_valid_reason="XSD does not declare attribute used by tool",
                validity=[False] * len(profiles),
            ),
        ),
        _row(
            display_name="bgruening-galaxytools",
            sha="sha_d",
            stats=_stats(validity=[True] * len(profiles)),
        ),
    ]
    # Give the first two distinct tool_ids so they're github-only / toolshed-only.
    rows[0]["tool_id"] = "alpha"
    rows[1]["tool_id"] = "beta"
    # rows[2] and rows[3] share the default tool_id "kegalign" — present in both.
    _stamp_presence(rows)
    output = "\n".join(_format_presence_failures(rows))
    assert "## Failures by source presence" in output
    assert "### Failing on github" in output
    assert "### Failing on toolshed" in output
    assert "| github-only | 1 |" in output
    assert "| github + toolshed twin | 0 |" in output
    assert "| toolshed-only | 1 |" in output
    assert "| toolshed + github sibling | 1 |" in output


def test_write_failure_details_annotates_toolshed_rows_with_github_siblings(
    tmp_path: Path,
) -> None:
    """A toolshed row whose tool_id also exists in github gets `(also in github: …)`."""
    profiles = available_profiles()
    rows: list[dict[str, str | int | None]] = [
        # github tool, same tool_id as the failing toolshed one — provides the sibling
        _row(
            display_name="tools-iuc",
            sha="sha_gh",
            stats=_stats(validity=[True] * len(profiles)),
        ),
        # The failing toolshed tool — shares default tool_id "kegalign"
        _row(
            display_name="someone/kegalign",
            sha="sha_ts",
            stats=_stats(
                no_valid_reason="XSD does not declare attribute used by tool",
                validity=[False] * len(profiles),
            ),
        ),
    ]
    _stamp_presence(rows)
    _write_failure_details(rows=rows, output_dir=tmp_path)
    page = (tmp_path / "xsd-does-not-declare-attribute-used-by-tool.md").read_text(
        encoding="utf-8"
    )
    assert "someone/kegalign (also in github: tools-iuc)" in page


def test_profile_sort_key_distinguishes_version_equal_strings() -> None:
    """``20.5`` and ``20.05`` are numerically equal but must get distinct keys.

    Otherwise their stat-table rows tie and the order depends on dict iteration,
    churning the regenerated artifact on every sweep.
    """
    assert corpus_check._profile_sort_key("20.5") != corpus_check._profile_sort_key(
        "20.05"
    )
    assert corpus_check._profile_sort_key_newest_first(
        "24.1"
    ) != corpus_check._profile_sort_key_newest_first("24.01")


def test_profile_sort_is_deterministic_regardless_of_input_order() -> None:
    """Sorting the same labels in any input order yields one canonical order."""
    labels = ["24.1", "24.01", "20.05", "20.5", "24.0", "24.00", "19.01", "26.0"]
    forward = sorted(labels, key=corpus_check._profile_sort_key)
    reversed_in = sorted(labels[::-1], key=corpus_check._profile_sort_key)
    assert forward == reversed_in
    # oldest-first: a genuinely older version precedes a newer one.
    assert forward.index("19.01") < forward.index("26.0")


def test_profile_sort_key_handles_numeric_prefix_without_typeerror() -> None:
    """A bare ``24`` vs ``24.0`` must not compare an int against the raw string."""
    assert sorted(["24.0", "24"], key=corpus_check._profile_sort_key) == ["24", "24.0"]


# --- determinism guard: stat-table builders must be input-order independent ----
# The committed stat pages are regenerated by sweeps; if a builder iterated an
# unordered Counter/dict without sorting, row order would churn run-to-run (the
# bug fixed in `_profile_sort_key`). These feed identical data in two insertion
# orders and assert identical output. Pure (no corpus) so they run in CI.


def _reversed(d: dict[object, int]) -> _Counter[object]:
    return _Counter(dict(reversed(list(d.items()))))


def test_format_distribution_is_order_independent() -> None:
    data = {"24.1": 5, "26.1": 8440, "19.05": 10, "(none)": 3, "20.5": 1, "20.05": 2}
    out = corpus_check._format_distribution("D", _Counter(data), total=8461)
    assert out == corpus_check._format_distribution("D", _reversed(data), total=8461)
    assert any("8,440" in line for line in out)  # commafied + present


def test_format_crosstab_is_order_independent() -> None:
    data = {("19.05", "26.1"): 1, ("24.1", "24.1"): 2, ("26.1", "26.1"): 9}
    out = corpus_check._format_crosstab(_Counter(data))
    assert out == corpus_check._format_crosstab(_reversed(data))


def test_format_reason_table_is_order_independent() -> None:
    # ties on count (3 vs 3) must break deterministically by reason text.
    data = {"reason-b": 3, "reason-a": 3, "reason-c": 10}
    out = corpus_check._format_reason_table("T", "intro", _Counter(data))
    assert out == corpus_check._format_reason_table("T", "intro", _reversed(data))


# The corpus-completeness policy (the partial-corpus guard before a stats regen)
# is pure, so its decision table is unit-testable without a corpus on disk.


def test_corpus_completeness_missing_manifest_is_a_problem() -> None:
    # fetch_toolshed writes manifest.json only on completion, so its absence means
    # the fetch never finished — the dominant partial-corpus signal.
    problem = corpus_check._corpus_completeness_problem(
        manifest_exists=False, manifest_repo_count=0, disk_repo_count=0
    )
    assert problem is not None and "manifest" in problem


def test_corpus_completeness_full_corpus_is_fine() -> None:
    # Disk matches the manifest -> no problem (the 6 expected 404 failures keep
    # disk a hair under the eligible count, well within the 95% ratio).
    assert (
        corpus_check._corpus_completeness_problem(
            manifest_exists=True, manifest_repo_count=7678, disk_repo_count=7672
        )
        is None
    )


def test_corpus_completeness_clobbered_local_is_a_problem() -> None:
    # Manifest present but most clones gone (a .local clobbered by a merge
    # checkout) -> flagged with both counts named.
    problem = corpus_check._corpus_completeness_problem(
        manifest_exists=True, manifest_repo_count=7678, disk_repo_count=3080
    )
    assert problem is not None
    assert "3080" in problem and "7678" in problem


def test_corpus_completeness_empty_manifest_does_not_false_positive() -> None:
    # A manifest with nothing recorded gives no baseline to compare against, so we
    # decline to fail rather than block on a degenerate case.
    assert (
        corpus_check._corpus_completeness_problem(
            manifest_exists=True, manifest_repo_count=0, disk_repo_count=0
        )
        is None
    )


def test_corpus_completeness_just_under_threshold_trips() -> None:
    # 94% < 95% ratio -> a problem; 96% would pass. Pins the boundary.
    assert (
        corpus_check._corpus_completeness_problem(
            manifest_exists=True, manifest_repo_count=1000, disk_repo_count=940
        )
        is not None
    )
    assert (
        corpus_check._corpus_completeness_problem(
            manifest_exists=True, manifest_repo_count=1000, disk_repo_count=960
        )
        is None
    )
