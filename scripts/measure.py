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
from packaging.version import InvalidVersion, Version

from scripts._shared import PROFILE_NONE as _PROFILE_NONE
from scripts._shared import iter_tool_xmls as _iter_tool_xmls
from scripts._shared import row_source as _row_source
from scripts._shared import sha256_of as _sha256_of
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
            affected_tools.add(_display_path(path))
            if len(exemplars[element.tag]) < 5:
                exemplars[element.tag].append((_display_path(path), child_tags[0]))

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
        sha = _sha256_of(path)
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


# --- measurement: macro-profile-tokens ------------------------------------------
#
# The motivating case for token-aware profile upgrades: a tool whose ``profile=``
# is a macro token (e.g. ``@PROFILE@``) whose *expanded* value is older than the
# newest profile the tool actually validates at. Rewriting the token *definition*
# (not the attribute) would advance future expansions. Derived from the raw-vs-
# expanded profile columns already in combined_corpus_data.json; profiles are
# compared with ``packaging.version`` so ``19.1`` and ``19.01`` reconcile.


@dataclass
class _MacroProfileTokensResult:
    n_unique_tools: int
    n_profile_is_token: int
    n_upgradeable: int  # newest_valid strictly newer than the expanded value
    n_current: int  # expanded value already equals newest_valid
    n_token_ahead: int  # expanded value newer than newest_valid (rare)
    n_validates_nowhere: int
    n_unparseable_versions: int
    exemplars: list[tuple[str, str, str, str]]  # path, raw, expanded, newest_valid


def _as_version(value: object, /) -> Version | None:
    """Parse a profile label to a ``Version``, or ``None`` if not a version."""
    if not isinstance(value, str):
        return None
    try:
        return Version(value)
    except InvalidVersion:
        return None


def _measure_macro_profile_tokens(
    *, rows: list[dict[str, object]]
) -> _MacroProfileTokensResult:
    """Bucket macro-token ``profile=`` tools by raw/expanded/newest-valid skew."""
    unique = _unique_by_sha(rows)
    n_token = upgradeable = current = ahead = nowhere = unparseable = 0
    exemplars: list[tuple[str, str, str, str]] = []
    for row in unique:
        raw = row.get("profile_raw")
        if not isinstance(raw, str) or "@" not in raw:
            continue
        n_token += 1
        newest = row.get("newest_valid")
        if not isinstance(newest, str) or newest == _PROFILE_NONE:
            nowhere += 1
            continue
        expanded_version = _as_version(row.get("profile_expanded"))
        newest_version = _as_version(newest)
        if expanded_version is None or newest_version is None:
            unparseable += 1
            continue
        if newest_version > expanded_version:
            upgradeable += 1
            if len(exemplars) < 15:
                exemplars.append(
                    (
                        str(row.get("path", "")),
                        raw,
                        str(row.get("profile_expanded", "")),
                        newest,
                    )
                )
        elif newest_version == expanded_version:
            current += 1
        else:
            ahead += 1
    return _MacroProfileTokensResult(
        n_unique_tools=len(unique),
        n_profile_is_token=n_token,
        n_upgradeable=upgradeable,
        n_current=current,
        n_token_ahead=ahead,
        n_validates_nowhere=nowhere,
        n_unparseable_versions=unparseable,
        exemplars=exemplars,
    )


def _report_macro_profile_tokens(measurement: _MacroProfileTokensResult) -> None:
    token = measurement.n_profile_is_token
    unique = measurement.n_unique_tools

    def pct(n: int, of: int) -> float:
        return 100 * n / of if of else 0.0

    print("\n=== macro-profile-tokens ===")
    print(
        f"Tools whose profile= is a macro token: {token} / {unique} "
        f"({pct(token, unique):.1f}%)"
    )
    print(
        f"  upgradeable (token value stale; validates higher): "
        f"{measurement.n_upgradeable} ({pct(measurement.n_upgradeable, token):.1f}%)"
    )
    print(f"  already current:            {measurement.n_current}")
    print(f"  token ahead of validity:    {measurement.n_token_ahead}")
    print(f"  validates at no profile:    {measurement.n_validates_nowhere}")
    print(f"  unparseable profile value:  {measurement.n_unparseable_versions}")
    for path, raw, expanded, newest in measurement.exemplars[:10]:
        print(f"    {path}: {raw} -> expands {expanded}, validates {newest}")


def _run_macro_profile_tokens(args: argparse.Namespace) -> None:
    _report_macro_profile_tokens(
        _measure_macro_profile_tokens(rows=_load_combined_data(path=args.data))
    )


# --- measurement: macro-topology ------------------------------------------------
#
# How macros are organised across the corpus: inline <macros> vs imported macro
# files vs none; how many tools import a given macro file (the shared-macro
# blast-radius input for the macro-aware-editing plan); token names in use;
# <yield> / <macro> prevalence; and where a tool's profile token is defined.
# Re-walks the corpus (the structure is not in combined_corpus_data.json),
# sha-deduping tools like ``macro-usage``, and writes docs/macro_corpus_stats.md.
#
# Caveat: the importer graph and token-location follow a tool's *direct*
# <macros><import>s only (transitive macro-file imports are not chased) and key
# macro files by resolved on-disk path, so "shared" means within-repo sharing
# (sibling tools importing one file) — cross-repo copies are distinct files.

_NOTABLE_TOKENS: tuple[str, ...] = (
    "@TOOL_VERSION@",
    "@VERSION_SUFFIX@",
    "@WRAPPER_VERSION@",
    "@GALAXY_VERSION@",
    "@PROFILE@",
    "@TOOL_CITATION@",
)


@dataclass
class _MacroFileFacts:
    token_names: frozenset[str]
    has_yield: bool
    has_named_yield: bool
    defines_macro: bool


@dataclass
class _MacroTopologyResult:
    n_unique_tools: int
    n_unparseable_skipped: int
    n_no_macros: int
    n_inline_only: int  # macro defs inline, no <import>
    n_with_imports: int  # at least one <macros><import>
    n_unresolved_imports: int  # tools with an <import> target missing on disk
    n_uses_expand: int
    n_uses_yield: int  # tool's inline macros or its imported files use <yield>
    n_named_yield: int
    n_defines_macro: int
    n_profile_is_token: int
    n_profile_token_inline: int
    n_profile_token_imported: int
    n_profile_token_unresolved: int
    n_version_is_token: int
    n_macro_files: int
    n_shared_macro_files: int  # imported by >1 unique tool
    n_imports_shared_macro: int  # tools importing >=1 shared macro file
    n_no_shared_macro: int  # tools importing NO shared file (v1-eligible population)
    max_importers: int
    importer_histogram: list[tuple[int, int]]  # (importer_count, n_macro_files)
    top_shared: list[tuple[str, int]]  # (macro file path, importer count)
    notable_token_counts: list[tuple[str, int]]  # (token name, n_tools)
    top_token_names: list[tuple[str, int]]  # (token name, n_tools)


def _facts_from_macro_container(element: etree._Element, /) -> _MacroFileFacts:
    """Extract token names / <yield> / <macro> facts from a <macros>-like element."""
    token_names = frozenset(
        name
        for token in element.iter("token")
        if (name := token.get("name")) is not None
    )
    yields = list(element.iter("yield"))
    return _MacroFileFacts(
        token_names=token_names,
        has_yield=bool(yields),
        has_named_yield=any(node.get("name") is not None for node in yields),
        defines_macro=element.find(".//macro") is not None,
    )


@cache
def _macro_file_facts(path: Path, /) -> _MacroFileFacts | None:
    """Parse an imported macro file and return its facts, or ``None`` if unusable."""
    if not path.is_file():
        return None
    parser = etree.XMLParser(recover=True, strip_cdata=False)
    try:
        with path.open("rb") as handle:
            tree = etree.parse(handle, parser)
    except (etree.XMLSyntaxError, OSError):
        return None
    root = tree.getroot() if tree is not None else None
    if root is None:
        return None
    return _facts_from_macro_container(root)


def _import_paths(root: etree._Element, *, tool_path: Path) -> list[tuple[str, Path]]:
    """Return ``(relative, resolved)`` for each <macros><import> in a tool."""
    pairs: list[tuple[str, Path]] = []
    for element in root.findall("macros/import"):
        relative = element.text.strip() if element.text else ""
        if relative:
            pairs.append((relative, (tool_path.parent / relative).resolve()))
    return pairs


