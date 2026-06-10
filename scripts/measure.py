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
import copy
import importlib.resources
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
from typing import TYPE_CHECKING

from lxml import etree
from packaging.version import InvalidVersion, Version

from scripts._shared import PROFILE_NONE as _PROFILE_NONE
from scripts._shared import iter_tool_xmls as _iter_tool_xmls
from scripts._shared import row_source as _row_source
from scripts._shared import sha256_of as _sha256_of
from scripts._shared import unique_by_sha as _unique_by_sha

if TYPE_CHECKING:
    from galaxy_tool_xml_codemod.codemod import CodemodCommand
    from galaxy_tool_xml_codemod.profile_semantics import ProfileUpgradeCode

logger = logging.getLogger("measure")


@cache
def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _corpus_root() -> Path:
    return _repo_root() / ".local" / "corpus"


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
    # Imports-per-tool (the inverse of importer_histogram): over tools that pull in
    # >=1 macro file, how big is each tool's bundle? Transitive uses tier-1
    # imported_macro_paths (the canonical de-duplicated resolver); direct counts the
    # tool's own <macros><import> targets only.
    n_tools_importing: int  # tools with >=1 resolvable imported macro file
    n_tools_multi_import: int  # tools whose transitive bundle is >=2 files
    n_nested_import_tools: int  # tools whose transitive bundle > direct (nested <import>)
    max_transitive_imports: int
    transitive_import_histogram: list[tuple[int, int]]  # (bundle_size, n_tools)
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
    from galaxy_tool_xml.macros import has_macros, imported_macro_paths

    seen_sha: set[str] = set()
    importers: dict[Path, set[Path]] = defaultdict(set)
    per_tool_imports: list[set[Path]] = []  # resolved, on-disk imports per tool
    transitive_per_tool: list[int] = []  # bundle size (transitive) over importing tools
    nested_import_tools = 0  # transitive bundle larger than direct (nested <import>)
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

        # Imports-per-tool bundle size, over tools that pull in >=1 macro file.
        # Transitive resolution reuses tier-1 imported_macro_paths (de-duplicated,
        # skips ../absolute/missing); direct is the tool's own existing <import>s.
        transitive_count = len(imported_macro_paths(path))
        direct_count = len(existing_imports)
        if transitive_count or direct_count:
            transitive_per_tool.append(transitive_count)
            if transitive_count > direct_count:
                nested_import_tools += 1

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
    transitive_sorted = sorted(transitive_per_tool)
    transitive_histogram = sorted(Counter(transitive_sorted).items())
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
        n_tools_importing=len(transitive_per_tool),
        n_tools_multi_import=sum(1 for n in transitive_per_tool if n >= 2),
        n_nested_import_tools=nested_import_tools,
        max_transitive_imports=transitive_sorted[-1] if transitive_sorted else 0,
        transitive_import_histogram=transitive_histogram,
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
    print(
        f"  imports per tool (bundle size over {measurement.n_tools_importing} "
        f"importing tools): max {measurement.max_transitive_imports}; "
        f"multi-file (>=2): {measurement.n_tools_multi_import}; "
        f"nested <import> (transitive > direct): {measurement.n_nested_import_tools}"
    )
    print("  bundle-size histogram (transitive files: #tools):")
    for bundle_size, n_tools in measurement.transitive_import_histogram:
        print(f"    {bundle_size}: {n_tools}")
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
            "## Imports per tool (bundle size)",
            "",
            "The inverse of the importer-count distribution above: over the "
            f"**{num(topology.n_tools_importing)}** tools that pull in at least one "
            "macro file, how many files does each tool's transitively-resolved "
            "**bundle** contain? *Direct* counts the tool's own "
            "`<macros><import>` targets; *transitive* follows each imported file's "
            "own `<import>`s (tier-1 `imported_macro_paths`). This sizes the "
            "multi-file bundle population behind a consistent expand-and-modify "
            "model (`docs/macro_handling_architecture.md` §1.4 / §7).",
            "",
            f"Max bundle size: **{num(topology.max_transitive_imports)}** files. "
            f"Tools importing **2 or more** files: "
            f"**{num(topology.n_tools_multi_import)}** "
            f"({pct(topology.n_tools_multi_import, topology.n_tools_importing):.1f}% "
            "of importing tools). Tools whose transitive bundle is larger than its "
            "direct imports — i.e. with **nested `<import>`s**: "
            f"**{num(topology.n_nested_import_tools)}** "
            f"({pct(topology.n_nested_import_tools, topology.n_tools_importing):.1f}%).",
            "",
            "Bundle-size distribution (transitively-imported files per tool):",
            "",
            "| Files in bundle | Tools |",
            "|--:|--:|",
        ]
    )
    lines.extend(
        f"| {bundle_size} | {num(n_tools)} |"
        for bundle_size, n_tools in topology.transitive_import_histogram
    )

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
# Sizes the two reserved advisory placeholders (check §D1): GTR020.2 (single-quote
# Cheetah variables in <command>) and GTR032 (join shell commands with `&&`, not
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
    n_tools_unquoted_var: int  # GTR020.2 candidates: >=1 unquoted Cheetah var
    n_unquoted_var_findings: int  # total unquoted-var occurrences
    n_tools_lone_amp: int  # GTR032 candidates: >=1 lone `&`
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
    """Count GTR020.2/GTR032 candidate findings across each tool's first command."""
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

    print("\n=== command-iuc-heuristics (GTR020.2/GTR032 sizing; heuristic) ===")
    print(
        f"Unique tools: {result.n_unique_tools}; with <command>: {with_cmd}"
    )
    print(
        f"GTR020.2 unquoted Cheetah $var: {result.n_tools_unquoted_var} tools "
        f"({pct(result.n_tools_unquoted_var):.1f}%), "
        f"{result.n_unquoted_var_findings} findings"
    )
    print(
        f"GTR032 lone '&':              {result.n_tools_lone_amp} tools "
        f"({pct(result.n_tools_lone_amp):.1f}%), "
        f"{result.n_lone_amp_findings} findings"
    )


def _run_command_iuc_heuristics(args: argparse.Namespace) -> None:
    _report_command_iuc_heuristics(
        _measure_command_iuc_heuristics(corpus_root=args.corpus_root)
    )


# --- measurement: command-lone-amp ----------------------------------------------
#
# Classifies every lone `&` (the crude GTR032 candidate) in each tool's first
# <command> by what it actually IS, to settle whether the GTR032 check
# ("join with && not a lone &") is worth implementing. The crude `_LONE_AMP`
# heuristic that command-iuc-heuristics counts is dominated by constructs that are
# NOT the anti-pattern: shell redirections (`2>&1`, `&>file`, `<&3`), the `|&`
# pipe operator, and a literal `&` inside a quoted argument (sed/awk's
# "matched text"). The genuine anti-pattern — `cmd1 & cmd2` written where `&&`
# was meant — is what's left. A quote-state scan (single/double) tags the quoted
# class; the rest is classified by adjacency. Heuristic, not a shell parse (that
# is the deferred M5 lexer); backs the GTR032 deferral in
# `galaxy-tool-xml-check/docs/decisions.md`. Needs the corpus, not in CI.

from galaxy_tool_xml_check.lone_amp import (  # noqa: E402 (module section)
    LONE_AMP_CLASSES as _LONE_AMP_CLASSES,
    classify_lone_amps as _classify_lone_amps,
)


@dataclass
class _LoneAmpResult:
    n_unique_tools: int
    n_with_command: int
    n_tools_any_lone_amp: int  # >=1 lone & of any class (the crude GTR032 count)
    n_tools_genuine: int  # >=1 background/joining lone & (what GTR032 could flag)
    per_class_occurrences: dict[str, int]


def _measure_command_lone_amp(*, corpus_root: Path) -> _LoneAmpResult:
    """Classify every tool's first-command lone ``&`` to size the GTR032 anti-pattern."""
    seen: set[str] = set()
    n_tools = n_with = n_any = n_genuine = 0
    per_class: Counter[str] = Counter()
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
        counts = _classify_lone_amps("".join(command.itertext()))
        if not counts:
            continue
        n_any += 1
        per_class.update(counts)
        if counts["background"] or counts["joining"]:
            n_genuine += 1
    return _LoneAmpResult(
        n_unique_tools=n_tools,
        n_with_command=n_with,
        n_tools_any_lone_amp=n_any,
        n_tools_genuine=n_genuine,
        per_class_occurrences=dict(per_class),
    )


def _report_command_lone_amp(result: _LoneAmpResult) -> None:
    print("\n=== command-lone-amp (GTR032 lone-& classification; heuristic) ===")
    print(
        f"Unique tools: {result.n_unique_tools}; "
        f"with <command>: {result.n_with_command}"
    )
    print(
        f"Tools with >=1 lone & (crude GTR032 count): {result.n_tools_any_lone_amp}"
    )
    print(
        f"Tools with a GENUINE lone & (background/joining, not redirect/pipe/quoted):"
        f" {result.n_tools_genuine}"
    )
    print("Occurrences by class:")
    for name in _LONE_AMP_CLASSES:
        print(f"  {name:11} {result.per_class_occurrences.get(name, 0)}")


def _run_command_lone_amp(args: argparse.Namespace) -> None:
    _report_command_lone_amp(_measure_command_lone_amp(corpus_root=args.corpus_root))


# --- measurement: command-unquoted-var ------------------------------------------
#
# Sizes GTR020.2 ("single-quote Cheetah variables in <command>") honestly. The crude
# `command-iuc-heuristics` count (any `$var` not preceded by a single quote) fires
# on 87% of tools — but that is dominated by `$var` in Cheetah *directives*
# (`#if $x`, `#set $y = ...`), which are template logic, NOT shell arguments the
# practice is about. This classifies every `$var` by where it sits: on a Cheetah
# directive/comment line (`#…`), or — on a shell line, via a quote-state scan —
# single-quoted (the IUC-correct form), double-quoted (a lesser concern), or fully
# unquoted (the genuine candidate GTR020.2 would flag). The "unquoted on a shell
# line" population is the real question: does a tokenizer-backed GTR020.2 have signal
# worth shipping, or is it noise like GTR032? This scan IS the core of the
# read-only Cheetah/shell lexer such a check needs. Heuristic (no escape handling,
# inline directives ignored); backs the GTR020.2 decision. Needs the corpus, not in
# CI.

_VAR_CLASSES = ("directive", "single_quoted", "double_quoted", "unquoted")


def _classify_command_vars(text: str, /) -> Counter[str]:
    """Tally each Cheetah ``$var`` in *text* into a ``_VAR_CLASSES`` bucket.

    Pure (string in, counts out), so it is unit-tested with synthetic bodies. A
    line whose stripped form starts with ``#`` is a Cheetah directive/comment (its
    ``$var``s are template logic, bucketed ``directive``); on every other line a
    single-pass single/double quote scan classifies each ``$var`` as
    ``single_quoted`` / ``double_quoted`` / ``unquoted``.
    """
    counts: Counter[str] = Counter()
    for line in text.splitlines():
        if line.strip().startswith("#"):
            counts["directive"] += sum(1 for _ in _CHEETAH_VAR.finditer(line))
            continue
        in_single = in_double = False
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "$":
                match = _CHEETAH_VAR.match(line, i)
                if match is not None:
                    counts[
                        "single_quoted"
                        if in_single
                        else "double_quoted"
                        if in_double
                        else "unquoted"
                    ] += 1
                    i = match.end()
                    continue
            i += 1
    return counts


@dataclass
class _UnquotedVarResult:
    n_unique_tools: int
    n_with_command: int
    n_tools_unquoted: int  # >=1 fully-unquoted shell-line $var (the GTR020.2 target)
    per_class_occurrences: dict[str, int]


def _measure_command_unquoted_var(*, corpus_root: Path) -> _UnquotedVarResult:
    """Classify each tool's first-command ``$var`` to size the genuine GTR020.2 set."""
    seen: set[str] = set()
    n_tools = n_with = n_unquoted = 0
    per_class: Counter[str] = Counter()
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
        counts = _classify_command_vars("".join(command.itertext()))
        per_class.update(counts)
        if counts["unquoted"]:
            n_unquoted += 1
    return _UnquotedVarResult(
        n_unique_tools=n_tools,
        n_with_command=n_with,
        n_tools_unquoted=n_unquoted,
        per_class_occurrences=dict(per_class),
    )


def _report_command_unquoted_var(result: _UnquotedVarResult) -> None:
    with_cmd = result.n_with_command
    pct = 100 * result.n_tools_unquoted / with_cmd if with_cmd else 0.0
    print("\n=== command-unquoted-var (GTR020.2 sizing; heuristic) ===")
    print(
        f"Unique tools: {result.n_unique_tools}; with <command>: {with_cmd}"
    )
    print(
        f"Tools with >=1 fully-unquoted shell-line $var (the GTR020.2 target): "
        f"{result.n_tools_unquoted} ({pct:.1f}%)"
    )
    print("$var occurrences by class:")
    for name in _VAR_CLASSES:
        print(f"  {name:14} {result.per_class_occurrences.get(name, 0)}")


def _run_command_unquoted_var(args: argparse.Namespace) -> None:
    _report_command_unquoted_var(
        _measure_command_unquoted_var(corpus_root=args.corpus_root)
    )


# --- measurement: iuc011-fixability ---------------------------------------------
#
# Sizes the provably-safe auto-fix population for GTR020.2 — the GTR020 codemod's
# scope. Of every unquoted $var the GTR020.2 lexer reports, how many fall in the
# provably-quotable subset {safe, attr_safe, builtin_path} that single-quoting
# cannot change for a tool that currently works (the classifier lives in tier 1:
# `galaxy_tool_xml.command_vars`). Reports the Option-A floor (bare single-token
# `safe` params) and the Option-B delta the path-built-in + space-free-attr
# classes add, so the GTR020 scope decision is data-backed. Reuses the shipped
# GTR020.2 lexer so the population is exactly what the check reports. Heuristic
# (root-name resolution against <inputs>, no full param-model walk). Needs the
# corpus, not in CI.


@dataclass
class _Iuc011FixabilityResult:
    n_tools_flagged: int  # tools with >=1 unquoted var (the GTR020.2 population)
    n_occurrences: int
    per_class: dict[str, int]
    n_tools_all_provable: int  # flagged tools whose every unquoted var is provable
    n_tools_beyond_safe: int  # of those, the ones with >=1 non-safe provable var


def _measure_iuc011_fixability(*, corpus_root: Path) -> _Iuc011FixabilityResult:
    """Classify every GTR020.2 occurrence by whether single-quoting it is provable."""
    from galaxy_tool_xml.command_text import unquoted_cheetah_vars
    from galaxy_tool_xml.command_vars import classify_var, input_param_info

    provable = {"safe", "attr_safe", "builtin_path"}
    seen: set[str] = set()
    n_flagged = n_occ = n_all_provable = n_beyond = 0
    per_class: Counter[str] = Counter()
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
        command = root.find("command")
        if command is None:
            continue
        occurrences = unquoted_cheetah_vars("".join(command.itertext()))
        if not occurrences:
            continue
        n_flagged += 1
        kinds, structural = input_param_info(root)
        classes = [
            classify_var(occurrence.name, kinds, structural)
            for occurrence in occurrences
        ]
        per_class.update(classes)
        n_occ += len(classes)
        if all(cls in provable for cls in classes):
            n_all_provable += 1
            if not all(cls == "safe" for cls in classes):
                n_beyond += 1
    return _Iuc011FixabilityResult(
        n_tools_flagged=n_flagged,
        n_occurrences=n_occ,
        per_class=dict(per_class),
        n_tools_all_provable=n_all_provable,
        n_tools_beyond_safe=n_beyond,
    )


def _report_iuc011_fixability(result: _Iuc011FixabilityResult) -> None:
    from galaxy_tool_xml.command_vars import VAR_CLASSES

    total = result.n_occurrences
    print("\n=== iuc011-fixability (provably-safe auto-quote population; heuristic) ===")
    print(
        f"Flagged tools (>=1 unquoted var): {result.n_tools_flagged}; "
        f"occurrences: {total}"
    )

    def pct(n: int) -> float:
        return 100 * n / total if total else 0.0

    print("Occurrences by reference class:")
    for name in VAR_CLASSES:
        count = result.per_class.get(name, 0)
        print(f"  {name:13} {count:7d}  ({pct(count):.1f}%)")
    safe = result.per_class.get("safe", 0)
    attr_safe = result.per_class.get("attr_safe", 0)
    builtin_path = result.per_class.get("builtin_path", 0)
    option_b = safe + attr_safe + builtin_path
    print(
        f"\nOption A floor (safe bare single-token params): "
        f"{safe} occurrences ({pct(safe):.1f}%)"
    )
    print(
        f"Option B provable (+ attr_safe + builtin_path): "
        f"{option_b} occurrences ({pct(option_b):.1f}%) "
        f"[delta +{attr_safe} attr_safe, +{builtin_path} builtin_path]"
    )
    print(
        f"Tools whose EVERY unquoted var is provable (whole-tool auto-fixable): "
        f"{result.n_tools_all_provable} / {result.n_tools_flagged}"
    )
    print(
        f"  ...of which Option B newly unlocks (>=1 non-safe provable var): "
        f"{result.n_tools_beyond_safe}"
    )


def _run_iuc011_fixability(args: argparse.Namespace) -> None:
    _report_iuc011_fixability(_measure_iuc011_fixability(corpus_root=args.corpus_root))


# --- measurement: select-quoting-safety -----------------------------------------
#
# Sizes the GTR020.1 select/drill_down scope-narrowing (codemod decisions §30; tier-1
# §16). Until this fix, `select` and `drill_down` were blanket members of
# SAFE_SINGLE_TYPES, so GTR020.1 single-quoted ANY bare unquoted `$select_param` in
# <command> — including the widespread multi-flag-dropdown idiom (`<option
# value="-b -h">`), where quoting fuses several argv words into one literal token and
# changes the command Galaxy runs (the behavior-preservation audit's counterexample).
# This measure splits select/drill_down params by static option-value safety and,
# crucially, counts the regression scope: bare select/drill_down references GTR020.1
# would have quoted, split provable vs unsound. Heuristic (root-name resolution
# against <inputs>, no full param-model walk). Needs the corpus, not in CI.

