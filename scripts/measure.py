#!/usr/bin/env python3
"""Master dispatcher for empirical measurements that inform ``docs/decisions.md`` §10.

Each subcommand answers one specific empirical question against the
committed corpus artifacts (``docs/corpus_data/combined_corpus_data.json``)
or, where needed, the on-disk corpus tree under ``corpus/``. The output
of each subcommand is shaped for direct lift into a §10 measurement
entry — counts, percentages, exemplar tool paths.

Adding a measurement: write ``_measure_<slug>`` and ``_report_<slug>``
helpers, then register them in ``_MEASUREMENTS`` at the bottom. Keep
``_measure_*`` pure (no printing); confine printing to ``_report_*``
so the measurement can be tested or composed without I/O noise.

Run::

    uv run python -m scripts.measure --list               # list available
    uv run python -m scripts.measure lenient-text-fields  # one measurement
    uv run python -m scripts.measure --all                # every measurement

Companion to the project memory entries on
``use-corpus-for-questions`` and ``measurements-as-scripts``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from lxml import etree

from scripts._shared import PROFILE_NONE as _PROFILE_NONE
from scripts._shared import iter_tool_xmls as _iter_tool_xmls
from scripts._shared import row_source as _row_source
from scripts._shared import unique_by_sha as _unique_by_sha

logger = logging.getLogger("measure")


@cache
def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _corpus_root() -> Path:
    return _repo_root() / "corpus"


def _display_path(path: Path) -> str:
    """Render *path* repo-relative (clickable) when it lives under the repo."""
    root = _repo_root()
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def _combined_data_path() -> Path:
    return _repo_root() / "docs" / "corpus_data" / "combined_corpus_data.json"


# --- shared utilities -----------------------------------------------------------


@cache
def _load_combined_data(*, path: Path | None = None) -> list[dict[str, object]]:
    """Return the full combined-corpus rows list, or fail loudly.

    Cached so that ``--all`` (which invokes every measurement in turn) reads
    the JSON exactly once. The cache key is ``path``; passing a different
    file re-loads.
    """
    resolved = path if path is not None else _combined_data_path()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"{resolved} not found; run `uv run python -m scripts.corpus_check "
            f"validate --source combined` first."
        )
    return json.loads(resolved.read_text(encoding="utf-8"))


def _validity_columns(rows: list[dict[str, object]]) -> tuple[str, ...]:
    """Return the vendored profile suffixes (oldest→newest) from the row schema."""
    if not rows:
        return ()
    keys = [k for k in rows[0] if isinstance(k, str) and k.startswith("valid_")]
    return tuple(
        sorted(
            (k.removeprefix("valid_") for k in keys),
            key=lambda v: tuple(int(part) for part in v.split(".")),
        )
    )


def _iter_corpus_tool_xmls(corpus_root: Path) -> Iterable[Path]:
    """Yield every corpus XML, skipping Mercurial metadata and deprecated dirs."""
    yield from _iter_tool_xmls(corpus_root)


def _parse_tool_root(path: Path) -> etree._Element | None:
    """Return the parsed root if it is ``<tool>``, else ``None``.

    Uses ``recover=True`` to match the lenient sweep semantics in
    ``corpus_check.py``. ``None`` covers a missing file, a hard parse
    failure, an I/O error, or a non-``<tool>`` root.
    """
    if not path.is_file():
        return None
    parser = etree.XMLParser(recover=True, strip_cdata=False)
    try:
        with path.open("rb") as fh:
            tree = etree.parse(fh, parser)
    except (etree.XMLSyntaxError, OSError):
        return None
    root = tree.getroot() if tree is not None else None
    if root is None or root.tag != "tool":
        return None
    return root


# --- measurement: lenient-text-fields -------------------------------------------
#
# Justifies _patch_xsdata_primitive_node_leniency in document.py.

_TEXT_STYLE_ELEMENTS: frozenset[str] = frozenset(
    {
        "citation",
        "command",
        "configfile",
        "container",
        "description",
        "display",
        "environment_variable",
        "expression",
        "file",
        "help",
        "label",
        "postprocess_expression",
        "request_body",
        "request_headers",
        "requirement",
        "resource",
        "validator",
        "version_command",
    }
)


# --- measurement result types ---------------------------------------------------


@dataclass
class _LenientTextFieldsResult:
    parsed_tool_files: int
    unparseable_files_skipped: int
    counts_total: Counter[str]
    counts_with_children: Counter[str]
    affected_tools: set[str]
    exemplars: dict[str, list[tuple[str, str]]]


@dataclass
class _ValidityDistributionResult:
    n_total_rows: int
    n_unique_tools: int
    latest_profile: str
    n_vendored_profiles: int
    n_validates_at_latest: int
    n_no_valid_profile: int
    n_noncontiguous: int
    declared_counts: list[tuple[object, int]]
    newest_counts: list[tuple[object, int]]


@dataclass
class _ExpansionFailedIdsResult:
    n_expansion_failed: int
    n_tool_id_with_at: int
    exemplar_tool_ids: list[str]


@dataclass
class _MacroPlaceholderProfileResult:
    n_unique_tools: int
    n_with_macro_placeholder: int
    distinct_placeholder_values: list[str]


@dataclass
class _ToolIdVsPathResult:
    n_unique_tools: int
    n_with_id: int
    n_with_macro_token_in_id: int
    n_id_matches_file_stem: int
    n_id_matches_parent_dir: int


@dataclass
class _CorpusSizeSourceMixResult:
    n_total_rows: int
    n_unique_tools: int
    n_duplicate_rows: int
    n_github_rows: int
    n_toolshed_rows: int
    n_github_unique_credited: int
    n_toolshed_unique_credited: int
    n_github_repos: int
    n_toolshed_repos: int


@dataclass
class _NoValidProfileTaxonomyResult:
    n_unique_tools: int
    n_no_valid: int
    group_a_counts: list[tuple[str, int]]
    group_b_counts: list[tuple[str, int]]


@dataclass
class _MacroUsageResult:
    n_unique_tools: int
    n_with_macros: int
    n_without_macros: int
    n_unparseable_skipped: int


@dataclass
class _CrossSourcePresenceResult:
    n_unique_tools: int
    n_failing_tools: int
    overall_presence_counts: dict[str, int]
    failure_presence_counts: dict[str, int]
    github_failures_total: int
    github_failures_with_toolshed_twin: int
    toolshed_failures_total: int
    toolshed_failures_with_github_sibling: int
    # Match-key sanity check (§10.11 / §6): for each candidate match key,
    # (all-corpus matches, failure-subset matches) — distinct key values that
    # appear in both github and toolshed rows. Justifies keying ``presence`` on
    # ``tool_id`` rather than the tighter ``(tool_id, basename)`` or ``sha256``.
    match_key_counts: dict[str, tuple[int, int]]


@dataclass
class _CorrectionsResult:
    n_target_tools: int
    n_resolved_on_disk: int
    n_missing_on_disk: int
    per_cutoff_tools: dict[float, int]
    per_cutoff_suggestion_count: dict[float, int]
    default_cutoff: float


@dataclass
class _ParamTypesResult:
    n_tools_parsed: int
    n_params_total: int
    type_counts: Counter[str]


@dataclass
class _CollectionTypeNormalizationResult:
    n_unique_tools: int
    n_unparseable_skipped: int
    n_values_total: int
    n_already_valid: int
    n_whitespace_fixable: int
    n_other_violation: int
    # (tool_path, attr, raw_value, normalized_value) for each fixable value.
    fixable_exemplars: list[tuple[str, str, str, str]]
    # ((tag, attr, value), count) for values that violate the grammar even
    # after whitespace normalization (e.g. a datatype where a collection
    # structure belongs).
    other_violation_values: list[tuple[tuple[str, str, str], int]]


# --- measurements ---------------------------------------------------------------


def _measure_lenient_text_fields(*, corpus_root: Path) -> _LenientTextFieldsResult:
    """Count text-style elements that carry element children in the corpus."""
    counts_total: Counter[str] = Counter()
    counts_with_children: Counter[str] = Counter()
    exemplars: dict[str, list[tuple[str, str]]] = defaultdict(list)
    affected_tools: set[str] = set()
    parsed = 0
    skipped = 0

    for path in _iter_corpus_tool_xmls(corpus_root):
        root = _parse_tool_root(path)
        if root is None:
            skipped += 1
            continue
        parsed += 1
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            if element.tag not in _TEXT_STYLE_ELEMENTS:
                continue
            counts_total[element.tag] += 1
            child_tags = [c.tag for c in element if isinstance(c.tag, str)]
            if not child_tags:
                continue
            counts_with_children[element.tag] += 1
            affected_tools.add(str(path.relative_to(_repo_root())))
            if len(exemplars[element.tag]) < 5:
                exemplars[element.tag].append(
                    (str(path.relative_to(_repo_root())), child_tags[0])
                )

    return _LenientTextFieldsResult(
        parsed_tool_files=parsed,
        unparseable_files_skipped=skipped,
        counts_total=counts_total,
        counts_with_children=counts_with_children,
        affected_tools=affected_tools,
        exemplars=dict(exemplars),
    )


def _report_lenient_text_fields(measurement: _LenientTextFieldsResult) -> None:
    counts_total = measurement.counts_total
    counts_with_children = measurement.counts_with_children
    exemplars = measurement.exemplars
    affected = measurement.affected_tools
    parsed = measurement.parsed_tool_files
    skipped = measurement.unparseable_files_skipped

    print("\n=== lenient-text-fields ===")
    print(f"Parsed {parsed} <tool> files; skipped {skipped} unparseable.\n")
    header = f"{'element':22s} {'occurrences':>12s} {'with_children':>14s} {'rate':>8s}"
    print(header)
    print("-" * 60)
    total_occ = 0
    total_children = 0
    for name in sorted(_TEXT_STYLE_ELEMENTS):
        occurrences = counts_total.get(name, 0)
        with_children = counts_with_children.get(name, 0)
        if occurrences == 0:
            continue
        total_occ += occurrences
        total_children += with_children
        rate = 100 * with_children / occurrences
        row = f"<{name + '>':21s} {occurrences:>12d} {with_children:>14d} {rate:>7.3f}%"
        print(row)
    print("-" * 60)
    overall_rate = 100 * total_children / total_occ if total_occ else 0
    print(f"{'TOTAL':22s} {total_occ:>12d} {total_children:>14d} {overall_rate:>7.3f}%")
    print(f"\nDistinct affected tools: {len(affected)}")
    print("\nExemplars (first 3 per element):")
    for name in sorted(exemplars):
        seen = exemplars[name]
        if not seen:
            continue
        print(f"  <{name}>:")
        for tool_path, child_tag in seen[:3]:
            print(f"    {tool_path}  ← child <{child_tag}>")


def _run_lenient_text_fields(args: argparse.Namespace) -> None:
    _report_lenient_text_fields(
        _measure_lenient_text_fields(corpus_root=args.corpus_root)
    )


# --- measurement: validity-distribution -----------------------------------------
#
# A1 (validates-at-latest), A2 (non-contiguous %), A6 (declared and newest-valid
# distributions). All derived from combined_corpus_data.json.


def _is_contiguous(vector: tuple[int, ...]) -> bool:
    """A validity vector is contiguous when it has at most one 0/1 transition."""
    return sum(1 for i in range(1, len(vector)) if vector[i] != vector[i - 1]) <= 1


def _measure_validity_distribution(
    *, rows: list[dict[str, object]]
) -> _ValidityDistributionResult:
    """Compute A1, A2, A6 from the combined data file."""
    unique = _unique_by_sha(rows)
    val_cols = _validity_columns(rows)
    if not val_cols:
        raise ValueError("no validity columns in combined data — wrong artifact?")
    latest = val_cols[-1]
    declared = Counter(row.get("profile_expanded") for row in unique)
    newest = Counter(row.get("newest_valid") for row in unique)
    n_at_latest = sum(1 for row in unique if row.get("newest_valid") == latest)
    n_no_valid = sum(
        1 for row in unique if row.get("newest_valid") in (None, "", _PROFILE_NONE)
    )
    def _validity_vector(row: dict[str, object]) -> tuple[int, ...]:
        return tuple(int(row[f"valid_{p}"]) for p in val_cols)  # type: ignore[call-overload]

    n_noncontig = sum(
        1 for row in unique if not _is_contiguous(_validity_vector(row))
    )
    return _ValidityDistributionResult(
        n_total_rows=len(rows),
        n_unique_tools=len(unique),
        latest_profile=latest,
        n_vendored_profiles=len(val_cols),
        n_validates_at_latest=n_at_latest,
        n_no_valid_profile=n_no_valid,
        n_noncontiguous=n_noncontig,
        declared_counts=declared.most_common(),
        newest_counts=newest.most_common(),
    )


def _report_validity_distribution(measurement: _ValidityDistributionResult) -> None:
    n_unique = measurement.n_unique_tools
    latest = measurement.latest_profile
    n_at_latest = measurement.n_validates_at_latest
    n_no_valid = measurement.n_no_valid_profile
    n_noncontig = measurement.n_noncontiguous
    declared = measurement.declared_counts
    newest = measurement.newest_counts

    print("\n=== validity-distribution ===")
    print(
        f"Combined sweep: {measurement.n_total_rows} rows, "
        f"{n_unique} unique tools, latest profile {latest} "
        f"({measurement.n_vendored_profiles} vendored)."
    )
    print(
        f"A1 — validates at latest ({latest}): "
        f"{n_at_latest} / {n_unique} ({100 * n_at_latest / n_unique:.1f}%)"
    )
    print(
        f"A2 — non-contiguous validity vector: "
        f"{n_noncontig} / {n_unique} ({100 * n_noncontig / n_unique:.2f}%)"
    )
    print(
        f"     no valid vendored profile: "
        f"{n_no_valid} / {n_unique} ({100 * n_no_valid / n_unique:.1f}%)"
    )
    print("\nA6 — top declared profiles (post-expansion):")
    for profile, count in declared:
        print(f"  {profile!s:25s} {count:5d}  ({100 * count / n_unique:.1f}%)")
    print("\nA6 — top newest-valid profiles:")
    for profile, count in newest:
        print(f"  {profile!s:25s} {count:5d}  ({100 * count / n_unique:.1f}%)")


def _run_validity_distribution(args: argparse.Namespace) -> None:
    _report_validity_distribution(
        _measure_validity_distribution(rows=_load_combined_data(path=args.data))
    )


# --- measurement: expansion-failed-ids ------------------------------------------
#
# A3 — among tools whose macro expansion failed, how often does the fallback
# raw @id literally contain a macro token like `@FOO@`?


def _measure_expansion_failed_ids(
    *, rows: list[dict[str, object]]
) -> _ExpansionFailedIdsResult:
    """Tally `@`-containing tool_id values among expansion-failed tools."""
    unique = _unique_by_sha(rows)
    failed = [row for row in unique if row.get("expansion_failure_reason")]
    with_at = [
        row
        for row in failed
        if isinstance(row.get("tool_id"), str) and "@" in row["tool_id"]  # type: ignore[operator]
    ]
    return _ExpansionFailedIdsResult(
        n_expansion_failed=len(failed),
        n_tool_id_with_at=len(with_at),
        exemplar_tool_ids=sorted({str(row["tool_id"]) for row in failed})[:10],
    )


def _report_expansion_failed_ids(measurement: _ExpansionFailedIdsResult) -> None:
    failed = measurement.n_expansion_failed
    with_at = measurement.n_tool_id_with_at
    examples = measurement.exemplar_tool_ids
    rate = 100 * with_at / failed if failed else 0
    print("\n=== expansion-failed-ids ===")
    print(
        f"A3 — expansion-failed tools: {failed}; "
        f"tool_id contains '@': {with_at} ({rate:.1f}%)"
    )
    print("Exemplar tool_id values seen on expansion-failed rows:")
    for example in examples:
        print(f"  {example!r}")


def _run_expansion_failed_ids(args: argparse.Namespace) -> None:
    _report_expansion_failed_ids(
        _measure_expansion_failed_ids(rows=_load_combined_data(path=args.data))
    )


# --- measurement: macro-placeholder-profile -------------------------------------
#
# The abstract claim that ~16% of tools encode their profile attribute as a
# macro token (e.g., `@PROFILE@`) — measurable from profile_raw.


def _looks_like_version(value: object) -> bool:
    """Return ``True`` iff ``value`` is a literal ``MAJOR.MINOR`` version."""
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    return len(parts) == 2 and all(part.isdigit() for part in parts)


def _measure_macro_placeholder_profile(
    *, rows: list[dict[str, object]]
) -> _MacroPlaceholderProfileResult:
    """Count tools whose ``profile_raw`` is a macro placeholder string."""
    unique = _unique_by_sha(rows)
    with_macro_profile = [
        row
        for row in unique
        if isinstance(row.get("profile_raw"), str)
        and row["profile_raw"] != _PROFILE_NONE
        and not _looks_like_version(row["profile_raw"])
    ]
    placeholder_values = sorted(
        {str(row["profile_raw"]) for row in with_macro_profile}
    )
    return _MacroPlaceholderProfileResult(
        n_unique_tools=len(unique),
        n_with_macro_placeholder=len(with_macro_profile),
        distinct_placeholder_values=placeholder_values,
    )


def _report_macro_placeholder_profile(measurement: _MacroPlaceholderProfileResult) -> None:
    unique = measurement.n_unique_tools
    with_macro = measurement.n_with_macro_placeholder
    values = measurement.distinct_placeholder_values
    rate = 100 * with_macro / unique if unique else 0
    print("\n=== macro-placeholder-profile ===")
    print(
        f"Tools whose profile attribute is a macro placeholder: "
        f"{with_macro} / {unique} ({rate:.1f}%)"
    )
    print(f"Distinct placeholder values seen: {len(values)}")
    for value in values[:15]:
        print(f"  {value!r}")


def _run_macro_placeholder_profile(args: argparse.Namespace) -> None:
    _report_macro_placeholder_profile(
        _measure_macro_placeholder_profile(rows=_load_combined_data(path=args.data))
    )


# --- measurement: tool-id-vs-path -----------------------------------------------
#
# §10.1 — verify the @id presence rate, macro-token rate, and how often @id
# coincides with the file stem or parent directory name. The post-expansion
# tool_id is in combined_corpus_data.json; the path is too — so the comparison
# is a JSON walk, no corpus re-walk needed.


def _measure_tool_id_vs_path(*, rows: list[dict[str, object]]) -> _ToolIdVsPathResult:
    """Compute @id presence, macro-token rate, and path/stem/parent agreement."""
    unique = _unique_by_sha(rows)
    n_with_id = sum(1 for row in unique if row.get("tool_id"))
    n_with_macro_token = sum(
        1
        for row in unique
        if isinstance(row.get("tool_id"), str) and "@" in str(row.get("tool_id", ""))
    )
    n_stem_match = 0
    n_parent_match = 0
    for row in unique:
        tool_id = row.get("tool_id")
        path = row.get("path")
        if not isinstance(tool_id, str) or not isinstance(path, str):
            continue
        parts = path.split("/")
        stem = parts[-1].removesuffix(".xml")
        if stem == tool_id:
            n_stem_match += 1
        if len(parts) >= 2 and parts[-2] == tool_id:
            n_parent_match += 1
    return _ToolIdVsPathResult(
        n_unique_tools=len(unique),
        n_with_id=n_with_id,
        n_with_macro_token_in_id=n_with_macro_token,
        n_id_matches_file_stem=n_stem_match,
        n_id_matches_parent_dir=n_parent_match,
    )


def _report_tool_id_vs_path(measurement: _ToolIdVsPathResult) -> None:
    unique = measurement.n_unique_tools
    with_id = measurement.n_with_id
    with_macro = measurement.n_with_macro_token_in_id
    stem = measurement.n_id_matches_file_stem
    parent = measurement.n_id_matches_parent_dir
    def pct(n: int) -> float:
        return 100 * n / unique if unique else 0.0
    print("\n=== tool-id-vs-path ===")
    print(
        f"Of {unique} unique <tool> files:\n"
        f"  @id present:                  {with_id} ({pct(with_id):.1f}%)\n"
        f"  @id contains a macro token:   {with_macro} ({pct(with_macro):.1f}%)\n"
        f"  @id matches the file stem:    {stem} ({pct(stem):.1f}%)\n"
        f"  @id matches the parent dir:   {parent} ({pct(parent):.1f}%)"
    )


def _run_tool_id_vs_path(args: argparse.Namespace) -> None:
    _report_tool_id_vs_path(
        _measure_tool_id_vs_path(rows=_load_combined_data(path=args.data))
    )


# --- measurement: corpus-size-source-mix ----------------------------------------
#
# §10.2 — total rows, unique tools, per-source contribution, repo counts.


def _measure_corpus_size_source_mix(
    *, rows: list[dict[str, object]]
) -> _CorpusSizeSourceMixResult:
    """Tally per-source row counts, unique counts, and distinct repos."""
    unique = _unique_by_sha(rows)
    gh_rows = [
        r for r in rows if isinstance(r.get("repo"), str) and "/" not in r["repo"]  # type: ignore[operator]
    ]
    ts_rows = [
        r for r in rows if isinstance(r.get("repo"), str) and "/" in r["repo"]  # type: ignore[operator]
    ]
    gh_unique = [
        r
        for r in unique
        if isinstance(r.get("repo"), str) and "/" not in r["repo"]  # type: ignore[operator]
    ]
    ts_unique = [
        r
        for r in unique
        if isinstance(r.get("repo"), str) and "/" in r["repo"]  # type: ignore[operator]
    ]
    return _CorpusSizeSourceMixResult(
        n_total_rows=len(rows),
        n_unique_tools=len(unique),
        n_duplicate_rows=len(rows) - len(unique),
        n_github_rows=len(gh_rows),
        n_toolshed_rows=len(ts_rows),
        n_github_unique_credited=len(gh_unique),
        n_toolshed_unique_credited=len(ts_unique),
        n_github_repos=len({r["repo"] for r in gh_rows}),
        n_toolshed_repos=len({r["repo"] for r in ts_rows}),
    )


def _report_corpus_size_source_mix(measurement: _CorpusSizeSourceMixResult) -> None:
    print("\n=== corpus-size-source-mix ===")
    print(f"Total rows in combined data:    {measurement.n_total_rows}")
    print(f"Unique tools (sha256 dedup):    {measurement.n_unique_tools}")
    print(f"Duplicate occurrences dropped:  {measurement.n_duplicate_rows}")
    print(
        f"  github rows:                  {measurement.n_github_rows} "
        f"(credited unique: {measurement.n_github_unique_credited})"
    )
    print(
        f"  toolshed rows:                {measurement.n_toolshed_rows} "
        f"(credited unique: {measurement.n_toolshed_unique_credited})"
    )
    print(f"Distinct github repos in data:  {measurement.n_github_repos}")
    print(f"Distinct toolshed repos in data: {measurement.n_toolshed_repos}")


def _run_corpus_size_source_mix(args: argparse.Namespace) -> None:
    _report_corpus_size_source_mix(
        _measure_corpus_size_source_mix(rows=_load_combined_data(path=args.data))
    )


# --- measurement: no-valid-profile-taxonomy -------------------------------------
#
# §10.4 — break the 8.1% no-valid-profile bucket into named reason categories.
# Reads expansion_failure_reason and no_valid_reason columns directly.


def _measure_no_valid_profile_taxonomy(
    *, rows: list[dict[str, object]]
) -> _NoValidProfileTaxonomyResult:
    """Categorise the no-valid-profile tools by reason."""
    unique = _unique_by_sha(rows)
    no_valid = [r for r in unique if r.get("newest_valid") in (None, "", _PROFILE_NONE)]
    group_a: Counter[str] = Counter(  # macro-expansion failures
        str(r["expansion_failure_reason"])
        for r in no_valid
        if isinstance(r.get("expansion_failure_reason"), str)
    )
    group_b: Counter[str] = Counter(  # XSD rejects (excluding the macro-expansion-failed bucket)
        str(r["no_valid_reason"])
        for r in no_valid
        if isinstance(r.get("no_valid_reason"), str)
        and r["no_valid_reason"] != "(macro expansion failed)"
    )
    return _NoValidProfileTaxonomyResult(
        n_unique_tools=len(unique),
        n_no_valid=len(no_valid),
        group_a_counts=group_a.most_common(),
        group_b_counts=group_b.most_common(),
    )


def _report_no_valid_profile_taxonomy(measurement: _NoValidProfileTaxonomyResult) -> None:
    unique = measurement.n_unique_tools
    no_valid = measurement.n_no_valid
    group_a = measurement.group_a_counts
    group_b = measurement.group_b_counts
    rate = 100 * no_valid / unique if unique else 0
    print("\n=== no-valid-profile-taxonomy ===")
    print(
        f"§10.4 — {no_valid} / {unique} ({rate:.1f}%) tools do not validate "
        f"against any vendored XSD."
    )
    a_total = sum(n for _, n in group_a)
    print(f"\nGroup A — macro expansion failed ({a_total} tools):")
    for reason, count in group_a:
        print(f"  {count:5d}  {reason}")
    b_total = sum(n for _, n in group_b)
    print(f"\nGroup B — expansion ok, XSD rejects everywhere ({b_total} tools):")
    for reason, count in group_b:
        print(f"  {count:5d}  {reason}")


def _run_no_valid_profile_taxonomy(args: argparse.Namespace) -> None:
    _report_no_valid_profile_taxonomy(
        _measure_no_valid_profile_taxonomy(rows=_load_combined_data(path=args.data))
    )


# --- measurement: macro-usage ---------------------------------------------------
#
# The "Macro usage" stats section claims ~55% of tools use macros. The
# has_macros column isn't in combined_corpus_data.json, so re-derive from the
# corpus tree using the library's own ``has_macros()``. This is the slow
# variant (parses every tool) but matches the canonical detector exactly.


def _measure_macro_usage(*, corpus_root: Path) -> _MacroUsageResult:
    """Re-walk the corpus and count tools that use Galaxy macros."""
    from galaxy_tool_xml.macros import has_macros

    seen_sha: set[str] = set()
    n_with_macros = 0
    n_without_macros = 0
    n_parsed = 0
    n_skipped = 0

    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        root = _parse_tool_root(path)
        if root is None:
            n_skipped += 1
            continue
        n_parsed += 1
        if has_macros(root):
            n_with_macros += 1
        else:
            n_without_macros += 1
    return _MacroUsageResult(
        n_unique_tools=n_parsed,
        n_with_macros=n_with_macros,
        n_without_macros=n_without_macros,
        n_unparseable_skipped=n_skipped,
    )


def _report_macro_usage(measurement: _MacroUsageResult) -> None:
    unique = measurement.n_unique_tools
    with_m = measurement.n_with_macros
    without_m = measurement.n_without_macros
    skipped = measurement.n_unparseable_skipped
    rate = 100 * with_m / unique if unique else 0
    print("\n=== macro-usage ===")
    print(
        f"Unique tools parsed (sha256-deduped): {unique}; "
        f"unparseable skipped: {skipped}"
    )
    print(f"  Uses macros: {with_m} ({rate:.1f}%)")
    print(f"  Macro-free:  {without_m} ({100 - rate:.1f}%)")


def _run_macro_usage(args: argparse.Namespace) -> None:
    _report_macro_usage(_measure_macro_usage(corpus_root=args.corpus_root))


# --- measurement: cross-source-presence -----------------------------------------
#
# Justifies the `presence` column in combined_corpus_data.json and the
# "Failures by source presence" section in combined_corpus_stats.md. Counts
# how often a tool's logical identity (its `tool_id`) appears in github,
# toolshed, or both, and how that splits across the failure population.


# Candidate match keys for the cross-source sanity check, ordered loosest →
# strictest. Each maps a combined-data row to the value compared across sources.
_MATCH_KEYS: dict[str, Callable[[dict[str, object]], object]] = {
    "tool_id": lambda row: row.get("tool_id"),
    "(tool_id, basename)": lambda row: (
        row.get("tool_id"),
        str(row.get("path")).rsplit("/", 1)[-1],
    ),
    "sha256": lambda row: row.get("sha256"),
}


def _cross_source_key_matches(
    rows: list[dict[str, object]],
    *,
    key: Callable[[dict[str, object]], object],
) -> tuple[int, int]:
    """Return ``(all_corpus, failure_subset)`` cross-source match counts for *key*.

    A match is a distinct *key* value present in both a github row and a toolshed
    row (full row set, **not** sha-deduped — byte-identical copies must still
    count as the same logical tool present in both sources). The failure-subset
    count is the number of failing-tool key values that appear anywhere in the
    opposite source, not only among other failures.
    """
    github: set[object] = set()
    toolshed: set[object] = set()
    failing: set[object] = set()
    for row in rows:
        value = key(row)
        source = _row_source(row.get("repo"))
        if source == "github":
            github.add(value)
        elif source == "toolshed":
            toolshed.add(value)
        if row.get("expansion_failure_reason") or row.get("no_valid_reason"):
            failing.add(value)
    both = github & toolshed
    return len(both), len(failing & both)


def _measure_cross_source_presence(
    *, rows: list[dict[str, object]]
) -> _CrossSourcePresenceResult:
    """Split the corpus and the failure subset by `presence` bucket."""
    unique = _unique_by_sha(rows)
    overall: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    for row in unique:
        presence = row.get("presence")
        if not isinstance(presence, str) or not presence:
            continue
        overall[presence] += 1
        if row.get("expansion_failure_reason") or row.get("no_valid_reason"):
            failures[presence] += 1
    # Source-and-presence cross-tab for the failure population — the same
    # numbers the "Failures by source presence" stats section reports.
    failing_rows = [
        row
        for row in unique
        if row.get("expansion_failure_reason") or row.get("no_valid_reason")
    ]

    gh_failures = [row for row in failing_rows if _row_source(row.get("repo")) == "github"]
    ts_failures = [row for row in failing_rows if _row_source(row.get("repo")) == "toolshed"]
    gh_both = sum(1 for row in gh_failures if row.get("presence") == "both")
    ts_both = sum(1 for row in ts_failures if row.get("presence") == "both")
    match_key_counts = {
        label: _cross_source_key_matches(rows, key=key)
        for label, key in _MATCH_KEYS.items()
    }
    return _CrossSourcePresenceResult(
        n_unique_tools=len(unique),
        n_failing_tools=len(failing_rows),
        overall_presence_counts=dict(overall),
        failure_presence_counts=dict(failures),
        github_failures_total=len(gh_failures),
        github_failures_with_toolshed_twin=gh_both,
        toolshed_failures_total=len(ts_failures),
        toolshed_failures_with_github_sibling=ts_both,
        match_key_counts=match_key_counts,
    )


def _report_cross_source_presence(measurement: _CrossSourcePresenceResult) -> None:
    n_unique = measurement.n_unique_tools
    n_failing = measurement.n_failing_tools
    overall = measurement.overall_presence_counts
    failures = measurement.failure_presence_counts
    gh_total = measurement.github_failures_total
    gh_both = measurement.github_failures_with_toolshed_twin
    ts_total = measurement.toolshed_failures_total
    ts_both = measurement.toolshed_failures_with_github_sibling
    print("\n=== cross-source-presence ===")
    print(f"Unique tools: {n_unique}; failing tools: {n_failing}")
    print("\nOverall presence (keyed on tool_id):")
    for bucket in ("github_only", "toolshed_only", "both"):
        count = overall.get(bucket, 0)
        rate = 100 * count / n_unique if n_unique else 0
        print(f"  {bucket:<15s} {count:>6d}  ({rate:>5.1f}%)")
    print("\nFailing-tool presence:")
    for bucket in ("github_only", "toolshed_only", "both"):
        count = failures.get(bucket, 0)
        rate = 100 * count / n_failing if n_failing else 0
        print(f"  {bucket:<15s} {count:>6d}  ({rate:>5.1f}%)")
    print("\nFailures × source cross-tab:")
    print(f"  github failures total:     {gh_total}; with toolshed twin: {gh_both}")
    print(f"  toolshed failures total:   {ts_total}; with github sibling: {ts_both}")
    print("\nMatch-key sanity check (distinct keys present in both sources):")
    print(f"  {'key':<20s} {'all-corpus':>11s} {'failure subset':>15s}")
    for label, (all_corpus, failure_subset) in measurement.match_key_counts.items():
        print(f"  {label:<20s} {all_corpus:>11d} {failure_subset:>15d}")


def _run_cross_source_presence(args: argparse.Namespace) -> None:
    _report_cross_source_presence(
        _measure_cross_source_presence(rows=_load_combined_data(path=args.data))
    )


# --- measurement: corrections-cutoff --------------------------------------------
#
# Justifies the ``_CUTOFF = 0.8`` constant in src/galaxy_tool_xml/corrections.py.
# For each of the no-valid-profile tools whose reason is "XSD does not declare
# attribute used by tool" (~351), monkey-patch `_CUTOFF` to a sweep of values
# and count how many tools yield at least one suggestion. The trade-off: a
# lower cutoff produces more (and looser) suggestions; a higher cutoff produces
# fewer (and tighter). The right cutoff sits in the knee of the curve.

_CORRECTIONS_TARGET_REASON = "XSD does not declare attribute used by tool"


def _row_to_xml_path(row: dict[str, object], *, corpus_root: Path) -> Path | None:
    """Map a combined-corpus row to its XML file on disk.

    Toolshed repos are stored under ``corpus/galaxy-toolshed/<owner>/<name>/``;
    github repos are stored under ``corpus/<repo>/``. The row's ``path`` is
    relative to that root. Returns ``None`` when either the row is missing
    fields or the resolved path doesn't exist on disk (the file may have
    been excluded from the corpus or its repo not yet cloned).
    """
    repo = row.get("repo")
    sub_path = row.get("path")
    if not isinstance(repo, str) or not isinstance(sub_path, str):
        return None
    if "/" in repo:
        candidate = corpus_root / "galaxy-toolshed" / repo / sub_path
    else:
        candidate = corpus_root / repo / sub_path
    return candidate if candidate.is_file() else None


def _measure_corrections_cutoff(
    *, rows: list[dict[str, object]], corpus_root: Path, cutoffs: tuple[float, ...]
) -> _CorrectionsResult:
    """Sweep ``_CUTOFF`` across ``cutoffs`` and tally suggestion outcomes."""
    from galaxy_tool_xml import corrections as corrections_mod
    from galaxy_tool_xml.corrections import suggest_corrections

    unique = _unique_by_sha(rows)
    targets = [
        row
        for row in unique
        if row.get("no_valid_reason") == _CORRECTIONS_TARGET_REASON
    ]
    resolved_paths: list[Path] = []
    missing = 0
    for row in targets:
        path = _row_to_xml_path(row, corpus_root=corpus_root)
        if path is None:
            missing += 1
            continue
        resolved_paths.append(path)

    original_cutoff = corrections_mod._CUTOFF
    results: dict[float, Counter[str]] = {cutoff: Counter() for cutoff in cutoffs}
    suggestion_counts: dict[float, int] = {cutoff: 0 for cutoff in cutoffs}
    try:
        for cutoff in cutoffs:
            corrections_mod._CUTOFF = cutoff
            for path in resolved_paths:
                corrections = suggest_corrections(path)
                if any(c.kind == "attribute" for c in corrections):
                    results[cutoff]["tools_with_attribute_suggestion"] += 1
                suggestion_counts[cutoff] += sum(
                    1 for c in corrections if c.kind == "attribute"
                )
    finally:
        corrections_mod._CUTOFF = original_cutoff

    return _CorrectionsResult(
        n_target_tools=len(targets),
        n_resolved_on_disk=len(resolved_paths),
        n_missing_on_disk=missing,
        per_cutoff_tools={
            cutoff: results[cutoff]["tools_with_attribute_suggestion"]
            for cutoff in cutoffs
        },
        per_cutoff_suggestion_count=dict(suggestion_counts),
        default_cutoff=original_cutoff,
    )


def _report_corrections_cutoff(measurement: _CorrectionsResult) -> None:
    targets = measurement.n_target_tools
    resolved = measurement.n_resolved_on_disk
    missing = measurement.n_missing_on_disk
    per_cutoff_tools = measurement.per_cutoff_tools
    per_cutoff_count = measurement.per_cutoff_suggestion_count
    default_cutoff = measurement.default_cutoff
    print("\n=== corrections-cutoff ===")
    print(
        f"Target failure category: {_CORRECTIONS_TARGET_REASON!r}\n"
        f"  unique tools in category: {targets}\n"
        f"  resolved to a file on disk: {resolved}\n"
        f"  not found on disk:         {missing}\n"
        f"  default cutoff in code:    {default_cutoff}"
    )
    header = (
        f"\n{'cutoff':>8s} "
        f"{'tools w/ ≥1 attr suggestion':>30s} "
        f"{'total attr suggestions':>24s}"
    )
    print(header)
    for cutoff, count in sorted(per_cutoff_tools.items()):
        total = per_cutoff_count[cutoff]
        rate = 100 * count / resolved if resolved else 0
        print(f"{cutoff:>8.2f} {count:>22d} ({rate:>5.1f}%) {total:>26d}")


def _run_corrections_cutoff(args: argparse.Namespace) -> None:
    _report_corrections_cutoff(
        _measure_corrections_cutoff(
            rows=_load_combined_data(path=args.data),
            corpus_root=args.corpus_root,
            cutoffs=(0.6, 0.7, 0.75, 0.8, 0.85, 0.9),
        )
    )


# --- measurement: param-types ---------------------------------------------------
#
# Distributions of ``type`` attribute values on ``<param>`` elements, measured
# directly from the corpus XML (not the swept artifacts). Informs which param
# types must round-trip correctly through the formatter.


def _measure_param_types(*, corpus_root: Path) -> _ParamTypesResult:
    """Count ``<param type=...>`` values across all corpus tool XML files."""
    type_counts: Counter[str] = Counter()
    n_tools = 0
    n_params = 0
    for path in _iter_corpus_tool_xmls(corpus_root):
        root = _parse_tool_root(path)
        if root is None:
            continue
        n_tools += 1
        for elem in root.iter("param"):
            param_type = elem.get("type")
            if param_type is not None:
                type_counts[param_type] += 1
                n_params += 1
    return _ParamTypesResult(
        n_tools_parsed=n_tools,
        n_params_total=n_params,
        type_counts=type_counts,
    )


def _report_param_types(measurement: _ParamTypesResult) -> None:
    """Print the ``<param type>`` distribution."""
    n_tools = measurement.n_tools_parsed
    n_params = measurement.n_params_total
    print("\n=== param-types ===")
    print(f"Tools parsed: {n_tools};  <param> elements with type attr: {n_params}")
    if not measurement.type_counts:
        return
    print("\ntype attribute distribution:")
    for param_type, count in measurement.type_counts.most_common():
        print(f"  {param_type:25s} {count:7d}  ({100 * count / n_params:.1f}%)")


def _run_param_types(args: argparse.Namespace) -> None:
    _report_param_types(_measure_param_types(corpus_root=args.corpus_root))


# --- measurement: collection-type-normalization ---------------------------------
#
# Sizes a hypothetical `Upgrade22_1`-style codemod that would whitespace-
# normalize collection-structure attribute values, the way Upgrade24_1 already
# normalizes ftype/format (codemod docs/decisions.md §14). The 22.01 schema
# pattern-restricted `collection_type`/`type` to a `(list|paired|…)` grammar;
# 25.0 broadened the grammar to admit `paired_or_unpaired`/`record`. A tool can
# therefore stick below latest if such a value carries stray whitespace
# (`"list, list:paired"`). This measures how many corpus values are
# whitespace-fixable vs. genuinely-wrong, to judge whether the codemod earns
# its keep.

# Token grammar for collection-type-family attributes, transcribed from the
# latest vendored XSD's ``CollectionType`` (colon-only) and ``CollectionTypeList``
# (comma-or-colon) simpleTypes. ``test_measure.py`` guards this against schema
# regen drift. ``type`` (on ``<collection>``/``<output_collection>``) is
# colon-only; ``collection_type`` may also use commas.
_COLLECTION_TYPE_MEMBERS: tuple[str, ...] = (
    "list",
    "paired",
    "paired_or_unpaired",
    "record",
)

# Values carrying a macro placeholder or Cheetah template marker — skipped,
# since the corpus walk does not expand macros (same limitation as param-types).
_TEMPLATE_MARKER = re.compile(r"[@${}#]")


@cache
def _collection_type_patterns() -> dict[str, re.Pattern[str]]:
    """Compile the per-attribute collection-type grammars from the member list.

    Keyed by attribute name: ``type`` is colon-only; ``collection_type`` also
    permits commas (the XSD ``CollectionTypeList`` form).
    """
    members = "|".join(_COLLECTION_TYPE_MEMBERS)
    return {
        "type": re.compile(rf"^({members})([:]({members}))*$"),
        "collection_type": re.compile(rf"^({members})([:,]({members}))*$"),
    }


def _collection_type_candidates(
    element: etree._Element,
) -> Iterable[tuple[str, re.Pattern[str]]]:
    """Yield ``(attr, pattern)`` for collection-structure attrs on *element*.

    ``collection_type`` is collection-typed on any element; ``type`` only on
    ``<collection>``/``<output_collection>`` (elsewhere it is a param/data type).
    """
    patterns = _collection_type_patterns()
    if element.tag in ("collection", "output_collection"):
        yield "type", patterns["type"]
    yield "collection_type", patterns["collection_type"]


def _measure_collection_type_normalization(
    *, corpus_root: Path
) -> _CollectionTypeNormalizationResult:
    """Classify every literal collection-structure attribute value in the corpus."""
    seen_sha: set[str] = set()
    n_tools = 0
    n_skipped = 0
    n_already = 0
    n_fixable = 0
    n_other = 0
    fixable_exemplars: list[tuple[str, str, str, str]] = []
    other_values: Counter[tuple[str, str, str]] = Counter()

    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        root = _parse_tool_root(path)
        if root is None:
            n_skipped += 1
            continue
        n_tools += 1
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            for attr, pattern in _collection_type_candidates(element):
                value = element.get(attr)
                if value is None or _TEMPLATE_MARKER.search(value):
                    continue
                if pattern.match(value):
                    n_already += 1
                    continue
                normalized = re.sub(r"\s+", "", value)
                if normalized and pattern.match(normalized):
                    n_fixable += 1
                    if len(fixable_exemplars) < 20:
                        fixable_exemplars.append(
                            (_display_path(path), attr, value, normalized)
                        )
                else:
                    n_other += 1
                    other_values[(element.tag, attr, value)] += 1

    return _CollectionTypeNormalizationResult(
        n_unique_tools=n_tools,
        n_unparseable_skipped=n_skipped,
        n_values_total=n_already + n_fixable + n_other,
        n_already_valid=n_already,
        n_whitespace_fixable=n_fixable,
        n_other_violation=n_other,
        fixable_exemplars=fixable_exemplars,
        other_violation_values=other_values.most_common(),
    )


def _report_collection_type_normalization(
    measurement: _CollectionTypeNormalizationResult,
) -> None:
    print("\n=== collection-type-normalization ===")
    print(
        f"Unique tools parsed (sha256-deduped): {measurement.n_unique_tools}; "
        f"unparseable skipped: {measurement.n_unparseable_skipped}"
    )
    total = measurement.n_values_total
    print(
        f"Literal collection-structure attr values ({total} total, "
        f"macro/template values skipped):"
    )
    print(f"  already valid at latest:        {measurement.n_already_valid}")
    print(f"  whitespace-fixable:             {measurement.n_whitespace_fixable}")
    print(f"  other (not whitespace-fixable): {measurement.n_other_violation}")
    if measurement.fixable_exemplars:
        print("\nWhitespace-fixable values:")
        for tool_path, attr, raw, normalized in measurement.fixable_exemplars:
            print(f"  {tool_path}\n    {attr}: {raw!r} -> {normalized!r}")
    if measurement.other_violation_values:
        print("\nOther violations (value × occurrences):")
        for (tag, attr, value), count in measurement.other_violation_values:
            print(f"  {count:4d}  <{tag} {attr}={value!r}>")


def _run_collection_type_normalization(args: argparse.Namespace) -> None:
    _report_collection_type_normalization(
        _measure_collection_type_normalization(corpus_root=args.corpus_root)
    )


# --- passthrough: corpus-check --------------------------------------------------
#
# corpus_check.py is the canonical (and slow) sweep step. Exposing it here as a
# passthrough subcommand unifies the CLI surface — `scripts/measure.py
# corpus-check ...` and `scripts/corpus_check.py ...` are equivalent. The
# heavy operation lives in corpus_check.py; this is just a delegated entry
# point so callers can invoke everything through one master command.


def _run_corpus_check(args: argparse.Namespace, extra: list[str]) -> int:
    """Delegate to ``scripts/corpus_check.py``'s main with passthrough args."""
    del args  # corpus_check parses its own
    import corpus_check  # local import: avoids loading galaxy_tool_xml just to --list

    return corpus_check.main(extra)