def _measure_macro_topology(*, corpus_root: Path) -> _MacroTopologyResult:
    """Re-walk the corpus and characterise macro organisation across unique tools."""
    from galaxy_tool_xml.macros import has_macros

    seen_sha: set[str] = set()
    importers: dict[Path, set[Path]] = defaultdict(set)
    per_tool_imports: list[set[Path]] = []  # resolved, on-disk imports per tool
    token_tools: Counter[str] = Counter()
    skipped = no_macros = inline_only = with_imports = unresolved = 0
    uses_expand = uses_yield = named_yield = defines_macro = 0
    profile_token = profile_inline = profile_imported = profile_unresolved = 0
    version_token = 0

    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        sha = _sha256_of(path)
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        root = _parse_tool_root(path)
        if root is None:
            skipped += 1
            continue

        inline = root.find("macros")
        inline_facts = (
            _facts_from_macro_container(inline) if inline is not None else None
        )
        imports = _import_paths(root, tool_path=path)
        imported_facts = [
            facts
            for _relative, resolved in imports
            if (facts := _macro_file_facts(resolved)) is not None
        ]
        existing_imports = {
            resolved for _relative, resolved in imports if resolved.is_file()
        }
        per_tool_imports.append(existing_imports)
        for resolved in existing_imports:
            importers[resolved].add(path)

        if not has_macros(root):
            no_macros += 1
        elif imports:
            with_imports += 1
        else:
            inline_only += 1
        if any(not resolved.is_file() for _relative, resolved in imports):
            unresolved += 1

        if root.find(".//expand") is not None:
            uses_expand += 1
        all_facts = ([inline_facts] if inline_facts is not None else []) + imported_facts
        if any(facts.has_yield for facts in all_facts):
            uses_yield += 1
        if any(facts.has_named_yield for facts in all_facts):
            named_yield += 1
        if any(facts.defines_macro for facts in all_facts):
            defines_macro += 1

        token_names: set[str] = set()
        for facts in all_facts:
            token_names |= facts.token_names
        for name in token_names:
            token_tools[name] += 1

        profile_raw = root.get("profile")
        if profile_raw is not None and "@" in profile_raw:
            profile_token += 1
            inline_names = inline_facts.token_names if inline_facts else frozenset()
            imported_names: set[str] = set()
            for facts in imported_facts:
                imported_names |= facts.token_names
            if profile_raw in inline_names:
                profile_inline += 1
            elif profile_raw in imported_names:
                profile_imported += 1
            else:
                profile_unresolved += 1

        version_raw = root.get("version")
        if version_raw is not None and "@" in version_raw:
            version_token += 1

    counts = sorted(len(tools) for tools in importers.values())
    histogram = sorted(Counter(counts).items())
    shared_files = {macro for macro, tools in importers.items() if len(tools) > 1}
    imports_shared = sum(
        1 for tool_imports in per_tool_imports if tool_imports & shared_files
    )
    shared = [(macro, len(tools)) for macro, tools in importers.items() if len(tools) > 1]
    shared.sort(key=lambda item: (-item[1], str(item[0])))
    top_shared = [(_display_path(macro), count) for macro, count in shared[:15]]
    notable = [(name, token_tools.get(name, 0)) for name in _NOTABLE_TOKENS]
    top_tokens = sorted(token_tools.items(), key=lambda item: (-item[1], item[0]))[:25]

    return _MacroTopologyResult(
        n_unique_tools=len(seen_sha) - skipped,
        n_unparseable_skipped=skipped,
        n_no_macros=no_macros,
        n_inline_only=inline_only,
        n_with_imports=with_imports,
        n_unresolved_imports=unresolved,
        n_uses_expand=uses_expand,
        n_uses_yield=uses_yield,
        n_named_yield=named_yield,
        n_defines_macro=defines_macro,
        n_profile_is_token=profile_token,
        n_profile_token_inline=profile_inline,
        n_profile_token_imported=profile_imported,
        n_profile_token_unresolved=profile_unresolved,
        n_version_is_token=version_token,
        n_macro_files=len(importers),
        n_shared_macro_files=len(shared),
        n_imports_shared_macro=imports_shared,
        n_no_shared_macro=(len(seen_sha) - skipped) - imports_shared,
        max_importers=counts[-1] if counts else 0,
        importer_histogram=histogram,
        top_shared=top_shared,
        notable_token_counts=notable,
        top_token_names=top_tokens,
    )


def _report_macro_topology(measurement: _MacroTopologyResult) -> None:
    unique = measurement.n_unique_tools

    def pct(n: int) -> float:
        return 100 * n / unique if unique else 0.0

    print("\n=== macro-topology ===")
    print(
        f"Unique tools parsed (sha256-deduped): {unique}; "
        f"non-<tool>/unparseable skipped: {measurement.n_unparseable_skipped}"
    )
    print(
        f"  no macros:        {measurement.n_no_macros} "
        f"({pct(measurement.n_no_macros):.1f}%)"
    )
    print(
        f"  inline only:      {measurement.n_inline_only} "
        f"({pct(measurement.n_inline_only):.1f}%)"
    )
    print(
        f"  imports a file:   {measurement.n_with_imports} "
        f"({pct(measurement.n_with_imports):.1f}%); "
        f"{measurement.n_unresolved_imports} have an unresolved <import>"
    )
    print(
        f"  uses <expand>: {measurement.n_uses_expand}; uses <yield>: "
        f"{measurement.n_uses_yield} (named: {measurement.n_named_yield}); "
        f"defines <macro>: {measurement.n_defines_macro}"
    )
    print(
        f"  profile= is a token: {measurement.n_profile_is_token} "
        f"(inline {measurement.n_profile_token_inline} / imported "
        f"{measurement.n_profile_token_imported} / unresolved "
        f"{measurement.n_profile_token_unresolved}); "
        f"version= is a token: {measurement.n_version_is_token}"
    )
    print(
        f"  distinct imported macro files: {measurement.n_macro_files}; "
        f"shared by >1 tool: {measurement.n_shared_macro_files}; "
        f"max importers: {measurement.max_importers}"
    )
    print(
        f"  tools importing a shared macro file: "
        f"{measurement.n_imports_shared_macro} "
        f"({pct(measurement.n_imports_shared_macro):.1f}%); "
        f"no shared macro (v1-eligible): {measurement.n_no_shared_macro} "
        f"({pct(measurement.n_no_shared_macro):.1f}%)"
    )
    print("  importer-count histogram (importers: #files):")
    for importer_count, n_files in measurement.importer_histogram:
        print(f"    {importer_count}: {n_files}")
    print("  most-shared macro files:")
    for macro, count in measurement.top_shared[:10]:
        print(f"    {count}x  {macro}")
    print("  notable token names (tools defining/importing them):")
    for name, count in measurement.notable_token_counts:
        print(f"    {name}: {count}")


def _render_macro_stats_page(
    topology: _MacroTopologyResult, *, profile_tokens: _MacroProfileTokensResult
) -> str:
    """Render the macro-corpus stats markdown page (deterministic)."""
    unique = topology.n_unique_tools

    def pct(n: int, of: int) -> float:
        return 100 * n / of if of else 0.0

    def num(n: int) -> str:
        return f"{n:,}"

    lines: list[str] = [
        "# Macro corpus statistics",
        "",
        "Phase-0 measurements for the macro-aware refactoring plan: how Galaxy",
        "tool macros are organised across the combined corpus (parsing, sharing,",
        "tokens, `<yield>`), and how often a macro-token `profile=` is stale. These",
        "numbers gate the macro-aware design decisions (shared-macro edit policy,",
        "token-aware profile upgrades, deferring `<yield>`).",
        "",
        "Regenerate with:",
        "",
        "```sh",
        "uv run python -m scripts.measure macro-topology",
        "```",
        "",
        f"Unique `<tool>` files (sha256-deduped): **{num(unique)}** "
        f"({num(topology.n_unparseable_skipped)} non-`<tool>`-root or "
        "unparseable XML files skipped — including the macro libraries "
        "themselves).",
        "",
        "## Macro organisation",
        "",
        "| Bucket | Tools | Share |",
        "|---|--:|--:|",
        f"| No macros | {num(topology.n_no_macros)} | {pct(topology.n_no_macros, unique):.1f}% |",
        f"| Inline `<macros>` only | {num(topology.n_inline_only)} | {pct(topology.n_inline_only, unique):.1f}% |",
        f"| Imports a macro file | {num(topology.n_with_imports)} | {pct(topology.n_with_imports, unique):.1f}% |",
        "",
        f"Tools with an unresolved `<import>` (target missing on disk): "
        f"**{num(topology.n_unresolved_imports)}**.",
        "",
        "## Construct usage",
        "",
        "| Construct | Tools | Share |",
        "|---|--:|--:|",
        f"| `<expand>` | {num(topology.n_uses_expand)} | {pct(topology.n_uses_expand, unique):.1f}% |",
        f"| `<yield>` (tool + its macro files) | {num(topology.n_uses_yield)} | {pct(topology.n_uses_yield, unique):.1f}% |",
        f"| `<yield name=...>` (named) | {num(topology.n_named_yield)} | {pct(topology.n_named_yield, unique):.1f}% |",
        f"| defines `<macro>` | {num(topology.n_defines_macro)} | {pct(topology.n_defines_macro, unique):.1f}% |",
        "",
        "`<yield>` appears in the inline or imported macros of a third of tools,",
        "but named yields and tool-defined `<macro>`s are rare. v1 must therefore",
        "**preserve** `<yield>`/`<macro>` faithfully; yield-aware *editing*",
        "(resolving parameterized macros) can still defer to a later phase.",
        "",
        "## Shared macro files (blast-radius input)",
        "",
        f"Distinct imported macro files: **{num(topology.n_macro_files)}**; "
        f"imported by more than one tool: **{num(topology.n_shared_macro_files)}**; "
        f"max importers of a single file: **{num(topology.max_importers)}**.",
        "",
        f"Tools importing at least one shared macro file: "
        f"**{num(topology.n_imports_shared_macro)}** "
        f"({pct(topology.n_imports_shared_macro, unique):.1f}%). Tools with **no "
        f"shared macro** (none, inline-only, or importing only sole-owner files) "
        f"— the population safe to edit without cross-tool blast radius, i.e. the "
        f"**v1-eligible test set while the shared-macro edit policy is deferred**: "
        f"**{num(topology.n_no_shared_macro)}** "
        f"({pct(topology.n_no_shared_macro, unique):.1f}%).",
        "",
        "Importer-count distribution (how many tools import each macro file):",
        "",
        "| Importers | Macro files |",
        "|--:|--:|",
    ]
    lines.extend(
        f"| {importer_count} | {num(n_files)} |"
        for importer_count, n_files in topology.importer_histogram
    )
    lines.extend(["", "Most-shared macro files:", ""])
    if topology.top_shared:
        lines.append("| Importers | Macro file |")
        lines.append("|--:|---|")
        lines.extend(
            f"| {count} | `{macro}` |" for macro, count in topology.top_shared
        )
    else:
        lines.append("_None imported by more than one tool._")

    lines.extend(
        [
            "",
            "## Tokens",
            "",
            f"`profile=` is a macro token: **{num(topology.n_profile_is_token)}** "
            f"(token defined inline {num(topology.n_profile_token_inline)} / in an "
            f"imported file {num(topology.n_profile_token_imported)} / unresolved "
            f"{num(topology.n_profile_token_unresolved)}). `version=` is a token: "
            f"**{num(topology.n_version_is_token)}**.",
            "",
            "Notable token names (tools that define or import them):",
            "",
            "| Token | Tools |",
            "|---|--:|",
        ]
    )
    lines.extend(
        f"| `{name}` | {num(count)} |"
        for name, count in topology.notable_token_counts
    )
    lines.extend(
        [
            "",
            "## Stale macro-token profiles (token-aware upgrade target)",
            "",
            "Of the tools whose `profile=` is a macro token, how the token's",
            "*expanded* value compares to the newest profile the tool validates at",
            "(profiles compared with `packaging.version`). **Upgradeable** is the",
            "motivating case: the token value is stale, so rewriting the token",
            "*definition* would advance the tool while keeping the `@TOKEN@`",
            "reference. The token-aware `UpdateProfile` (codemod §21) does this for",
            "a token defined *inline* in the tool's own `<macros>`; an *imported*",
            "token awaits the bundle-aware step (Phase 3b). Earlier `UpdateProfile`",
            "left every `@TOKEN@` profile untouched (a no-op, never a literal).",
            "",
            "| Outcome | Tools |",
            "|---|--:|",
            f"| profile= is a macro token | {num(profile_tokens.n_profile_is_token)} |",
            f"| └ upgradeable (token value stale) | {num(profile_tokens.n_upgradeable)} |",
            f"| └ already current | {num(profile_tokens.n_current)} |",
            f"| └ token ahead of validity | {num(profile_tokens.n_token_ahead)} |",
            f"| └ validates at no profile | {num(profile_tokens.n_validates_nowhere)} |",
            f"| └ unparseable profile value | {num(profile_tokens.n_unparseable_versions)} |",
            "",
        ]
    )
    if profile_tokens.exemplars:
        lines.append("Upgradeable exemplars (`raw` → expands → validates):")
        lines.append("")
        lines.extend(
            f"- `{path}`: `{raw}` → {expanded} → validates {newest}"
            for path, raw, expanded, newest in profile_tokens.exemplars[:10]
        )
        lines.append("")
    return "\n".join(lines)