_SELECT_WHITESPACE = re.compile(r"\s")
# Glob / shell-active metacharacters whose meaning changes when single-quoted (mirrors
# the non-whitespace half of command_vars._NOT_SINGLE_TOKEN).
_SELECT_METACHAR = re.compile(r"[*?\[\]$`\\]")


def _select_safety_class(param: etree._Element, /) -> str:
    """Bucket one select/drill_down param by static option-value quoting safety.

    Mirrors ``command_vars._select_options_are_single_tokens`` (``provable`` ==
    that helper's ``True``), splitting the unsafe residual for reporting.
    """
    options = param.find("options")
    if options is not None and any(n.startswith("from_") for n in options.attrib):
        return "dynamic"  # runtime-sourced values -> not statically provable
    values = [option.get("value") for option in param.iter("option")]
    if not values or any(not value for value in values):
        return "noopts"  # no static option set (or an empty value) -> nothing to prove
    if any(_SELECT_WHITESPACE.search(value) for value in values if value):
        return "multiflag"  # a value word-splits -> the multi-flag idiom
    if any(_SELECT_METACHAR.search(value) for value in values if value):
        return "metachar"  # a glob/shell-active value expands unquoted
    return "provable"


@dataclass
class _SelectQuotingResult:
    n_params: int  # all non-multiple select/drill_down params corpus-wide
    per_class: Counter[str]  # by _select_safety_class
    n_referenced: int  # of those, bare-referenced unquoted in <command> (GTR020.1 scope)
    referenced_per_class: Counter[str]
    n_tools_unsound_before: int  # tools where old GTR020.1 would quote an unsound select


def _measure_select_quoting_safety(*, corpus_root: Path) -> _SelectQuotingResult:
    """Split select/drill_down params by quoting safety + the GTR020.1 regression scope."""
    from galaxy_tool_xml.command_text import unquoted_cheetah_vars

    option_valued = {"select", "drill_down"}
    seen: set[str] = set()
    per_class: Counter[str] = Counter()
    referenced_per_class: Counter[str] = Counter()
    n_params = n_referenced = n_tools_unsound = 0
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
        inputs = root.find("inputs")
        if inputs is None:
            continue
        classes: dict[str, str] = {}  # param-name -> safety class (non-multiple only)
        for param in inputs.iter("param"):
            name = param.get("name")
            if not name or param.get("type", "") not in option_valued:
                continue
            if param.get("multiple") in ("true", "True", "1"):
                continue  # multiple= is a deliberate splat, never GTR020.1's scope
            safety = _select_safety_class(param)
            classes[name] = safety
            per_class[safety] += 1
            n_params += 1
        if not classes:
            continue
        command = root.find("command")
        if command is None:
            continue
        tool_unsound = False
        for occurrence in unquoted_cheetah_vars("".join(command.itertext())):
            # GTR020.1's select bug was for a BARE $param (no .attr / [idx]).
            bare = occurrence.name.strip("${}")
            if bare not in classes or any(sep in bare for sep in ".["):
                continue
            safety = classes[bare]
            referenced_per_class[safety] += 1
            n_referenced += 1
            if safety != "provable":
                tool_unsound = True
        if tool_unsound:
            n_tools_unsound += 1
    return _SelectQuotingResult(
        n_params=n_params,
        per_class=per_class,
        n_referenced=n_referenced,
        referenced_per_class=referenced_per_class,
        n_tools_unsound_before=n_tools_unsound,
    )


def _report_select_quoting_safety(result: _SelectQuotingResult) -> None:
    order = ("provable", "multiflag", "metachar", "dynamic", "noopts")
    print("\n=== select-quoting-safety (GTR020.1 scope-narrowing; heuristic) ===")

    def line(label: str, per: Counter[str], total: int) -> None:
        print(f"{label} (total {total}):")
        for name in order:
            count = per.get(name, 0)
            pct = 100 * count / total if total else 0.0
            print(f"  {name:10} {count:7d}  ({pct:.1f}%)")

    line("All non-multiple select/drill_down params", result.per_class, result.n_params)
    line(
        "Bare-referenced unquoted in <command> (GTR020.1 scope)",
        result.referenced_per_class,
        result.n_referenced,
    )
    unsound = result.n_referenced - result.referenced_per_class.get("provable", 0)
    print(
        f"\nUnsound-before occurrences (old GTR020.1 would have mis-quoted): {unsound} "
        f"across {result.n_tools_unsound_before} tools"
    )
    print(
        f"Provable subset retained by the fix: "
        f"{result.referenced_per_class.get('provable', 0)} / {result.n_referenced}"
    )


def _run_select_quoting_safety(args: argparse.Namespace) -> None:
    _report_select_quoting_safety(
        _measure_select_quoting_safety(corpus_root=args.corpus_root)
    )


# --- measurement: shell-oracle-quoting ------------------------------------------
#
# Sizes the shell boundary oracle's effect on GTR020.1 vs the pure value-domain rule
# (the Phase-1 widening payoff). For every unquoted $var in a pure-text <command>,
# compares `provably_quotable` (value-domain) with `quote_is_behavior_preserving`
# (value-domain + bashlex shell-context): WIDENED = the oracle now quotes a var the
# value-domain rule would not (a residual var in a no-word-splitting context, e.g. an
# assignment RHS); NARROWED = the oracle declines a value-domain-safe var (an fd-dup
# target). Requires the `galaxy-tool-xml[shell-oracle]` extra (bashlex) — without it
# the oracle degrades to the value-domain rule and both counts are 0. Needs the
# corpus, not in CI. See galaxy-tool-xml `docs/decisions.md` §17, codemod §31.


@dataclass
class _ShellOracleQuotingResult:
    oracle_available: bool
    n_tools_flagged: int  # pure-text commands with >=1 unquoted var
    n_occurrences: int
    widened_occurrences: int  # value-domain says no, oracle says yes
    widened_tools: int
    narrowed_occurrences: int  # value-domain says yes, oracle says no
    narrowed_tools: int


def _measure_shell_oracle_quoting(*, corpus_root: Path) -> _ShellOracleQuotingResult:
    """Count where the shell oracle widens / narrows GTR020.1 vs the value-domain rule."""
    from galaxy_tool_xml.command_text import unquoted_cheetah_vars
    from galaxy_tool_xml.command_vars import input_param_info, provably_quotable
    from galaxy_tool_xml.shell_oracle import (
        quote_is_behavior_preserving,
        shell_oracle_available,
    )

    seen: set[str] = set()
    n_flagged = n_occ = widened_occ = widened_tools = narrowed_occ = narrowed_tools = 0
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
        command = root.find("command")
        if command is None or len(command) > 0:  # mixed content: GTR020.1 skips it
            continue
        body = command.text or ""
        occurrences = unquoted_cheetah_vars(body)
        if not occurrences:
            continue
        n_flagged += 1
        kinds, structural = input_param_info(root)
        tool_widened = tool_narrowed = 0
        for occurrence in occurrences:
            n_occ += 1
            value_domain = provably_quotable(occurrence.name, kinds, structural)
            oracle = quote_is_behavior_preserving(
                body, occurrence=occurrence, kinds=kinds, structural=structural
            )
            if oracle and not value_domain:
                tool_widened += 1
            elif value_domain and not oracle:
                tool_narrowed += 1
        widened_occ += tool_widened
        narrowed_occ += tool_narrowed
        widened_tools += tool_widened > 0
        narrowed_tools += tool_narrowed > 0
    return _ShellOracleQuotingResult(
        oracle_available=shell_oracle_available(),
        n_tools_flagged=n_flagged,
        n_occurrences=n_occ,
        widened_occurrences=widened_occ,
        widened_tools=widened_tools,
        narrowed_occurrences=narrowed_occ,
        narrowed_tools=narrowed_tools,
    )


def _report_shell_oracle_quoting(result: _ShellOracleQuotingResult) -> None:
    print("\n=== shell-oracle-quoting (GTR020.1 widen/narrow vs value-domain) ===")
    if not result.oracle_available:
        print(
            "shell-oracle extra (bashlex) NOT installed — oracle degrades to the "
            "value-domain rule; widen/narrow are 0 by construction."
        )
    print(
        f"Pure-text <command>s with >=1 unquoted var: {result.n_tools_flagged}; "
        f"occurrences: {result.n_occurrences}"
    )
    print(
        f"WIDENED (value-domain no -> oracle yes; e.g. assignment-RHS residual): "
        f"{result.widened_occurrences} occurrences across {result.widened_tools} tools"
    )
    print(
        f"NARROWED (value-domain yes -> oracle no; fd-dup targets): "
        f"{result.narrowed_occurrences} occurrences across {result.narrowed_tools} tools"
    )