# --- dispatcher -----------------------------------------------------------------
#
# Two registries: _MEASUREMENTS are cheap analyses that --all sweeps through;
# _PASSTHROUGH are delegated to existing scripts and are too heavy / too
# orthogonal to include in --all.


_MEASUREMENTS: dict[str, Callable[[argparse.Namespace], None]] = {
    "tool-id-vs-path": _run_tool_id_vs_path,
    "corpus-size-source-mix": _run_corpus_size_source_mix,
    "validity-distribution": _run_validity_distribution,
    "no-valid-profile-taxonomy": _run_no_valid_profile_taxonomy,
    "macro-usage": _run_macro_usage,
    "macro-placeholder-profile": _run_macro_placeholder_profile,
    "expansion-failed-ids": _run_expansion_failed_ids,
    "cross-source-presence": _run_cross_source_presence,
    "lenient-text-fields": _run_lenient_text_fields,
    "corrections-cutoff": _run_corrections_cutoff,
    "param-types": _run_param_types,
    "collection-type-normalization": _run_collection_type_normalization,
}

_PASSTHROUGH: dict[str, Callable[[argparse.Namespace, list[str]], int]] = {
    "corpus-check": _run_corpus_check,
}


def _run_all_parallel(args: argparse.Namespace) -> int:
    """Fan out every measurement as its own subprocess; print outputs in order.

    Each subprocess re-invokes this script with the single measurement name
    plus shared ``--data`` / ``--corpus-root`` flags, so the plugins stay
    independent (no shared mutable state, each subprocess loads its own JSON).
    Output is captured per subprocess and emitted in registration order so a
    reader sees the same layout as the serial ``--all`` mode.

    Worth the subprocess overhead when at least one slow measurement
    (corpus-walking) is on the list — the per-process startup cost is
    dwarfed by the parsing time saved. For the fast JSON-driven
    measurements, this approach is no slower than serial.
    """
    base_cmd: list[str] = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--data",
        str(args.data),
        "--corpus-root",
        str(args.corpus_root),
    ]
    from concurrent.futures import Future

    futures: dict[str, Future[subprocess.CompletedProcess[str]]] = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for name in _MEASUREMENTS:
            futures[name] = pool.submit(
                subprocess.run,
                base_cmd + [name],
                capture_output=True,
                text=True,
                check=False,
            )
        for name in _MEASUREMENTS:
            result = futures[name].result()
            sys.stdout.write(result.stdout)
            if result.returncode != 0:
                sys.stderr.write(result.stderr)
                logger.error("%s exited %d", name, result.returncode)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run an empirical measurement that informs docs/decisions.md §10, "
            "or delegate to a passthrough subcommand like corpus-check."
        )
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available subcommands and exit.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run every registered measurement in sequence (excludes passthroughs).",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help=(
            "With --all: run up to N measurements concurrently as subprocesses, "
            "preserving output order. Default 1 (serial, in-process)."
        ),
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=_combined_data_path(),
        help=(
            "Path to combined_corpus_data.json; used by data-driven measurements. "
            "Default: %(default)s."
        ),
    )
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=_corpus_root(),
        help=(
            "Directory holding the swept corpus; used by lenient-text-fields. "
            "Default: %(default)s."
        ),
    )
    parser.add_argument(
        "name",
        nargs="?",
        choices=tuple(_MEASUREMENTS) + tuple(_PASSTHROUGH),
        help=(
            "The subcommand to run (omit with --list / --all). "
            "Args after a passthrough subcommand are forwarded to it."
        ),
    )
    return parser


def main(argv: list[str]) -> int:
    """Parse *argv* and dispatch to the requested measurement or passthrough."""
    parser = _build_parser()
    args, extra = parser.parse_known_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.list:
        print("Measurements:")
        for name in _MEASUREMENTS:
            print(f"  {name}")
        print("Passthrough subcommands:")
        for name in _PASSTHROUGH:
            print(f"  {name}")
        return 0

    if args.all:
        if extra:
            logger.error("unexpected positional args with --all: %r", extra)
            return 2
        if args.jobs > 1:
            return _run_all_parallel(args)
        for name in _MEASUREMENTS:
            _MEASUREMENTS[name](args)
        return 0

    if args.name is None:
        parser.print_help()
        return 2

    if args.name in _MEASUREMENTS:
        if extra:
            logger.error("unexpected positional args: %r", extra)
            return 2
        _MEASUREMENTS[args.name](args)
        return 0

    return _PASSTHROUGH[args.name](args, extra)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