def _run_macro_topology(args: argparse.Namespace) -> None:
    topology = _measure_macro_topology(corpus_root=args.corpus_root)
    profile_tokens = _measure_macro_profile_tokens(
        rows=_load_combined_data(path=args.data)
    )
    _report_macro_topology(topology)
    _report_macro_profile_tokens(profile_tokens)
    # Emit the persistent stats page on a direct run, not during a --all sweep
    # (which is a read-only fan-out over every measurement).
    if not args.all:
        out_path = _repo_root() / "docs" / "macro_corpus_stats.md"
        out_path.write_text(
            _render_macro_stats_page(topology, profile_tokens=profile_tokens) + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {_display_path(out_path)}")


# --- measurement: macro-profile-ownership ---------------------------------------
#
# Phase-3b decision input. When a tool's profile= is a macro token defined in an
# IMPORTED macro file, can we rewrite that file's <token> IN PLACE, or must we
# FORK it (copy-on-write) so other importers' profiles do not change? Measures:
#
#   - where the profile token is defined: inline / directly-imported file /
#     deeper in the import chain / unresolved (sizes the branches; prices the
#     "handle direct, report deeper" punt);
#   - sole-owned vs shared defining file (the edit-in-place vs fork branches of
#     plan choice (b));
#   - for SHARED defining files, whether the token's profile-using importers
#     AGREE on the target profile (their newest-valid). Frequent agreement means
#     forking shared files is usually unnecessary — the headline number that can
#     flip the fork-vs-edit decision;
#   - <import> paths that are absolute or use `..` (validates the bounded-scan
#     soundness argument: with no `..`, importers live only at/above a macro
#     file, so a subtree scan finds them all);
#   - defining file in the tool's own directory vs elsewhere (path-rewriting).
#
# newest-valid per tool is joined from combined_corpus_data.json by content
# sha256 (validation is deterministic per content), so this never re-validates.
# Sharedness uses the TRANSITIVE importer graph (tier-1 imported_macro_paths),
# so a deeply-imported defining file's importers are counted correctly.


@dataclass
class _ProfileOwnershipResult:
    n_unique_tools: int
    n_profile_token_tools: int  # profile= contains '@'
    n_inline: int  # token defined in the tool's own <macros>
    n_imported_direct: int  # defined in a directly <import>ed file
    n_imported_deeper: int  # defined only deeper in the import chain
    n_unresolved: int  # token not found inline or in any imported file
    n_imported_total: int  # n_imported_direct + n_imported_deeper
    n_defining_sole_owned: int  # defining file has exactly one importer (transitive)
    n_defining_shared: int  # defining file imported by >= 2 tools
    n_shared_defining_files: int  # distinct shared files defining a used profile token
    n_shared_multi_user: int  # ... with >= 2 profile-using importers (agreement tested)
    n_shared_agree: int  # all profile-using importers want the same target
    n_shared_diverge: int  # importers want different targets
    n_shared_indeterminate: int  # no profile-using importer validates anywhere
    n_import_stmts: int  # tool-level <macros><import> statements seen
    n_import_dotdot: int  # ... whose path contains '..'
    n_import_absolute: int  # ... whose path is absolute
    n_defining_same_dir: int  # defining file in the importing tool's own directory
    n_defining_other_dir: int  # defining file elsewhere (path rewrite needed)
    diverge_exemplars: list[tuple[str, list[tuple[str, str]]]]


def _measure_macro_profile_ownership(
    *, corpus_root: Path, rows: list[dict[str, object]]
) -> _ProfileOwnershipResult:
    """Characterise where profile tokens live and whether their files are shared."""
    from galaxy_tool_xml.macros import imported_macro_paths, token_definitions

    sha_to_newest: dict[str, str] = {}
    for row in rows:
        sha = row.get("sha256")
        newest = row.get("newest_valid")
        if isinstance(sha, str) and isinstance(newest, str):
            sha_to_newest.setdefault(sha, newest)

    seen_sha: set[str] = set()
    importers: dict[Path, set[str]] = defaultdict(set)  # defining file -> tool shas
    # Per profile-token tool: (defining_file | None, placement, sha, same_dir)
    profile_tools: list[tuple[Path | None, str, str, bool]] = []
    skipped = n_profile = n_inline = n_unresolved = 0
    n_stmts = n_dotdot = n_absolute = 0

    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        sha = _sha256_of(path)
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        root = _parse_tool_root(path)
        if root is None:
            skipped += 1
            continue

        for element in root.findall("macros/import"):
            relative = element.text.strip() if element.text else ""
            if not relative:
                continue
            n_stmts += 1
            if ".." in Path(relative).parts:
                n_dotdot += 1
            if Path(relative).is_absolute():
                n_absolute += 1

        for macro_path in imported_macro_paths(path):
            importers[macro_path].add(sha)

        profile_raw = root.get("profile")
        if profile_raw is None or "@" not in profile_raw:
            continue
        n_profile += 1
        definition = next(
            (d for d in token_definitions(path) if d.name == profile_raw), None
        )
        if definition is None:
            n_unresolved += 1
            continue
        if definition.source is None:
            n_inline += 1
            continue
        direct = {resolved for _rel, resolved in _import_paths(root, tool_path=path)}
        placement = "direct" if definition.source in direct else "deeper"
        same_dir = definition.source.parent == path.parent
        profile_tools.append((definition.source, placement, sha, same_dir))

    return _summarise_profile_ownership(
        n_unique_tools=len(seen_sha) - skipped,
        n_profile=n_profile,
        n_inline=n_inline,
        n_unresolved=n_unresolved,
        n_stmts=n_stmts,
        n_dotdot=n_dotdot,
        n_absolute=n_absolute,
        importers=importers,
        profile_tools=profile_tools,
        sha_to_newest=sha_to_newest,
    )


def _summarise_profile_ownership(
    *,
    n_unique_tools: int,
    n_profile: int,
    n_inline: int,
    n_unresolved: int,
    n_stmts: int,
    n_dotdot: int,
    n_absolute: int,
    importers: dict[Path, set[str]],
    profile_tools: list[tuple[Path | None, str, str, bool]],
    sha_to_newest: dict[str, str],
) -> _ProfileOwnershipResult:
    """Aggregate the per-tool ownership rows into the result counters."""
    n_direct = sum(1 for _f, placement, _s, _d in profile_tools if placement == "direct")
    n_deeper = sum(1 for _f, placement, _s, _d in profile_tools if placement == "deeper")
    n_same_dir = sum(1 for _f, _p, _s, same_dir in profile_tools if same_dir)

    sole = shared = 0
    # Group profile-using importers (their target profiles) per defining file.
    per_file_targets: dict[Path, list[str]] = defaultdict(list)
    for defining_file, _placement, sha, _same_dir in profile_tools:
        if defining_file is None:
            continue
        if len(importers.get(defining_file, set())) <= 1:
            sole += 1
        else:
            shared += 1
        newest = sha_to_newest.get(sha)
        if isinstance(newest, str) and newest not in ("", _PROFILE_NONE):
            per_file_targets[defining_file].append(newest)
        else:
            per_file_targets[defining_file].append("")

    shared_files = sorted(
        (f for f in per_file_targets if len(importers.get(f, set())) > 1),
        key=str,
    )
    n_agree = n_diverge = n_indeterminate = n_multi_user = 0
    diverge_exemplars: list[tuple[str, list[tuple[str, str]]]] = []
    for defining_file in shared_files:
        targets = per_file_targets[defining_file]
        if len(targets) >= 2:
            n_multi_user += 1
        distinct = {t for t in targets if t}
        if not distinct:
            n_indeterminate += 1
        elif len(distinct) == 1:
            n_agree += 1
        else:
            n_diverge += 1
            if len(diverge_exemplars) < 10:
                shas = sorted(set(targets))
                diverge_exemplars.append(
                    (_display_path(defining_file), [(t or "(none)", "") for t in shas])
                )

    return _ProfileOwnershipResult(
        n_unique_tools=n_unique_tools,
        n_profile_token_tools=n_profile,
        n_inline=n_inline,
        n_imported_direct=n_direct,
        n_imported_deeper=n_deeper,
        n_unresolved=n_unresolved,
        n_imported_total=n_direct + n_deeper,
        n_defining_sole_owned=sole,
        n_defining_shared=shared,
        n_shared_defining_files=len(shared_files),
        n_shared_multi_user=n_multi_user,
        n_shared_agree=n_agree,
        n_shared_diverge=n_diverge,
        n_shared_indeterminate=n_indeterminate,
        n_import_stmts=n_stmts,
        n_import_dotdot=n_dotdot,
        n_import_absolute=n_absolute,
        n_defining_same_dir=n_same_dir,
        n_defining_other_dir=(n_direct + n_deeper) - n_same_dir,
        diverge_exemplars=diverge_exemplars,
    )


def _render_profile_ownership_page(result: _ProfileOwnershipResult) -> str:
    """Render docs/macro_profile_ownership_stats.md (deterministic)."""

    def pct(n: int, of: int) -> float:
        return 100 * n / of if of else 0.0

    imported = result.n_imported_total
    lines = [
        "# Macro profile-token ownership (Phase-3b decision input)",
        "",
        "Reproduced-by: `uv run python -m scripts.measure macro-profile-ownership`.",
        "",
        "When a tool's `profile=` is a macro token (e.g. `@PROFILE@`), where is the",
        "token defined, is that file shared, and — if shared — do the importers",
        "agree on the target profile? These numbers decide whether Phase 3b must",
        "fork shared macro files (copy-on-write) or can edit them in place.",
        "",
        "## Where the profile token is defined",
        "",
        "| Placement | Tools |",
        "|---|--:|",
        f"| profile= is a macro token | {result.n_profile_token_tools} |",
        f"| └ defined inline (handled in Phase 3a) | {result.n_inline} |",
        f"| └ in a directly-imported file | {result.n_imported_direct} |",
        f"| └ deeper in the import chain | {result.n_imported_deeper} |",
        f"| └ unresolved (token not found) | {result.n_unresolved} |",
        "",
        "## Defining-file ownership (imported tokens only)",
        "",
        f"Of the {imported} imported-token tools:",
        "",
        "| Defining file | Tools |",
        "|---|--:|",
        f"| sole-owned (1 importer) → edit in place | {result.n_defining_sole_owned} "
        f"({pct(result.n_defining_sole_owned, imported):.1f}%) |",
        f"| shared (≥2 importers) → fork candidate | {result.n_defining_shared} "
        f"({pct(result.n_defining_shared, imported):.1f}%) |",
        "",
        "## Do shared files' importers agree on the target profile?",
        "",
        "The headline: if importers of a shared defining file almost always want the",
        "same newest-valid profile, forking is usually unnecessary (an in-place bump",
        "would satisfy them all).",
        "",
        "| Shared defining file | Files |",
        "|---|--:|",
        f"| importers agree on one target | {result.n_shared_agree} |",
        f"| importers diverge | {result.n_shared_diverge} |",
        f"| indeterminate (none validate) | {result.n_shared_indeterminate} |",
        f"| total shared defining files | {result.n_shared_defining_files} |",
        f"| └ with ≥2 profile-using importers (agreement actually tested) "
        f"| {result.n_shared_multi_user} |",
        "",
        "## Scan-soundness and path rewriting",
        "",
        "| Metric | Count |",
        "|---|--:|",
        f"| tool `<macros><import>` statements | {result.n_import_stmts} |",
        f"| └ path contains `..` | {result.n_import_dotdot} |",
        f"| └ path is absolute | {result.n_import_absolute} |",
        f"| defining file in tool's own directory | {result.n_defining_same_dir} |",
        f"| defining file elsewhere | {result.n_defining_other_dir} |",
        "",
    ]
    if result.diverge_exemplars:
        lines.append("Diverging shared files (file: targets wanted):")
        lines.append("")
        lines.extend(
            f"- `{path}`: {', '.join(t for t, _ in targets)}"
            for path, targets in result.diverge_exemplars
        )
        lines.append("")
    return "\n".join(lines)


def _report_macro_profile_ownership(result: _ProfileOwnershipResult) -> None:
    imported = result.n_imported_total

    def pct(n: int, of: int) -> float:
        return 100 * n / of if of else 0.0

    print("\n=== macro-profile-ownership ===")
    print(
        f"profile= is a macro token: {result.n_profile_token_tools} "
        f"(inline {result.n_inline}, direct-import {result.n_imported_direct}, "
        f"deeper {result.n_imported_deeper}, unresolved {result.n_unresolved})"
    )
    print(
        f"  imported defining file: sole-owned {result.n_defining_sole_owned} "
        f"({pct(result.n_defining_sole_owned, imported):.1f}%), "
        f"shared {result.n_defining_shared} "
        f"({pct(result.n_defining_shared, imported):.1f}%)"
    )
    print(
        f"  shared defining files ({result.n_shared_defining_files}; "
        f"{result.n_shared_multi_user} with >=2 profile users): "
        f"importers agree {result.n_shared_agree}, diverge {result.n_shared_diverge}, "
        f"indeterminate {result.n_shared_indeterminate}"
    )
    print(
        f"  imports: {result.n_import_stmts} stmts, {result.n_import_dotdot} use '..', "
        f"{result.n_import_absolute} absolute"
    )
    print(
        f"  defining file location: same-dir {result.n_defining_same_dir}, "
        f"elsewhere {result.n_defining_other_dir}"
    )
    for path, targets in result.diverge_exemplars[:10]:
        print(f"    {path}: {', '.join(t for t, _ in targets)}")


def _run_macro_profile_ownership(args: argparse.Namespace) -> None:
    result = _measure_macro_profile_ownership(
        corpus_root=args.corpus_root, rows=_load_combined_data(path=args.data)
    )
    _report_macro_profile_ownership(result)
    if not args.all:
        out_path = _repo_root() / "docs" / "macro_profile_ownership_stats.md"
        out_path.write_text(
            _render_profile_ownership_page(result) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {_display_path(out_path)}")


# --- measurement: command-iuc-heuristics ----------------------------------------
#
# Sizes the two reserved advisory placeholders (check §D1): IUC011 (single-quote
# Cheetah variables in <command>) and IUC012 (join shell commands with `&&`, not
# a lone `&`). Both would be CDATA-text heuristics, deferred precisely because
# they risk firing as noise. This counts, across each unique tool's first
# <command> body, how many candidate findings each heuristic would raise — the
# number that decides whether the checks are worth implementing and how loud
# they would be. Heuristic, not a Cheetah/shell parser; deliberately matches the
# crude detection the placeholders would use, so the counts reflect real noise.

# A `$name` or `${name}` Cheetah reference. "Quoted" is approximated by a single
# quote immediately preceding the `$` (the IUC convention `'$x'`); anything else
# counts as a candidate. Crude on purpose — the noise is the point.
_CHEETAH_VAR = re.compile(r"\$\{?[A-Za-z_][\w.]*\}?")
# A lone `&` — not part of `&&`. In itertext, `&amp;` is already unescaped to `&`.
_LONE_AMP = re.compile(r"(?<!&)&(?!&)")


@dataclass
class _CommandIucHeuristicsResult:
    n_unique_tools: int
    n_with_command: int
    n_tools_unquoted_var: int  # IUC011 candidates: >=1 unquoted Cheetah var
    n_unquoted_var_findings: int  # total unquoted-var occurrences
    n_tools_lone_amp: int  # IUC012 candidates: >=1 lone `&`
    n_lone_amp_findings: int  # total lone-`&` occurrences


def _count_unquoted_vars(text: str, /) -> int:
    """Count Cheetah ``$var`` references not immediately preceded by a quote."""
    count = 0
    for match in _CHEETAH_VAR.finditer(text):
        start = match.start()
        if start == 0 or text[start - 1] != "'":
            count += 1
    return count


def _measure_command_iuc_heuristics(
    *, corpus_root: Path
) -> _CommandIucHeuristicsResult:
    """Count IUC011/IUC012 candidate findings across each tool's first command."""
    seen: set[str] = set()
    n_tools = n_with = 0
    tools_var = var_findings = tools_amp = amp_findings = 0
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        digest = _sha256_of(path)
        if digest in seen:
            continue
        seen.add(digest)
        root = _parse_tool_root(path)
        if root is None:
            continue
        n_tools += 1
        command = root.find("command")
        if command is None:
            continue
        n_with += 1
        text = "".join(command.itertext())
        unquoted = _count_unquoted_vars(text)
        lone_amps = len(_LONE_AMP.findall(text))
        if unquoted:
            tools_var += 1
            var_findings += unquoted
        if lone_amps:
            tools_amp += 1
            amp_findings += lone_amps
    return _CommandIucHeuristicsResult(
        n_unique_tools=n_tools,
        n_with_command=n_with,
        n_tools_unquoted_var=tools_var,
        n_unquoted_var_findings=var_findings,
        n_tools_lone_amp=tools_amp,
        n_lone_amp_findings=amp_findings,
    )


def _report_command_iuc_heuristics(result: _CommandIucHeuristicsResult) -> None:
    with_cmd = result.n_with_command

    def pct(n: int) -> float:
        return 100 * n / with_cmd if with_cmd else 0.0

    print("\n=== command-iuc-heuristics (IUC011/IUC012 sizing; heuristic) ===")
    print(
        f"Unique tools: {result.n_unique_tools}; with <command>: {with_cmd}"
    )
    print(
        f"IUC011 unquoted Cheetah $var: {result.n_tools_unquoted_var} tools "
        f"({pct(result.n_tools_unquoted_var):.1f}%), "
        f"{result.n_unquoted_var_findings} findings"
    )
    print(
        f"IUC012 lone '&':              {result.n_tools_lone_amp} tools "
        f"({pct(result.n_tools_lone_amp):.1f}%), "
        f"{result.n_lone_amp_findings} findings"
    )


def _run_command_iuc_heuristics(args: argparse.Namespace) -> None:
    _report_command_iuc_heuristics(
        _measure_command_iuc_heuristics(corpus_root=args.corpus_root)
    )


# --- measurement: version-tokenization ------------------------------------------
#
# Sizes the Phase-3c "create tokens" opportunity: the canonical IUC convention
# factors a tool's version into `<token name="@TOOL_VERSION@">` (the upstream
# package version) + `<token name="@VERSION_SUFFIX@">` (the Galaxy wrapper bump),
# writing version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@" and
# <requirement version="@TOOL_VERSION@">. This counts how many tools are clean
# candidates for that extraction — a literal version="<base>+galaxy<suffix>"
# whose <base> equals a package <requirement> version — and, of those, how many
# already have a <macros> block vs would need one created (the inline-vs-new-file
# target the create step must choose). Heuristic on the version-string shape.

_GALAXY_SUFFIX = re.compile(r"^(?P<base>.+)\+galaxy(?P<suffix>.*)$")


@dataclass
class _VersionTokenizationResult:
    n_unique_tools: int
    n_missing_version: int
    n_already_tokenized: int  # version= already contains a @TOKEN@
    n_candidates: int  # literal <base>+galaxy<suffix>, base == a package req version
    n_candidates_have_macros: int  # ... already have a <macros> block
    n_candidates_need_macros: int  # ... would need one created
    n_version_equals_req_no_suffix: int  # version == a req literal, no +galaxy
    n_other_literal: int  # some other literal version
    exemplars: list[tuple[str, str]]  # (path, version) for candidates


def _package_requirement_versions(root: etree._Element, /) -> set[str]:
    """Return the literal versions of ``<requirement type="package">`` elements."""
    versions: set[str] = set()
    for requirement in root.findall("requirements/requirement"):
        if requirement.get("type") == "package":
            version = requirement.get("version")
            if version:
                versions.add(version)
    return versions


def _measure_version_tokenization(*, corpus_root: Path) -> _VersionTokenizationResult:
    """Bucket each tool by its readiness for @TOOL_VERSION@/@VERSION_SUFFIX@."""
    seen: set[str] = set()
    n_tools = missing = tokenized = candidates = have = need = 0
    eq_no_suffix = other = 0
    exemplars: list[tuple[str, str]] = []
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        digest = _sha256_of(path)
        if digest in seen:
            continue
        seen.add(digest)
        root = _parse_tool_root(path)
        if root is None:
            continue
        n_tools += 1
        version = root.get("version")
        if version is None:
            missing += 1
            continue
        if "@" in version:
            tokenized += 1
            continue
        match = _GALAXY_SUFFIX.match(version)
        base = match.group("base") if match else version
        req_versions = _package_requirement_versions(root)
        if match is not None and base in req_versions:
            candidates += 1
            if root.find("macros") is None:
                need += 1
            else:
                have += 1
            if len(exemplars) < 10:
                exemplars.append((_display_path(path), version))
        elif base in req_versions:
            eq_no_suffix += 1
        else:
            other += 1
    return _VersionTokenizationResult(
        n_unique_tools=n_tools,
        n_missing_version=missing,
        n_already_tokenized=tokenized,
        n_candidates=candidates,
        n_candidates_have_macros=have,
        n_candidates_need_macros=need,
        n_version_equals_req_no_suffix=eq_no_suffix,
        n_other_literal=other,
        exemplars=exemplars,
    )


def _report_version_tokenization(result: _VersionTokenizationResult) -> None:
    total = result.n_unique_tools

    def pct(n: int) -> float:
        return 100 * n / total if total else 0.0

    print("\n=== version-tokenization (Phase-3c @TOOL_VERSION@ sizing) ===")
    print(f"Unique tools: {total}")
    print(
        f"  version= already tokenized (@…@): {result.n_already_tokenized} "
        f"({pct(result.n_already_tokenized):.1f}%)"
    )
    print(f"  no version= attribute:            {result.n_missing_version}")
    print(
        f"  clean @TOOL_VERSION@ candidates:  {result.n_candidates} "
        f"({pct(result.n_candidates):.1f}%) — "
        f"have <macros> {result.n_candidates_have_macros}, "
        f"need one created {result.n_candidates_need_macros}"
    )
    print(
        f"  version==req literal, no +galaxy: {result.n_version_equals_req_no_suffix}"
    )
    print(f"  other literal version:            {result.n_other_literal}")
    for path, version in result.exemplars[:10]:
        print(f'    {path}: version="{version}"')


def _run_version_tokenization(args: argparse.Namespace) -> None:
    _report_version_tokenization(
        _measure_version_tokenization(corpus_root=args.corpus_root)
    )


# --- measurement: macro-fmt-idempotence -----------------------------------------
#
# Backs fmt §D16 (cosmetic formatting of <macros>-library files) with the same
# corpus evidence tool files already have (fmt §D9/§D13): of the distinct macro
# files in the corpus, how many would `format_macro_document` change, and is the
# formatter idempotent on them (format∘format == format)? A non-idempotent file
# is a bug to retain as a fixture. Macro files are identified by a `<macros>`
# root; deduplicated by content sha256 like the other corpus walks.


@dataclass
class _MacroFmtIdempotenceResult:
    n_macro_files: int  # distinct <macros>-root files (sha-deduped)
    n_unparseable: int  # failed strict load_macros (syntax error)
    n_would_change: int  # formatting changes the bytes
    n_idempotent: int  # format(format(x)) == format(x)
    n_non_idempotent: int
    non_idempotent_exemplars: list[str]


def _measure_macro_fmt_idempotence(
    *, corpus_root: Path
) -> _MacroFmtIdempotenceResult:
    """Sweep distinct macro files for fmt idempotence and change rate."""
    from galaxy_tool_xml.binding import ToolXmlSyntaxError, load_macros
    from galaxy_tool_xml_fmt.format import format_macro_document

    seen: set[str] = set()
    n_files = n_unparseable = n_changed = n_idempotent = n_non_idempotent = 0
    exemplars: list[str] = []
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        root = _parse_macros_root(path)
        if root is None:
            continue
        digest = _sha256_of(path)
        if digest in seen:
            continue
        seen.add(digest)
        n_files += 1
        original = path.read_bytes()
        # load_macros parses strictly; a file the lenient walk accepted may still
        # fail here — count it rather than crash the sweep (adapter boundary).
        try:
            once = format_macro_document(load_macros(path))
            twice = format_macro_document(load_macros(once))
        except ToolXmlSyntaxError:
            n_unparseable += 1
            continue
        if once != original:
            n_changed += 1
        if once == twice:
            n_idempotent += 1
        else:
            n_non_idempotent += 1
            if len(exemplars) < 10:
                exemplars.append(_display_path(path))
    return _MacroFmtIdempotenceResult(
        n_macro_files=n_files,
        n_unparseable=n_unparseable,
        n_would_change=n_changed,
        n_idempotent=n_idempotent,
        n_non_idempotent=n_non_idempotent,
        non_idempotent_exemplars=exemplars,
    )


def _parse_macros_root(path: Path) -> etree._Element | None:
    """Return the parsed root if it is ``<macros>``, else ``None`` (lenient)."""
    if not path.is_file():
        return None
    parser = etree.XMLParser(recover=True, strip_cdata=False)
    try:
        with path.open("rb") as handle:
            tree = etree.parse(handle, parser)
    except (etree.XMLSyntaxError, OSError):
        return None
    root = tree.getroot() if tree is not None else None
    if root is None or root.tag != "macros":
        return None
    return root


def _report_macro_fmt_idempotence(result: _MacroFmtIdempotenceResult) -> None:
    files = result.n_macro_files

    def pct(n: int) -> float:
        return 100 * n / files if files else 0.0

    print("\n=== macro-fmt-idempotence ===")
    print(f"Distinct macro files (sha256 dedup): {files}")
    print(f"  unparseable (strict load failed): {result.n_unparseable}")
    print(
        f"  would change on format: {result.n_would_change} "
        f"({pct(result.n_would_change):.1f}%)"
    )
    print(
        f"  idempotent: {result.n_idempotent}; "
        f"non-idempotent: {result.n_non_idempotent}"
    )
    for path in result.non_idempotent_exemplars[:10]:
        print(f"    NON-IDEMPOTENT: {path}")


def _run_macro_fmt_idempotence(args: argparse.Namespace) -> None:
    _report_macro_fmt_idempotence(
        _measure_macro_fmt_idempotence(corpus_root=args.corpus_root)
    )


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

    ``type`` is collection-typed only on ``<collection>``/``<output_collection>``
    (elsewhere it is a param/data type). ``collection_type`` is the
    comma-permitting ``CollectionTypeList`` grammar only on ``<param>``; on
    ``<output>``/``<collection>`` contexts the XSD types it as colon-only
    ``CollectionType``, so the stricter pattern applies there.
    """
    patterns = _collection_type_patterns()
    if element.tag in ("collection", "output_collection"):
        yield "type", patterns["type"]
    yield "collection_type", (
        patterns["collection_type"] if element.tag == "param" else patterns["type"]
    )


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
        sha = _sha256_of(path)
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


# --- measurement: upgrade-headroom ----------------------------------------------
#
# Sizes what the tier-4 `galaxy-tool-refactor upgrade` command addresses, read
# straight from the combined data: declared profile vs newest-valid vs latest.
# No pipeline run needed — the columns already encode each tool's standing.


def _version_tuple(value: object) -> tuple[int, ...] | None:
    """Return a dotted version string as an int tuple, or ``None`` if not numeric.

    ``"20.05"`` and ``"20.5"`` both yield ``(20, 5)`` (numerically equal); a
    macro placeholder like ``"@PROFILE@"`` or a missing value yields ``None``.
    """
    if not isinstance(value, str):
        return None
    parts = value.split(".")
    if not parts or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


@dataclass
class _UpgradeHeadroomResult:
    """Per-tool classification of upgrade-addressability across the corpus."""

    n_unique_tools: int
    latest_profile: str
    declaration_buckets: list[tuple[str, int]]
    n_with_valid_profile: int
    n_at_latest: int
    n_below_latest: int


def _measure_upgrade_headroom(*, rows: list[dict[str, object]]) -> _UpgradeHeadroomResult:
    """Classify unique tools by what `upgrade` would do to each.

    Declaration buckets mirror ``UpdateProfile``: a tool that validates nowhere
    needs repair first; a macro-placeholder profile is left alone; a missing or
    too-old declaration is added/bumped to the newest valid; an accurate or
    already-newer declaration is unchanged. The structural split counts tools
    whose newest-valid profile is below the latest vendored profile — the
    population a single-step ``upgrade_vN`` could advance.
    """
    unique = _unique_by_sha(rows)
    columns = _validity_columns(rows)
    latest = columns[-1] if columns else ""
    latest_key = _version_tuple(latest)
    buckets: Counter[str] = Counter()
    n_with_valid = n_at_latest = n_below_latest = 0
    for row in unique:
        newest = row.get("newest_valid")
        if newest in (None, "", _PROFILE_NONE):
            buckets["no valid profile (repair first)"] += 1
            continue
        n_with_valid += 1
        newest_key = _version_tuple(newest)
        if newest_key is not None and latest_key is not None:
            if newest_key == latest_key:
                n_at_latest += 1
            elif newest_key < latest_key:
                n_below_latest += 1
        declared = row.get("profile_expanded")
        declared_key = _version_tuple(declared)
        if declared is None or declared == "":
            buckets["no declaration (would be added)"] += 1
        elif declared_key is None:
            buckets["macro-placeholder declaration (left as-is)"] += 1
        elif newest_key is None:
            buckets["non-vendored newest-valid (skipped)"] += 1
        elif declared_key < newest_key:
            buckets["understated (declaration bumped up)"] += 1
        elif declared_key == newest_key:
            buckets["accurate (declaration unchanged)"] += 1
        else:
            buckets["overstated (left as-is, bump-up-only)"] += 1
    return _UpgradeHeadroomResult(
        n_unique_tools=len(unique),
        latest_profile=latest,
        declaration_buckets=buckets.most_common(),
        n_with_valid_profile=n_with_valid,
        n_at_latest=n_at_latest,
        n_below_latest=n_below_latest,
    )


def _report_upgrade_headroom(measurement: _UpgradeHeadroomResult) -> None:
    total = measurement.n_unique_tools
    print("\n=== upgrade-headroom ===")
    print(f"Unique tools (sha256 dedup):  {total}")
    print(f"Latest vendored profile:      {measurement.latest_profile}")
    print("\nDeclaration change `galaxy-tool-refactor upgrade` would make:")
    for label, count in measurement.declaration_buckets:
        pct = count / total * 100 if total else 0
        print(f"  {count:5d}  ({pct:4.1f}%)  {label}")
    valid = measurement.n_with_valid_profile
    at_pct = measurement.n_at_latest / valid * 100 if valid else 0
    below_pct = measurement.n_below_latest / valid * 100 if valid else 0
    print(f"\nStructural headroom (of {valid} tools that validate somewhere):")
    print(f"  {measurement.n_at_latest:5d}  ({at_pct:4.1f}%)  newest-valid is the latest profile")
    print(
        f"  {measurement.n_below_latest:5d}  ({below_pct:4.1f}%)  "
        f"newest-valid below latest (upgrade_vN candidate)"
    )


def _run_upgrade_headroom(args: argparse.Namespace) -> None:
    _report_upgrade_headroom(
        _measure_upgrade_headroom(rows=_load_combined_data(path=args.data))
    )


# --- measurement: semantic-upgrade-boundaries -----------------------------------
#
# How many corpus tools would cross each runtime-behaviour (semantic) profile
# boundary on `upgrade` — the blast radius of the warning in codemod
# decisions.md §23. Baseline = the tool's macro-expanded declared profile, or
# Galaxy's 16.01 runtime default when none is declared; target = newest_valid
# (the pre-upgrade reachable profile — a slight undercount for the ~1.6% of tools
# a structural upgrade_vN advances further). Pinnability per boundary is in
# galaxy-tool-xml-codemod/docs/behavior-preserving-upgrade.md.

# Galaxy upgrade codes a future `--preserve-behaviour` mode could pin CLEANLY (a
# single documented attribute/element restores the old behaviour); the rest have
# no XML opt-out knob (see galaxy-tool-xml-codemod/docs/behavior-preserving-upgrade.md).
_PINNABLE_CLEAN = frozenset(
    {
        "16_04_exit_code",
        "17_09_consider_provided_metadata_style",
        "18_01_consider_home_directory",
        "20_09_consider_set_e",
    }
)


@dataclass
class _SemanticBoundariesResult:
    """Per-upgrade-code crossing counts for `upgrade`-to-latest across the corpus."""

    n_unique_tools: int
    n_no_valid_profile: int
    n_unplaceable_baseline: int
    n_considered: int
    n_no_declaration_baseline: int
    n_cross_any: int
    n_cross_none: int
    per_code: dict[str, int]
    distribution: list[tuple[int, int]]
    total_crossing_events: int
    pinnable_clean_events: int
    n_fully_pinnable_tools: int


def _measure_semantic_upgrade_boundaries(
    *, rows: list[dict[str, object]]
) -> _SemanticBoundariesResult:
    """Tally, per Galaxy upgrade code, how many tools `upgrade`-to-latest would cross.

    A tool is *considered* when it validates somewhere (a target exists) and its
    declared profile is placeable — a literal version, or absent (→ Galaxy's
    16.01 runtime default). A macro-token / unparseable declaration is excluded
    (the live warning skips it too). Crossed codes come from
    ``upgrade_codes_crossed`` — the same function the warning uses (range-based,
    so a code counts whenever its profile is crossed, not whether the tool trips it).
    """
    from galaxy_tool_xml_codemod.profile_semantics import upgrade_codes_crossed

    unique = _unique_by_sha(rows)
    per_code: Counter[str] = Counter()
    distribution: Counter[int] = Counter()
    n_no_valid = n_unplaceable = n_considered = n_no_decl = n_cross_any = 0
    total_events = pinnable_clean = n_fully_pinnable = 0
    for row in unique:
        target = row.get("newest_valid")
        if target in (None, "", _PROFILE_NONE) or _version_tuple(target) is None:
            n_no_valid += 1
            continue
        declared = row.get("profile_expanded")
        if declared in (None, "", _PROFILE_NONE):
            # No profile= (the corpus writes the _PROFILE_NONE sentinel): Galaxy
            # runs these as 16.01, so that is the runtime baseline.
            baseline, no_declaration = "16.01", True
        elif _version_tuple(declared) is not None:
            baseline, no_declaration = str(declared), False
        else:
            # A macro token or "(expansion failed)" — can't place a baseline.
            n_unplaceable += 1
            continue
        n_considered += 1
        n_no_decl += int(no_declaration)
        crossed = upgrade_codes_crossed(from_profile=baseline, to_profile=str(target))
        distribution[len(crossed)] += 1
        n_cross_any += int(bool(crossed))
        codes = [change.code for change in crossed]
        for code in codes:
            per_code[code] += 1
            total_events += 1
            pinnable_clean += int(code in _PINNABLE_CLEAN)
        if codes and all(code in _PINNABLE_CLEAN for code in codes):
            n_fully_pinnable += 1
    return _SemanticBoundariesResult(
        n_unique_tools=len(unique),
        n_no_valid_profile=n_no_valid,
        n_unplaceable_baseline=n_unplaceable,
        n_considered=n_considered,
        n_no_declaration_baseline=n_no_decl,
        n_cross_any=n_cross_any,
        n_cross_none=n_considered - n_cross_any,
        per_code=dict(per_code),
        distribution=sorted(distribution.items()),
        total_crossing_events=total_events,
        pinnable_clean_events=pinnable_clean,
        n_fully_pinnable_tools=n_fully_pinnable,
    )


def _report_semantic_upgrade_boundaries(
    measurement: _SemanticBoundariesResult,
) -> None:
    from galaxy_tool_xml_codemod.profile_semantics import PROFILE_UPGRADE_CODES

    considered = measurement.n_considered
    print("\n=== semantic-upgrade-boundaries ===")
    print(f"Unique tools (sha256 dedup):  {measurement.n_unique_tools}")
    print(
        f"  excluded: {measurement.n_no_valid_profile} validate nowhere"
        f" (repair first); {measurement.n_unplaceable_baseline} unplaceable"
        f" declared profile (macro token)"
    )
    print(f"Considered (placeable baseline + valid target):  {considered}")
    print(
        f"  of which {measurement.n_no_declaration_baseline} have no profile="
        f" (baseline = Galaxy default 16.01)"
    )
    if considered:
        pct = measurement.n_cross_any / considered * 100
        print(
            f"\nWould cross ≥1 Galaxy upgrade code on upgrade-to-latest (the warning"
            f" fires):  {measurement.n_cross_any} ({pct:.1f}%);"
            f" cross none:  {measurement.n_cross_none}"
        )
    print("\nPer-code crossings (tools the bump opts into this change), catalogue order:")
    for change in PROFILE_UPGRADE_CODES:
        count = measurement.per_code.get(change.code, 0)
        if not count:
            continue
        tag = "pinnable" if change.code in _PINNABLE_CLEAN else "no-knob"
        cpct = count / considered * 100 if considered else 0
        print(
            f"  {change.profile:6} {change.level:8} {count:6d} ({cpct:4.1f}%)"
            f"  [{tag}] {change.code}"
        )
    print("\n#codes crossed per tool:")
    for n_codes, n_tools in measurement.distribution:
        print(f"  {n_codes:2d}:  {n_tools}")
    print("\nPinnability (see behavior-preserving-upgrade.md):")
    print(
        f"  crossing-events total:                          "
        f"{measurement.total_crossing_events}"
    )
    print(
        f"  at a cleanly-pinnable code (4 CLEAN knobs):     "
        f"{measurement.pinnable_clean_events}"
    )
    print(
        f"  tools whose EVERY crossed code is cleanly pinnable: "
        f"{measurement.n_fully_pinnable_tools}"
        f"  (a --preserve-behaviour mode could fully cover these)"
    )


def _run_semantic_upgrade_boundaries(args: argparse.Namespace) -> None:
    _report_semantic_upgrade_boundaries(
        _measure_semantic_upgrade_boundaries(rows=_load_combined_data(path=args.data))
    )


# --- measurement: upgrade-codes-applicability -----------------------------------
#
# How much per-tool detection narrows the `upgrade` semantic warning. For each
# considered corpus tool, compare the codes a baseline->newest_valid bump CROSSES
# (range-based `upgrade_codes_crossed`) against those that actually APPLY (the
# per-tool detector fired, `tripped_upgrade_codes`). Backs codemod decisions.md
# §23. Detection runs on the as-loaded (un-expanded) tree, mirroring the live
# facade; it also sanity-checks each detector (e.g. an inverted predicate would
# show applicable ~= crossed or ~= 0). Needs the corpus, so not run in CI.


@dataclass
class _ApplicabilityResult:
    """Range-crossed vs per-tool-applicable upgrade-code counts across the corpus."""

    n_considered: int
    n_warn_range: int  # tools with >=1 crossed code (the old, range-based warning)
    n_warn_applicable: int  # tools with >=1 applicable code (the new warning)
    per_code_crossed: dict[str, int]
    per_code_applicable: dict[str, int]
    total_crossed_events: int
    total_applicable_events: int


def _tally_applicability(
    *, samples: list[tuple[str, str, frozenset[str]]]
) -> _ApplicabilityResult:
    """Tally crossed-vs-applicable over ``(baseline, target, tripped)`` samples.

    Pure (no IO), so it is unit-tested with synthetic samples. ``tripped`` is the
    set of codes whose detector fired for that tool (range-independent).
    """
    from galaxy_tool_xml_codemod.profile_semantics import upgrade_codes_crossed

    per_crossed: Counter[str] = Counter()
    per_applicable: Counter[str] = Counter()
    n_warn_range = n_warn_applicable = total_crossed = total_applicable = 0
    for baseline, target, tripped in samples:
        crossed = upgrade_codes_crossed(from_profile=baseline, to_profile=target)
        if crossed:
            n_warn_range += 1
        applicable = [change for change in crossed if change.code in tripped]
        if applicable:
            n_warn_applicable += 1
        for change in crossed:
            per_crossed[change.code] += 1
            total_crossed += 1
        for change in applicable:
            per_applicable[change.code] += 1
            total_applicable += 1
    return _ApplicabilityResult(
        n_considered=len(samples),
        n_warn_range=n_warn_range,
        n_warn_applicable=n_warn_applicable,
        per_code_crossed=dict(per_crossed),
        per_code_applicable=dict(per_applicable),
        total_crossed_events=total_crossed,
        total_applicable_events=total_applicable,
    )


def _applicability_baseline(declared: object, /) -> str | None:
    """The semantic baseline for a row's ``profile_expanded`` (mirrors the warning).

    No declaration (the ``_PROFILE_NONE`` sentinel) -> Galaxy's 16.01 default; a
    literal version -> itself; a macro token / failed expansion -> ``None`` (the
    live warning skips it too).
    """
    if declared in (None, "", _PROFILE_NONE):
        return "16.01"
    if _version_tuple(declared) is not None:
        return str(declared)
    return None


def _measure_upgrade_codes_applicability(
    *, corpus_root: Path, rows: list[dict[str, object]]
) -> _ApplicabilityResult:
    """Build ``(baseline, target, tripped)`` samples from the corpus + JSON.

    A tool is *considered* on the same terms as ``semantic-upgrade-boundaries``
    (placeable baseline + valid ``newest_valid`` target). The row is joined to
    the on-disk file by sha256 (the corpus dedup key), so no fragile path
    reconstruction is needed; the file is loaded only for detection.
    """
    from galaxy_tool_xml.document import ToolDocument
    from galaxy_tool_xml_codemod.profile_semantics import tripped_upgrade_codes

    row_by_sha = {
        str(row["sha256"]): row for row in rows if isinstance(row.get("sha256"), str)
    }
    samples: list[tuple[str, str, frozenset[str]]] = []
    seen_sha: set[str] = set()
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        sha = _sha256_of(path)
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        row = row_by_sha.get(sha)
        if row is None:
            continue
        target = row.get("newest_valid")
        if target in (None, "", _PROFILE_NONE) or _version_tuple(target) is None:
            continue
        baseline = _applicability_baseline(row.get("profile_expanded"))
        if baseline is None:
            continue
        root = _parse_tool_root(path)
        if root is None:
            continue
        tripped = tripped_upgrade_codes(ToolDocument(root.getroottree()))
        samples.append((baseline, str(target), tripped))
    return _tally_applicability(samples=samples)


def _report_upgrade_codes_applicability(measurement: _ApplicabilityResult) -> None:
    from galaxy_tool_xml_codemod.profile_semantics import PROFILE_UPGRADE_CODES

    considered = measurement.n_considered
    print("\n=== upgrade-codes-applicability ===")
    print(f"Considered tools (placeable baseline + valid target):  {considered}")
    if considered:
        rpct = measurement.n_warn_range / considered * 100
        apct = measurement.n_warn_applicable / considered * 100
        print(
            f"Warning fires, range-based (>=1 code crossed):    "
            f"{measurement.n_warn_range} ({rpct:.1f}%)"
        )
        print(
            f"Warning fires, per-tool   (>=1 code applies):     "
            f"{measurement.n_warn_applicable} ({apct:.1f}%)"
        )
    print(
        f"Crossing events total {measurement.total_crossed_events}"
        f" -> applicable {measurement.total_applicable_events}"
        f" ({100 * measurement.total_applicable_events / measurement.total_crossed_events:.1f}%"
        f" of crossings actually apply)"
        if measurement.total_crossed_events
        else "No crossings."
    )
    print("\nPer-code  crossed -> applies (catalogue order):")
    for change in PROFILE_UPGRADE_CODES:
        crossed = measurement.per_code_crossed.get(change.code, 0)
        if not crossed:
            continue
        applies = measurement.per_code_applicable.get(change.code, 0)
        print(
            f"  {change.profile:6} {change.level:8} {crossed:6d} -> {applies:6d}"
            f"  {change.code}"
        )


def _run_upgrade_codes_applicability(args: argparse.Namespace) -> None:
    _report_upgrade_codes_applicability(
        _measure_upgrade_codes_applicability(
            corpus_root=args.corpus_root, rows=_load_combined_data(path=args.data)
        )
    )


# --- measurement: element-cardinality -------------------------------------------
#
# How many <test>/<requirement>/<conditional>/<collection>/<output_collection>
# elements a tool carries — characterises the structures codemods must traverse.


_CARDINALITY_TAGS = (
    "test",
    "requirement",
    "conditional",
    "collection",
    "output_collection",
)


@dataclass
class _ElementCardinalityResult:
    """Per-tag occurrence stats across unique corpus tools."""

    n_unique_tools: int
    # (tag, tools_with_at_least_one, total_occurrences, max_in_one_tool)
    per_tag: list[tuple[str, int, int, int]]


def _measure_element_cardinality(*, corpus_root: Path) -> _ElementCardinalityResult:
    """Count selected element occurrences per unique tool (sha256 dedup)."""
    seen: set[str] = set()
    n_tools = 0
    with_tag: Counter[str] = Counter()
    total: Counter[str] = Counter()
    max_in_one: Counter[str] = Counter()
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        digest = _sha256_of(path)
        if digest in seen:
            continue
        seen.add(digest)
        root = _parse_tool_root(path)
        if root is None:
            continue
        n_tools += 1
        for tag in _CARDINALITY_TAGS:
            count = sum(1 for _ in root.iter(tag))
            if count:
                with_tag[tag] += 1
                total[tag] += count
                max_in_one[tag] = max(max_in_one[tag], count)
    per_tag = [
        (tag, with_tag[tag], total[tag], max_in_one[tag]) for tag in _CARDINALITY_TAGS
    ]
    return _ElementCardinalityResult(n_unique_tools=n_tools, per_tag=per_tag)


def _report_element_cardinality(measurement: _ElementCardinalityResult) -> None:
    total = measurement.n_unique_tools
    print("\n=== element-cardinality ===")
    print(f"Unique tools (sha256 dedup): {total}")
    print(f"\n  {'element':<18}{'tools >=1':>10}{'(%)':>8}{'total':>9}{'max/tool':>10}")
    for tag, with_tag, occurrences, max_one in measurement.per_tag:
        pct = with_tag / total * 100 if total else 0
        print(f"  <{tag:<17}{with_tag:>10}{pct:>7.1f}%{occurrences:>9}{max_one:>10}")


def _run_element_cardinality(args: argparse.Namespace) -> None:
    _report_element_cardinality(
        _measure_element_cardinality(corpus_root=args.corpus_root)
    )


# --- measurement: command-language ----------------------------------------------
#
# Heuristic interpreter classification of each tool's <command>. Galaxy commands
# are Cheetah-templated shell, often wrapping another interpreter; this scans the
# command text for the first recognised interpreter token (precedence below). It
# is a heuristic, not a parser — a command that merely mentions "python" in a
# comment is counted as python.


_LANGUAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("python", re.compile(r"\bpython[0-9.]*\b")),
    ("Rscript", re.compile(r"\bRscript\b")),
    ("perl", re.compile(r"\bperl\b")),
    ("shell", re.compile(r"\b(?:bash|/bin/sh|\bsh)\b")),
)


def _classify_command_language(text: str) -> str:
    """Return a heuristic interpreter label for one <command> body."""
    for label, pattern in _LANGUAGE_PATTERNS:
        if pattern.search(text):
            return label
    return "other"


@dataclass
class _CommandLanguageResult:
    """Heuristic interpreter-bucket counts across unique corpus tools."""

    n_unique_tools: int
    n_without_command: int
    buckets: list[tuple[str, int]]


def _measure_command_language(*, corpus_root: Path) -> _CommandLanguageResult:
    """Bucket each unique tool's first <command> by detected interpreter."""
    seen: set[str] = set()
    n_tools = 0
    n_without = 0
    buckets: Counter[str] = Counter()
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        digest = _sha256_of(path)
        if digest in seen:
            continue
        seen.add(digest)
        root = _parse_tool_root(path)
        if root is None:
            continue
        n_tools += 1
        command = root.find("command")
        if command is None:
            n_without += 1
            continue
        buckets[_classify_command_language("".join(command.itertext()))] += 1
    return _CommandLanguageResult(
        n_unique_tools=n_tools,
        n_without_command=n_without,
        buckets=buckets.most_common(),
    )


def _report_command_language(measurement: _CommandLanguageResult) -> None:
    total = measurement.n_unique_tools
    print("\n=== command-language (heuristic) ===")
    print(f"Unique tools (sha256 dedup): {total}")
    print(f"Tools with no <command>:     {measurement.n_without_command}")
    print("\nDetected interpreter (first token wins; heuristic, not a parser):")
    for label, count in measurement.buckets:
        pct = count / total * 100 if total else 0
        print(f"  {count:5d}  ({pct:4.1f}%)  {label}")


def _run_command_language(args: argparse.Namespace) -> None:
    _report_command_language(_measure_command_language(corpus_root=args.corpus_root))


# --- measurement: output-format-input -------------------------------------------
#
# Sizes a candidate `format="input"` -> `format_source="X"` runtime-gated fix
# (Galaxy's 16_04_fix_output_format must-fix code; behavior-preserving-upgrade.md).
# The fix is mechanical only when a tool has exactly one data input addressable by
# an unqualified name (a top-level `<param type="data">`); otherwise choosing the
# source input is author intent. Counts tools with an output `<data format="input">`
# and splits them by data-input cardinality to judge whether the codemod earns its
# keep. (Macro walk is shallow — same caveat as param-types.)


@dataclass
class _OutputFormatInputResult:
    """``format="input"`` output population, split by auto-fixability."""

    n_tools_parsed: int
    n_tools_with_format_input: int
    n_format_input_elements: int
    by_data_input_bucket: dict[str, int]
    n_auto_fixable: int


def _measure_output_format_input(*, corpus_root: Path) -> _OutputFormatInputResult:
    """Count output ``<data format="input">`` and the single-top-level-input subset."""
    n_tools = n_with = n_elements = n_auto = 0
    buckets: Counter[str] = Counter()
    for path in _iter_corpus_tool_xmls(corpus_root):
        root = _parse_tool_root(path)
        if root is None:
            continue
        n_tools += 1
        outputs = root.find("outputs")
        if outputs is None:
            continue
        format_input = [d for d in outputs.iter("data") if d.get("format") == "input"]
        if not format_input:
            continue
        n_with += 1
        n_elements += len(format_input)
        inputs = root.find("inputs")
        data_params = (
            [p for p in inputs.iter("param") if p.get("type") == "data"]
            if inputs is not None
            else []
        )
        if len(data_params) == 0:
            buckets["0 data inputs"] += 1
        elif len(data_params) == 1:
            parent = data_params[0].getparent()
            if parent is not None and parent.tag == "inputs":
                buckets["1 top-level (auto-fixable)"] += 1
                n_auto += 1
            else:
                buckets["1 nested (needs qualified ref)"] += 1
        else:
            buckets["2+ data inputs"] += 1
    return _OutputFormatInputResult(
        n_tools_parsed=n_tools,
        n_tools_with_format_input=n_with,
        n_format_input_elements=n_elements,
        by_data_input_bucket=dict(buckets),
        n_auto_fixable=n_auto,
    )


def _report_output_format_input(measurement: _OutputFormatInputResult) -> None:
    print("\n=== output-format-input ===")
    print(f"Tools parsed: {measurement.n_tools_parsed}")
    print(
        f"Tools with an output <data format=\"input\">: "
        f"{measurement.n_tools_with_format_input}"
        f"  ({measurement.n_format_input_elements} such elements)"
    )
    print("\nBy data-input cardinality (of those tools):")
    for label, count in sorted(measurement.by_data_input_bucket.items()):
        print(f"  {count:5d}  {label}")
    print(
        f"\nAuto-fixable (single top-level data input -> unqualified format_source): "
        f"{measurement.n_auto_fixable}"
    )


def _run_output_format_input(args: argparse.Namespace) -> None:
    _report_output_format_input(
        _measure_output_format_input(corpus_root=args.corpus_root)
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
    "macro-profile-tokens": _run_macro_profile_tokens,
    "macro-topology": _run_macro_topology,
    "macro-profile-ownership": _run_macro_profile_ownership,
    "command-iuc-heuristics": _run_command_iuc_heuristics,
    "macro-fmt-idempotence": _run_macro_fmt_idempotence,
    "version-tokenization": _run_version_tokenization,
    "expansion-failed-ids": _run_expansion_failed_ids,
    "cross-source-presence": _run_cross_source_presence,
    "lenient-text-fields": _run_lenient_text_fields,
    "corrections-cutoff": _run_corrections_cutoff,
    "param-types": _run_param_types,
    "collection-type-normalization": _run_collection_type_normalization,
    "upgrade-headroom": _run_upgrade_headroom,
    "semantic-upgrade-boundaries": _run_semantic_upgrade_boundaries,
    "upgrade-codes-applicability": _run_upgrade_codes_applicability,
    "element-cardinality": _run_element_cardinality,
    "command-language": _run_command_language,
    "output-format-input": _run_output_format_input,
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
            "Directory holding the swept corpus; used by the corpus-walking "
            "measurements (lenient-text-fields, param-types, macro-usage, "
            "collection-type-normalization, element-cardinality, "
            "command-language, upgrade-codes-applicability). Default: %(default)s."
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