def _run_shell_oracle_quoting(args: argparse.Namespace) -> None:
    _report_shell_oracle_quoting(
        _measure_shell_oracle_quoting(corpus_root=args.corpus_root)
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
# per-tool detector fired). Backs codemod decisions.md §23. Detection runs on the
# **raw** (un-expanded) tree via `detect_codes_on_root` — this is a raw-tree
# diagnostic. The live facade now detects post-macro-expansion
# (`tripped_upgrade_codes`); the size of that shift is the
# `macro-expansion-detection-gap` measure (codemod §25). It also sanity-checks
# each detector (an inverted predicate would show applicable ~= crossed or ~= 0).
# Needs the corpus, so not run in CI.


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
    from galaxy_tool_xml_codemod.profile_semantics import detect_codes_on_root

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
        tripped = detect_codes_on_root(root)
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


# --- measurement: set-e-tightening ----------------------------------------------
#
# Sizes the SOUND tightening of the `20_09_consider_set_e` detector (codemod
# decisions §28). The current detector (`_detects_no_strict`) fires for any
# `<command>` without `strict="false"` — ~every command-bearing tool. But `set -e`
# (20.09+) only changes behaviour when an earlier command in a SEQUENCE can fail
# non-fatally and a later one still runs; a body that is a single simple command
# runs identically with or without it, so the note does not apply. This counts,
# per unique tool, how many the current detector fires on vs how many are a
# provably-single-simple command (the sound suppression). Heuristic over the
# `<command>` CDATA text, NOT a Cheetah/shell parse; conservative — any control
# directive or sequencing/pipeline/background metacharacter counts as NOT simple,
# so it never suppresses a tool `set -e` could affect. The sizing reuses the SAME
# predicate the shipped detector uses (`profile_semantics.
# _command_text_is_single_simple_statement`, imported in the measure below) so the
# two can't drift. Needs the corpus, not in CI.


@dataclass
class _SetETighteningResult:
    n_unique_tools: int
    n_with_command: int
    n_current_fires: int  # <command> present, no strict= (today's detector)
    n_single_simple: int  # of those, provably single simple command (suppressible)


def _measure_set_e_tightening(*, corpus_root: Path) -> _SetETighteningResult:
    """Count current ``set_e`` detector hits vs the sound single-command suppression."""
    from galaxy_tool_xml_codemod.profile_semantics import (
        _command_text_is_single_simple_statement,
    )

    seen: set[str] = set()
    n_tools = n_with = fires = simple = 0
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
        if command.get("strict") is not None:
            continue  # current detector fires only when strict= is absent
        fires += 1
        if _command_text_is_single_simple_statement("".join(command.itertext())):
            simple += 1
    return _SetETighteningResult(
        n_unique_tools=n_tools,
        n_with_command=n_with,
        n_current_fires=fires,
        n_single_simple=simple,
    )


def _report_set_e_tightening(result: _SetETighteningResult) -> None:
    fires = result.n_current_fires
    print("\n=== set-e-tightening (20_09_consider_set_e detector precision) ===")
    print(
        f"Unique tools: {result.n_unique_tools}; "
        f"with <command>: {result.n_with_command}"
    )
    print(f"Current detector fires (no strict=):              {fires}")
    if fires:
        pct = 100 * result.n_single_simple / fires
        print(
            f"Provably single simple command (sound suppress): "
            f"{result.n_single_simple} ({pct:.1f}% of fires)"
        )
        print(
            f"After tightening, set_e still applies to:         "
            f"{fires - result.n_single_simple}"
        )


def _run_set_e_tightening(args: argparse.Namespace) -> None:
    _report_set_e_tightening(_measure_set_e_tightening(corpus_root=args.corpus_root))


# --- measurement: macro-expansion-detection-gap ---------------------------------
#
# Sizes the cost of running the upgrade-code detectors (`_DETECTORS` /
# `tripped_upgrade_codes`) on the RAW tool tree while Galaxy's own advisor runs
# POST-macro-expansion (`xml_macros.load_with_references`). For every macro-bearing
# tool that expands cleanly, compares the codes each detector fires raw vs expanded:
#   - over-flag  = fires raw but NOT expanded -> a false positive vs Galaxy: the raw
#                  tree lacks a construct a macro supplies, e.g. `<expand
#                  macro="stdio"/>` hides error handling, so `16_04_exit_code` ("no
#                  error handling") fires on the raw tree but not after expansion.
#   - under-report = fires expanded but NOT raw -> the §25 detection gap: the macro
#                  supplies the triggering construct, unseen on the raw tree.
#   - agree       = both fire.
# Macro-free tools have raw == expanded by construction (not compared); expansion
# failures are uncomparable. Backs codemod decisions §25 and the macro-expansion
# detector port. Needs the corpus, so not run in CI.


@dataclass
class _ExpansionGapResult:
    """Raw-tree vs post-macro-expansion detector divergence across the corpus."""

    n_unique_tools: int  # deduped <tool> files parsed (compared + no_macros + failed)
    n_unparseable: int  # deduped XML skipped (non-<tool> root or hard parse failure)
    n_no_macros: int  # macro-free: raw == expanded by construction
    n_expansion_failed: int  # macro-bearing but expansion returned no tree
    n_compared: int  # macro-bearing AND expanded cleanly
    n_tools_over_flag: int  # compared tools with >=1 over-flag code
    n_tools_under_report: int  # compared tools with >=1 under-report code (§25 gap)
    n_tools_divergent: int  # compared tools with >=1 code differing either direction
    over_flag: dict[str, int]  # per code: fires raw, not expanded
    under_report: dict[str, int]  # per code: fires expanded, not raw
    agree_positive: dict[str, int]  # per code: fires on both


# One walked tool classified for the pure tally: its status plus, when
# ``status == "compared"``, the codes that fired on the raw and expanded trees.
_GapSample = tuple[str, frozenset[str], frozenset[str]]


def _tally_expansion_gap(*, samples: list[_GapSample]) -> _ExpansionGapResult:
    """Tally raw-vs-expanded detector divergence over classified tool samples.

    Pure (no IO / no parsing), so it is unit-tested with synthetic samples. Each
    sample is ``(status, raw_codes, expanded_codes)`` where ``status`` is one of
    ``"unparseable"`` / ``"no_macros"`` / ``"expansion_failed"`` / ``"compared"``;
    the code sets carry meaning only for ``"compared"``.
    """
    over: Counter[str] = Counter()
    under: Counter[str] = Counter()
    agree: Counter[str] = Counter()
    unparseable = no_macros = expansion_failed = compared = 0
    n_over = n_under = n_divergent = 0
    for status, raw_codes, expanded_codes in samples:
        if status == "unparseable":
            unparseable += 1
            continue
        if status == "no_macros":
            no_macros += 1
            continue
        if status == "expansion_failed":
            expansion_failed += 1
            continue
        compared += 1
        raw_only = raw_codes - expanded_codes
        expanded_only = expanded_codes - raw_codes
        for code in raw_only:
            over[code] += 1
        for code in expanded_only:
            under[code] += 1
        for code in raw_codes & expanded_codes:
            agree[code] += 1
        if raw_only:
            n_over += 1
        if expanded_only:
            n_under += 1
        if raw_only or expanded_only:
            n_divergent += 1
    return _ExpansionGapResult(
        n_unique_tools=no_macros + expansion_failed + compared,
        n_unparseable=unparseable,
        n_no_macros=no_macros,
        n_expansion_failed=expansion_failed,
        n_compared=compared,
        n_tools_over_flag=n_over,
        n_tools_under_report=n_under,
        n_tools_divergent=n_divergent,
        over_flag=dict(over),
        under_report=dict(under),
        agree_positive=dict(agree),
    )


def _classify_expansion_gap(path: Path, /) -> _GapSample:
    """Classify one corpus tool into a ``_tally_expansion_gap`` sample.

    Parses the raw tree and — only when the tool uses macros — expands it from
    disk (so ``<import>``s resolve against the tool's own directory), running the
    detectors over each tree directly via ``detect_codes_on_root`` (the raw-tree
    primitive — *not* ``tripped_upgrade_codes``, which would itself expand and
    collapse the comparison). Macro-free tools are ``"no_macros"`` (raw ==
    expanded); a failed expansion is ``"expansion_failed"`` (uncomparable).
    """
    from galaxy_tool_xml.macros import expand_from_path, has_macros
    from galaxy_tool_xml_codemod.profile_semantics import detect_codes_on_root

    empty: frozenset[str] = frozenset()
    root = _parse_tool_root(path)
    if root is None:
        return ("unparseable", empty, empty)
    if not has_macros(root):
        return ("no_macros", empty, empty)
    raw_codes = detect_codes_on_root(root)
    expanded_tree, _errors = expand_from_path(path)
    if expanded_tree is None:
        return ("expansion_failed", raw_codes, empty)
    expanded_codes = detect_codes_on_root(expanded_tree.getroot())
    return ("compared", raw_codes, expanded_codes)


def _measure_macro_expansion_detection_gap(
    *, corpus_root: Path
) -> _ExpansionGapResult:
    """Walk the corpus (sha-deduped) and tally raw-vs-expanded detector divergence."""
    seen_sha: set[str] = set()
    samples: list[_GapSample] = []
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        sha = _sha256_of(path)
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        samples.append(_classify_expansion_gap(path))
    return _tally_expansion_gap(samples=samples)


def _report_macro_expansion_detection_gap(measurement: _ExpansionGapResult) -> None:
    from galaxy_tool_xml_codemod.profile_semantics import PROFILE_UPGRADE_CODES

    m = measurement
    print("\n=== macro-expansion-detection-gap ===")
    print(f"Unique <tool> files (sha-deduped):       {m.n_unique_tools}")
    print(f"  macro-free (raw == expanded):          {m.n_no_macros}")
    print(f"  macro-bearing, expansion failed:       {m.n_expansion_failed}")
    print(f"  macro-bearing, compared:               {m.n_compared}")
    print(f"  (non-<tool>/unparseable XML skipped:   {m.n_unparseable})")
    if m.n_compared:
        opct = m.n_tools_over_flag / m.n_compared * 100
        upct = m.n_tools_under_report / m.n_compared * 100
        print(
            f"Compared tools over-flagged (raw fires, Galaxy would not):  "
            f"{m.n_tools_over_flag} ({opct:.1f}%)"
        )
        print(
            f"Compared tools under-reported (macro supplies it, §25 gap): "
            f"{m.n_tools_under_report} ({upct:.1f}%)"
        )
    print("\nPer-code  over-flag / under-report / agree (catalogue order):")
    for change in PROFILE_UPGRADE_CODES:
        over = m.over_flag.get(change.code, 0)
        under = m.under_report.get(change.code, 0)
        agree = m.agree_positive.get(change.code, 0)
        if not (over or under or agree):
            continue
        print(
            f"  {change.profile:6} {change.level:8} "
            f"over {over:6d}  under {under:6d}  agree {agree:6d}  {change.code}"
        )


def _run_macro_expansion_detection_gap(args: argparse.Namespace) -> None:
    _report_macro_expansion_detection_gap(
        _measure_macro_expansion_detection_gap(corpus_root=args.corpus_root)
    )


# --- measurement: upgrade-profile-shift -----------------------------------------
#
# Where does `upgrade` move a tool's profile? Compares the profile the tool
# *declares* (defaulting no-profile to Galaxy's 16.01 runtime default — the "as
# reported, or as defaulted" baseline) against the profile it *reaches* after the
# `UpgradeToLatest` pipeline runs. Unlike combined_corpus_stats.md's "newest valid
# profile distribution" (the pre-upgrade validity ceiling), this runs the actual
# structural upgrade codemods (GTR007-012), so a tool stuck below its ceiling by a
# restrict-transition climbs. Runtime-gated fixes (GTR014/015) don't change the
# profile, so they don't affect this. UpgradeToLatest-only (no FixTypos), matching
# the reach figure in docs/profile_upgrades.md. Writes
# docs/upgrade_profile_shift_stats.md. Needs the corpus, so not run in CI.


@dataclass
class _ProfileShiftResult:
    """Declared/defaulted vs post-`upgrade` profile distributions across the corpus."""

    n_tools: int
    latest: str
    before: dict[str, int]  # declared (no-profile -> 16.01) bucket -> count
    after: dict[str, int]  # reached profile bucket -> count ("(none)" = nowhere)
    n_at_latest_before: int
    n_at_latest_after: int
    n_advanced: int  # reached a strictly newer profile (both placeable)
    n_unchanged: int  # reached the same profile
    n_unplaceable_baseline: int  # declared a macro token / unparseable profile
    n_after_validates_nowhere: int  # did not validate at any profile after upgrade


def _baseline_bucket(declared: str | None, /) -> str:
    """The "as reported, or as defaulted" baseline bucket for a declared profile.

    No declaration -> ``"16.01"`` (Galaxy's runtime default, matching
    ``resolve_profile(None)`` and the facade's ``_semantic_baseline``); a literal
    version -> itself; a macro token / unparseable value -> a single
    ``"(macro/unparseable)"`` bucket (the facade can't place it either).
    """
    if declared is None:
        return "16.01"
    if _version_tuple(declared) is not None:
        return declared
    return "(macro/unparseable)"


def _tally_profile_shift(
    *, samples: list[tuple[str, str]], latest: str
) -> _ProfileShiftResult:
    """Tally before/after profile buckets over ``(baseline, reached)`` samples.

    Pure (no IO), so it is unit-tested with synthetic samples. ``reached`` is the
    post-upgrade profile, or ``"(none)"`` when the tool validates nowhere.
    """
    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    n_at_before = n_at_after = n_advanced = n_unchanged = 0
    n_unplaceable = n_nowhere = 0
    for baseline, reached in samples:
        before[baseline] += 1
        after[reached] += 1
        n_at_before += int(baseline == latest)
        n_at_after += int(reached == latest)
        before_v = _version_tuple(baseline)
        reached_v = _version_tuple(reached)
        if baseline == "(macro/unparseable)":
            n_unplaceable += 1
        if reached == "(none)":
            n_nowhere += 1
        if before_v is not None and reached_v is not None:
            if reached_v > before_v:
                n_advanced += 1
            elif reached_v == before_v:
                n_unchanged += 1
    return _ProfileShiftResult(
        n_tools=len(samples),
        latest=latest,
        before=dict(before),
        after=dict(after),
        n_at_latest_before=n_at_before,
        n_at_latest_after=n_at_after,
        n_advanced=n_advanced,
        n_unchanged=n_unchanged,
        n_unplaceable_baseline=n_unplaceable,
        n_after_validates_nowhere=n_nowhere,
    )


def _measure_upgrade_profile_shift(*, corpus_root: Path) -> _ProfileShiftResult:
    """Run ``UpgradeToLatest`` over the corpus and tally declared -> reached profile."""
    from galaxy_tool_xml.binding import newest_valid_profile
    from galaxy_tool_xml.document import ToolDocument
    from galaxy_tool_xml.profiles import latest_profile
    from galaxy_tool_xml_codemod.module import Module
    from galaxy_tool_xml_codemod.upgrades import UpgradeToLatest

    samples: list[tuple[str, str]] = []
    seen_sha: set[str] = set()
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        sha = _sha256_of(path)
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        root = _parse_tool_root(path)
        if root is None:
            continue
        baseline = _baseline_bucket(root.get("profile"))
        document = ToolDocument(root.getroottree(), source_path=path)
        UpgradeToLatest().apply(Module(document))
        reached = newest_valid_profile(document)
        samples.append((baseline, reached if reached is not None else "(none)"))
    return _tally_profile_shift(samples=samples, latest=latest_profile())


def _profile_dist_rows(counts: dict[str, int], total: int, /) -> list[str]:
    """Markdown table rows for a profile distribution, version order then specials."""

    def sort_key(item: tuple[str, int]) -> tuple[int, tuple[int, ...]]:
        version = _version_tuple(item[0])
        return (0, version) if version is not None else (1, ())

    bar_max = max(counts.values(), default=0)
    rows: list[str] = []
    for profile, count in sorted(counts.items(), key=sort_key):
        pct = 100 * count / total if total else 0.0
        bar = "█" * round(30 * count / bar_max) if bar_max else ""
        rows.append(f"| {profile} | {count:,} | {pct:.1f}% | {bar} |")
    return rows


def _render_profile_shift_page(result: _ProfileShiftResult) -> str:
    """Render the upgrade-profile-shift stats markdown page (deterministic)."""
    total = result.n_tools

    def pct(n: int) -> str:
        return f"{100 * n / total:.1f}%" if total else "0.0%"

    lines: list[str] = [
        "# Upgrade profile-shift statistics",
        "",
        "Where `galaxy-tool-refactor upgrade` moves a tool's profile: the profile it",
        "**declares** (no-profile defaulted to Galaxy's `16.01` runtime default — the",
        '"as reported, or as defaulted" baseline) vs the profile it **reaches** after',
        "the `UpgradeToLatest` pipeline runs. This differs from",
        "`combined_corpus_stats.md`'s *newest valid profile distribution* (the",
        "pre-upgrade validity ceiling): here the structural upgrade codemods",
        "(GTR007-012) actually run, so a tool stuck below its ceiling by a",
        "restrict-transition climbs. `UpgradeToLatest`-only (no `FixTypos`); the",
        "runtime-gated fixes (GTR014/015) don't change `profile=`. See",
        "`profile_upgrades.md` and codemod `docs/decisions.md` §11-14.",
        "",
        "Regenerate with (needs the corpus, so not run in CI):",
        "",
        "```sh",
        "uv run python -m scripts.measure upgrade-profile-shift",
        "```",
        "",
        f"Unique `<tool>` files (sha256-deduped): **{result.n_tools:,}**. "
        f"Latest vendored profile: `{result.latest}`.",
        "",
        "## Shift summary",
        "",
        "| Measure | Tools | Share |",
        "|---|--:|--:|",
        f"| At latest **before** upgrade (declared = `{result.latest}`) "
        f"| {result.n_at_latest_before:,} | {pct(result.n_at_latest_before)} |",
        f"| At latest **after** upgrade | {result.n_at_latest_after:,} "
        f"| {pct(result.n_at_latest_after)} |",
        f"| Advanced (reached a newer profile) | {result.n_advanced:,} "
        f"| {pct(result.n_advanced)} |",
        f"| Unchanged (same profile) | {result.n_unchanged:,} "
        f"| {pct(result.n_unchanged)} |",
        f"| Macro-token / unplaceable baseline | {result.n_unplaceable_baseline:,} "
        f"| {pct(result.n_unplaceable_baseline)} |",
        f"| Validates nowhere after upgrade | {result.n_after_validates_nowhere:,} "
        f"| {pct(result.n_after_validates_nowhere)} |",
        "",
        "## Declared (defaulted) profile distribution — before",
        "",
        "| Profile | Tools | % | Histogram |",
        "|---|--:|--:|---|",
        *_profile_dist_rows(result.before, total),
        "",
        "## Reached profile distribution — after `upgrade`",
        "",
        "| Profile | Tools | % | Histogram |",
        "|---|--:|--:|---|",
        *_profile_dist_rows(result.after, total),
        "",
        "`(none)` = validates at no profile after the run. Because this is "
        "`UpgradeToLatest`-only, these are the tools that need a `FixTypos` repair "
        "first (the full `galaxy-tool-refactor upgrade` runs `FixTypos` before "
        "`UpgradeToLatest`, so it would carry many of them further). A sub-latest "
        "literal profile (e.g. `24.1`) is a genuine sticking point — no registered "
        "upgrade codemod advances it. The macro-token baselines counted above are "
        "not lost: they appear here at the profile they actually reached.",
    ]
    return "\n".join(lines)


def _report_upgrade_profile_shift(result: _ProfileShiftResult) -> None:
    total = result.n_tools
    print("\n=== upgrade-profile-shift ===")
    print(f"Unique tools (sha256 dedup): {total}; latest = {result.latest}")
    if total:
        print(
            f"  at latest before: {result.n_at_latest_before}"
            f" ({100 * result.n_at_latest_before / total:.1f}%)"
            f"  ->  after: {result.n_at_latest_after}"
            f" ({100 * result.n_at_latest_after / total:.1f}%)"
        )
        print(
            f"  advanced: {result.n_advanced}; unchanged: {result.n_unchanged};"
            f" unplaceable baseline: {result.n_unplaceable_baseline};"
            f" nowhere after: {result.n_after_validates_nowhere}"
        )


def _run_upgrade_profile_shift(args: argparse.Namespace) -> None:
    result = _measure_upgrade_profile_shift(corpus_root=args.corpus_root)
    _report_upgrade_profile_shift(result)
    if not args.all:
        out_path = _repo_root() / "docs" / "upgrade_profile_shift_stats.md"
        out_path.write_text(_render_profile_shift_page(result) + "\n", encoding="utf-8")
        print(f"\nwrote {_display_path(out_path)}")


# --- measurement: upgrade-behavior-blocks ---------------------------------------
#
# A hypothetical *behavior-preserving* auto-upgrade: walk a tool's profile from
# its declared (or Galaxy-defaulted 16.01) baseline toward the latest, but STOP
# the moment it would cross a Galaxy profile-behaviour change (`PROFILE_UPGRADE_CODES`)
# that (a) actually applies to the tool (its per-tool detector fires) and (b) the
# toolchain cannot automatically fix. Reports the distribution of where tools get
# stuck, keyed by the blocking profile version + behavior code, under two severity
# policies (must_fix only; must_fix + consider). Unlike `upgrade` (which never
# stops on behaviour, only warns), this layers the stop rule on the existing
# range + detector primitives, so it does NOT call the facade. Auto-fixability is
# judged exactly, by applying the mapped codemod to a copy and re-detecting — so
# GTR015's sole-data-input partiality is modeled precisely. Writes
# docs/upgrade_behavior_block_stats.md. Needs the corpus, so not run in CI.

_MUST_FIX_ONLY = frozenset({"must_fix"})
_MUST_FIX_AND_CONSIDER = frozenset({"must_fix", "consider"})


@dataclass
class _BlockPolicyResult:
    """Behaviour-block outcomes under one severity policy (which levels halt)."""

    reached_latest: int  # no applicable, unfixable blocker of this severity
    stuck_total: int  # halted at the first such blocker
    per_code: dict[str, int]  # first-blocker code -> tools stuck there


@dataclass
class _BehaviorBlockResult:
    """Where a behavior-preserving auto-upgrade stalls across the corpus."""

    n_considered: int  # unique tools with a placeable baseline
    n_excluded: int  # macro-token / unparseable declared profile (can't range)
    latest: str
    must_fix: _BlockPolicyResult
    must_fix_and_consider: _BlockPolicyResult


def _tally_one_policy(
    *, samples: list[tuple[ProfileUpgradeCode, ...]], levels: frozenset[str]
) -> _BlockPolicyResult:
    """Tally first-blocker outcomes for one severity policy (pure, no IO).

    Each sample is a tool's applicable, non-auto-fixable crossed codes. The first
    blocker is the lowest-profile code whose level halts under *levels*; a sample
    with no such code reaches the latest profile behavior-preservingly.
    """
    reached = 0
    per_code: Counter[str] = Counter()
    for sample in samples:
        blockers = [change for change in sample if change.level in levels]
        if not blockers:
            reached += 1
            continue
        first = min(blockers, key=lambda change: Version(change.profile))
        per_code[first.code] += 1
    return _BlockPolicyResult(
        reached_latest=reached,
        stuck_total=sum(per_code.values()),
        per_code=dict(per_code),
    )


def _tally_behavior_blocks(
    *,
    samples: list[tuple[ProfileUpgradeCode, ...]],
    n_excluded: int,
    latest: str,
) -> _BehaviorBlockResult:
    """Tally behaviour blocks over per-tool applicable-unfixable code samples.

    Pure (no IO), so it is unit-tested with synthetic ``ProfileUpgradeCode``
    samples. Reports both severity policies side by side.
    """
    return _BehaviorBlockResult(
        n_considered=len(samples),
        n_excluded=n_excluded,
        latest=latest,
        must_fix=_tally_one_policy(samples=samples, levels=_MUST_FIX_ONLY),
        must_fix_and_consider=_tally_one_policy(
            samples=samples, levels=_MUST_FIX_AND_CONSIDER
        ),
    )


def _behavior_code_autofixed(
    root: etree._Element, *, codemod_cls: type[CodemodCommand], code: str
) -> bool:
    """Whether *codemod_cls* clears *code*'s detector when applied to a copy of *root*.

    Applies the mapped codemod to a deep copy (so the caller's tree is untouched)
    and re-runs the detectors on the raw result (``detect_codes_on_root`` — this
    is a raw-tree diagnostic, matching the codemods, which operate on the raw
    tree); the code is auto-fixable for this tool iff its detector no longer fires.
    This captures partial coverage exactly (e.g. GTR015 only fixes a
    sole-top-level-data-input tool).
    """
    from galaxy_tool_xml.document import ToolDocument
    from galaxy_tool_xml_codemod.module import Module
    from galaxy_tool_xml_codemod.profile_semantics import detect_codes_on_root

    copied = copy.deepcopy(root)
    document = ToolDocument(etree.ElementTree(copied))
    codemod_cls().apply(Module(document))
    return code not in detect_codes_on_root(document.root)


def _measure_upgrade_behavior_blocks(*, corpus_root: Path) -> _BehaviorBlockResult:
    """Walk the corpus and tally where a behavior-preserving upgrade would stall."""
    from galaxy_tool_xml.profiles import GALAXY_DEFAULT_PROFILE, latest_profile
    from galaxy_tool_xml_codemod.codemods.fix_from_work_dir_whitespace import (
        FixFromWorkDirWhitespace,
    )
    from galaxy_tool_xml_codemod.codemods.fix_interpreter import FixInterpreter
    from galaxy_tool_xml_codemod.codemods.fix_output_format_input import (
        FixOutputFormatInput,
    )
    from galaxy_tool_xml_codemod.profile_semantics import (
        detect_codes_on_root,
        upgrade_codes_crossed,
    )

    autofix: dict[str, type[CodemodCommand]] = {
        "16_04_fix_interpreter": FixInterpreter,
        "16_04_fix_output_format": FixOutputFormatInput,
        "21_09_fix_from_work_dir_whitespace": FixFromWorkDirWhitespace,
    }
    latest = latest_profile()
    samples: list[tuple[ProfileUpgradeCode, ...]] = []
    n_excluded = 0
    seen_sha: set[str] = set()
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        sha = _sha256_of(path)
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        root = _parse_tool_root(path)
        if root is None:
            continue
        declared = root.get("profile")
        baseline = declared if declared is not None else GALAXY_DEFAULT_PROFILE
        if _version_tuple(baseline) is None:
            n_excluded += 1  # macro token / unparseable — can't range the bump
            continue
        # Raw-tree applicability (this is a raw-tree diagnostic; the auto-fix check
        # below also runs raw, matching the codemods). The live `upgrade` warning
        # detects post-expansion — see `macro-expansion-detection-gap` for the gap.
        tripped = detect_codes_on_root(root)
        applicable = [
            change
            for change in upgrade_codes_crossed(
                from_profile=baseline, to_profile=latest
            )
            if change.code in tripped
        ]
        blocking = tuple(
            change
            for change in applicable
            if not (
                change.code in autofix
                and _behavior_code_autofixed(
                    root, codemod_cls=autofix[change.code], code=change.code
                )
            )
        )
        samples.append(blocking)
    return _tally_behavior_blocks(samples=samples, n_excluded=n_excluded, latest=latest)


def _behavior_block_rows(policy: _BlockPolicyResult) -> list[tuple[str, str, str, int]]:
    """``(profile, level, code, tools-stuck)`` rows in catalogue (profile) order."""
    from galaxy_tool_xml_codemod.profile_semantics import PROFILE_UPGRADE_CODES

    rows: list[tuple[str, str, str, int]] = []
    for change in PROFILE_UPGRADE_CODES:
        stuck = policy.per_code.get(change.code, 0)
        if stuck:
            rows.append((change.profile, change.level, change.code, stuck))
    return rows


def _render_behavior_block_section(
    title: str, *, policy: _BlockPolicyResult
) -> list[str]:
    """Markdown lines for one severity policy's stuck distribution."""
    rows = _behavior_block_rows(policy)
    lines = [
        f"## {title}",
        "",
        f"Reaches latest behavior-preservingly: **{policy.reached_latest:,}**; "
        f"stuck: **{policy.stuck_total:,}**.",
        "",
        "| Profile | Level | Behavior code (first blocker) | Tools stuck |",
        "|---|---|---|--:|",
    ]
    lines.extend(
        f"| {profile} | {level} | `{code}` | {stuck:,} |"
        for profile, level, code, stuck in rows
    )
    if not rows:
        lines.append("| — | — | (none) | 0 |")
    return lines


def _render_behavior_block_page(result: _BehaviorBlockResult) -> str:
    """Render the upgrade-behavior-blocks stats markdown page (deterministic)."""
    lines: list[str] = [
        "# Upgrade behavior-block statistics",
        "",
        "A hypothetical **behavior-preserving** auto-upgrade: walk each tool's",
        "profile from its declared (no-profile defaulted to Galaxy's `16.01`)",
        "baseline toward the latest, but **stop at the first Galaxy profile-behaviour",
        "change that both applies to the tool and the toolchain cannot auto-fix**.",
        "This is stricter than `galaxy-tool-refactor upgrade`, which bumps `profile=`",
        "to the newest structurally-valid version and only *warns* about crossed",
        "behaviour changes (codemod `docs/decisions.md` §22). A code *applies* when",
        "its per-tool detector fires (`upgrade_codes_applicable`); auto-fixability is",
        "judged exactly by applying the mapped codemod and re-detecting.",
        "",
        "Only two behaviour codes are auto-fixable: `21_09_fix_from_work_dir_whitespace`",
        "(GTR014, full) and `16_04_fix_output_format` (GTR015, only a sole-top-level",
        "data-input tool). The structural `upgrade_vN` codemods fix *validity*, not",
        "behaviour, so they never clear a blocker here.",
        "",
        "Two policies are reported: blocking on `must_fix` codes only (the sharper,",
        "more actionable view) and on `must_fix` + `consider` (every behaviour change).",
        "The latter is dominated by `16_04_consider_implicit_extra_file_collection`,",
        "which Galaxy emits **unconditionally** — so essentially every sub-16.04 tool",
        "stalls at 16.04 immediately.",
        "",
        "`24_2_fix_test_case_validation` counts are an **upper bound** (ships `<test>`;",
        "not validated): its detector fires on tools that merely *ship* a `<test>` —",
        "we don't vendor Galaxy's parameter-model validator — not on tools whose tests",
        "actually fail, so the true blocker count is a smaller subset (see",
        "`upgrade_research/24_2_fix_test_case_validation.md`).",
        "",
        "Regenerate with (needs the corpus, so not run in CI):",
        "",
        "```sh",
        "uv run python -m scripts.measure upgrade-behavior-blocks",
        "```",
        "",
        f"Unique `<tool>` files (sha256-deduped) with a placeable baseline: "
        f"**{result.n_considered:,}**. Excluded (macro-token / unparseable "
        f"`profile=`): **{result.n_excluded:,}**. Latest vendored profile: "
        f"`{result.latest}`. `Reaches latest` includes tools already at/above every "
        "applicable code.",
        "",
        *_render_behavior_block_section(
            "Blocking on `must_fix` only", policy=result.must_fix
        ),
        "",
        *_render_behavior_block_section(
            "Blocking on `must_fix` + `consider`", policy=result.must_fix_and_consider
        ),
    ]
    return "\n".join(lines)


def _report_behavior_block_policy(label: str, *, policy: _BlockPolicyResult) -> None:
    print(
        f"\n  [{label}]  reaches latest: {policy.reached_latest}; "
        f"stuck: {policy.stuck_total}"
    )
    for profile, level, code, stuck in _behavior_block_rows(policy):
        print(f"    {profile:6} {level:8} {stuck:6d}  {code}")


def _report_upgrade_behavior_blocks(result: _BehaviorBlockResult) -> None:
    print("\n=== upgrade-behavior-blocks ===")
    print(
        f"Considered (placeable baseline): {result.n_considered}; "
        f"excluded (macro/unparseable): {result.n_excluded}; latest = {result.latest}"
    )
    _report_behavior_block_policy("must_fix only", policy=result.must_fix)
    _report_behavior_block_policy(
        "must_fix + consider", policy=result.must_fix_and_consider
    )


def _run_upgrade_behavior_blocks(args: argparse.Namespace) -> None:
    result = _measure_upgrade_behavior_blocks(corpus_root=args.corpus_root)
    _report_upgrade_behavior_blocks(result)
    if not args.all:
        out_path = _repo_root() / "docs" / "upgrade_behavior_block_stats.md"
        out_path.write_text(_render_behavior_block_page(result) + "\n", encoding="utf-8")
        print(f"\nwrote {_display_path(out_path)}")


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


# --- measurement: cheetah-command-complexity ------------------------------------
#
# Sizes how complex the Cheetah-templated sections of corpus tools are, to ground
# the feasibility of statically locating/rewriting Cheetah variables
# (docs/upgrade_research/cheetah_variable_rewriting.md). Galaxy Cheetah-processes
# `<command>`, inline `<configfile>` (XML default engine = cheetah), env-var and
# output-label templates (.local/galaxy-src lib/galaxy/tools/evaluation.py:767,952
# and tools/actions/__init__.py:1091). We survey the two big ones — `<command>` and
# inline `<configfile>` — counting Cheetah directives, variable-reference shapes,
# and the hazards that defeat naive rewriting (scope-introducing #set/#for/#def,
# `##` comments, escaped `\$`, macro `@TOKEN@`/`<expand>` interplay). This is a
# regex HEURISTIC, not a Cheetah parse (the whole point of the research doc is that
# a real parse is hard); counts are an honest lower/upper bound, labelled as such.
# Writes docs/cheetah_command_stats.md. Needs the corpus, so not run in CI.

# Cheetah directive keywords we scan for (lowercase; matched as `#name` + boundary).
_CHEETAH_DIRECTIVE_NAMES: tuple[str, ...] = (
    "if", "for", "set", "def", "import", "echo", "while", "try", "raw", "slurp",
)
_CHEETAH_DIRECTIVE_RES: dict[str, re.Pattern[str]] = {
    name: re.compile(r"#" + name + r"\b") for name in _CHEETAH_DIRECTIVE_NAMES
}
# (flag, pattern) for variable-reference shapes + rewrite hazards.
_CHEETAH_SHAPE_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("shape:braced", re.compile(r"\$\{")),
    ("shape:dotted", re.compile(r"\$\{?[A-Za-z_]\w*\.[A-Za-z_]")),
    ("shape:indexed", re.compile(r"\$\{?[A-Za-z_][\w.]*\[")),
    ("shape:call", re.compile(r"\$\{?[A-Za-z_][\w.]*\(")),
    ("shape:special", re.compile(r"\$\{?__\w+__")),
    ("shape:env", re.compile(r"\$\{?[A-Z][A-Z0-9_]{2,}\b")),
    ("hazard:comment", re.compile(r"##")),
    ("hazard:escaped", re.compile(r"\\\$")),
    ("macro:token", re.compile(r"@[A-Z0-9_]{2,}@")),
)
# Display order + labels for the rendered tables (flag -> (group, label)).
_CHEETAH_FEATURE_DISPLAY: tuple[tuple[str, str, str], ...] = (
    *((f"directive:{name}", "Directives", f"#{name}") for name in _CHEETAH_DIRECTIVE_NAMES),
    ("shape:braced", "Variable shapes", "${...} braced"),
    ("shape:dotted", "Variable shapes", "$x.y dotted attribute"),
    ("shape:indexed", "Variable shapes", "$x[...] indexing"),
    ("shape:call", "Variable shapes", "$x(...) call"),
    ("shape:special", "Variable shapes", "$__x__ Galaxy special"),
    ("shape:env", "Variable shapes", "$UPPER env-style"),
    ("hazard:comment", "Rewrite hazards", "## Cheetah comment"),
    ("hazard:escaped", "Rewrite hazards", "\\$ escaped dollar"),
    ("macro:token", "Macro interplay", "@TOKEN@ macro token"),
)


def _cheetah_feature_flags(text: str, /) -> frozenset[str]:
    """Heuristically detect Cheetah directives/shapes/hazards present in *text*.

    Pure and regex-based (no Cheetah parse), so it is unit-tested with synthetic
    snippets. Returns the set of feature flags (keys of ``_CHEETAH_FEATURE_DISPLAY``)
    whose pattern matches anywhere in *text*.
    """
    flags: set[str] = set()
    for name, pattern in _CHEETAH_DIRECTIVE_RES.items():
        if pattern.search(text):
            flags.add(f"directive:{name}")
    for flag, pattern in _CHEETAH_SHAPE_RES:
        if pattern.search(text):
            flags.add(flag)
    return frozenset(flags)


@dataclass
class _CheetahComplexityResult:
    """Heuristic Cheetah-complexity survey over command + inline configfile text."""

    n_tools: int  # unique parsed tools
    n_with_command: int
    n_command_trivial: int  # has <command>, no Cheetah directive in it
    n_command_with_directive: int
    n_with_configfile: int  # has >=1 inline <configfile> with text
    n_with_expand: int  # has >=1 <expand> (macro inclusion)
    n_with_cheetah_text: int  # has command and/or inline configfile text
    feature_counts: dict[str, int]  # flag -> tools whose Cheetah text exhibits it


def _measure_cheetah_command_complexity(
    *, corpus_root: Path
) -> _CheetahComplexityResult:
    """Survey Cheetah complexity of command + inline configfile across the corpus."""
    seen: set[str] = set()
    n_tools = n_with_command = n_trivial = n_directive = 0
    n_configfile = n_expand = n_cheetah = 0
    feature_counts: Counter[str] = Counter()
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
        command_text = "".join(command.itertext()) if command is not None else None
        cf_texts = [
            text
            for cf in root.iter("configfile")
            if (text := "".join(cf.itertext()).strip())
        ]
        if command_text is not None:
            n_with_command += 1
            if any(p.search(command_text) for p in _CHEETAH_DIRECTIVE_RES.values()):
                n_directive += 1
            else:
                n_trivial += 1
        if cf_texts:
            n_configfile += 1
        if root.find(".//expand") is not None:
            n_expand += 1
        cheetah_text = "\n".join(t for t in (command_text, *cf_texts) if t)
        if cheetah_text.strip():
            n_cheetah += 1
            for flag in _cheetah_feature_flags(cheetah_text):
                feature_counts[flag] += 1
    return _CheetahComplexityResult(
        n_tools=n_tools,
        n_with_command=n_with_command,
        n_command_trivial=n_trivial,
        n_command_with_directive=n_directive,
        n_with_configfile=n_configfile,
        n_with_expand=n_expand,
        n_with_cheetah_text=n_cheetah,
        feature_counts=dict(feature_counts),
    )


def _render_cheetah_complexity_page(result: _CheetahComplexityResult) -> str:
    """Render the cheetah-command-complexity stats markdown page (deterministic)."""
    base = result.n_with_cheetah_text

    def pct(n: int, of: int) -> str:
        return f"{100 * n / of:.1f}%" if of else "0.0%"

    lines: list[str] = [
        "# Cheetah command/configfile complexity statistics",
        "",
        "A **heuristic** (regex, not a Cheetah parse) survey of how complex the",
        "Cheetah-templated sections of corpus tools are — backing",
        "`upgrade_research/cheetah_variable_rewriting.md`, which assesses whether",
        "variables in those sections can be located/rewritten mechanically.",
        "",
        "Galaxy Cheetah-processes `<command>`, inline `<configfile>` (XML tools'",
        "default engine), env-var templates, and output `label`s "
        "(`lib/galaxy/tools/evaluation.py:767,952`, `tools/actions/__init__.py:1091`).",
        "This survey covers the two large ones: `<command>` and inline `<configfile>`.",
        "Because it is a regex heuristic (not a Cheetah parse), counts are noisy in",
        "**both** directions: a construct can hide from the pattern (under-count), and",
        "a `#`-keyword or `$x` sitting inside a `##` comment or a `#raw`…`#end raw`",
        "block still matches even though Cheetah would not treat it as live",
        "(over-count). The directive over-count is negligible in practice (only a",
        "handful of commands match a directive *solely* inside a comment/raw block),",
        "so the trivial-vs-directive headline is, if anything, conservative for the",
        "trivial (easy) subset.",
        "",
        "Regenerate with (needs the corpus, so not run in CI):",
        "",
        "```sh",
        "uv run python -m scripts.measure cheetah-command-complexity",
        "```",
        "",
        "## Overview",
        "",
        "| Measure | Tools | Share |",
        "|---|--:|--:|",
        f"| Unique `<tool>` files (sha256-deduped) | {result.n_tools:,} | — |",
        f"| Have a `<command>` | {result.n_with_command:,} "
        f"| {pct(result.n_with_command, result.n_tools)} |",
        f"| `<command>` is **trivial** (no Cheetah directive) | {result.n_command_trivial:,} "
        f"| {pct(result.n_command_trivial, result.n_with_command)} of commands |",
        f"| `<command>` has a Cheetah directive | {result.n_command_with_directive:,} "
        f"| {pct(result.n_command_with_directive, result.n_with_command)} of commands |",
        f"| Have an inline `<configfile>` (also Cheetah) | {result.n_with_configfile:,} "
        f"| {pct(result.n_with_configfile, result.n_tools)} |",
        f"| Have an `<expand>` (macro inclusion) | {result.n_with_expand:,} "
        f"| {pct(result.n_with_expand, result.n_tools)} |",
        f"| Have any Cheetah text (command + inline configfile) | {result.n_with_cheetah_text:,} "
        f"| {pct(result.n_with_cheetah_text, result.n_tools)} |",
        "",
        f"Feature counts below are over the **{base:,}** tools with Cheetah text "
        "(command and/or inline configfile).",
    ]
    last_group = ""
    for flag, group, label in _CHEETAH_FEATURE_DISPLAY:
        if group != last_group:
            lines += ["", f"## {group}", "", "| Construct | Tools | Share |", "|---|--:|--:|"]
            last_group = group
        count = result.feature_counts.get(flag, 0)
        lines.append(f"| {label} | {count:,} | {pct(count, base)} |")
    lines += [
        "",
        "The `#set` / `#for` / `#def` rows are the scope-introducing hazards: each",
        "binds Cheetah-local names that can shadow tool parameters, so a parameter",
        "rename cannot be a blind textual substitution. See the research doc for what",
        "this implies for feasibility.",
        "",
        "The `##` (Cheetah comment) row is an **upper bound** on Cheetah comments: the",
        "regex `##` also matches POSIX shell parameter expansion `${var##*/}` (a common",
        "basename idiom in `ln -s` setups), so an unknown fraction of these tools carry",
        "shell `##`, not a Cheetah comment — do not read its share as Cheetah-comment",
        "prevalence. The direction is conservative (it makes the hazard-free subset look",
        "smaller), so it does not threaten the feasibility conclusion.",
    ]
    return "\n".join(lines)


def _report_cheetah_command_complexity(result: _CheetahComplexityResult) -> None:
    print("\n=== cheetah-command-complexity (heuristic) ===")
    print(
        f"Unique tools: {result.n_tools}; with <command>: {result.n_with_command} "
        f"(trivial {result.n_command_trivial}, with-directive "
        f"{result.n_command_with_directive}); inline <configfile>: "
        f"{result.n_with_configfile}; <expand>: {result.n_with_expand}"
    )
    print(f"Tools with Cheetah text: {result.n_with_cheetah_text}")
    for flag, _group, label in _CHEETAH_FEATURE_DISPLAY:
        count = result.feature_counts.get(flag, 0)
        if count:
            print(f"  {count:6d}  {label}")


def _run_cheetah_command_complexity(args: argparse.Namespace) -> None:
    result = _measure_cheetah_command_complexity(corpus_root=args.corpus_root)
    _report_cheetah_command_complexity(result)
    if not args.all:
        out_path = _repo_root() / "docs" / "cheetah_command_stats.md"
        out_path.write_text(
            _render_cheetah_complexity_page(result) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {_display_path(out_path)}")


# --- measurement: cheetah-cdm-coverage ------------------------------------------
#
# Parity + sizing for the SHIPPED faithful Cheetah lexer (galaxy_tool_xml.cheetah_cdm,
# the M5.1 CDM lexer): run cheetah_spans() over every pure-text <command> body and
# report the parse-clean rate (vs the ~0.4% that bail to the regex fallback) plus the
# rename scope-shadowing population (tools whose directive spans include a
# #set/#for/#def local binding). Reproduces the read-only Phase-0 spike with shipped
# code, grounding the numbers in docs/upgrade_research/cheetah_section_editing.md.
# Needs the corpus (CT3 is a base dep), so it is print-only and not run in
# CI; the pure aggregation is pinned by a synthetic-fixture unit test.


@dataclass
class _CheetahCdmCoverageResult:
    """Coverage of the faithful CDM lexer over corpus <command> bodies."""

    cdm_available: bool
    n_bodies: int  # pure-text <command> bodies carrying a $ or #
    n_clean: int  # cheetah_spans returned spans
    n_bail: int  # cheetah_spans returned None (CT3 could not compile)
    n_with_directive: int  # clean body with >=1 #directive span
    n_with_locals: int  # clean body with a #set/#for/#def span (rename hazard)
    n_placeholders: int  # total placeholder spans across clean bodies


# Directive keywords that introduce a local binding shadowing a param under rename.
_CDM_LOCAL_DIRECTIVES = frozenset({"set", "for", "def"})


def _measure_cheetah_cdm_coverage(*, corpus_root: Path) -> _CheetahCdmCoverageResult:
    """Run the shipped CDM lexer over the corpus; size parse-clean + scope hazards."""
    from galaxy_tool_xml.cheetah_cdm import (
        SpanKind,
        cheetah_cdm_available,
        cheetah_spans,
    )

    seen: set[str] = set()
    n_bodies = n_clean = n_bail = n_directive = n_locals = n_placeholders = 0
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
        command = root.find("command")
        if command is None or len(command) > 0:  # pure-text bodies only (no children)
            continue
        body = command.text or ""
        if not body.strip() or ("$" not in body and "#" not in body):
            continue
        n_bodies += 1
        spans = cheetah_spans(body)
        if spans is None:
            n_bail += 1
            continue
        n_clean += 1
        directives = [s.directive for s in spans if s.kind is SpanKind.DIRECTIVE]
        if directives:
            n_directive += 1
        if any(name in _CDM_LOCAL_DIRECTIVES for name in directives):
            n_locals += 1
        n_placeholders += sum(1 for s in spans if s.kind is SpanKind.PLACEHOLDER)
    return _CheetahCdmCoverageResult(
        cdm_available=cheetah_cdm_available(),
        n_bodies=n_bodies,
        n_clean=n_clean,
        n_bail=n_bail,
        n_with_directive=n_directive,
        n_with_locals=n_locals,
        n_placeholders=n_placeholders,
    )


def _report_cheetah_cdm_coverage(result: _CheetahCdmCoverageResult) -> None:
    print("\n=== cheetah-cdm-coverage (faithful CDM lexer parity + scope sizing) ===")
    if not result.cdm_available:
        print("  CT3 not importable — it is a base dependency; reinstall galaxy-tool-xml.")
        return

    def pct(n: int, of: int) -> str:
        return f"{100 * n / of:.1f}%" if of else "0.0%"

    print(f"Pure-text <command> bodies (with $ or #): {result.n_bodies}")
    print(f"  CT3 parse CLEAN: {result.n_clean} ({pct(result.n_clean, result.n_bodies)})")
    print(f"  CT3 parse BAIL:  {result.n_bail} ({pct(result.n_bail, result.n_bodies)})")
    print(f"  clean w/ directives:                 {result.n_with_directive}")
    print(
        f"  clean w/ #set/#for/#def (rename scope hazard): {result.n_with_locals} "
        f"({pct(result.n_with_locals, result.n_clean)} of clean)"
    )
    print(f"  total placeholders harvested:        {result.n_placeholders}")


def _run_cheetah_cdm_coverage(args: argparse.Namespace) -> None:
    result = _measure_cheetah_cdm_coverage(corpus_root=args.corpus_root)
    _report_cheetah_cdm_coverage(result)


# --- measurement: cheetah-cdm-bails ---------------------------------------------
#
# Save the ~0.4% of pure-text <command> bodies CT3 cannot compile (cheetah_spans ->
# None) as a retained corpus for later work. These are exactly the bodies where
# command_text / cheetah_refs fall back to the regex (galaxy-tool-xml/docs/decisions.md
# §19); capturing them gives real test fixtures without needing the full corpus when we
# later improve CT3-bail handling. Writes docs/corpus_data/cheetah_cdm_bail_cases.json.
# Needs the corpus, not run in CI; the tally is pinned by a synthetic-fixture unit test.


@dataclass
class _CdmBailCase:
    source: str  # corpus-relative path to the tool XML
    tool_id: str
    body: str  # the pure-text <command> body CT3 could not compile


def _measure_cheetah_cdm_bails(*, corpus_root: Path) -> list[_CdmBailCase]:
    """Collect every pure-text <command> body where ``cheetah_spans`` bails to ``None``."""
    from galaxy_tool_xml.cheetah_cdm import cheetah_spans

    seen: set[str] = set()
    cases: list[_CdmBailCase] = []
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
        command = root.find("command")
        if command is None or len(command) > 0:  # pure-text bodies only (no children)
            continue
        body = command.text or ""
        if not body.strip() or ("$" not in body and "#" not in body):
            continue
        if cheetah_spans(body) is None:
            source = str(path.relative_to(corpus_root)) if path.is_relative_to(
                corpus_root
            ) else path.name
            cases.append(_CdmBailCase(source=source, tool_id=root.get("id", ""), body=body))
    cases.sort(key=lambda case: (case.source, case.tool_id))
    return cases


def _run_cheetah_cdm_bails(args: argparse.Namespace) -> None:
    cases = _measure_cheetah_cdm_bails(corpus_root=args.corpus_root)
    print("\n=== cheetah-cdm-bails (CT3 cannot-compile <command> bodies) ===")
    print(f"bail cases retained: {len(cases)}")
    for case in cases[:10]:
        print(f"  {case.source}  (id={case.tool_id!r})  {len(case.body)} chars")
    if not args.all:
        out_path = _repo_root() / "docs" / "corpus_data" / "cheetah_cdm_bail_cases.json"
        payload = [
            {"source": case.source, "tool_id": case.tool_id, "body": case.body}
            for case in cases
        ]
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {_display_path(out_path)} ({len(cases)} cases)")


# --- measurement: rename-coverage -----------------------------------------------
#
# Blast-radius / coverage sizing for the first Cheetah MUTATOR (M5.3): attempt to
# rename EVERY input definition (`<param>`/`<conditional>`/`<repeat>`/`<section>` name)
# of every corpus tool via the shipped tier-1 `cheetah_rename.rename_param`, and tally
# how the atomic rename resolves — clean rewrite vs each bail reason (shadowed / mixed-
# content / lexer-bail / filter-bare-ref / cross-ref-residual). Answers "how often does
# a comprehensive+atomic rename actually apply, and what blocks it." Also checks Tier-B
# parity: the offset-returning `rename_param_plan` must reach the same verdict as the tree
# mutator (same apply / same bail reason), except where the stricter offset path soundly
# bails (entity-content / locator-failed); genuine mismatches must be 0. Needs the corpus
# (CT3 is a base dep); print-only, not run in CI; the pure tally is pinned
# by a synthetic-fixture unit test. Backs galaxy-tool-xml/docs/decisions.md §20.

_RENAME_DEFINITION_TAGS = frozenset({"param", "conditional", "repeat", "section"})
# The bail reasons cheetah_rename.rename_param can return, in display order.
_RENAME_BAIL_REASONS = (
    "shadowed",
    "mixed-content",
    "lexer-bail",
    "filter-bare-ref",
    "cross-ref-residual",
    "not-found",
)


@dataclass
class _RenameCoverageResult:
    """Outcome distribution of renaming every input definition across the corpus."""

    cdm_available: bool
    n_tools: int  # tools with >=1 renameable input definition
    n_attempts: int  # (tool, name) rename attempts
    n_success: int  # rename applied (every live ref + definition rewritten)
    n_sites: int  # total reference/definition sites rewritten across successes
    bail_counts: dict[str, int]  # bail reason -> attempts
    n_tools_all_clean: int  # tools where every input definition renamed cleanly
    # Tier-B offset-path (`rename_param_plan`) parity vs the tree mutator.
    n_plan_agree: int  # offset path reached the SAME verdict (apply, or same bail reason)
    n_plan_stricter: int  # tree applied but offset path soundly bailed (entity / locator)
    n_plan_mismatch: int  # genuine divergence (MUST be 0 — the two share one planner)
    plan_stricter_counts: dict[str, int]  # the offset-only bail reason -> attempts


def _measure_rename_coverage(*, corpus_root: Path) -> _RenameCoverageResult:
    """Rename every input definition of every tool; tally success vs each bail reason."""
    import copy

    from galaxy_tool_xml.cheetah_cdm import cheetah_cdm_available
    from galaxy_tool_xml.cheetah_rename import rename_param, rename_param_plan

    # Offset-only bails the stricter Tier-B path may add when the tree mutator applied.
    plan_only_bails = frozenset(
        {"entity-content", "locator-failed", "parse-error", "encoding"}
    )
    seen: set[str] = set()
    n_tools = n_attempts = n_success = n_sites = n_all_clean = 0
    n_plan_agree = n_plan_stricter = n_plan_mismatch = 0
    bail_counts: Counter[str] = Counter()
    plan_stricter_counts: Counter[str] = Counter()
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
        inputs = root.find("inputs")
        if inputs is None:
            continue
        names: list[str] = []
        for element in inputs.iter():
            name = element.get("name") if element.tag in _RENAME_DEFINITION_TAGS else None
            if name and name.isidentifier() and name not in names:
                names.append(name)
        if not names:
            continue
        source = path.read_bytes()
        n_tools += 1
        all_clean = True
        for name in names:
            new = f"{name}_gtr0"
            outcome = rename_param(copy.deepcopy(root), old=name, new=new)
            plan = rename_param_plan(source, old=name, new=new)
            n_attempts += 1
            if outcome.bailed:
                bail_counts[outcome.reason or "unknown"] += 1
                all_clean = False
            else:
                n_success += 1
                n_sites += outcome.renamed
            # Parity classification. A plan bail with a plan-only reason is always a
            # sound decline (the offset path refuses rather than mis-edit), whether or not
            # the tree mutator applied. Otherwise the two must agree exactly: both apply,
            # or both bail the same shared reason. Anything else is a real divergence —
            # the shared planner makes that a bug, so it must be 0.
            if plan.reason in plan_only_bails:
                n_plan_stricter += 1
                plan_stricter_counts[plan.reason or "unknown"] += 1
            elif plan.bailed == outcome.bailed and plan.reason == outcome.reason:
                n_plan_agree += 1
            else:
                n_plan_mismatch += 1
        if all_clean:
            n_all_clean += 1
    return _RenameCoverageResult(
        cdm_available=cheetah_cdm_available(),
        n_tools=n_tools,
        n_attempts=n_attempts,
        n_success=n_success,
        n_sites=n_sites,
        bail_counts=dict(bail_counts),
        n_tools_all_clean=n_all_clean,
        n_plan_agree=n_plan_agree,
        n_plan_stricter=n_plan_stricter,
        n_plan_mismatch=n_plan_mismatch,
        plan_stricter_counts=dict(plan_stricter_counts),
    )


def _report_rename_coverage(result: _RenameCoverageResult) -> None:
    print("\n=== rename-coverage (first Cheetah mutator: outcome distribution) ===")
    if not result.cdm_available:
        print("  CT3 not importable — it is a base dependency; reinstall galaxy-tool-xml.")
        return

    def pct(n: int, of: int) -> str:
        return f"{100 * n / of:.1f}%" if of else "0.0%"

    print(f"Tools with renameable input definitions: {result.n_tools}")
    print(f"Rename attempts (one per definition):    {result.n_attempts}")
    print(
        f"  applied:  {result.n_success} "
        f"({pct(result.n_success, result.n_attempts)})  "
        f"— {result.n_sites} sites rewritten"
    )
    bailed = result.n_attempts - result.n_success
    print(f"  bailed:   {bailed} ({pct(bailed, result.n_attempts)})")
    for reason in _RENAME_BAIL_REASONS:
        count = result.bail_counts.get(reason, 0)
        if count:
            print(f"      {reason:18} {count:6d} ({pct(count, result.n_attempts)})")
    print(
        f"Tools where EVERY definition renames cleanly: {result.n_tools_all_clean} "
        f"({pct(result.n_tools_all_clean, result.n_tools)})"
    )
    print("Tier-B offset path (rename_param_plan) parity vs the tree mutator:")
    print(
        f"  same verdict:   {result.n_plan_agree} "
        f"({pct(result.n_plan_agree, result.n_attempts)})"
    )
    print(
        f"  offset stricter:{result.n_plan_stricter} "
        f"({pct(result.n_plan_stricter, result.n_attempts)})  "
        "— tree applied, offsets soundly bailed"
    )
    for reason, count in sorted(result.plan_stricter_counts.items()):
        print(f"      {reason:18} {count:6d} ({pct(count, result.n_attempts)})")
    print(f"  MISMATCH:       {result.n_plan_mismatch}  (must be 0)")


def _run_rename_coverage(args: argparse.Namespace) -> None:
    result = _measure_rename_coverage(corpus_root=args.corpus_root)
    _report_rename_coverage(result)


# --- measurement: rename-macro-spread -------------------------------------------
#
# Sizes the cross-file rename feature (tool bundle + sole-owned gate). For every
# input definition of every tool, rename it across the tool AND its imported macro
# files and classify the outcome: tool-only (no macro touched), spills-to-macro
# (>=1 macro rewritten — split sole-owned vs shared by the transitive importer map),
# or bailed (by reason). The headline ``silent-break-today`` count is the bug the
# feature fixes: renames the *old* single-file path reported as success while leaving
# a ``$old`` reference dangling in an imported macro. Reuses the SHIPPED
# build_importer_map / rename_param_in_bundle so the measure can't drift from the
# code. Writes docs/rename_macro_spread_stats.md. Needs the corpus (CT3 is a base dep);
# not run in CI. Backs galaxy-tool-xml/docs/decisions.md §21.


@dataclass
class _RenameMacroSpreadResult:
    """How often a param rename reaches into an imported macro, and the gate split."""

    cdm_available: bool
    n_tools: int  # tools with >=1 renameable input definition
    n_attempts: int  # (tool, name) rename attempts across the bundle
    n_tool_only: int  # applied, no macro file touched
    n_spills_sole: int  # applied, every touched macro is sole-owned (v1 applies)
    n_spills_shared: int  # applied, >=1 touched macro is shared (v1 skips)
    n_silent_break_today: int  # spills where the old single-file rename "succeeded"
    bail_counts: dict[str, int]  # bundle bail reason -> attempts


def _measure_rename_macro_spread(*, corpus_root: Path) -> _RenameMacroSpreadResult:
    """Rename every input definition across its bundle; classify the spread + gate."""
    import copy

    from galaxy_tool_xml.binding import ToolXmlSyntaxError
    from galaxy_tool_xml.bundle import load_bundle, rename_param_in_bundle
    from galaxy_tool_xml.cheetah_cdm import cheetah_cdm_available

    from galaxy_tool_refactor_registry.bundle_rename import build_importer_map

    importers = build_importer_map(corpus_root)
    seen: set[str] = set()
    n_tools = n_attempts = n_tool_only = 0
    n_spills_sole = n_spills_shared = n_silent_break = 0
    bail_counts: Counter[str] = Counter()
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        digest = _sha256_of(path)
        if digest in seen:
            continue
        seen.add(digest)
        root = _parse_tool_root(path)
        if root is None or root.tag != "tool":
            continue
        inputs = root.find("inputs")
        if inputs is None:
            continue
        names: list[str] = []
        for element in inputs.iter():
            name = element.get("name") if element.tag in _RENAME_DEFINITION_TAGS else None
            if name and name.isidentifier() and name not in names:
                names.append(name)
        if not names:
            continue
        try:
            bundle = load_bundle(path)
        except ToolXmlSyntaxError:
            continue
        tool_resolved = path.resolve()
        n_tools += 1
        for name in names:
            outcome = rename_param_in_bundle(
                copy.deepcopy(bundle), old=name, new=f"{name}_gtr0"
            )
            n_attempts += 1
            if outcome.bailed:
                bail_counts[outcome.reason or "unknown"] += 1
                continue
            if not outcome.edited_macros:
                n_tool_only += 1
                continue
            any_shared = any(
                importers.get(macro, frozenset({tool_resolved})) - {tool_resolved}
                for macro in outcome.edited_macros
            )
            if any_shared:
                n_spills_shared += 1
            else:
                n_spills_sole += 1
            tool_member = outcome.members[0]
            if not tool_member.bailed and tool_member.renamed > 0:
                n_silent_break += 1
    return _RenameMacroSpreadResult(
        cdm_available=cheetah_cdm_available(),
        n_tools=n_tools,
        n_attempts=n_attempts,
        n_tool_only=n_tool_only,
        n_spills_sole=n_spills_sole,
        n_spills_shared=n_spills_shared,
        n_silent_break_today=n_silent_break,
        bail_counts=dict(bail_counts),
    )


def _render_rename_macro_spread_page(result: _RenameMacroSpreadResult) -> str:
    """Render docs/rename_macro_spread_stats.md from the measured result."""

    def pct(n: int, of: int) -> str:
        return f"{100 * n / of:.1f}%" if of else "0.0%"

    a = result.n_attempts
    spills = result.n_spills_sole + result.n_spills_shared
    lines = [
        "# Cross-file rename: macro spread + sole-owned gate",
        "",
        "Reproduced by `uv run python -m scripts.measure rename-macro-spread` "
        "(needs the corpus; CT3 is a base dependency).",
        "",
        f"- Tools with renameable input definitions: **{result.n_tools}**",
        f"- Rename attempts (one per definition): **{a}**",
        f"  - tool-only (no macro touched): **{result.n_tool_only}** "
        f"({pct(result.n_tool_only, a)})",
        f"  - spills into a macro: **{spills}** ({pct(spills, a)})",
        f"    - every touched macro **sole-owned** (v1 applies with `--repo-root`): "
        f"**{result.n_spills_sole}** ({pct(result.n_spills_sole, a)})",
        f"    - some touched macro **shared** (v1 skips + reports): "
        f"**{result.n_spills_shared}** ({pct(result.n_spills_shared, a)})",
        f"  - bailed: **{a - result.n_tool_only - spills}**",
        "",
        f"**Silent-break-today: {result.n_silent_break_today}** "
        f"({pct(result.n_silent_break_today, a)} of attempts) — renames the *old* "
        "single-file path reported as success while leaving a `$old` reference "
        "dangling in an imported macro. This is the correctness bug the bundle "
        "rename fixes.",
        "",
        "Bundle bail reasons:",
        "",
    ]
    lines.extend(
        f"- `{reason}`: {result.bail_counts.get(reason, 0)}"
        for reason in (*_RENAME_BAIL_REASONS, "unparseable-macro")
        if result.bail_counts.get(reason)
    )
    return "\n".join(lines)


def _report_rename_macro_spread(result: _RenameMacroSpreadResult) -> None:
    print("\n=== rename-macro-spread (cross-file rename: spread + gate) ===")
    if not result.cdm_available:
        print("  CT3 not importable — it is a base dependency; reinstall galaxy-tool-xml.")
        return
    print(_render_rename_macro_spread_page(result))


def _run_rename_macro_spread(args: argparse.Namespace) -> None:
    result = _measure_rename_macro_spread(corpus_root=args.corpus_root)
    _report_rename_macro_spread(result)
    if not args.all and result.cdm_available:
        out_path = _repo_root() / "docs" / "rename_macro_spread_stats.md"
        out_path.write_text(
            _render_rename_macro_spread_page(result) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {_display_path(out_path)}")



# --- measurement: xsd-tightenings -------------------------------------------------
#
# The systematic per-release tightening ladder behind the Upgrade_vN gap audit
# (docs/deferred_fix_opportunities.md): diff every adjacent pair of vendored XSDs
# and report only the deltas that can STRAND an existing tool — an attribute site
# moving from a builtin type to a restricted simpleType (`typed`), an attribute
# becoming `use="required"` (`required`), an existing simpleType's pattern set
# changing (`pattern-changed`), and enum members being REMOVED (`enums-removed`).
# Enum additions are widenings (more permissive) and are deliberately ignored.
# Schema-only — no corpus needed, so the fixture test runs in CI.

_XS = "{http://www.w3.org/2001/XMLSchema}"


@dataclass
class _XsdTighteningsResult:
    """Per-version-pair schema deltas that can strand an existing tool."""

    versions: list[str]
    # (from_version, to_version, kind, site, detail)
    rows: list[tuple[str, str, str, str, str]]


def _xsd_model(
    path: Path, /
) -> tuple[dict[str, tuple[tuple[str, ...], frozenset[str]]], dict[str, tuple[str | None, str | None]]]:
    """Reduce one XSD to comparable maps: simpleType facets + attribute sites."""
    root = etree.parse(str(path)).getroot()
    simple: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {}
    for st in root.findall(f"{_XS}simpleType"):
        name = st.get("name")
        if name is None:
            continue
        patterns = tuple(
            value
            for pat in st.iter(f"{_XS}pattern")
            if (value := pat.get("value")) is not None
        )
        enums = frozenset(
            value
            for enum in st.iter(f"{_XS}enumeration")
            if (value := enum.get("value")) is not None
        )
        simple[name] = (patterns, enums)
    sites: dict[str, tuple[str | None, str | None]] = {}
    for ct in root.findall(f"{_XS}complexType"):
        ct_name = ct.get("name")
        for attr in ct.iter(f"{_XS}attribute"):
            sites[f"{ct_name}.{attr.get('name')}"] = (attr.get("type"), attr.get("use"))
    return simple, sites


def _measure_xsd_tightenings(*, schema_dir: Path) -> _XsdTighteningsResult:
    """Diff adjacent vendored XSDs for tool-stranding deltas (see section comment)."""
    versions = sorted(
        (path.stem.removeprefix("galaxy-") for path in schema_dir.glob("galaxy-*.xsd")),
        key=Version,
    )
    rows: list[tuple[str, str, str, str, str]] = []
    previous: tuple[str, dict, dict] | None = None
    for version in versions:
        simple, sites = _xsd_model(schema_dir / f"galaxy-{version}.xsd")
        if previous is not None:
            prev_version, prev_simple, prev_sites = previous
            for name in sorted(set(simple) & set(prev_simple)):
                old_patterns, old_enums = prev_simple[name]
                new_patterns, new_enums = simple[name]
                if old_patterns != new_patterns:
                    rows.append(
                        (prev_version, version, "pattern-changed", name,
                         f"{old_patterns} -> {new_patterns}")
                    )
                removed = old_enums - new_enums
                if removed:
                    rows.append(
                        (prev_version, version, "enums-removed", name,
                         ",".join(sorted(removed)))
                    )
            for site in sorted(set(sites) & set(prev_sites)):
                old_type, old_use = prev_sites[site]
                new_type, new_use = sites[site]
                old_builtin = old_type is None or old_type.startswith("xs:")
                new_builtin = new_type is None or new_type.startswith("xs:")
                if old_builtin and not new_builtin:
                    rows.append(
                        (prev_version, version, "typed", site,
                         f"{old_type or 'xs:string'} -> {new_type}")
                    )
                if old_use != "required" and new_use == "required":
                    rows.append((prev_version, version, "required", site, ""))
        previous = (version, simple, sites)
    return _XsdTighteningsResult(versions=list(versions), rows=rows)


def _report_xsd_tightenings(measurement: _XsdTighteningsResult) -> None:
    print("\n=== xsd-tightenings ===")
    print(f"Vendored schema versions diffed: {len(measurement.versions)}")
    print(f"Tool-stranding deltas (typed / required / pattern-changed / enums-removed): {len(measurement.rows)}")
    for from_version, to_version, kind, site, detail in measurement.rows:
        suffix = f"  {detail}" if detail else ""
        print(f"  {from_version} -> {to_version}: {kind:16s} {site}{suffix}")


def _run_xsd_tightenings(args: argparse.Namespace) -> None:
    schema_resource = importlib.resources.files("galaxy_tool_xml") / "schema"
    with importlib.resources.as_file(schema_resource) as schema_dir:
        _report_xsd_tightenings(_measure_xsd_tightenings(schema_dir=schema_dir))


# --- measurement: interpreter-bucket-split --------------------------------------
#
# Sizes the auto-fixable population for a `16_04_fix_interpreter` codemod (GTR016;
# docs/upgrade_research/16_04_fix_interpreter.md). Tools with a deprecated
# `<command interpreter=…>` split into: A (bucket-A: any non-empty interpreter value
# + literal leading script token that exists beside the XML — exactly what the codemod
# rewrites; the legacy `interpreter + " " + command` composition is verbatim, so
# flag-bearing / non-script values rewrite too), A-missing (would-be-A but the named
# script isn't co-located), B (leading-Cheetah / non-literal first token), empty
# (`interpreter=""` — legacy gated on `if interpreter:`, so it was ignored; nothing to
# reproduce). Classification reuses the codemod's own eligibility predicate
# (`codemods/_interpreter.py`) so the measure and the codemod agree by construction.
# Writes docs/interpreter_bucket_stats.md. Needs the corpus, so not run in CI.


@dataclass
class _InterpreterBucketResult:
    """`<command interpreter=…>` tools split by codemod auto-fixability."""

    n_tools: int  # unique parsed tools
    n_with_interpreter: int
    bucket_a: int  # auto-fixable now (literal script, exists beside the XML)
    bucket_a_missing: int  # structurally A, but the named script is not co-located
    bucket_b: int  # leading Cheetah / non-literal first token
    bucket_empty: int  # interpreter="" — legacy-ignored, nothing to reproduce
    interpreter_values: dict[str, int]  # interpreter attribute value -> tools


def _measure_interpreter_buckets(*, corpus_root: Path) -> _InterpreterBucketResult:
    """Classify every `<command interpreter=…>` tool by codemod auto-fixability."""
    from galaxy_tool_xml_codemod.codemods._interpreter import (
        interpreter_rewrite_target,
    )

    seen: set[str] = set()
    n_tools = n_with = a = a_missing = b = empty = 0
    values: Counter[str] = Counter()
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
        interpreter = command.get("interpreter")
        if interpreter is None:
            continue
        n_with += 1
        values[interpreter] += 1
        if not interpreter:
            empty += 1  # legacy `if interpreter:` ignored it — the codemod skips too
            continue
        # Non-empty interpreter: A vs A-missing vs B turns on the body + co-location.
        structural = interpreter_rewrite_target(root)
        if structural is None:
            b += 1
        elif interpreter_rewrite_target(root, tool_dir=path.parent) is not None:
            a += 1
        else:
            a_missing += 1
    return _InterpreterBucketResult(
        n_tools=n_tools,
        n_with_interpreter=n_with,
        bucket_a=a,
        bucket_a_missing=a_missing,
        bucket_b=b,
        bucket_empty=empty,
        interpreter_values=dict(values),
    )


def _render_interpreter_bucket_page(result: _InterpreterBucketResult) -> str:
    """Render the interpreter-bucket-split stats markdown page (deterministic)."""
    base = result.n_with_interpreter

    def pct(n: int) -> str:
        return f"{100 * n / base:.1f}%" if base else "0.0%"

    bar_max = max(result.interpreter_values.values(), default=0)
    value_rows = [
        f"| `{value}` | {count:,} | {'█' * round(30 * count / bar_max) if bar_max else ''} |"
        for value, count in sorted(
            result.interpreter_values.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]
    return "\n".join(
        [
            "# Interpreter-rewrite bucket statistics",
            "",
            "Sizes the auto-fixable population for a `16_04_fix_interpreter` codemod",
            "(GTR016; see `upgrade_research/16_04_fix_interpreter.md`). Tools carrying a",
            "deprecated `<command interpreter=…>` are split by whether the codemod can",
            "mechanically rewrite them to `interpreter '$__tool_directory__/script'`.",
            "Buckets are computed by the codemod's own eligibility predicate",
            "(`galaxy_tool_xml_codemod.codemods._interpreter`), so the A + A-missing",
            "total is exactly what the codemod rewrites.",
            "",
            "Regenerate with (needs the corpus, so not run in CI):",
            "",
            "```sh",
            "uv run python -m scripts.measure interpreter-bucket-split",
            "```",
            "",
            f"Unique `<tool>` files (sha256-deduped): **{result.n_tools:,}**. With a",
            f"`<command interpreter=…>`: **{result.n_with_interpreter:,}** "
            "(the table shares below are of this population).",
            "",
            "## Buckets",
            "",
            "| Bucket | Tools | Share | Meaning |",
            "|---|--:|--:|---|",
            f"| **A — auto-fixable** | {result.bucket_a:,} | {pct(result.bucket_a)} "
            "| any non-empty interpreter (incl. flags / `java -jar` — the legacy "
            "composition is verbatim concatenation) + literal leading script that "
            "exists beside the XML |",
            f"| A-missing | {result.bucket_a_missing:,} | {pct(result.bucket_a_missing)} "
            "| structurally A but the named script isn't co-located — still rewritten "
            "(the codemod has no file-exists gate; the split is a measurement refinement) |",
            f"| B — leading Cheetah / non-literal | {result.bucket_b:,} "
            f"| {pct(result.bucket_b)} | command starts with a `#`-directive or `$var`, "
            "so the script isn't statically first |",
            f"| empty `interpreter=\"\"` | {result.bucket_empty:,} "
            f"| {pct(result.bucket_empty)} | legacy gated on `if interpreter:` — the "
            "attribute was ignored, so there is no composition to reproduce |",
            "",
            f"Buckets **A + A-missing** ({result.bucket_a + result.bucket_a_missing:,} "
            "tools) are the codemod's target — the file-exists split is a measurement-only "
            "refinement, not a codemod gate (`fix_interpreter.py` calls the eligibility "
            "predicate with no `tool_dir`). Only **B** (and the degenerate empty "
            "attribute) remains detect/warn-only (the §23 upgrade warning) — the "
            "rendered first token needs author intent or a richer parse.",
            "",
            "## Interpreter values",
            "",
            "| `interpreter=` | Tools | Histogram |",
            "|---|--:|---|",
            *value_rows,
        ]
    )


def _report_interpreter_buckets(result: _InterpreterBucketResult) -> None:
    print("\n=== interpreter-bucket-split ===")
    print(
        f"Unique tools: {result.n_tools}; with <command interpreter=>: "
        f"{result.n_with_interpreter}"
    )
    print(
        f"  A (auto-fixable):     {result.bucket_a}\n"
        f"  A-missing (no script): {result.bucket_a_missing}\n"
        f"  B (leading cheetah):  {result.bucket_b}\n"
        f"  empty interpreter=\"\": {result.bucket_empty}"
    )


def _run_interpreter_buckets(args: argparse.Namespace) -> None:
    result = _measure_interpreter_buckets(corpus_root=args.corpus_root)
    _report_interpreter_buckets(result)
    if not args.all:
        out_path = _repo_root() / "docs" / "interpreter_bucket_stats.md"
        out_path.write_text(
            _render_interpreter_bucket_page(result) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {_display_path(out_path)}")


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
    # GTR015's format_source guard (codemod decisions §24): a `format="input"`
    # output that ALSO carries `format_source` is inert (Galaxy's source branch
    # wins) and must not be overwritten. `n_format_input_with_format_source` is the
    # raw co-present element count; `n_auto_fixable_with_format_source` is the
    # guard-relevant subset — auto-fixable tools the guard now spares.
    n_format_input_with_format_source: int
    n_auto_fixable_with_format_source: int
    # GTR015's crossing-gate (codemod decisions §24): a tool already declaring
    # profile >= 16.04 is left untouched by `upgrade` (Galaxy already disabled
    # `format="input"` there, so a rewrite would change, not preserve, behaviour).
    # The count of auto-fixable tools the crossing-gate would now skip.
    n_auto_fixable_already_at_16_04: int


def _measure_output_format_input(*, corpus_root: Path) -> _OutputFormatInputResult:
    """Count output ``<data format="input">`` and the sole-data-input subset."""
    from galaxy_tool_xml_codemod.codemods.fix_output_format_input import (
        _sole_data_input_qualified_name,
    )

    n_tools = n_with = n_elements = n_auto = 0
    n_copresent = n_auto_copresent = n_auto_past_1604 = 0
    introduced = Version("16.04")
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
        n_copresent += sum(
            1 for d in format_input if d.get("format_source") is not None
        )
        inputs = root.find("inputs")
        data_params = (
            [p for p in inputs.iter("param") if p.get("type") == "data"]
            if inputs is not None
            else []
        )
        if len(data_params) == 0:
            buckets["0 data inputs"] += 1
        elif len(data_params) == 1:
            # The codemod's own resolver (agreement by construction): a bare name
            # for a top-level input, a qualified `cond|sect|name` for an
            # addressable nested one, None for a repeat-nested/unnamed one.
            qualified = _sole_data_input_qualified_name(root)
            if qualified is None:
                buckets["1 under repeat / unnamed (needs author intent)"] += 1
            else:
                label = (
                    "1 top-level (auto-fixable)"
                    if "|" not in qualified
                    else "1 nested, addressable (auto-fixable)"
                )
                buckets[label] += 1
                n_auto += 1
                if any(d.get("format_source") is not None for d in format_input):
                    n_auto_copresent += 1
                # A missing profile= runs as Galaxy's 16.01 default; an unparseable
                # (macro-token) profile can't be placed, so it is not counted here.
                declared = _as_version(root.get("profile") or "16.01")
                if declared is not None and declared >= introduced:
                    n_auto_past_1604 += 1
        else:
            buckets["2+ data inputs"] += 1
    return _OutputFormatInputResult(
        n_tools_parsed=n_tools,
        n_tools_with_format_input=n_with,
        n_format_input_elements=n_elements,
        by_data_input_bucket=dict(buckets),
        n_auto_fixable=n_auto,
        n_format_input_with_format_source=n_copresent,
        n_auto_fixable_with_format_source=n_auto_copresent,
        n_auto_fixable_already_at_16_04=n_auto_past_1604,
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
        f"\nAuto-fixable (sole addressable data input -> format_source): "
        f"{measurement.n_auto_fixable}"
    )
    print(
        "Co-present format_source (GTR015 guard skips these — §24):"
        f" {measurement.n_format_input_with_format_source} format=\"input\" element(s)"
        f" overall, {measurement.n_auto_fixable_with_format_source} within the"
        " auto-fixable subset"
    )
    print(
        "Auto-fixable already declaring profile >= 16.04 (GTR015 crossing-gate skips"
        f" these — §24): {measurement.n_auto_fixable_already_at_16_04}"
    )


def _run_output_format_input(args: argparse.Namespace) -> None:
    _report_output_format_input(
        _measure_output_format_input(corpus_root=args.corpus_root)
    )


# --- measurement: help-formats --------------------------------------------------
#
# Buckets each unique tool by how its <help> declares a markup format. Galaxy's
# XSD (HelpFormatType) allows format="restructuredtext" | "markdown", and
# parse_help defaults a missing format to "restructuredtext". Both are supported:
# RST is rendered to HTML server-side, while markdown is passed raw to the Vue
# client and rendered there (see docs/galaxy_processing_model.md). This sizes how
# many corpus tools declare a non-default help format. Format values are
# normalised to lowercase; an absent/blank attribute counts as implicit
# reStructuredText.

_HELP_FORMAT_EXAMPLE_CAP = 10


@dataclass
class _HelpFormatsResult:
    """How unique corpus tools declare their ``<help>`` markup format."""

    n_unique_tools: int
    n_without_help: int
    n_help_implicit_rst: int
    explicit_format_buckets: list[tuple[str, int]]
    markdown_example_ids: list[str]


def _measure_help_formats(*, corpus_root: Path) -> _HelpFormatsResult:
    """Bucket each unique tool's ``<help>`` by its declared ``format`` attribute."""
    seen: set[str] = set()
    n_tools = 0
    n_without = 0
    n_implicit = 0
    buckets: Counter[str] = Counter()
    markdown_ids: list[str] = []
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
        help_elem = root.find("help")
        if help_elem is None:
            n_without += 1
            continue
        raw = help_elem.get("format")
        if raw is None or not raw.strip():
            n_implicit += 1
            continue
        value = raw.strip().lower()
        buckets[value] += 1
        if value == "markdown" and len(markdown_ids) < _HELP_FORMAT_EXAMPLE_CAP:
            markdown_ids.append(root.get("id") or path.name)
    return _HelpFormatsResult(
        n_unique_tools=n_tools,
        n_without_help=n_without,
        n_help_implicit_rst=n_implicit,
        explicit_format_buckets=buckets.most_common(),
        markdown_example_ids=markdown_ids,
    )


def _report_help_formats(measurement: _HelpFormatsResult) -> None:
    total = measurement.n_unique_tools
    with_help = total - measurement.n_without_help
    n_explicit = sum(count for _, count in measurement.explicit_format_buckets)
    print("\n=== help-formats ===")
    print(f"Unique tools (sha256 dedup):        {total}")
    print(f"Tools with no <help>:               {measurement.n_without_help}")
    print(f"Tools with <help>:                  {with_help}")
    print(f"  implicit format (no attr -> rst): {measurement.n_help_implicit_rst}")
    print(f"  explicit format= attribute:       {n_explicit}")
    for value, count in measurement.explicit_format_buckets:
        pct = count / total * 100 if total else 0
        print(f'      {count:5d}  ({pct:4.1f}%)  format="{value}"')
    if measurement.markdown_example_ids:
        print(
            '\n  format="markdown" example tool ids '
            "(schema-legal but not RST-rendered):"
        )
        for tool_id in measurement.markdown_example_ids:
            print(f"      {tool_id}")


def _run_help_formats(args: argparse.Namespace) -> None:
    _report_help_formats(_measure_help_formats(corpus_root=args.corpus_root))


# --- reStructuredText <help> investigation (R1/R2/R3) ---------------------------
#
# Backs docs/upgrade_research/restructuredtext_codemods.md: feasibility of RST
# codemods on <help> — auto-fix invalid RST, normalize RST, and convert valid RST
# -> Markdown (the gateway to doing advanced help codemods in Markdown, which —
# unlike RST — has faithful, source-mapped parsers). docutils gives a doctree but
# NO faithful RST writer and NO character offsets, so parse->mutate->reserialise RST
# is out; these measures size what's actually fixable / convertible in the corpus.
#
# Markdown target = markdown-it ^14 "default" preset (CommonMark + tables +
# strikethrough), html:false (raw HTML not rendered) — Galaxy renders tool help
# markdown via configurationMarkdown.ts `MarkdownIt({html:false}).render`.

# Markdown-it/CommonMark-expressible docutils node types (the RST->MD-convertible
# shape). Tables are tracked SEPARATELY (RST grid tables don't map to GFM tables).
_MD_CONVERTIBLE_NODES = frozenset({
    "document", "section", "title", "subtitle", "paragraph", "Text", "inline",
    "emphasis", "strong", "literal", "literal_block",
    "bullet_list", "enumerated_list", "list_item",
    "block_quote", "transition", "reference", "target", "image",
})
# Transient nodes that only appear because the RST is invalid — gone after a fix,
# so they don't count against convertibility.
_RST_TRANSIENT_NODES = frozenset({"system_message", "problematic"})
_MACRO_TOKEN = re.compile(r"@[A-Z0-9_]+@")
_RST_EXAMPLE_CAP = 8


def _iter_corpus_rst_help(corpus_root: Path) -> Iterable[tuple[str, str]]:
    """Yield ``(tool_id, help_text)`` for each unique tool whose ``<help>`` is RST.

    Skips tools with no ``<help>``, ``format="markdown"``, or a help body carrying a
    macro token (``@…@``) — the same exclusions GTR089 applies (we can't expand
    macros here; an un-expanded ``@TOKEN@`` is not valid RST on its own).
    """
    seen: set[str] = set()
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
        help_elem = root.find("help")
        if help_elem is None:
            continue
        if (help_elem.get("format") or "").strip().lower() == "markdown":
            continue
        text = help_elem.text
        if not text or not text.strip():
            continue
        if _MACRO_TOKEN.search(text):
            continue
        yield (root.get("id") or path.name, text)


def _rst_doctree(text: str) -> object | None:
    """Parse RST to a docutils doctree, capturing (never raising on) messages."""
    import contextlib
    import io

    import docutils.core

    overrides = {
        "report_level": 1,
        "halt_level": 5,
        "input_encoding": "unicode",
        "doctitle_xform": False,
        "warning_stream": io.StringIO(),
    }
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return docutils.core.publish_doctree(text, settings_overrides=overrides)
    except Exception:
        return None


def _rst_messages(doctree: object) -> list[tuple[int, str]]:
    """Return ``(level, message_class)`` for each docutils system message."""
    import docutils.nodes

    out: list[tuple[int, str]] = []
    for node in doctree.findall(docutils.nodes.system_message):  # type: ignore[attr-defined]
        first = node.astext().splitlines()[0] if node.astext() else ""
        first = re.sub(r"^<string>:\d+: \([^)]*\) ", "", first)  # drop loc/level prefix
        first = re.sub(r'"[^"]*"', '"X"', first)  # quoted names
        first = re.sub(r"`[^`]*`", "`X`", first)
        first = re.sub(r"\b\d+\b", "N", first)  # numbers
        out.append((int(node["level"]), first.strip()))
    return out


def _rst_node_types(doctree: object) -> set[str]:
    """The set of docutils node type names present in *doctree*."""
    return {type(node).__name__ for node in doctree.findall()}  # type: ignore[attr-defined]


# --- measurement: help-rst-errors (R1) ------------------------------------------

# docutils message classes judged DETERMINISTICALLY fixable by a narrow surgical
# edit anchored on the reporter's line number — the "chase what we can fix" target
# (a future GTR089.1 partition-fix). Each maps to a recipe in the findings doc:
# title underlines extend; a trailing transition is dropped; a "block ends without
# a blank line; unexpected unindent" inserts the missing blank line. The ambiguous
# residual (Unexpected indentation, unclosed inline markup, section nesting) is NOT
# here — it stays the GTR089 advisory.
_FIXABLE_RST_CLASSES = frozenset({
    "Title underline too short.",
    "Title overline too short.",
    "Missing matching underline for section title overline.",
    "Transition at the end of the document.",
    "Block quote ends without a blank line; unexpected unindent.",
    "Definition list ends without a blank line; unexpected unindent.",
    "Bullet list ends without a blank line; unexpected unindent.",
    "Enumerated list ends without a blank line; unexpected unindent.",
    "Option list ends without a blank line; unexpected unindent.",
    "Literal block ends without a blank line; unexpected unindent.",
    "Explicit markup ends without a blank line; unexpected unindent.",
    "Line block ends without a blank line.",
})


@dataclass
class _HelpRstErrorsResult:
    """docutils system-message distribution across corpus RST ``<help>`` bodies."""

    n_rst_tools: int
    n_parse_fail: int
    n_invalid: int  # >= 1 message at level >= 2 (the GTR089 "invalid" threshold)
    n_info_only: int  # only sub-threshold (level-1 INFO) messages
    n_fully_fixable: int  # invalid tools whose EVERY serious error is fixable
    class_buckets: list[tuple[str, int, int]]  # (class, occurrences, tools_flagged)
    level_hist: list[tuple[int, int]]


def _measure_help_rst_errors(*, corpus_root: Path) -> _HelpRstErrorsResult:
    """Bucket the RST validity errors in corpus ``<help>`` by message class."""
    n = n_fail = n_invalid = n_info_only = n_fixable = 0
    occ: Counter[str] = Counter()
    tools_per_class: defaultdict[str, set[int]] = defaultdict(set)
    levels: Counter[int] = Counter()
    for idx, (_tool_id, text) in enumerate(_iter_corpus_rst_help(corpus_root)):
        n += 1
        doctree = _rst_doctree(text)
        if doctree is None:
            n_fail += 1
            continue
        messages = _rst_messages(doctree)
        serious = [(lvl, cls) for lvl, cls in messages if lvl >= 2]
        if serious:
            n_invalid += 1
            if all(cls in _FIXABLE_RST_CLASSES for _lvl, cls in serious):
                n_fixable += 1
        elif messages:
            n_info_only += 1
        for lvl, cls in serious:
            levels[lvl] += 1
            occ[cls] += 1
            tools_per_class[cls].add(idx)
    class_buckets = [
        (cls, count, len(tools_per_class[cls])) for cls, count in occ.most_common()
    ]
    return _HelpRstErrorsResult(
        n_rst_tools=n,
        n_parse_fail=n_fail,
        n_invalid=n_invalid,
        n_info_only=n_info_only,
        n_fully_fixable=n_fixable,
        class_buckets=class_buckets,
        level_hist=sorted(levels.items()),
    )


def _report_help_rst_errors(m: _HelpRstErrorsResult) -> None:
    total = m.n_rst_tools or 1
    invalid = m.n_invalid or 1
    print("\n=== help-rst-errors ===")
    print(f"RST <help> tools (deduped, non-macro):   {m.n_rst_tools}")
    print(f"  docutils parse failures:               {m.n_parse_fail}")
    print(f"  invalid (>=1 msg level>=2, ~GTR089):   {m.n_invalid} "
          f"({m.n_invalid / total * 100:.1f}%)")
    print(f"  ...fully fixable (all errors in the    {m.n_fully_fixable} "
          f"({m.n_fully_fixable / invalid * 100:.1f}% of invalid)")
    print("     deterministic-fix class set):")
    print(f"  info-only (sub-threshold level 1):     {m.n_info_only}")
    print("  level histogram (serious messages): "
          + ", ".join(f"L{lvl}:{c}" for lvl, c in m.level_hist))
    print("  top error classes (occurrences / tools; * = deterministically fixable):")
    for cls, occ_n, tools in m.class_buckets[:20]:
        mark = " *" if cls in _FIXABLE_RST_CLASSES else "  "
        print(f"    {occ_n:5d} / {tools:4d}{mark} {cls[:76]}")


def _run_help_rst_errors(args: argparse.Namespace) -> None:
    _report_help_rst_errors(_measure_help_rst_errors(corpus_root=args.corpus_root))


# --- measurement: help-rst-features (R2) ----------------------------------------


@dataclass
class _HelpRstFeaturesResult:
    """RST node-type inventory across corpus ``<help>`` (sizes MD-convertibility)."""

    n_rst_tools: int
    n_parse_fail: int
    n_convertible_shape: int  # node types (minus transient) within the MD whitelist
    n_uses_table: int
    node_type_tools: list[tuple[str, int]]  # node type -> tools using it
    blocking_features: list[tuple[str, int]]  # non-convertible node -> tools using it


def _measure_help_rst_features(*, corpus_root: Path) -> _HelpRstFeaturesResult:
    """Tally docutils node types across corpus RST ``<help>`` bodies."""
    n = n_fail = n_convertible = n_table = 0
    node_tools: Counter[str] = Counter()
    blocking: Counter[str] = Counter()
    for _tool_id, text in _iter_corpus_rst_help(corpus_root):
        n += 1
        doctree = _rst_doctree(text)
        if doctree is None:
            n_fail += 1
            continue
        types = _rst_node_types(doctree)
        for t in types:
            node_tools[t] += 1
        if "table" in types:
            n_table += 1
        non_convertible = types - _RST_TRANSIENT_NODES - _MD_CONVERTIBLE_NODES
        if not non_convertible:
            n_convertible += 1
        for t in non_convertible:
            blocking[t] += 1
    return _HelpRstFeaturesResult(
        n_rst_tools=n,
        n_parse_fail=n_fail,
        n_convertible_shape=n_convertible,
        n_uses_table=n_table,
        node_type_tools=node_tools.most_common(),
        blocking_features=blocking.most_common(),
    )


def _report_help_rst_features(m: _HelpRstFeaturesResult) -> None:
    total = m.n_rst_tools or 1
    print("\n=== help-rst-features ===")
    print(f"RST <help> tools (deduped, non-macro):   {m.n_rst_tools}")
    print(f"  parse failures:                        {m.n_parse_fail}")
    print(f"  MD-convertible shape (whitelist only): {m.n_convertible_shape} "
          f"({m.n_convertible_shape / total * 100:.1f}%)")
    print(f"  uses an RST table:                     {m.n_uses_table}")
    print("  node types by tools-using (top 25):")
    for t, c in m.node_type_tools[:25]:
        print(f"    {c:5d}  {t}")
    print("  blocking (non-CommonMark) features by tools-using:")
    for t, c in m.blocking_features[:20]:
        print(f"    {c:5d}  {t}")


def _run_help_rst_features(args: argparse.Namespace) -> None:
    _report_help_rst_features(_measure_help_rst_features(corpus_root=args.corpus_root))


# --- measurement: help-rst-to-markdown (R3) -------------------------------------


@dataclass
class _HelpRstToMarkdownResult:
    """RST -> Markdown convertibility 2x2 (valid/invalid x simple/complex shape)."""

    n_rst_tools: int
    n_parse_fail: int
    pandoc_available: bool
    valid_convertible: int  # already convertible: no fix needed
    invalid_convertible: int  # fix-then-convert candidates (the pipeline's payoff)
    valid_complex: int
    invalid_complex: int
    blocking_among_valid: list[tuple[str, int]]


def _measure_help_rst_to_markdown(*, corpus_root: Path) -> _HelpRstToMarkdownResult:
    """Cross-tab corpus RST ``<help>`` by {valid, invalid} x {convertible, complex}."""
    import shutil

    n = n_fail = vc = ic = vx = ix = 0
    blocking_valid: Counter[str] = Counter()
    for _tool_id, text in _iter_corpus_rst_help(corpus_root):
        n += 1
        doctree = _rst_doctree(text)
        if doctree is None:
            n_fail += 1
            continue
        types = _rst_node_types(doctree)
        valid = not any(lvl >= 2 for lvl, _cls in _rst_messages(doctree))
        non_convertible = types - _RST_TRANSIENT_NODES - _MD_CONVERTIBLE_NODES
        convertible = not non_convertible
        if valid and convertible:
            vc += 1
        elif (not valid) and convertible:
            ic += 1
        elif valid:
            vx += 1
            for t in non_convertible:
                blocking_valid[t] += 1
        else:
            ix += 1
    return _HelpRstToMarkdownResult(
        n_rst_tools=n,
        n_parse_fail=n_fail,
        pandoc_available=shutil.which("pandoc") is not None,
        valid_convertible=vc,
        invalid_convertible=ic,
        valid_complex=vx,
        invalid_complex=ix,
        blocking_among_valid=blocking_valid.most_common(),
    )


def _report_help_rst_to_markdown(m: _HelpRstToMarkdownResult) -> None:
    total = m.n_rst_tools or 1
    print("\n=== help-rst-to-markdown ===")
    print(f"RST <help> tools (deduped, non-macro):   {m.n_rst_tools}")
    print(f"  parse failures:                        {m.n_parse_fail}")
    print(f"  pandoc available on PATH:              {m.pandoc_available}")
    print("  convertibility 2x2 (rows: validity; cols: MD-convertible shape):")
    print(f"    valid   + convertible:  {m.valid_convertible:5d} "
          f"({m.valid_convertible / total * 100:.1f}%)  <- convert today, no fix")
    print(f"    invalid + convertible:  {m.invalid_convertible:5d} "
          f"({m.invalid_convertible / total * 100:.1f}%)  <- fix-then-convert payoff")
    print(f"    valid   + complex:      {m.valid_complex:5d} "
          f"({m.valid_complex / total * 100:.1f}%)  <- bail (non-CommonMark feature)")
    print(f"    invalid + complex:      {m.invalid_complex:5d} "
          f"({m.invalid_complex / total * 100:.1f}%)")
    print("  features blocking conversion among VALID tools:")
    for t, c in m.blocking_among_valid[:15]:
        print(f"    {c:5d}  {t}")


def _run_help_rst_to_markdown(args: argparse.Namespace) -> None:
    _report_help_rst_to_markdown(
        _measure_help_rst_to_markdown(corpus_root=args.corpus_root)
    )


# --- measurement: help-rst-md-convert (R4) ----------------------------------------
#
# The REAL converter + semantic-equivalence gate behind R3's node-type heuristic.
# The converter and gate are the SHIPPED tier-1 ``galaxy_tool_xml.rst_markdown``
# (they graduated there when the conversion capability was built; this measure
# consumes the same code paths the ConvertHelpToMarkdown codemod runs): convert
# each RST <help> doctree to CommonMark (whitelist visitor; bail on the first
# non-CommonMark node), render BOTH sides — RST through docutils html4css1 (what
# Galaxy's server-side galaxy.util.rst_to_html uses) and the CommonMark through
# markdown-it-py's "js-default" preset with html:false (faithful to the client-side
# `MarkdownIt({html:false}).render` of ToolHelpMarkdown.vue) — and count a body
# convertible only when the two semantic skeletons are EQUAL. A conversion the gate
# rejects is counted gate-FAIL: converted, but correctly NOT convertible.
# NOTE: unlike the codemod, this sizing measure runs the raw convert->gate pipeline
# WITHOUT the repair composition or the profile>=24.2 gate — it sizes the
# conversion itself. Backs docs/upgrade_research/restructuredtext_codemods.md;
# needs markdown-it-py (a galaxy-tool-xml dev dependency, like bashlex) + the
# corpus, so not run in CI (the synthetic-fixture test is).


@dataclass
class _HelpRstMdConvertResult:
    """Converter + render-equivalence-gate verdicts across corpus RST ``<help>``."""

    n_rst_tools: int
    n_pass: int  # converted AND render-equivalent: the true convertible population
    n_bail: int  # converter bail (incl. docutils parse failure)
    n_gate_fail: int  # converted but NOT render-equivalent -> correctly skipped
    bail_classes: list[tuple[str, int]]  # first-unhandled node type -> bodies


def _measure_help_rst_md_convert(*, corpus_root: Path) -> _HelpRstMdConvertResult:
    """Convert + gate every corpus RST ``<help>`` body; tally the verdicts."""
    from galaxy_tool_xml.rst_markdown import (
        conversion_is_render_equivalent,
        rst_to_commonmark,
    )

    n = n_pass = n_bail = n_gate_fail = 0
    bail_classes: Counter[str] = Counter()
    for _tool_id, text in _iter_corpus_rst_help(corpus_root):
        n += 1
        commonmark, bail_class = rst_to_commonmark(text)
        if commonmark is None:
            n_bail += 1
            bail_classes[bail_class or "?"] += 1
        elif conversion_is_render_equivalent(text, commonmark):
            n_pass += 1
        else:
            n_gate_fail += 1
    return _HelpRstMdConvertResult(
        n_rst_tools=n,
        n_pass=n_pass,
        n_bail=n_bail,
        n_gate_fail=n_gate_fail,
        bail_classes=bail_classes.most_common(),
    )


def _report_help_rst_md_convert(m: _HelpRstMdConvertResult) -> None:
    total = m.n_rst_tools or 1
    print("\n=== help-rst-md-convert ===")
    print(f"RST <help> bodies (deduped, non-macro):  {m.n_rst_tools}")
    print(f"  CONVERT + gate PASS: {m.n_pass:5d} ({m.n_pass / total * 100:.1f}%)"
          "  <- true behaviour-equivalent convertible population")
    print(f"  converter BAIL     : {m.n_bail:5d} ({m.n_bail / total * 100:.1f}%)"
          "  <- genuine non-CommonMark feature (or parse-fail)")
    print(f"  gate FAIL          : {m.n_gate_fail:5d} "
          f"({m.n_gate_fail / total * 100:.1f}%)"
          "  <- converted but not render-equivalent: correctly skipped")
    print("  bail by first-unhandled node type (top 15):")
    for node_type, count in m.bail_classes[:15]:
        print(f"    {count:5d}  {node_type}")


def _run_help_rst_md_convert(args: argparse.Namespace) -> None:
    _report_help_rst_md_convert(
        _measure_help_rst_md_convert(corpus_root=args.corpus_root)
    )


# --- measurement: macro-format-residual -----------------------------------------
#
# Sizes the population the imported-macro `format`/`ftype` normalization pass
# (Phase 2a; `galaxy_tool_refactor_registry.macro_datatype`) unsticks: tools stuck
# below the latest profile that reach a newer one once the literal `format`/`ftype`
# values in their *imported* macro files are lowercased — the value `Upgrade24_1`
# cannot reach from the tool's own tree. Replaces the ad-hoc "~18" in
# `galaxy-tool-xml-codemod/docs/macro-aware-normalization.md`. Sound by construction:
# per candidate the bundle is copied to a temp dir, normalized, and the tool
# re-validated — counted only if its newest valid profile strictly increases. Split by
# shared (>=2 importers) vs sole-owned defining macro file. Needs the corpus (not CI).


@dataclass
class _MacroFormatResidualResult:
    """Tools unstuck by normalizing `format`/`ftype` in their imported macro files."""

    n_tools: int  # unique parsed tools
    n_importing: int  # tools importing >=1 macro file
    residual_tools: int  # tools whose newest valid profile rises after macro normalization
    shared_file_residual: int  # of those, whose defining file is shared (>=2 importers)
    sole_file_residual: int  # of those, whose defining file is sole-owned
    defining_files: dict[str, int]  # defining macro file -> residual tools it unblocks


def _macro_format_unsticks(tool_path: Path, /, *, latest: str) -> list[Path] | None:
    """Return the bundle macro files that unstick *tool_path*, or ``None``.

    ``None`` when the tool imports nothing, has no coercible literal in its bundle,
    is not stuck below *latest*, cannot be safely mirrored (an out-of-dir import —
    none occur in the corpus), or does not actually reach a newer profile once its
    bundle is normalized. The cheap filters run before the expensive validation.
    """
    import shutil
    import tempfile

    from galaxy_tool_xml.binding import (
        ToolXmlSyntaxError,
        load_tool,
        newest_valid_profile,
    )
    from galaxy_tool_xml.macros import imported_macro_paths
    from galaxy_tool_xml.profiles import is_newer_profile

    from galaxy_tool_refactor_registry.macro_datatype import normalize_macro_files

    bundle = imported_macro_paths(tool_path)
    if not bundle:
        return None
    would = normalize_macro_files(bundle, write=False).edits
    if not would:
        return None  # no coercible literal anywhere in the bundle
    tool_dir = tool_path.parent
    members = [tool_path, *bundle]
    if any(not member.is_relative_to(tool_dir) for member in members):
        return None  # cannot mirror an import outside the tool dir (none in corpus)
    try:
        reached = newest_valid_profile(load_tool(tool_path))
        if reached is None or not is_newer_profile(latest, reached):
            return None  # validates nowhere, or already at latest — not a residual
        with tempfile.TemporaryDirectory() as temp_name:
            temp_dir = Path(temp_name)
            for member in members:
                dest = temp_dir / member.relative_to(tool_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(member, dest)
            temp_bundle = [temp_dir / path.relative_to(tool_dir) for path in bundle]
            normalize_macro_files(temp_bundle, write=True)
            temp_tool = temp_dir / tool_path.relative_to(tool_dir)
            reached_after = newest_valid_profile(load_tool(temp_tool))
    except ToolXmlSyntaxError:
        return None  # malformed tool / macro — skip (parsing has no LBYL form)
    if reached_after is None or not is_newer_profile(reached_after, reached):
        return None  # normalizing the bundle did not actually advance the tool
    return [edit.macro_file for edit in would]


def _measure_macro_format_residual(*, corpus_root: Path) -> _MacroFormatResidualResult:
    """Count tools the macro-file `format`/`ftype` normalization pass would unstick."""
    from galaxy_tool_xml.macros import imported_macro_paths
    from galaxy_tool_xml.profiles import latest_profile

    latest = latest_profile()
    seen: set[str] = set()
    importers: dict[Path, set[Path]] = {}
    importing_tools: list[Path] = []
    n_tools = 0
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        digest = _sha256_of(path)
        if digest in seen:
            continue
        seen.add(digest)
        if _parse_tool_root(path) is None:
            continue  # not a <tool> file (macro library, datatypes_conf, …)
        n_tools += 1
        bundle = imported_macro_paths(path)
        if not bundle:
            continue
        importing_tools.append(path)
        for macro_file in bundle:
            importers.setdefault(macro_file, set()).add(path)

    residual = shared = sole = 0
    defining: Counter[str] = Counter()
    for path in importing_tools:
        unblocking = _macro_format_unsticks(path, latest=latest)
        if not unblocking:
            continue
        residual += 1
        if any(len(importers.get(macro_file, ())) >= 2 for macro_file in unblocking):
            shared += 1
        else:
            sole += 1
        for macro_file in unblocking:
            defining[str(macro_file)] += 1
    return _MacroFormatResidualResult(
        n_tools=n_tools,
        n_importing=len(importing_tools),
        residual_tools=residual,
        shared_file_residual=shared,
        sole_file_residual=sole,
        defining_files=dict(defining),
    )


def _render_macro_format_residual_page(result: _MacroFormatResidualResult) -> str:
    """Render the macro-format-residual stats markdown page (deterministic)."""
    file_rows = [
        f"| `{Path(name).parent.name}/{Path(name).name}` | {count:,} |"
        for name, count in sorted(
            result.defining_files.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]
    return "\n".join(
        [
            "# Macro-file format/ftype residual statistics",
            "",
            "Sizes the population the imported-macro `format`/`ftype` normalization",
            "pass (Phase 2a; `galaxy_tool_refactor_registry.macro_datatype`) unsticks:",
            "tools stuck below the latest profile that reach a newer one once the",
            "literal `format`/`ftype` values in their *imported* macro files are",
            "lowercased — the value `Upgrade24_1` cannot reach from the tool's own tree",
            "(see `upgrade_research`/`macro-aware-normalization.md`). A tool counts only",
            "when its newest valid profile **strictly increases** after its bundle is",
            "normalized in a temp copy and the tool is re-validated.",
            "",
            "Regenerate with (needs the corpus, so not run in CI):",
            "",
            "```sh",
            "uv run python -m scripts.measure macro-format-residual",
            "```",
            "",
            f"Unique `<tool>` files (sha256-deduped): **{result.n_tools:,}**; importing",
            f"a macro file: **{result.n_importing:,}**.",
            "",
            "## Tools unstuck by macro-file normalization",
            "",
            f"- **Residual tools:** {result.residual_tools:,}",
            f"- via a **shared** defining file (≥2 importers): "
            f"{result.shared_file_residual:,}",
            f"- via a **sole-owned** defining file: {result.sole_file_residual:,}",
            "",
            "## Defining macro files (residual tools each unblocks)",
            "",
            "| Macro file | Tools unblocked |",
            "|---|--:|",
            *file_rows,
        ]
    )


def _report_macro_format_residual(result: _MacroFormatResidualResult) -> None:
    print("\n=== macro-format-residual ===")
    print(
        f"Unique tools: {result.n_tools}; importing a macro file: "
        f"{result.n_importing}"
    )
    print(
        f"  residual (unstuck by macro normalization): {result.residual_tools}\n"
        f"    via shared defining file:   {result.shared_file_residual}\n"
        f"    via sole-owned defining file: {result.sole_file_residual}"
    )


def _run_macro_format_residual(args: argparse.Namespace) -> None:
    result = _measure_macro_format_residual(corpus_root=args.corpus_root)
    _report_macro_format_residual(result)
    if not args.all:
        out_path = _repo_root() / "docs" / "macro_format_residual_stats.md"
        out_path.write_text(
            _render_macro_format_residual_page(result) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {_display_path(out_path)}")


# --- measurement: macro-token-datatype-residual ---------------------------------
#
# Phase-2b sizing (macro epic): of the tools still stuck after Phase 2a (literal
# format/ftype normalization in macro files + the tool's own tree), how many reach a
# newer profile when the *token-supplied* datatype values are also normalized — i.e.
# a `format="@FORMAT@"` whose `<token name="@FORMAT@">` value is coercible (`GTiff`).
# Split by where the helping token is defined: inline (the tool's own `<macros>`,
# reachable by an Upgrade24_1 extension) vs imported (a macro file, the macro_profile
# consensus shape). Both are *locate-in-source* fixes — so a non-zero count sizes the
# cheap Phase-2 consumer, and a ~zero remainder means the heavyweight
# expansion-provenance layer (M1) is unjustified for datatypes. Sound: temp-copy the
# bundle, normalize literals (baseline) then literals+token-values, count only a strict
# profile increase from the token values. Needs the corpus (not CI).


@dataclass
class _MacroTokenResidualResult:
    """Tools unstuck by normalizing token-supplied datatype values (beyond 2a)."""

    n_tools: int  # unique parsed tools
    n_token_datatype: int  # tools with a coercible token-supplied format/ftype, stuck
    residual_tools: int  # of those, unstuck by normalizing the token value(s)
    inline_only: int  # residual whose helping token(s) are all inline-defined
    imported_involved: int  # residual with >=1 imported-defined helping token


def _temp_normalize_reached(
    tool_path: Path, bundle: list[Path], /, *, token_names: frozenset[str]
) -> str | None:
    """Newest valid profile after temp-normalizing the tool + bundle.

    Always normalizes literal `format`/`ftype` (tool tree + macro files — the 2a /
    Upgrade24_1 baseline); additionally rewrites each `<token name=…>` in *token_names*
    to its lowercased datatype value. Returns the reached profile, or ``None`` if the
    bundle cannot be mirrored (out-of-dir import) or anything fails to parse.
    """
    import shutil
    import tempfile

    from lxml import etree

    from galaxy_tool_xml.binding import (
        ToolXmlSyntaxError,
        load_tool,
        newest_valid_profile,
    )
    from galaxy_tool_xml_codemod.datatype_format import (
        normalize_datatype_attributes,
        normalize_datatype_value,
    )

    tool_dir = tool_path.parent
    members = [tool_path, *bundle]
    if any(not member.is_relative_to(tool_dir) for member in members):
        return None
    parser = etree.XMLParser(strip_cdata=False)
    try:
        with tempfile.TemporaryDirectory() as temp_name:
            temp_dir = Path(temp_name)
            for member in members:
                dest = temp_dir / member.relative_to(tool_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(member, dest)
            for temp_file in (temp_dir / m.relative_to(tool_dir) for m in members):
                tree = etree.parse(str(temp_file), parser)
                changed = False
                for element in tree.getroot().iter():
                    if not isinstance(element.tag, str):
                        continue
                    if normalize_datatype_attributes(element, skip_tokens=True):
                        changed = True
                    if element.tag == "token" and element.get("name") in token_names:
                        value = (element.text or "").strip()
                        normalized = normalize_datatype_value(value)
                        if value and "@" not in value and normalized not in (value, ""):
                            element.text = normalized
                            changed = True
                if changed:
                    temp_file.write_bytes(etree.tostring(tree))
            temp_tool = temp_dir / tool_path.relative_to(tool_dir)
            return newest_valid_profile(load_tool(temp_tool))
    except ToolXmlSyntaxError:
        return None


def _measure_macro_token_residual(*, corpus_root: Path) -> _MacroTokenResidualResult:
    """Size the token-supplied datatype residual left after Phase 2a."""
    import re as _re

    from galaxy_tool_xml.binding import (
        ToolXmlSyntaxError,
        load_tool,
        newest_valid_profile,
    )
    from galaxy_tool_xml.macros import imported_macro_paths, token_definitions
    from galaxy_tool_xml.profiles import is_newer_profile, latest_profile
    from galaxy_tool_xml_codemod.datatype_format import normalize_datatype_value

    latest = latest_profile()
    token_ref = _re.compile(r"@[A-Za-z0-9_]+@")
    seen: set[str] = set()
    n_tools = n_token_datatype = residual = inline_only = imported_involved = 0
    for path in _iter_corpus_tool_xmls(corpus_root):
        if not path.is_file():
            continue
        digest = _sha256_of(path)
        if digest in seen:
            continue
        seen.add(digest)
        if _parse_tool_root(path) is None:
            continue
        n_tools += 1
        try:
            document = load_tool(path)
            refs: set[str] = set()
            for element in document.root.iter():
                if not isinstance(element.tag, str):
                    continue
                for attribute in ("format", "ftype"):
                    value = element.get(attribute)
                    if value and "@" in value:
                        refs.update(token_ref.findall(value))
            if not refs:
                continue
            defs = {d.name: d for d in token_definitions(document)}
            candidates = {
                name: defs[name]
                for name in refs
                if name in defs
                and "@" not in defs[name].value
                and normalize_datatype_value(defs[name].value)
                not in (defs[name].value, "")
            }
            if not candidates:
                continue
            reached_before = newest_valid_profile(document)
            if reached_before is None or not is_newer_profile(latest, reached_before):
                continue
            n_token_datatype += 1
            bundle = imported_macro_paths(path)
            reached_literal = _temp_normalize_reached(
                path, bundle, token_names=frozenset()
            )
            reached_token = _temp_normalize_reached(
                path, bundle, token_names=frozenset(candidates)
            )
        except ToolXmlSyntaxError:
            continue
        if reached_literal is None or reached_token is None:
            continue
        if not is_newer_profile(reached_token, reached_literal):
            continue
        residual += 1
        if any(definition.source is not None for definition in candidates.values()):
            imported_involved += 1
        else:
            inline_only += 1
    return _MacroTokenResidualResult(
        n_tools=n_tools,
        n_token_datatype=n_token_datatype,
        residual_tools=residual,
        inline_only=inline_only,
        imported_involved=imported_involved,
    )


def _render_macro_token_residual_page(result: _MacroTokenResidualResult) -> str:
    """Render the macro-token-datatype-residual stats markdown page (deterministic)."""
    return "\n".join(
        [
            "# Macro token-supplied datatype residual (Phase-2b sizing)",
            "",
            "Sizes what Phase 2a (literal `format`/`ftype` normalization) leaves on the",
            "table: tools still stuck below the latest profile that reach a newer one",
            "only when the **token-supplied** datatype values are also normalized — a",
            '`format="@FORMAT@"` whose `<token>` value is coercible (e.g. `GTiff`).',
            "Both fixes are *locate-in-source* (the token's definition), so this sizes",
            "the cheap Phase-2 consumer; a near-zero count means the heavyweight",
            "expansion-provenance layer (M1) is unjustified for datatypes (see the 2b",
            "design note). Sound: temp-copy, normalize literals (baseline) then",
            "literals+token-values, count only a strict profile increase from the tokens.",
            "",
            "Regenerate with (needs the corpus, so not run in CI):",
            "",
            "```sh",
            "uv run python -m scripts.measure macro-token-datatype-residual",
            "```",
            "",
            f"Unique `<tool>` files (sha256-deduped): **{result.n_tools:,}**; with a",
            "coercible token-supplied `format`/`ftype` and stuck below latest: "
            f"**{result.n_token_datatype:,}**.",
            "",
            "## Tools unstuck by normalizing the token value (beyond Phase 2a)",
            "",
            f"- **Residual tools:** {result.residual_tools:,}",
            "- helping token defined **inline** only (Upgrade24_1 extension): "
            f"{result.inline_only:,}",
            "- **imported** token involved (macro_profile-shape consensus): "
            f"{result.imported_involved:,}",
        ]
    )


def _report_macro_token_residual(result: _MacroTokenResidualResult) -> None:
    print("\n=== macro-token-datatype-residual ===")
    print(
        f"Unique tools: {result.n_tools}; coercible token-supplied datatype + stuck: "
        f"{result.n_token_datatype}"
    )
    print(
        f"  residual (unstuck by token-value normalization): {result.residual_tools}\n"
        f"    inline-only token:    {result.inline_only}\n"
        f"    imported token:       {result.imported_involved}"
    )


def _run_macro_token_residual(args: argparse.Namespace) -> None:
    result = _measure_macro_token_residual(corpus_root=args.corpus_root)
    _report_macro_token_residual(result)
    if not args.all:
        out_path = _repo_root() / "docs" / "macro_token_residual_stats.md"
        out_path.write_text(
            _render_macro_token_residual_page(result) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {_display_path(out_path)}")


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
    "command-lone-amp": _run_command_lone_amp,
    "command-unquoted-var": _run_command_unquoted_var,
    "iuc011-fixability": _run_iuc011_fixability,
    "select-quoting-safety": _run_select_quoting_safety,
    "shell-oracle-quoting": _run_shell_oracle_quoting,
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
    "set-e-tightening": _run_set_e_tightening,
    "macro-expansion-detection-gap": _run_macro_expansion_detection_gap,
    "upgrade-profile-shift": _run_upgrade_profile_shift,
    "upgrade-behavior-blocks": _run_upgrade_behavior_blocks,
    "element-cardinality": _run_element_cardinality,
    "command-language": _run_command_language,
    "cheetah-command-complexity": _run_cheetah_command_complexity,
    "cheetah-cdm-coverage": _run_cheetah_cdm_coverage,
    "cheetah-cdm-bails": _run_cheetah_cdm_bails,
    "rename-coverage": _run_rename_coverage,
    "rename-macro-spread": _run_rename_macro_spread,
    "xsd-tightenings": _run_xsd_tightenings,
    "interpreter-bucket-split": _run_interpreter_buckets,
    "output-format-input": _run_output_format_input,
    "help-formats": _run_help_formats,
    "help-rst-errors": _run_help_rst_errors,
    "help-rst-features": _run_help_rst_features,
    "help-rst-to-markdown": _run_help_rst_to_markdown,
    "help-rst-md-convert": _run_help_rst_md_convert,
    "macro-format-residual": _run_macro_format_residual,
    "macro-token-datatype-residual": _run_macro_token_residual,
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
            "command-language, upgrade-codes-applicability, "
            "upgrade-profile-shift). Default: %(default)s."
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
