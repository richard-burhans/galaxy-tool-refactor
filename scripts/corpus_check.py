#!/usr/bin/env python3
"""Sweep public Galaxy tool repositories through the galaxy-tool-xml ecosystem.

A maintainer QA tool with four subcommands:

``validate`` — sweep the corpus through the galaxy-tool-xml API and check the
library's invariants on each tool:

* it must not **crash** on tool input;
* serialising the parsed tree must be **idempotent** (CDATA/comments preserved);
* the API must not **mutate** the ``ToolDocument`` tree;
* the typed ``model()`` must agree with the tree's root attributes;
* ``parse_tool().well_formed`` must agree with whether ``load_tool`` raises;
* a macro-free tool must validate the same under every ``macro_handling``;
* ``newest_valid_profile`` must return the newest profile that validates.

``fmt`` — sweep the corpus through the galaxy-tool-xml-fmt pipeline and check:

* the formatter must not **crash** on tool input;
* re-formatting the formatter's output must yield identical bytes
  (**idempotence**: ``format(format(x)) == format(x)``).

``codemod`` — sweep the corpus through a single structural codemod and check:

* idempotence (apply-twice = apply-once) and post-codemod validity;
* a per-step **discovery report** — the post-apply profile distribution, the
  ``STICKING POINT`` versions still needing an upgrade codemod, and the
  per-codemod upgrade counts (how many tools each ``upgrade_vN`` advanced).

``rules`` — sweep the corpus through **every** GTX rule in isolation (one rule
at a time, no others) and write ``docs/corpus_rule_stats.md``:

* fmt rules (GTX001/003/004) — idempotence + no-crash only (a rule run without
  its usual predecessors emits valid-but-non-canonical output, which is fine);
* codemods (GTX002, GTX005–GTX012) — idempotence + post-codemod validity, with
  ``UpgradeToLatest``'s reach / sticking-point / per-step discovery as upgrade QA.

Each distinct violation in any subcommand is retained under the relevant
package's ``tests/data/regressions/`` as a permanent regression fixture.

Usage::

    uv run python -m scripts.corpus_check validate [--source github|toolshed|combined] \\
        [--repo NAME] [--limit N] [--no-stats] [--include-raw-profile]

    uv run python -m scripts.corpus_check fmt [--source github|toolshed|combined] \\
        [--repo NAME] [--limit N] [--no-stats] [--profile VERSION]

    uv run python -m scripts.corpus_check codemod <dotted.module>:<ClassName> \\
        [--source github|toolshed|combined] [--repo NAME] [--limit N]

    uv run python -m scripts.corpus_check rules \\
        [--source github|toolshed|combined] [--repo NAME] [--limit N] \\
        [--profile VERSION] [--no-stats]

GitHub-source repositories are shallow-cloned into the gitignored ``corpus/``
directory and reused on later runs. A repository that cannot be cloned is
skipped with a warning.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import traceback
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from pathlib import Path

from lxml import etree
from packaging.version import Version

from scripts._shared import PROFILE_NONE as _PROFILE_NONE
from scripts._shared import iter_tool_xmls as _iter_tool_xmls
from scripts._shared import row_source as _row_source
from scripts._shared import sha256_of as _sha256_of
from scripts._shared import unique_by_sha as _unique_by_sha

logger = logging.getLogger("corpus_check")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CORPUS_ROOT = _REPO_ROOT / "corpus"
_CORPUS_SOURCES_FILE = _REPO_ROOT / "corpus_sources.json"

# --- validate subcommand paths -----------------------------------------------

_TOOLSHED_ROOT = _CORPUS_ROOT / "galaxy-toolshed"
_TOOLSHED_MANIFEST = _TOOLSHED_ROOT / "manifest.json"
_VALIDATE_REGRESSIONS = (
    _REPO_ROOT / "galaxy-tool-xml" / "tests" / "data" / "regressions"
)
_VALIDATE_STATS_FILES = {
    "github": _REPO_ROOT / "docs" / "corpus_stats.md",
    "toolshed": _REPO_ROOT / "docs" / "toolshed_corpus_stats.md",
    "combined": _REPO_ROOT / "docs" / "combined_corpus_stats.md",
}
_CORPUS_DATA_DIR = _REPO_ROOT / "docs" / "corpus_data"
_CORPUS_DATA_BASENAMES = {
    "github": "corpus_data",
    "toolshed": "toolshed_corpus_data",
    "combined": "combined_corpus_data",
}
_FINE_GRAINED_BASE_COLUMNS = ("repo", "version", "path", "tool_id", "sha256")
_FINE_GRAINED_PROFILE_COLUMNS = (
    "profile_raw",
    "profile_expanded",
    "newest_valid",
    "expansion_failure_reason",
    "no_valid_reason",
    "source",
    "presence",
)
_FAILURE_DETAILS_SUBDIR = "failures"
_TOOLSHED_VIEW_URL = "https://toolshed.g2.bx.psu.edu/view"
_SOURCES = ("github", "toolshed", "combined")
_COMBINED_SUB_SOURCES = ("github", "toolshed")
_PROFILE_EXPANSION_FAILED = "(expansion failed)"
_UNKNOWN = "unknown"

# --- fmt subcommand paths ----------------------------------------------------

_FMT_REGRESSIONS = (
    _REPO_ROOT / "galaxy-tool-xml-fmt" / "tests" / "data" / "regressions"
)
_FMT_STATS_FILE = _REPO_ROOT / "docs" / "corpus_format_stats.md"
_RULE_STATS_FILE = _REPO_ROOT / "docs" / "corpus_rule_stats.md"


# =============================================================================
# Shared helpers
# =============================================================================


@cache
def _corpus_sources() -> tuple[tuple[str, str], ...]:
    """Return ``(name, url)`` pairs for every corpus repository.

    Loaded once from ``corpus_sources.json`` at the workspace root — the
    canonical source for anything that walks the corpus, so adding or rerouting
    a repository is a config edit, not a code change. The order in the file is
    preserved (sweep order), and ``name`` is also the local clone directory
    name under ``corpus/``.
    """
    raw = json.loads(_CORPUS_SOURCES_FILE.read_text(encoding="utf-8"))
    return tuple((entry["name"], entry["url"]) for entry in raw["repositories"])


def _clone_repo(name: str, url: str) -> Path | None:
    """Shallow-clone a repository into the corpus, or reuse / skip it."""
    dest = _CORPUS_ROOT / name
    if dest.exists():
        logger.info("using existing clone: %s", name)
        return dest
    logger.info("cloning %s ...", url)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.warning("SKIPPED %s: clone failed — %s", name, result.stderr.strip())
        return None
    return dest


def _corpus_commit(repo_dir: Path) -> str:
    """Return a repository checkout's commit SHA, or ``"unknown"``."""
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _signature(exc: BaseException) -> str:
    """A short, dedup-friendly key for a crash: exception type + deepest frame."""
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return type(exc).__name__
    deepest = frames[-1]
    return f"{type(exc).__name__} @ {Path(deepest.filename).name}:{deepest.lineno}"


def _imported_macro_files(path: Path) -> list[Path]:
    """Return the macro files a tool ``<import>``s, resolved beside the tool."""
    tree = etree.parse(path, etree.XMLParser(recover=True))
    base = path.parent
    return [
        base / element.text.strip()
        for element in tree.iter("import")
        if element.text and element.text.strip()
    ]


def _retain(path: Path, repo: str, *, regressions_dir: Path) -> Path:
    """Copy an offending tool, and any macro files it imports, into the fixtures."""
    name = f"{repo}__{path.parent.name or path.stem}"
    dest = regressions_dir / name
    suffix = 2
    while dest.exists():
        dest = regressions_dir / f"{name}-{suffix}"
        suffix += 1
    dest.mkdir(parents=True)
    shutil.copy(path, dest / "tool.xml")
    for macro in _imported_macro_files(path):
        if macro.is_file():
            shutil.copy(macro, dest / macro.name)
    return dest


def _append_provenance(
    retained: list[tuple[str, str, Path, str, str]],
    *,
    regressions_dir: Path,
) -> None:
    """Append the newly retained fixtures to the regression PROVENANCE.md."""
    path = regressions_dir / "PROVENANCE.md"
    existing = path.read_text(encoding="utf-8").rstrip() if path.exists() else ""
    new = [
        f"- `{fixture}` — {repo} `{rel}` @ `{commit[:12]}` — {signature}"
        for fixture, repo, rel, commit, signature in retained
    ]
    path.write_text(existing + "\n\n" + "\n".join(new) + "\n", encoding="utf-8")


# =============================================================================
# validate subcommand — corpus sources walker
# =============================================================================


def _iter_github_sources(
    *,
    repo_filter: str | None,
) -> Iterable[tuple[str, str, Path, str]]:
    """Yield ``("github", display_name, repo_dir, commit_sha)`` per github repo."""
    for name, url in _corpus_sources():
        if repo_filter is not None and name != repo_filter:
            continue
        repo_dir = _clone_repo(name, url)
        if repo_dir is None:
            continue
        yield "github", name, repo_dir, _corpus_commit(repo_dir)


@cache
def _toolshed_manifest() -> dict[str, str]:
    """Return ``owner/name -> short changeset`` from the toolshed manifest."""
    if not _TOOLSHED_MANIFEST.exists():
        logger.warning(
            "no toolshed manifest at %s; toolshed versions will be %r. "
            "Re-run scripts/fetch_toolshed.py to populate it.",
            _TOOLSHED_MANIFEST.relative_to(_REPO_ROOT),
            _UNKNOWN,
        )
        return {}
    raw = json.loads(_TOOLSHED_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    repos = raw.get("repositories")
    if not isinstance(repos, dict):
        return {}
    result: dict[str, str] = {}
    for key, entry in repos.items():
        if not isinstance(entry, dict):
            continue
        changeset = entry.get("changeset")
        if isinstance(changeset, str) and changeset:
            result[key] = changeset
    return result


def _iter_toolshed_sources(
    *,
    repo_filter: str | None,
) -> Iterable[tuple[str, str, Path, str]]:
    """Yield ``("toolshed", "<owner>/<name>", repo_dir, changeset)`` per repo.

    Skips repos whose key (``"<owner>/<name>"``) does not match *repo_filter*
    when *repo_filter* is not ``None``.
    """
    manifest = _toolshed_manifest()
    for owner_dir in sorted(_TOOLSHED_ROOT.iterdir()):
        if not owner_dir.is_dir():
            continue
        for repo_dir in sorted(owner_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            key = f"{owner_dir.name}/{repo_dir.name}"
            if repo_filter is not None and key != repo_filter:
                continue
            yield "toolshed", key, repo_dir, manifest.get(key, _UNKNOWN)


def _iter_sources(
    sources: tuple[str, ...],
    *,
    repo_filter: str | None,
) -> Iterable[tuple[str, str, Path, str]]:
    """Yield ``(source_label, display_name, repo_dir, version)`` for each repo."""
    for source in sources:
        if source == "github":
            yield from _iter_github_sources(repo_filter=repo_filter)
        elif source == "toolshed":
            yield from _iter_toolshed_sources(repo_filter=repo_filter)
        else:
            raise ValueError(f"unknown source: {source!r}")


# =============================================================================
# validate subcommand — invariant checks
# =============================================================================

# These functions are also imported by galaxy-tool-xml/tests/test_regressions.py
# so a retained fixture is replayed through the same battery.

from galaxy_tool_xml.binding import (  # noqa: E402
    ToolXmlSyntaxError,
    load_tool,
    newest_valid_profile,
    parse_tool,
    validate_tool,
)
from galaxy_tool_xml.corrections import suggest_corrections  # noqa: E402
from galaxy_tool_xml.document import ToolDocument  # noqa: E402
from galaxy_tool_xml.macros import (  # noqa: E402
    MacroError,
    expand_from_path,
    has_macros,
)
from galaxy_tool_xml.profiles import available_profiles, latest_profile  # noqa: E402


def check_immutable(document: ToolDocument) -> tuple[str, str]:
    """The document tree must survive model / correction / validation intact."""
    before = etree.tostring(document.tree)
    document.model()
    suggest_corrections(document)
    validate_tool(document)
    if etree.tostring(document.tree) != before:
        return "tree-mutated", "an API call mutated the document tree"
    return "ok", ""


def check_roundtrip(document: ToolDocument) -> tuple[str, str]:
    """Serialising the document tree must be idempotent — CDATA/comments kept."""
    parser = etree.XMLParser(strip_cdata=False, recover=True)
    once = etree.tostring(document.tree)
    twice = etree.tostring(etree.fromstring(once, parser).getroottree())
    if once != twice:
        return "roundtrip-unstable", "tree serialisation is not idempotent"
    return "ok", ""


def check_model(document: ToolDocument) -> tuple[str, str]:
    """A root attribute present in the tree must match the bound model."""
    model = document.model()
    for attr in ("id", "name", "version"):
        tree_value = document.root.get(attr)
        if tree_value is None:
            continue
        model_value = getattr(model, attr, None)
        if tree_value != model_value:
            return "model-mismatch", (
                f"model.{attr}={model_value!r} but tree @{attr}={tree_value!r}"
            )
    return "ok", ""


def check_parse_load_agree(path: Path) -> tuple[str, str]:
    """``parse_tool().well_formed`` must agree with whether ``load_tool`` raises."""
    well_formed = parse_tool(path).well_formed
    try:
        load_tool(path)
        raised = False
    except ToolXmlSyntaxError:
        raised = True
    if well_formed == raised:
        return "parse-load-disagree", (
            f"parse_tool.well_formed={well_formed} but load_tool "
            f"{'raised' if raised else 'succeeded'}"
        )
    return "ok", ""


def check_macro_handling(path: Path, document: ToolDocument) -> tuple[str, str]:
    """A macro-free tool must validate identically under every macro_handling."""
    if has_macros(document.root):
        return "ok", ""
    results = {
        mode: validate_tool(path, macro_handling=mode).valid
        for mode in ("off", "expand", "strip")
    }
    if len(set(results.values())) != 1:
        return "macro-handling-divergence", (
            f"macro-free tool validates differently per mode: {results}"
        )
    return "ok", ""


def validity_vector(path: Path) -> list[bool]:
    """Return whether the tool validates against each vendored profile, oldest first."""
    return [
        validate_tool(path, profile=profile).valid for profile in available_profiles()
    ]


def check_newest_valid_profile(path: Path, vector: list[bool]) -> tuple[str, str]:
    """``newest_valid_profile`` must return the newest profile that validates."""
    profiles = available_profiles()
    expected = next(
        (p for p, ok in zip(reversed(profiles), reversed(vector), strict=True) if ok),
        None,
    )
    actual = newest_valid_profile(path)
    if actual != expected:
        return "wrong-newest-profile", (
            f"newest_valid_profile returned {actual!r}; "
            f"the validity vector's newest is {expected!r}"
        )
    return "ok", ""


def is_contiguous(vector: list[bool]) -> bool:
    """Whether a tool's valid profiles form a single contiguous range of releases."""
    if not any(vector):
        return True
    first = vector.index(True)
    last = len(vector) - 1 - vector[::-1].index(True)
    return all(vector[first : last + 1])


_MACRO_FAIL_MALFORMED = re.compile(
    r"invalid element|tag mismatch|hyphen within comment|StartTag|EndTag"
)


def _expansion_failure_reason(errors: list[MacroError]) -> str:
    """Categorise the first ``MacroError`` from a failed expansion."""
    if not errors:
        return "other macro error"
    message = errors[0].message
    if "No macro named" in message:
        return "undefined macro reference in <expand>"
    if "No such file or directory" in message:
        return "imported macros.xml file not on disk"
    if _MACRO_FAIL_MALFORMED.search(message):
        return "malformed XML in tool file"
    return "other macro error"


def _expanded_attrs(
    path: Path, document: ToolDocument, *, has_macros_flag: bool
) -> tuple[str, str, str | None]:
    """Return ``(profile, tool_id, expansion_failure_reason)`` after expansion."""
    raw_id = document.root.get("id") or ""
    if not has_macros_flag:
        return document.root.get("profile") or _PROFILE_NONE, raw_id, None
    expanded, errors = expand_from_path(path)
    if expanded is None:
        return _PROFILE_EXPANSION_FAILED, raw_id, _expansion_failure_reason(errors)
    expanded_root = expanded.getroot()
    return (
        expanded_root.get("profile") or _PROFILE_NONE,
        expanded_root.get("id") or raw_id,
        None,
    )


def _no_valid_reason(
    path: Path, document: ToolDocument, *, expansion_failure_reason: str | None
) -> str:
    """Categorise why a tool's validity vector is empty (no vendored profile)."""
    if expansion_failure_reason is not None:
        return "(macro expansion failed)"
    declared = document.root.get("profile")
    profile = declared if declared else latest_profile()
    result = validate_tool(path, profile=profile, on_missing="nearest")
    if result.syntax_errors:
        message = result.syntax_errors[0].message
        lowered = message.lower()
        if "character encoding" in lowered or "invalid bytes" in lowered:
            return "invalid character encoding (non-UTF-8 bytes)"
        return "other XML syntax error"
    if not result.errors:
        return "untriaged (no schema error at probed profile)"
    message = result.errors[0].message
    if "is not allowed" in message and "attribute" in message:
        return "XSD does not declare attribute used by tool"
    if "not expected" in message and "Element" in message:
        return "XSD does not allow element under this parent"
    if "is not allowed" in message and "Element" in message:
        return "XSD does not allow element at all"
    if "required but missing" in message:
        return "XSD-required attribute missing on tool element"
    if "facet 'enumeration'" in message:
        return "attribute value outside XSD's enumeration"
    if "not a valid value" in message and (
        "boolean" in message.lower() or "PermissiveBoolean" in message
    ):
        return "invalid boolean ('True'/'False' vs 'true'/'false')"
    if "not a valid value" in message or "facet" in message:
        return "other XSD type / pattern mismatch"
    return "other"


@dataclass
class ToolStats:
    """One tool's contribution to the corpus statistics."""

    profile_raw: str
    profile_expanded: str
    tool_id: str
    newest_valid: str
    validity: list[bool]
    has_macros: bool
    contiguous: bool
    expansion_failure_reason: str | None = None
    no_valid_reason: str | None = None


@dataclass
class _ValidateSweepState:
    """Mutable bookkeeping shared across one ``_validate_main`` invocation."""

    seen_hashes: set[str] = field(default_factory=set)
    sha_to_stats: dict[str, ToolStats] = field(default_factory=dict)
    rows: list[dict[str, str | int | None]] = field(default_factory=list)
    declared_raw_counts: Counter[str] = field(default_factory=Counter)
    declared_expanded_counts: Counter[str] = field(default_factory=Counter)
    newest_valid_counts: Counter[str] = field(default_factory=Counter)
    crosstab: Counter[tuple[str, str]] = field(default_factory=Counter)
    macro_counts: Counter[bool] = field(default_factory=Counter)
    contiguity_counts: Counter[bool] = field(default_factory=Counter)
    source_unique_counts: Counter[str] = field(default_factory=Counter)
    source_duplicate_counts: Counter[str] = field(default_factory=Counter)
    signatures: Counter[str] = field(default_factory=Counter)
    retained_signatures: set[str] = field(default_factory=set)
    retained: list[tuple[str, str, Path, str, str]] = field(default_factory=list)
    expansion_failure_counts: Counter[str] = field(default_factory=Counter)
    no_valid_counts: Counter[str] = field(default_factory=Counter)


def _validity_column(profile: str) -> str:
    """Column name for the per-profile validity flag (e.g. ``valid_26.1``)."""
    return f"valid_{profile}"


def _make_row(
    *,
    display_name: str,
    version: str,
    path: Path,
    repo_dir: Path,
    sha: str,
    stats: ToolStats,
) -> dict[str, str | int | None]:
    """Construct one fine-grained data row from a tool's stats."""
    row: dict[str, str | int | None] = {
        "repo": display_name,
        "version": version,
        "path": str(path.relative_to(repo_dir)),
        "tool_id": stats.tool_id,
        "sha256": sha,
        "profile_raw": stats.profile_raw,
        "profile_expanded": stats.profile_expanded,
        "newest_valid": stats.newest_valid,
        "has_macros": 1 if stats.has_macros else 0,
        "expansion_failure_reason": stats.expansion_failure_reason,
        "no_valid_reason": stats.no_valid_reason,
        # Explicit source ("github"/"toolshed") — only projected into the
        # combined data file (it would be constant in per-source files).
        "source": _row_source(display_name) or "",
    }
    for profile, ok in zip(available_profiles(), stats.validity, strict=True):
        row[_validity_column(profile)] = 1 if ok else 0
    return row


def _validate_exercise(
    path: Path, *, collect_stats: bool = True
) -> tuple[str, str, str, ToolStats | None]:
    """Run the public API over one XML file and check every invariant."""
    try:
        document = parse_tool(path).document
        if document is None or document.root.tag != "tool":
            return "skip", "", "", None
        vector = validity_vector(path)
        profiles = available_profiles()
        newest_valid = next(
            (
                profile
                for profile, ok in zip(
                    reversed(profiles), reversed(vector), strict=True
                )
                if ok
            ),
            _PROFILE_NONE,
        )
        contiguous = is_contiguous(vector)
        if collect_stats:
            has_macros_flag = has_macros(document.root)
            profile_expanded, tool_id, expansion_reason = _expanded_attrs(
                path, document, has_macros_flag=has_macros_flag
            )
            no_valid_reason = (
                _no_valid_reason(
                    path, document, expansion_failure_reason=expansion_reason
                )
                if newest_valid == _PROFILE_NONE
                else None
            )
            stats: ToolStats | None = ToolStats(
                profile_raw=document.root.get("profile") or _PROFILE_NONE,
                profile_expanded=profile_expanded,
                tool_id=tool_id,
                newest_valid=newest_valid,
                validity=vector,
                has_macros=has_macros_flag,
                contiguous=contiguous,
                expansion_failure_reason=expansion_reason,
                no_valid_reason=no_valid_reason,
            )
        else:
            stats = None
        for category, detail in (
            check_immutable(document),
            check_roundtrip(document),
            check_model(document),
            check_parse_load_agree(path),
            check_macro_handling(path, document),
            check_newest_valid_profile(path, vector),
        ):
            if category != "ok":
                return category, detail, category, stats
        if not contiguous:
            run = "".join("1" if ok else "0" for ok in vector)
            return "non-contiguous", f"validity vector: {run}", "non-contiguous", stats
    except Exception as exc:  # noqa: BLE001 — diagnostic sweep: every crash is a finding
        return "crash", traceback.format_exc(), _signature(exc), None
    return "ok", "", "", stats


def _known_signatures(*, regressions_dir: Path) -> set[str]:
    """Signatures already recorded in the regression PROVENANCE.md."""
    path = regressions_dir / "PROVENANCE.md"
    if not path.exists():
        return set()
    known = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- ") and " — " in line:
            known.add(line.rsplit(" — ", 1)[-1].strip())
    return known


def _validate_process_path(
    path: Path,
    *,
    source_label: str,
    display_name: str,
    repo_dir: Path,
    version: str,
    state: _ValidateSweepState,
    combined: bool,
    collect_stats: bool,
    need_sha: bool,
) -> bool:
    """Sweep one XML file and update ``state``; return ``True`` if it counts."""
    if not path.is_file():
        return False
    sha = _sha256_of(path) if need_sha else ""
    if combined and sha in state.seen_hashes:
        state.source_duplicate_counts[source_label] += 1
        cached = state.sha_to_stats.get(sha)
        if cached is not None:
            state.rows.append(
                _make_row(
                    display_name=display_name,
                    version=version,
                    path=path,
                    repo_dir=repo_dir,
                    sha=sha,
                    stats=cached,
                )
            )
        return False
    if combined:
        state.seen_hashes.add(sha)
    status, detail, signature, stats = _validate_exercise(
        path, collect_stats=collect_stats
    )
    if status == "skip":
        return False
    state.source_unique_counts[source_label] += 1
    if stats is not None:
        state.declared_raw_counts[stats.profile_raw] += 1
        state.declared_expanded_counts[stats.profile_expanded] += 1
        state.newest_valid_counts[stats.newest_valid] += 1
        state.crosstab[(stats.profile_expanded, stats.newest_valid)] += 1
        state.macro_counts[stats.has_macros] += 1
        state.contiguity_counts[stats.contiguous] += 1
        if stats.expansion_failure_reason is not None:
            state.expansion_failure_counts[stats.expansion_failure_reason] += 1
        if stats.no_valid_reason is not None:
            state.no_valid_counts[stats.no_valid_reason] += 1
        if combined:
            state.sha_to_stats[sha] = stats
        state.rows.append(
            _make_row(
                display_name=display_name,
                version=version,
                path=path,
                repo_dir=repo_dir,
                sha=sha,
                stats=stats,
            )
        )
    if status == "ok":
        return True
    state.signatures[signature] += 1
    if signature in state.retained_signatures:
        return True
    state.retained_signatures.add(signature)
    dest = _retain(
        path,
        display_name.replace("/", "__"),
        regressions_dir=_VALIDATE_REGRESSIONS,
    )
    relative = path.relative_to(repo_dir)
    state.retained.append((dest.name, display_name, relative, version, signature))
    logger.warning(
        "%s [%s] %s\n  %s\n  retained -> %s\n  %s",
        status.upper(),
        display_name,
        signature,
        relative,
        dest,
        detail.strip().replace("\n", "\n  "),
    )
    return True


def _profile_sort_key(profile: str) -> tuple[int, tuple[int, ...], str]:
    """Sort key: sentinels first, then numeric profiles oldest→newest.

    The raw profile string is the final tiebreak so version-equal but
    string-distinct labels (``20.5`` vs ``20.05``, ``24.0`` vs ``24.00``) get a
    deterministic, total order — otherwise their numeric keys tie and the row
    order depends on dict iteration, churning the regenerated stats. The numeric
    parts are nested in their own tuple so a shorter version that is a numeric
    prefix of another (``24`` vs ``24.0``) never compares an int against the raw
    string.
    """
    if profile == _PROFILE_NONE:
        return (0, (), profile)
    if profile == _PROFILE_EXPANSION_FAILED:
        return (0, (1,), profile)
    parts = profile.split(".")
    if all(part.isdigit() for part in parts):
        return (1, tuple(int(part) for part in parts), profile)
    return (2, (), profile)


def _profile_sort_key_newest_first(profile: str) -> tuple[int, tuple[int, ...], str]:
    """Sort key: numeric profiles newest→oldest, sentinels last.

    Like ``_profile_sort_key`` but reversed for numeric profiles; the raw string
    is still the final tiebreak so version-equal labels are deterministic.
    """
    if profile == _PROFILE_NONE:
        return (2, (), profile)
    if profile == _PROFILE_EXPANSION_FAILED:
        return (2, (1,), profile)
    parts = profile.split(".")
    if all(part.isdigit() for part in parts):
        return (0, tuple(-int(part) for part in parts), profile)
    return (1, (), profile)


def _bar(value: int, max_value: int, *, width: int = 30) -> str:
    """Render an ASCII histogram bar (length scaled to ``max_value``)."""
    if max_value == 0:
        return ""
    blocks = round(value / max_value * width)
    return "█" * blocks


def _format_distribution(title: str, counts: Counter[str], *, total: int) -> list[str]:
    """Render a profile distribution as a markdown table with histogram bars."""
    max_value = max(counts.values(), default=0)
    lines = [
        f"## {title}",
        "",
        "| Profile | Tools | % | Histogram |",
        "|---|---:|---:|---|",
    ]
    for profile in sorted(counts, key=_profile_sort_key):
        value = counts[profile]
        pct = value / total * 100 if total else 0
        lines.append(f"| {profile} | {value:,} | {pct:.1f}% | {_bar(value, max_value)} |")
    return lines


def _format_crosstab(crosstab: Counter[tuple[str, str]]) -> list[str]:
    """Render the declared × newest-valid cross-tab as a markdown table."""
    declared = sorted({d for d, _ in crosstab}, key=_profile_sort_key)
    newest = sorted({n for _, n in crosstab}, key=_profile_sort_key_newest_first)
    lines = [
        "## Declared (post-expansion) × newest-valid (cross-tab)",
        "",
        "Rows: declared profile *after macro expansion* (oldest first). "
        "Columns: newest validating profile (newest first). Read across a "
        "row to see where tools at a given declared profile actually end up.",
        "",
    ]
    lines.append("| declared \\\\ newest | " + " | ".join(newest) + " |")
    lines.append("|---|" + "|".join(["---:"] * len(newest)) + "|")
    for d in declared:
        row = [d, *(f"{crosstab.get((d, n), 0):,}" for n in newest)]
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _format_sources_table(unique: Counter[str], duplicates: Counter[str]) -> list[str]:
    """Render the combined-mode per-source breakdown as a markdown table."""
    lines = [
        "## Sources",
        "",
        "Per-source contribution to the deduplicated combined corpus. "
        "*Unique tools* are the ones whose sha256 hadn't been seen before "
        "(github is walked first, so a tool that exists in both sources is "
        "credited to github); *duplicates dropped* are tools whose bytes "
        "matched an earlier-seen tool from any source.",
        "",
        "| Source | Unique tools | Duplicates dropped |",
        "|---|---:|---:|",
    ]
    total_unique = 0
    total_duplicates = 0
    for source in _COMBINED_SUB_SOURCES:
        u = unique.get(source, 0)
        d = duplicates.get(source, 0)
        total_unique += u
        total_duplicates += d
        lines.append(f"| {source} | {u:,} | {d:,} |")
    lines.append(f"| **total** | **{total_unique:,}** | **{total_duplicates:,}** |")
    return lines


def _failure_slug(reason: str) -> str:
    """Return a filesystem- and URL-friendly slug for a failure category."""
    slug = re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-")
    return slug or "unknown"


def _stamp_presence(rows: list[dict[str, str | int | None]]) -> None:
    """Set ``presence`` on every row to ``github_only`` / ``toolshed_only`` / ``both``."""
    by_tool_id: dict[str, set[str]] = {}
    for row in rows:
        tool_id = row.get("tool_id")
        if not isinstance(tool_id, str) or not tool_id:
            continue
        source = _row_source(row.get("repo"))
        if source is None:
            continue
        by_tool_id.setdefault(tool_id, set()).add(source)
    for row in rows:
        tool_id = row.get("tool_id")
        if not isinstance(tool_id, str) or not tool_id:
            row["presence"] = ""
            continue
        sources = by_tool_id.get(tool_id, set())
        if {"github", "toolshed"} <= sources:
            row["presence"] = "both"
        elif sources == {"github"}:
            row["presence"] = "github_only"
        elif sources == {"toolshed"}:
            row["presence"] = "toolshed_only"
        else:
            row["presence"] = ""


def _format_presence_failures(rows: list[dict[str, str | int | None]]) -> list[str]:
    """Render the ``Failures by source presence`` section for the combined view."""
    unique = _unique_by_sha(rows)
    failures = [
        row
        for row in unique
        if row.get("expansion_failure_reason") or row.get("no_valid_reason")
    ]
    github_failures = [
        row for row in failures if _row_source(row.get("repo")) == "github"
    ]
    toolshed_failures = [
        row for row in failures if _row_source(row.get("repo")) == "toolshed"
    ]
    gh_both = sum(1 for row in github_failures if row.get("presence") == "both")
    gh_only = len(github_failures) - gh_both
    ts_both = sum(1 for row in toolshed_failures if row.get("presence") == "both")
    ts_only = len(toolshed_failures) - ts_both

    def _row(label: str, count: int, total: int) -> str:
        pct = 100 * count / total if total else 0
        return f"| {label} | {count:,} | {pct:.1f}% |"

    lines = [
        "## Failures by source presence",
        "",
        (
            f"Of the {len(failures):,} distinct failing tools (sha256-deduped), "
            "broken down by whether the tool's logical identity (its "
            "`tool_id`) also appears in the other corpus."
        ),
        "",
        "### Failing on github",
        "",
        "| | Tools | % of github failures |",
        "|---|---:|---:|",
    ]
    if github_failures:
        lines.append(_row("github-only", gh_only, len(github_failures)))
        lines.append(_row("github + toolshed twin", gh_both, len(github_failures)))
    else:
        lines.append("| _(no github failures)_ |  |  |")
    lines.extend(
        [
            "",
            "### Failing on toolshed",
            "",
            "| | Tools | % of toolshed failures |",
            "|---|---:|---:|",
        ]
    )
    if toolshed_failures:
        lines.append(_row("toolshed-only", ts_only, len(toolshed_failures)))
        lines.append(_row("toolshed + github sibling", ts_both, len(toolshed_failures)))
    else:
        lines.append("| _(no toolshed failures)_ |  |  |")
    return lines


def _format_reason_table(
    title: str,
    intro: str,
    counts: Counter[str],
    *,
    link_base: str | None = None,
) -> list[str]:
    """Render a failure-reason breakdown as a markdown table."""
    lines = [f"## {title}", "", intro, "", "| Reason | Tools | % |", "|---|---:|---:|"]
    total = sum(counts.values())
    if total == 0:
        lines.append("| _(none)_ |  |  |")
        return lines
    for reason in sorted(counts, key=lambda r: (-counts[r], r)):
        n = counts[reason]
        label = (
            f"[{reason}]({link_base}/{_failure_slug(reason)}.md)"
            if link_base is not None
            else reason
        )
        lines.append(f"| {label} | {n:,} | {n / total * 100:.1f}% |")
    lines.append(f"| **total** | **{total:,}** | **100.0%** |")
    return lines


def _tool_source_url(repo: str, version: str, path: str) -> str | None:
    """Return a clickable URL to ``path`` in ``repo`` at ``version``, or ``None``."""
    if version == _UNKNOWN:
        return None
    if "/" in repo:
        return f"{_TOOLSHED_VIEW_URL}/{repo}"
    sources = dict(_corpus_sources())
    clone_url = sources.get(repo)
    if clone_url is None:
        return None
    base = clone_url.removesuffix(".git").rstrip("/")
    if "github.com/" in base:
        return f"{base}/blob/{version}/{path}"
    if "gitlab.com/" in base:
        return f"{base}/-/blob/{version}/{path}"
    return None


def _write_failure_details(
    rows: list[dict[str, str | int | None]],
    *,
    output_dir: Path,
) -> None:
    """Write per-failure-mode markdown indexes under ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    github_siblings_unsorted: dict[str, set[str]] = {}
    for row in rows:
        repo = row.get("repo")
        tool_id = row.get("tool_id")
        if not isinstance(repo, str) or not isinstance(tool_id, str):
            continue
        if "/" in repo:
            continue
        github_siblings_unsorted.setdefault(tool_id, set()).add(repo)
    github_siblings: dict[str, tuple[str, ...]] = {
        tool_id: tuple(sorted(repos))
        for tool_id, repos in github_siblings_unsorted.items()
    }
    by_reason: dict[str, list[dict[str, str | int | None]]] = {}
    for row in _unique_by_sha(rows):
        for reason in (
            row.get("expansion_failure_reason"),
            row.get("no_valid_reason"),
        ):
            if isinstance(reason, str):
                by_reason.setdefault(reason, []).append(row)
    index_lines = [
        "# Failure-mode tool indexes",
        "",
        "One file per failure-reason category. Regenerated by every full "
        "`corpus_check.py validate --source combined` run.",
        "",
        "| Category | Tools | File |",
        "|---|---:|---|",
    ]
    for reason in sorted(by_reason, key=lambda r: (-len(by_reason[r]), r)):
        slug = _failure_slug(reason)
        index_lines.append(
            f"| {reason} | {len(by_reason[reason])} | [{slug}.md]({slug}.md) |"
        )
    (output_dir / "README.md").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8"
    )
    for reason, reason_rows in by_reason.items():
        slug = _failure_slug(reason)
        lines = [
            f"# {reason}",
            "",
            f"{len(reason_rows)} unique tool(s) fall into this category.",
            "",
            "| Repository | tool_id | Path | Version | Source |",
            "|---|---|---|---|---|",
        ]
        for row in sorted(reason_rows, key=lambda r: (str(r["repo"]), str(r["path"]))):
            repo = str(row["repo"])
            version = str(row["version"])
            path = str(row["path"])
            tool_id = str(row["tool_id"])
            url = _tool_source_url(repo, version, path)
            link = f"[view]({url})" if url else "—"
            repo_cell = repo
            if (
                "/" in repo
                and row.get("presence") == "both"
                and tool_id in github_siblings
            ):
                repo_cell = (
                    f"{repo} (also in github: {', '.join(github_siblings[tool_id])})"
                )
            lines.append(
                f"| {repo_cell} | `{tool_id}` | `{path}` | `{version[:12]}` | {link} |"
            )
        (output_dir / f"{slug}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )


def _format_binary_table(
    title: str, true_label: str, false_label: str, *, counts: Counter[bool]
) -> list[str]:
    """Render a true/false counter as a 2-row markdown table."""
    true_count = counts.get(True, 0)
    false_count = counts.get(False, 0)
    total = true_count + false_count
    lines = [f"## {title}", "", "| | Tools | % |", "|---|---:|---:|"]
    if total == 0:
        lines.append("| _(no data)_ |  |  |")
        return lines
    true_pct = true_count / total * 100
    false_pct = false_count / total * 100
    lines.append(f"| {true_label} | {true_count:,} | {true_pct:.1f}% |")
    lines.append(f"| {false_label} | {false_count:,} | {false_pct:.1f}% |")
    return lines


def _tsv_safe(value: str) -> str:
    """Replace tab/newline/CR with a single space — defensive TSV escape."""
    return value.replace("\t", " ").replace("\n", " ").replace("\r", " ")


def _write_corpus_data(
    *,
    rows: list[dict[str, str | int | None]],
    source: str,
    include_profile_columns: bool,
) -> None:
    """Write the fine-grained per-tool data as both JSON and TSV."""
    columns: tuple[str, ...] = _FINE_GRAINED_BASE_COLUMNS
    if include_profile_columns:
        columns = (
            columns
            + _FINE_GRAINED_PROFILE_COLUMNS
            + tuple(_validity_column(profile) for profile in available_profiles())
        )
    _CORPUS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    basename = _CORPUS_DATA_BASENAMES[source]
    projected = [{column: row[column] for column in columns} for row in rows]
    (_CORPUS_DATA_DIR / f"{basename}.json").write_text(
        json.dumps(projected, indent=2) + "\n", encoding="utf-8"
    )
    lines = ["\t".join(columns)]
    lines.extend(
        "\t".join(
            _tsv_safe("" if record[column] is None else str(record[column]))
            for column in columns
        )
        for record in projected
    )
    (_CORPUS_DATA_DIR / f"{basename}.tsv").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _validate_write_stats(
    *,
    stats_file: Path,
    source: str,
    repos: list[tuple[str, str, int]],
    declared_raw_counts: Counter[str],
    declared_expanded_counts: Counter[str],
    newest_valid_counts: Counter[str],
    crosstab: Counter[tuple[str, str]],
    macro_counts: Counter[bool],
    contiguity_counts: Counter[bool],
    include_raw: bool,
    total: int,
    source_unique_counts: Counter[str],
    source_duplicate_counts: Counter[str],
    expansion_failure_counts: Counter[str],
    no_valid_counts: Counter[str],
    rows: list[dict[str, str | int | None]] | None,
) -> None:
    """Write the corpus-validate statistics artifact to ``docs/``."""
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    if source == "combined":
        header_para = (
            f"Generated by `python -m scripts.corpus_check validate --source combined` on "
            f"{date.today().isoformat()}. Swept {total:,} unique tools across "
            f"{', '.join(_COMBINED_SUB_SOURCES)}, deduplicated by sha256 of "
            f"each tool's bytes."
        )
        regen_para = (
            "This file is regenerated by every full run of "
            "`corpus_check.py validate --source combined` unless `--no-stats` is "
            "given. The per-source artifacts (`corpus_stats.md`, "
            "`toolshed_corpus_stats.md`) are not refreshed by this run."
        )
    else:
        header_para = (
            f"Generated by `python -m scripts.corpus_check validate --source {source}` on "
            f"{date.today().isoformat()}. Swept {total:,} tools across "
            f"{len(repos):,} repositories."
        )
        regen_para = (
            "This file is regenerated by every full run of "
            "`corpus_check.py validate` for this source unless `--no-stats` is given; "
            "partial sweeps (`--limit` or `--repo`) do not regenerate it."
        )
    lines: list[str] = [
        f"# Corpus statistics — {source}",
        "",
        header_para,
        "",
        regen_para,
        "",
    ]
    if source == "combined":
        lines.extend(
            _format_sources_table(source_unique_counts, source_duplicate_counts)
        )
    else:
        lines.append("## Repositories")
        lines.append("")
        lines.append("| Repository | Version | Tools |")
        lines.append("|---|---|---:|")
        for name, commit, count in sorted(repos):
            lines.append(f"| {name} | `{commit[:12]}` | {count:,} |")
    lines.append("")
    lines.extend(
        _format_distribution(
            "Declared profile distribution (post macro expansion)",
            declared_expanded_counts,
            total=total,
        )
    )
    lines.append("")
    if include_raw:
        lines.extend(
            _format_distribution(
                "Declared profile distribution (raw, pre-expansion)",
                declared_raw_counts,
                total=total,
            )
        )
        lines.append("")
    lines.extend(
        _format_distribution(
            "Newest valid profile distribution", newest_valid_counts, total=total
        )
    )
    lines.append("")
    lines.extend(_format_crosstab(crosstab))
    lines.append("")
    if source == "combined":
        link_base = f"corpus_data/{_FAILURE_DETAILS_SUBDIR}"
        lines.extend(
            _format_reason_table(
                "Macro-expansion failure reasons",
                "Tools whose macros could not be expanded by "
                "`galaxy.util.xml_macros`. These are properties of the tool "
                "itself (or its `<import>`s), not library bugs.",
                expansion_failure_counts,
                link_base=link_base,
            )
        )
        lines.append("")
        lines.extend(
            _format_reason_table(
                "Tools with no valid vendored profile — reason breakdown",
                "Tools whose validity vector is empty (no vendored XSD accepts them).",
                no_valid_counts,
                link_base=link_base,
            )
        )
        lines.append("")
        if rows is not None:
            lines.extend(_format_presence_failures(rows))
            lines.append("")
    lines.extend(
        _format_binary_table("Macro usage", "Uses macros", "Macro-free", counts=macro_counts)
    )
    lines.append("")
    lines.extend(
        _format_binary_table(
            "Validity-vector contiguity",
            "Contiguous valid range",
            "Non-contiguous",
            counts=contiguity_counts,
        )
    )
    lines.append("")
    stats_file.write_text("\n".join(lines), encoding="utf-8")


def _validate_main(argv: list[str]) -> int:
    """Sweep one corpus source, report findings, and retain regression fixtures."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.corpus_check validate",
        description=(
            "Sweep a Galaxy tool corpus source (github, toolshed, or "
            "combined) through galaxy-tool-xml."
        ),
    )
    parser.add_argument(
        "--source",
        choices=_SOURCES,
        default="github",
        help=(
            "which corpus to sweep: 'github' (default) walks the "
            "repositories listed in corpus_sources.json; 'toolshed' walks "
            "corpus/galaxy-toolshed/ (populate first via "
            "scripts/fetch_toolshed.py); 'combined' deduplicates by sha256"
        ),
    )
    parser.add_argument(
        "--repo",
        help="sweep only this repository (by name); --source github only",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="stop after N tools total (0 sweeps everything)",
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="don't regenerate the corpus stats artifact for the selected source",
    )
    parser.add_argument(
        "--include-raw-profile",
        action="store_true",
        help="also include a raw (pre-macro-expansion) profile distribution",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.repo is not None and args.source != "github":
        logger.error(
            "--repo is only supported with --source github, not %r", args.source
        )
        return 1
    if args.source == "github" and args.repo is not None:
        known_names = {name for name, _ in _corpus_sources()}
        if args.repo not in known_names:
            known = ", ".join(sorted(known_names))
            logger.error("unknown --repo %r; known: %s", args.repo, known)
            return 1

    _CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
    stats_file = _VALIDATE_STATS_FILES[args.source]
    collect_stats = not (args.no_stats or args.limit or args.repo)
    combined = args.source == "combined"
    sources_to_walk = _COMBINED_SUB_SOURCES if combined else (args.source,)
    if "toolshed" in sources_to_walk and not _TOOLSHED_ROOT.exists():
        logger.error(
            "no toolshed corpus at %s; run scripts/fetch_toolshed.py first",
            _TOOLSHED_ROOT.relative_to(_REPO_ROOT),
        )
        return 1
    tools = 0
    repo_tool_counts: list[tuple[str, str, int]] = []
    state = _ValidateSweepState(
        retained_signatures=_known_signatures(regressions_dir=_VALIDATE_REGRESSIONS)
    )
    need_sha = combined or collect_stats
    for source_label, display_name, repo_dir, version in _iter_sources(
        sources_to_walk, repo_filter=args.repo
    ):
        repo_tool_count = 0
        for path in sorted(_iter_tool_xmls(repo_dir)):
            if args.limit and tools >= args.limit:
                break
            if not _validate_process_path(
                path,
                source_label=source_label,
                display_name=display_name,
                repo_dir=repo_dir,
                version=version,
                state=state,
                combined=combined,
                collect_stats=collect_stats,
                need_sha=need_sha,
            ):
                continue
            tools += 1
            repo_tool_count += 1
            if tools % 500 == 0:
                logger.info("... %d tools", tools)
        repo_tool_counts.append((display_name, version, repo_tool_count))
        if args.limit and tools >= args.limit:
            break

    logger.info("swept %d tools", tools)
    for sig, count in state.signatures.most_common():
        logger.info("  %6d  %s", count, sig)
    if "non-contiguous" in state.signatures:
        logger.info(
            "note: non-contiguous validity is an expected real-world property, "
            "not a library bug — newest_valid_profile handles it."
        )
    if state.retained:
        _append_provenance(state.retained, regressions_dir=_VALIDATE_REGRESSIONS)
        logger.info(
            "retained %d new regression fixture(s) under %s",
            len(state.retained),
            _VALIDATE_REGRESSIONS,
        )
    stats_path = stats_file.relative_to(_REPO_ROOT)
    data_basename = _CORPUS_DATA_BASENAMES[args.source]
    data_dir_rel = _CORPUS_DATA_DIR.relative_to(_REPO_ROOT)
    if args.no_stats:
        pass
    elif args.limit or args.repo:
        logger.info(
            "corpus stats not regenerated: partial sweep (--limit or --repo). "
            "Run the full sweep to refresh %s and %s/%s.{json,tsv}.",
            stats_path,
            data_dir_rel,
            data_basename,
        )
    else:
        if args.source == "combined":
            _stamp_presence(state.rows)
        _validate_write_stats(
            stats_file=stats_file,
            source=args.source,
            repos=repo_tool_counts,
            declared_raw_counts=state.declared_raw_counts,
            declared_expanded_counts=state.declared_expanded_counts,
            newest_valid_counts=state.newest_valid_counts,
            crosstab=state.crosstab,
            macro_counts=state.macro_counts,
            contiguity_counts=state.contiguity_counts,
            include_raw=args.include_raw_profile,
            total=tools,
            source_unique_counts=state.source_unique_counts,
            source_duplicate_counts=state.source_duplicate_counts,
            expansion_failure_counts=state.expansion_failure_counts,
            no_valid_counts=state.no_valid_counts,
            rows=state.rows if args.source == "combined" else None,
        )
        _write_corpus_data(
            rows=state.rows,
            source=args.source,
            include_profile_columns=args.source == "combined",
        )
        logger.info("corpus stats -> %s", stats_path)
        logger.info("corpus data  -> %s/%s.{json,tsv}", data_dir_rel, data_basename)
        if args.source == "combined":
            failures_dir = _CORPUS_DATA_DIR / _FAILURE_DETAILS_SUBDIR
            _write_failure_details(rows=state.rows, output_dir=failures_dir)
            logger.info(
                "failure details -> %s/", failures_dir.relative_to(_REPO_ROOT)
            )
    return 0


# =============================================================================
# fmt subcommand
# =============================================================================

from galaxy_tool_refactor_rules.meta import RuleMeta  # noqa: E402
from galaxy_tool_refactor_rules.reference import (  # noqa: E402
    render_rule_reference_table,
)
from galaxy_tool_xml_codemod.catalog import coded_codemods  # noqa: E402
from galaxy_tool_xml_fmt.detect import detect_tool_document  # noqa: E402
from galaxy_tool_xml_fmt.edits import apply_edits  # noqa: E402
from galaxy_tool_xml_fmt.format import all_rules  # noqa: E402
from galaxy_tool_xml_fmt.rules import Rule  # noqa: E402
from galaxy_tool_xml_fmt.serializer import to_bytes  # noqa: E402


@dataclass
class _FormatOutcome:
    """One tool's outcome through the format pipeline."""

    pass1_edits: Counter[str]
    pass2_edits: Counter[str]


@dataclass
class _FmtSweepState:
    """Mutable bookkeeping for one ``_fmt_main`` invocation."""

    parsed: int = 0
    non_tool: int = 0
    unparseable: int = 0
    validated: int = 0
    formatted_ok: int = 0
    idempotent: int = 0
    non_idempotent: int = 0
    crashed: int = 0
    pass1_tools_per_rule: Counter[str] = field(default_factory=Counter)
    pass1_edits_per_rule: Counter[str] = field(default_factory=Counter)
    pass2_tools_per_rule: Counter[str] = field(default_factory=Counter)
    pass2_edits_per_rule: Counter[str] = field(default_factory=Counter)
    signatures: Counter[str] = field(default_factory=Counter)
    known_fixture_paths: set[tuple[str, str]] = field(default_factory=set)
    retained: list[tuple[str, str, Path, str, str]] = field(default_factory=list)


def _format_with_stats(document: ToolDocument) -> tuple[bytes, Counter[str]]:
    """Run the formatter pipeline and return ``(bytes, per-rule edit counts)``."""
    tree = document.tree
    rule_edits: Counter[str] = Counter()
    for rule_cls in all_rules():
        edits = list(rule_cls().apply(tree))
        if edits:
            rule_edits[rule_cls.meta.code] += len(edits)
        apply_edits(edits)
    return to_bytes(tree), rule_edits


def _fmt_in_scope(path: Path, *, profile: str | None) -> bool:
    """Whether a parsed ``<tool>`` belongs in fmt's sweep population.

    fmt only sweeps *valid* tools — running the formatter over never-valid XML
    amplifies noise (fmt ``docs/decisions.md`` §D9). ``profile is None`` (the
    default) gates on validity under **any** vendored profile
    (``newest_valid_profile`` finds one); a specific ``profile`` pins the gate to
    validation at exactly that release (the legacy ``--profile`` behaviour). §D9
    anticipated relaxing the original latest-only cohort to any-valid. Shared by
    the ``fmt`` and ``rules`` sweeps — same fmt-population policy, one home.
    """
    if profile is None:
        return newest_valid_profile(path) is not None
    return validate_tool(path, profile=profile).valid


def _fmt_exercise(
    path: Path, *, profile: str | None
) -> tuple[str, str, str, _FormatOutcome | None]:
    """Run the formatter over one XML file and check every invariant."""
    try:
        result = parse_tool(path)
        if result.document is None:
            return "skip-unparseable", "", "", None
        if result.document.root.tag != "tool":
            return "skip-non-tool", "", "", None
        if not _fmt_in_scope(path, profile=profile):
            return "skip-no-validate", "", "", None
        document_one = parse_tool(path).document
        if document_one is None:
            return "skip-unparseable", "", "", None
        # Detect/format parity: the cosmetic detect phase must report a violation
        # exactly when formatting changes the document's net bytes. Run detect
        # (non-mutating) on the pristine tree, then format and compare.
        before_bytes = to_bytes(document_one.tree)
        detected = detect_tool_document(document_one)
        pass1_bytes, pass1_edits = _format_with_stats(document_one)
        if bool(detected) != (pass1_bytes != before_bytes):
            verb = "changed" if pass1_bytes != before_bytes else "did not change"
            return (
                "detect-parity-mismatch",
                "detect-parity:fmt",
                f"detect reported {len(detected)} violation(s) but format "
                f"{verb} the document",
                None,
            )
        document_two = load_tool(pass1_bytes)
        pass2_bytes, pass2_edits = _format_with_stats(document_two)
        outcome = _FormatOutcome(
            pass1_edits=pass1_edits,
            pass2_edits=pass2_edits,
        )
        if pass1_bytes != pass2_bytes:
            culprits = ",".join(sorted(pass2_edits)) if pass2_edits else "no-edits"
            sig = f"non-idempotent:{culprits}"
            return (
                "non-idempotent",
                sig,
                _fmt_byte_diff_excerpt(pass1_bytes, pass2_bytes),
                outcome,
            )
        return "ok", "", "", outcome
    except Exception as exc:  # noqa: BLE001 — diagnostic sweep: every crash is a finding
        return "crash", _signature(exc), traceback.format_exc(), None


def _fmt_byte_diff_excerpt(once: bytes, twice: bytes, *, span: int = 80) -> str:
    """Excerpt around the first byte where ``once`` and ``twice`` diverge."""
    limit = min(len(once), len(twice))
    for index in range(limit):
        if once[index] != twice[index]:
            start = max(0, index - span // 2)
            end_once = min(len(once), index + span // 2)
            end_twice = min(len(twice), index + span // 2)
            once_excerpt = once[start:end_once].decode("utf-8", errors="replace")
            twice_excerpt = twice[start:end_twice].decode("utf-8", errors="replace")
            return (
                f"first diff at byte {index}\n"
                f"  pass1: {once_excerpt!r}\n"
                f"  pass2: {twice_excerpt!r}"
            )
    return f"length differs: pass1={len(once)} pass2={len(twice)}"


def _fmt_known_fixture_paths(*, regressions_dir: Path) -> set[tuple[str, str]]:
    """Return ``(repo, relative_path)`` pairs already recorded in PROVENANCE.md."""
    path = regressions_dir / "PROVENANCE.md"
    if not path.exists():
        return set()
    known: set[tuple[str, str]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        parts = line.split(" — ")
        if len(parts) < 3:
            continue
        repo_field = parts[1]
        if "`" not in repo_field:
            continue
        display_name, _, rel_with_backtick = repo_field.partition("`")
        relative_path = rel_with_backtick.rstrip("`").split("` @ ", 1)[0]
        known.add((display_name.strip(), relative_path))
    return known


def _fmt_record_rule_stats(state: _FmtSweepState, outcome: _FormatOutcome) -> None:
    """Roll an outcome's per-rule edit counters into the sweep totals."""
    for rule_code, count in outcome.pass1_edits.items():
        state.pass1_tools_per_rule[rule_code] += 1
        state.pass1_edits_per_rule[rule_code] += count
    for rule_code, count in outcome.pass2_edits.items():
        state.pass2_tools_per_rule[rule_code] += 1
        state.pass2_edits_per_rule[rule_code] += count


def _fmt_process_path(
    path: Path,
    *,
    display_name: str,
    repo_dir: Path,
    version: str,
    profile: str | None,
    state: _FmtSweepState,
) -> bool:
    """Sweep one XML file and update ``state``; return ``True`` if it counted as a tool."""
    if not path.is_file():
        return False
    status, signature, detail, outcome = _fmt_exercise(path, profile=profile)
    if status == "skip-unparseable":
        state.unparseable += 1
        return False
    if status == "skip-non-tool":
        state.non_tool += 1
        return False
    state.parsed += 1
    if status == "skip-no-validate":
        return False
    state.validated += 1
    if outcome is not None:
        state.formatted_ok += 1
        _fmt_record_rule_stats(state, outcome)
    if status == "ok":
        state.idempotent += 1
        return True
    if status == "non-idempotent":
        state.non_idempotent += 1
    elif status == "crash":
        state.crashed += 1
    state.signatures[signature] += 1
    relative = path.relative_to(repo_dir)
    if (display_name, str(relative)) in state.known_fixture_paths:
        return True
    state.known_fixture_paths.add((display_name, str(relative)))
    dest = _retain(
        path,
        display_name.replace("/", "__"),
        regressions_dir=_FMT_REGRESSIONS,
    )
    state.retained.append((dest.name, display_name, relative, version, signature))
    logger.warning(
        "%s [%s] %s\n  %s\n  retained -> %s\n  %s",
        status.upper(),
        display_name,
        signature,
        relative,
        dest,
        detail.strip().replace("\n", "\n  "),
    )
    return True


def _gtx_reference_table(intro: str, /) -> list[str]:
    """Render the cross-tier GTX rule glossary (fmt + codemod) under *intro*.

    fmt-tier rules (``all_rules()``) and codemod-tier rules
    (``coded_codemods()``) share the ``RuleMeta`` vocabulary, so the glossary is
    generated from live metadata rather than hand-maintained. The IUC advisory
    checks (tier 3.5) carry their own codes and are reported separately on the
    ``check`` sweep page, so they are not part of this GTX glossary.
    """
    entries: list[tuple[RuleMeta, str]] = [
        (rule_cls.meta, "fmt") for rule_cls in all_rules()
    ]
    entries.extend((codemod_cls.meta, "codemod") for codemod_cls in coded_codemods())
    return ["## Rule reference", "", intro, "", *render_rule_reference_table(entries)]


def _fmt_format_rule_reference_table() -> list[str]:
    """The GTX glossary for the fmt stat page (codemod rows are reference-only)."""
    return _gtx_reference_table(
        "What each GTX rule does, across both tiers. *fmt*-tier rules are the "
        "cosmetic rules swept on this page; *codemod*-tier rules are structural "
        "transforms (run by the canonical pipeline) listed here for reference — "
        "they do not fire in this sweep, so they do not appear in the trigger "
        "tables below."
    )


def _fmt_format_rule_table(
    title: str,
    intro: str,
    *,
    tools_per_rule: Counter[str],
    edits_per_rule: Counter[str],
) -> list[str]:
    """Render a per-rule trigger table as markdown."""
    lines = [
        f"## {title}",
        "",
        intro,
        "",
        "| Rule | Tools touched | Edits emitted |",
        "|---|---:|---:|",
    ]
    if not tools_per_rule:
        lines.append("| _(no rule fired)_ |  |  |")
        return lines
    for rule_code in sorted(tools_per_rule):
        lines.append(
            f"| {rule_code} | {tools_per_rule[rule_code]:,} | "
            f"{edits_per_rule[rule_code]:,} |"
        )
    return lines


def _fmt_format_repos_section(
    repos: list[tuple[str, str, int]], *, source: str
) -> list[str]:
    """Render the repositories section.

    For ``github`` (a small, named set) list every repo with its pinned commit.
    For ``toolshed`` / ``combined`` that would be thousands of single-tool
    repositories, so emit a compact per-source rollup instead (toolshed display
    names carry an ``owner/`` slash; github names do not). The full per-repo
    list stays available via ``--source github``.
    """
    if source == "github":
        lines = [
            "## Repositories",
            "",
            "| Repository | Version | Tool documents |",
            "|---|---|---:|",
        ]
        for name, commit, count in sorted(repos):
            lines.append(f"| {name} | `{commit[:12]}` | {count:,} |")
        return lines
    github = [(name, count) for name, _version, count in repos if "/" not in name]
    toolshed = [(name, count) for name, _version, count in repos if "/" in name]
    return [
        "## Repositories",
        "",
        (
            "Per-source rollup — the combined sweep spans thousands of "
            "single-tool toolshed repositories, so the full per-repo list is "
            "omitted here (run `--source github` for it)."
        ),
        "",
        "| Source | Repositories | Tool documents |",
        "|---|---:|---:|",
        f"| github | {len(github):,} | {sum(count for _name, count in github):,} |",
        f"| toolshed | {len(toolshed):,} | {sum(count for _name, count in toolshed):,} |",
    ]


def _fmt_format_summary_table(state: _FmtSweepState) -> list[str]:
    """Render the headline counts as a markdown table."""
    return [
        "## Sweep summary",
        "",
        "| Outcome | Tools |",
        "|---|---:|",
        f"| Parsed as `<tool>` | {state.parsed:,} |",
        f"| Unparseable XML (skipped) | {state.unparseable:,} |",
        f"| Non-tool root (skipped) | {state.non_tool:,} |",
        f"| Validated (in fmt scope) | {state.validated:,} |",
        f"| Formatted without crashing | {state.formatted_ok:,} |",
        f"| **Idempotent** | **{state.idempotent:,}** |",
        f"| Non-idempotent | {state.non_idempotent:,} |",
        f"| Crashed | {state.crashed:,} |",
    ]


def _fmt_format_signatures_table(signatures: Counter[str]) -> list[str]:
    """Render the dedup'd failure signatures as a markdown table."""
    lines = ["## Failure signatures", ""]
    if not signatures:
        lines.append("_(no failures)_")
        return lines
    lines.extend(["| Signature | Occurrences |", "|---|---:|"])
    for sig, count in signatures.most_common():
        lines.append(f"| `{sig}` | {count} |")
    return lines


def _fmt_write_stats(
    *,
    profile: str | None,
    source: str,
    repos: list[tuple[str, str, int]],
    state: _FmtSweepState,
) -> None:
    """Write the corpus-format statistics artifact to ``docs/``."""
    _FMT_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    gate = f"profile `{profile}`" if profile else "any vendored profile"
    source_note = (
        "the combined corpus (github + toolshed, sha256-deduplicated)"
        if source == "combined"
        else f"the {source} corpus"
    )
    lines: list[str] = [
        "# Corpus format statistics",
        "",
        (
            f"Generated by `python -m scripts.corpus_check fmt` on "
            f"{date.today().isoformat()} over {source_note}, gated on "
            f"validation under {gate}. "
            f"Swept {state.parsed:,} tool documents across "
            f"{len(repos):,} repositories; "
            f"{state.validated:,} validated ({gate}) and were "
            f"format-checked."
        ),
        "",
        (
            "Regenerated by every full run of `corpus_check.py fmt` unless "
            "`--no-stats` is given; partial sweeps (`--limit` or `--repo`) "
            "do not regenerate it."
        ),
        "",
    ]
    lines.extend(_fmt_format_repos_section(repos, source=source))
    lines.append("")
    lines.extend(_fmt_format_summary_table(state))
    lines.append("")
    lines.extend(_fmt_format_rule_reference_table())
    lines.append("")
    lines.extend(
        _fmt_format_rule_table(
            "Pass 1 rule triggers (raw input → canonical)",
            (
                "Per-rule counts for the first format pass. *Tools touched* "
                "is the number of validated tools where the rule emitted at "
                "least one `Edit`; *edits emitted* is the literal count of "
                "`Edit` objects yielded."
            ),
            tools_per_rule=state.pass1_tools_per_rule,
            edits_per_rule=state.pass1_edits_per_rule,
        )
    )
    lines.append("")
    lines.extend(
        _fmt_format_rule_table(
            "Pass 2 rule triggers (canonical → canonical, must be empty)",
            (
                "Per-rule counts for the idempotence pass. A canonical-form "
                "input should produce no further edits; any rule that fires "
                "here is the source of a non-idempotence."
            ),
            tools_per_rule=state.pass2_tools_per_rule,
            edits_per_rule=state.pass2_edits_per_rule,
        )
    )
    lines.append("")
    lines.extend(_fmt_format_signatures_table(state.signatures))
    lines.append("")
    _FMT_STATS_FILE.write_text("\n".join(lines), encoding="utf-8")


def _fmt_main(argv: list[str]) -> int:
    """Sweep the corpus through the formatter and retain regression fixtures."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.corpus_check fmt",
        description=(
            "Sweep the Galaxy tool corpus through galaxy-tool-xml-fmt and "
            "check format → re-format idempotence."
        ),
    )
    parser.add_argument(
        "--repo",
        help="sweep only this repository (by name from corpus_sources.json)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="stop after N tools total (0 sweeps everything)",
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="don't regenerate docs/corpus_format_stats.md",
    )
    parser.add_argument(
        "--source",
        choices=("github", "toolshed", "combined"),
        default="combined",
        help=(
            "corpus to sweep: 'github', 'toolshed', or 'combined' (both, "
            "sha256-deduplicated). Default: combined."
        ),
    )
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "gating profile: if given, sweep only tools that validate under "
            "this exact profile; default (omitted) sweeps every tool that "
            "validates under ANY vendored profile (fmt decisions §D9)"
        ),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.repo is not None and args.source != "github":
        logger.error("--repo is only supported with --source github, not %r", args.source)
        return 1
    if args.repo is not None:
        known_names = {name for name, _ in _corpus_sources()}
        if args.repo not in known_names:
            known = ", ".join(sorted(known_names))
            logger.error("unknown --repo %r; known: %s", args.repo, known)
            return 1

    sources = ("github", "toolshed") if args.source == "combined" else (args.source,)
    if "toolshed" in sources and not _TOOLSHED_ROOT.exists():
        logger.error(
            "no toolshed corpus at %s; populate it via scripts/fetch_toolshed.py",
            _TOOLSHED_ROOT.relative_to(_REPO_ROOT),
        )
        return 1

    _CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
    state = _FmtSweepState(
        known_fixture_paths=_fmt_known_fixture_paths(regressions_dir=_FMT_REGRESSIONS)
    )
    repo_tool_counts: list[tuple[str, str, int]] = []
    tools = 0
    # Dedup identical tools by content hash so a tool present in both sources
    # (the corpus is ~46% cross-source duplicates) is swept and counted once.
    seen_sha: set[str] = set()
    for _source_label, display_name, repo_dir, version in _iter_sources(
        sources, repo_filter=args.repo
    ):
        repo_tool_count = 0
        for path in sorted(_iter_tool_xmls(repo_dir)):
            if args.limit and tools >= args.limit:
                break
            if not path.is_file():
                continue
            sha = _sha256_of(path)
            if sha in seen_sha:
                continue
            seen_sha.add(sha)
            if not _fmt_process_path(
                path,
                display_name=display_name,
                repo_dir=repo_dir,
                version=version,
                profile=args.profile,
                state=state,
            ):
                continue
            tools += 1
            repo_tool_count += 1
            if tools % 500 == 0:
                logger.info("... %d tools", tools)
        repo_tool_counts.append((display_name, version, repo_tool_count))
        if args.limit and tools >= args.limit:
            break

    logger.info(
        "swept %d tools; %d validated@%s; %d idempotent; %d non-idempotent; %d crashed",
        tools,
        state.validated,
        args.profile or "any-profile",
        state.idempotent,
        state.non_idempotent,
        state.crashed,
    )
    for sig, count in state.signatures.most_common():
        logger.info("  %6d  %s", count, sig)
    if state.retained:
        _append_provenance(state.retained, regressions_dir=_FMT_REGRESSIONS)
        logger.info(
            "retained %d new regression fixture(s) under %s",
            len(state.retained),
            _FMT_REGRESSIONS,
        )
    if args.no_stats:
        return 0
    if args.limit or args.repo:
        logger.info(
            "corpus stats not regenerated: partial sweep (--limit or --repo). "
            "Run the full sweep to refresh %s.",
            _FMT_STATS_FILE.relative_to(_REPO_ROOT),
        )
        return 0
    _fmt_write_stats(
        profile=args.profile,
        source=args.source,
        repos=repo_tool_counts,
        state=state,
    )
    logger.info(
        "corpus stats -> %s", _FMT_STATS_FILE.relative_to(_REPO_ROOT)
    )
    return 0


# =============================================================================
# codemod subcommand
# =============================================================================

import importlib  # noqa: E402

from galaxy_tool_xml_codemod.codemod import CodemodCommand  # noqa: E402
from galaxy_tool_xml_codemod.parse import parse_module  # noqa: E402
from galaxy_tool_xml_codemod.upgrades import UpgradeToLatest  # noqa: E402

_CODEMOD_REGRESSIONS = (
    _REPO_ROOT / "galaxy-tool-xml-codemod" / "tests" / "data" / "regressions"
)


@dataclass
class _CodemodSweepState:
    """Mutable bookkeeping for one ``_codemod_main`` invocation.

    ``ineligible_no_valid`` covers both "no profile at all validates" and
    "declared profile is invalid and no strictly-newer profile validates"
    — both are no-valid-anchor cases from the codemod-sweep perspective.
    """

    eligible: int = 0
    ineligible_no_valid: int = 0
    ineligible_non_tool: int = 0
    ineligible_unparseable: int = 0
    idempotent: int = 0
    non_idempotent: int = 0
    no_repair: int = 0
    post_validate_failed: int = 0
    crashed: int = 0
    # Eligible tools the codemod actually changed (pass-1 bytes differ from the
    # input). For FixTypos that's repairs; for UpdateProfile, profile add/bumps;
    # for the reorderers, tools whose attribute order was not already canonical.
    modified: int = 0
    signatures: Counter[str] = field(default_factory=Counter)
    # Post-apply profile distribution over processed-eligible tools. For an
    # upgrade sweep (UpgradeToLatest) the sub-latest buckets are the sticking
    # points still needing an upgrade codemod — the discovery signal.
    final_profiles: Counter[str] = field(default_factory=Counter)
    # Per-step upgrade tally: how many tools each ``upgrade_vN`` codemod
    # advanced, keyed by the from-version it upgraded.
    upgrade_steps: Counter[str] = field(default_factory=Counter)
    known_fixture_paths: set[tuple[str, str]] = field(default_factory=set)
    retained: list[tuple[str, str, Path, str, str]] = field(default_factory=list)


@dataclass
class _CodemodOutcome:
    """The classified result of running one codemod on one tool."""

    status: str
    signature: str = ""
    detail: str = ""
    modified: bool = False
    profile: str | None = None
    upgrade_steps: tuple[str, ...] = ()
    # Number of changes the non-mutating ``detect`` phase reported for this
    # tool. The detect/apply parity invariant is ``bool(detected) == modified``.
    detected: int = 0


def _resolve_codemod(spec: str) -> type[CodemodCommand]:
    """Parse ``dotted.module:ClassName`` and return the ``CodemodCommand`` subclass.

    Raises ``ValueError`` for any malformed spec, unimportable module,
    missing attribute, or non-``CodemodCommand`` resolution. The CLI
    main wraps this in a single try/except so the user sees a clean
    error message rather than a traceback.
    """
    if ":" not in spec:
        raise ValueError(
            f"codemod spec must be 'dotted.module:ClassName', got {spec!r}"
        )
    module_name, class_name = spec.split(":", 1)
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise ValueError(
            f"cannot import codemod module {module_name!r}: {error}"
        ) from error
    obj = getattr(module, class_name, None)
    if obj is None:
        raise ValueError(
            f"{spec!r}: module {module_name!r} has no attribute {class_name!r}"
        )
    if not isinstance(obj, type) or not issubclass(obj, CodemodCommand):
        raise ValueError(
            f"{spec!r} did not resolve to a CodemodCommand subclass"
        )
    return obj


def _codemod_exercise(path: Path, codemod: CodemodCommand) -> _CodemodOutcome:
    """Run ``codemod`` on ``path`` and classify the outcome.

    Status is one of ``"ok"``, ``"ineligible-unparseable"``,
    ``"ineligible-non-tool"``, ``"ineligible-no-valid"``, ``"non-idempotent"``,
    ``"no-repair"``, ``"post-validate-failed"``, ``"crash"``. ``modified`` is
    ``True`` when the codemod actually changed the tool (pass-1 bytes differ
    from the input) — repairs (FixTypos), profile add/bumps (UpdateProfile),
    upgrades, or real attribute reorders. ``profile`` is the post-apply
    validation profile (the version the tool ends up at) or ``None`` — the
    discovery signal for upgrade sweeps. ``upgrade_steps`` is the from-versions
    an upgrade orchestrator advanced the tool through (empty otherwise), for
    per-step upgrade stats.

    Eligibility filter:
    - non-tool roots and unparseable inputs are skipped at the top;
    - the codemod's own ``corpus_eligible`` decides the rest. The default
      (structural codemods) is eligible iff ``corpus_test_profile`` picks a
      profile; a repair codemod like ``FixTypos`` inverts it to target tools
      that validate at no profile. The post-codemod validity profile comes
      from ``corpus_validation_profile`` evaluated after apply; ``None`` there
      for an eligible tool means the codemod could not repair it (``no-repair``,
      a legitimate outcome rather than a failure).

    Idempotence is checked by re-parsing the codemod's serialised
    output between the two passes (matching ``_fmt_exercise``) — a
    weaker in-memory equality check would miss codemods whose output
    round-trips to a different tree.
    """
    try:
        parsed = parse_tool(path)
        if parsed.document is None or not parsed.well_formed:
            return _CodemodOutcome("ineligible-unparseable")
        if parsed.document.root.tag != "tool":
            return _CodemodOutcome("ineligible-non-tool")
        # Eligibility is the codemod's own policy (pre-codemod document):
        # the default codemods stay on ``corpus_test_profile``; a repair
        # codemod like FixTypos inverts it to target no-valid tools. The
        # already-parsed document avoids a re-parse per profile probe.
        if not type(codemod).corpus_eligible(parsed.document):
            return _CodemodOutcome("ineligible-no-valid")
        # Pass-1: codemod applied to the parsed input, then serialised.
        # We keep ``document_one`` for post-codemod validation because it
        # carries the source path — needed for macro ``<import>``
        # resolution. A re-parse from bytes loses that path.
        document_one = parse_module(path)
        before_bytes = etree.tostring(document_one.document.tree)
        # Detect phase first: non-mutating, so it reads the pristine tree. Its
        # change list is the lint report; apply must change the tool exactly
        # when detect reported something (the parity invariant below).
        detected = len(list(codemod.detect(document_one)))
        codemod.apply(document_one)
        pass1_bytes = etree.tostring(document_one.document.tree)
        # Did the codemod actually change anything? (atomic no-ops — e.g.
        # FixTypos that found no repair, UpdateProfile on an already-correct
        # profile — leave the bytes identical.)
        modified = pass1_bytes != before_bytes
        # Detect/apply parity: detect reports a change iff apply makes one. A
        # mismatch is a framework bug (detect drifted from apply) — retain it.
        if bool(detected) != modified:
            sig = f"detect-parity:{type(codemod).__name__}"
            detail = (
                f"detect reported {detected} change(s) but apply "
                f"{'changed' if modified else 'did not change'} the tool"
            )
            return _CodemodOutcome(
                "detect-parity-mismatch", sig, detail, modified=modified,
                detected=detected,
            )
        # Captured now, before pass-2 overwrites the orchestrator's state.
        upgrade_steps = codemod.upgrade_steps_applied()
        # Pass-2: codemod applied again to a freshly re-parsed copy of
        # pass-1 bytes — catches codemods whose output round-trips to a
        # different tree. This is the idempotence check ONLY; the tree
        # has no source path so we don't validate it directly.
        document_two = parse_module(pass1_bytes)
        codemod.apply(document_two)
        pass2_bytes = etree.tostring(document_two.document.tree)
        if pass1_bytes != pass2_bytes:
            sig = f"non-idempotent:{type(codemod).__name__}"
            return _CodemodOutcome(
                "non-idempotent",
                sig,
                _fmt_byte_diff_excerpt(pass1_bytes, pass2_bytes),
                modified=modified,
                upgrade_steps=upgrade_steps,
                detected=detected,
            )
        # Validate the POST-codemod document at the codemod's policy profile,
        # evaluated after apply. For the structural codemods this equals the
        # pre-codemod profile (they don't change which profiles validate); for
        # FixTypos it is whatever profile the repaired tool now validates at,
        # and for UpgradeToLatest it is the profile the tool ends up at — the
        # discovery signal: a value below the latest profile is a sticking point
        # that still needs an upgrade codemod. ``None`` means the codemod could
        # not bring the tool to validity at all.
        profile = type(codemod).corpus_validation_profile(document_one.document)
        if profile is None:
            return _CodemodOutcome(
                "no-repair", modified=modified, upgrade_steps=upgrade_steps,
                detected=detected,
            )
        validation = validate_tool(document_one.document, profile=profile)
        if not validation.valid:
            sig = f"post-validate-failed:{type(codemod).__name__}@{profile}"
            detail = "\n".join(str(e) for e in validation.errors[:5])
            return _CodemodOutcome(
                "post-validate-failed",
                sig,
                detail,
                modified=modified,
                profile=profile,
                upgrade_steps=upgrade_steps,
                detected=detected,
            )
    except Exception as exc:  # noqa: BLE001 — diagnostic sweep: every crash is a finding
        return _CodemodOutcome("crash", _signature(exc), traceback.format_exc())
    return _CodemodOutcome(
        "ok", modified=modified, profile=profile, upgrade_steps=upgrade_steps,
        detected=detected,
    )


def _codemod_process_path(
    path: Path,
    *,
    display_name: str,
    repo_dir: Path,
    version: str,
    codemod: CodemodCommand,
    state: _CodemodSweepState,
) -> bool:
    """Sweep one XML file; return ``True`` if it counted as an eligible tool.

    Per-status counters and the signature histogram are only updated
    when a fixture is genuinely *new* (not already in ``PROVENANCE.md``
    from a prior sweep) so re-runs don't double-count earlier finds.
    """
    if not path.is_file():
        return False
    outcome = _codemod_exercise(path, codemod)
    status = outcome.status
    if status == "ineligible-unparseable":
        state.ineligible_unparseable += 1
        return False
    if status == "ineligible-non-tool":
        state.ineligible_non_tool += 1
        return False
    if status == "ineligible-no-valid":
        state.ineligible_no_valid += 1
        return False
    state.eligible += 1
    if outcome.modified:
        # The codemod actually changed this tool (vs. an atomic no-op).
        state.modified += 1
    if outcome.profile is not None:
        # Post-apply landing profile — the discovery distribution.
        state.final_profiles[outcome.profile] += 1
    for from_version in outcome.upgrade_steps:
        # Per-step upgrade tally — how many tools each upgrade_vN advanced.
        state.upgrade_steps[from_version] += 1
    if status in {"ok", "post-validate-failed", "no-repair"}:
        # All three reach this point only after the apply-twice check has
        # succeeded, so they count toward the idempotent total.
        state.idempotent += 1
    elif status == "non-idempotent":
        state.non_idempotent += 1
    elif status == "crash":
        state.crashed += 1
    if status == "post-validate-failed":
        # Track separately too — these failed validity but were idempotent.
        state.post_validate_failed += 1
    if status == "no-repair":
        # Eligible + idempotent, but the codemod could not bring the tool to
        # validity (e.g. FixTypos found no repairing typo). Not a fixture.
        state.no_repair += 1
    if status in {"ok", "no-repair"}:
        return True
    relative = path.relative_to(repo_dir)
    if (display_name, str(relative)) in state.known_fixture_paths:
        return True
    # Only after we've confirmed this is a new fixture do we update the
    # signature histogram — keeps the headline counts honest on re-runs.
    state.signatures[outcome.signature] += 1
    state.known_fixture_paths.add((display_name, str(relative)))
    dest = _retain(
        path,
        display_name.replace("/", "__"),
        regressions_dir=_CODEMOD_REGRESSIONS,
    )
    state.retained.append(
        (dest.name, display_name, relative, version, outcome.signature)
    )
    logger.warning(
        "%s [%s] %s\n  %s\n  retained -> %s\n  %s",
        status.upper(),
        display_name,
        outcome.signature,
        relative,
        dest,
        outcome.detail.strip().replace("\n", "\n  "),
    )
    return True


def _codemod_main(argv: list[str]) -> int:
    """Sweep one codemod across the corpus and retain regression fixtures."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.corpus_check codemod",
        description=(
            "Sweep the Galaxy tool corpus through one codemod and assert "
            "idempotence (apply-twice = apply-once) plus post-codemod "
            "validity. Tools that do not validate under any profile are "
            "skipped (they're broken or exotic — out of scope for codemod "
            "quality)."
        ),
    )
    parser.add_argument(
        "spec",
        help=(
            "codemod to run, as 'dotted.module:ClassName' "
            "(e.g. "
            "'galaxy_tool_xml_codemod.codemods.reorder_param_attributes:"
            "ReorderParamAttributes')"
        ),
    )
    parser.add_argument(
        "--source",
        choices=("github", "toolshed", "combined"),
        default="combined",
        help=(
            "corpus to sweep: 'github' (corpus_sources.json clones), 'toolshed' "
            "(corpus/galaxy-toolshed/), or 'combined' (both, sha256-deduplicated). "
            "Default: combined."
        ),
    )
    parser.add_argument(
        "--repo",
        help="sweep only this repository (by name); --source github only",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="stop after N eligible tools (0 sweeps everything)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # CLI error boundary: turn spec parsing / import errors into a clean
    # error + non-zero exit code instead of a raw traceback.
    try:
        codemod_cls = _resolve_codemod(args.spec)
    except ValueError as error:
        logger.error("%s", error)
        return 1

    if args.repo is not None and args.source != "github":
        logger.error("--repo is only supported with --source github, not %r", args.source)
        return 1
    if args.repo is not None:
        known_names = {name for name, _ in _corpus_sources()}
        if args.repo not in known_names:
            known = ", ".join(sorted(known_names))
            logger.error("unknown --repo %r; known: %s", args.repo, known)
            return 1

    sources = ("github", "toolshed") if args.source == "combined" else (args.source,)
    if "toolshed" in sources and not _TOOLSHED_ROOT.exists():
        logger.error(
            "no toolshed corpus at %s; populate it via scripts/fetch_toolshed.py",
            _TOOLSHED_ROOT.relative_to(_REPO_ROOT),
        )
        return 1

    _CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
    _CODEMOD_REGRESSIONS.mkdir(parents=True, exist_ok=True)
    # Reuse a single codemod instance across all tools — codemods are
    # stateless by contract; one instantiation per sweep, not per tool.
    codemod = codemod_cls()
    state = _CodemodSweepState(
        known_fixture_paths=_fmt_known_fixture_paths(
            regressions_dir=_CODEMOD_REGRESSIONS
        )
    )
    # Dedup identical tools by content hash so a tool present in both sources
    # (the corpus is ~46% cross-source duplicates) is swept and counted once.
    seen_sha: set[str] = set()
    last_progress_log = 0
    for _source_label, display_name, repo_dir, version in _iter_sources(
        sources, repo_filter=args.repo
    ):
        for path in sorted(_iter_tool_xmls(repo_dir)):
            if args.limit and state.eligible >= args.limit:
                break
            if not path.is_file():
                continue
            sha = _sha256_of(path)
            if sha in seen_sha:
                continue
            seen_sha.add(sha)
            _codemod_process_path(
                path,
                display_name=display_name,
                repo_dir=repo_dir,
                version=version,
                codemod=codemod,
                state=state,
            )
            # Log progress at every 500-tool boundary, but only ONCE per
            # boundary — ineligible files don't bump state.eligible, so
            # a `% 500 == 0` check would spam the log between rare tools.
            if (
                state.eligible
                and state.eligible // 500 != last_progress_log // 500
            ):
                logger.info("... %d eligible tools", state.eligible)
                last_progress_log = state.eligible
        if args.limit and state.eligible >= args.limit:
            break

    logger.info(
        "codemod %s: %d eligible (skipped %d ineligible-by-policy, "
        "%d non-tool, %d unparseable); %d modified, %d idempotent, "
        "%d non-idempotent, %d no-repair, %d post-validate-failed, %d crashed",
        type(codemod).__name__,
        state.eligible,
        state.ineligible_no_valid,
        state.ineligible_non_tool,
        state.ineligible_unparseable,
        state.modified,
        state.idempotent,
        state.non_idempotent,
        state.no_repair,
        state.post_validate_failed,
        state.crashed,
    )
    for sig, count in state.signatures.most_common():
        logger.info("  %6d  %s", count, sig)
    # Discovery report: where did eligible tools land? For an upgrade sweep,
    # any bucket below the latest profile is a sticking point still needing an
    # upgrade codemod (named by its version).
    latest = latest_profile()
    stuck = {
        ver: n
        for ver, n in state.final_profiles.items()
        if ver != latest and Version(ver) < Version(latest)
    }
    logger.info(
        "post-apply profile: %d reached latest (%s); %d below latest",
        state.final_profiles.get(latest, 0),
        latest,
        sum(stuck.values()),
    )
    for ver in sorted(stuck, key=Version):
        logger.info(
            "  STICKING POINT  %5d tool(s) stuck at %s -> need upgrade codemod for %s",
            stuck[ver],
            ver,
            ver,
        )
    if state.upgrade_steps:
        logger.info("per-step upgrades (tools advanced by each upgrade_vN):")
        for ver in sorted(state.upgrade_steps, key=Version):
            logger.info("  %6d  upgraded from %s", state.upgrade_steps[ver], ver)
    if state.retained:
        _append_provenance(state.retained, regressions_dir=_CODEMOD_REGRESSIONS)
        logger.info(
            "retained %d new regression fixture(s) under %s",
            len(state.retained),
            _CODEMOD_REGRESSIONS,
        )
    return 0


# =============================================================================
# rules subcommand — per-rule isolation QA
# =============================================================================
#
# Runs EACH rule alone (no other rules), across the corpus, to isolate
# per-rule misbehaviour: fmt rules are checked for idempotence + no-crash only
# (a rule like GTX003 run without GTX001 emits valid-but-non-canonical output —
# that's expected; we only assert it is stable and does not raise); codemods
# reuse the full codemod exercise (idempotence + post-codemod validity), and
# ``UpgradeToLatest`` additionally surfaces its reach / sticking-point / per-step
# discovery as upgrade QA. Failures are retained as regression fixtures in the
# owning tier's regressions dir. Writes docs/corpus_rule_stats.md.


@dataclass
class _FmtRuleSweep:
    """Per-rule bookkeeping for one fmt rule swept in isolation."""

    code: str
    validated: int = 0
    touched: int = 0
    edits: int = 0
    non_idempotent: int = 0
    crashed: int = 0
    signatures: Counter[str] = field(default_factory=Counter)
    known_fixture_paths: set[tuple[str, str]] = field(default_factory=set)
    retained: list[tuple[str, str, Path, str, str]] = field(default_factory=list)


def _fmt_rule_apply(tree: etree._ElementTree, rule_cls: type[Rule]) -> int:
    """Apply ONE fmt rule to *tree* in place; return its edit count."""
    edits = list(rule_cls().apply(tree))
    apply_edits(edits)
    return len(edits)


def _fmt_rule_exercise(
    path: Path, rule_cls: type[Rule], *, profile: str | None
) -> tuple[str, str, str, int]:
    """Isolate one fmt rule on one tool: idempotence + no-crash only.

    Returns ``(status, signature, detail, pass1_edit_count)``. Status is one of
    ``skip-unparseable`` / ``skip-non-tool`` / ``skip-no-validate`` / ``ok`` /
    ``non-idempotent`` / ``crash``. Gated on the same fmt-population policy as
    the ``fmt`` sweep (``_fmt_in_scope``): any-valid by default, or a pinned
    ``profile``.
    """
    try:
        result = parse_tool(path)
        if result.document is None:
            return "skip-unparseable", "", "", 0
        if result.document.root.tag != "tool":
            return "skip-non-tool", "", "", 0
        if not _fmt_in_scope(path, profile=profile):
            return "skip-no-validate", "", "", 0
        document_one = parse_tool(path).document
        if document_one is None:
            return "skip-unparseable", "", "", 0
        edits = _fmt_rule_apply(document_one.tree, rule_cls)
        pass1_bytes = to_bytes(document_one.tree)
        document_two = load_tool(pass1_bytes)
        _fmt_rule_apply(document_two.tree, rule_cls)
        pass2_bytes = to_bytes(document_two.tree)
        if pass1_bytes != pass2_bytes:
            sig = f"non-idempotent:{rule_cls.meta.code}"
            return (
                "non-idempotent",
                sig,
                _fmt_byte_diff_excerpt(pass1_bytes, pass2_bytes),
                edits,
            )
        return "ok", "", "", edits
    except Exception as exc:  # noqa: BLE001 — diagnostic sweep: every crash is a finding
        return "crash", _signature(exc), traceback.format_exc(), 0


def _fmt_rule_process_path(
    path: Path,
    *,
    display_name: str,
    repo_dir: Path,
    version: str,
    profile: str | None,
    rule_cls: type[Rule],
    sweep: _FmtRuleSweep,
) -> None:
    """Sweep one file through one isolated fmt rule and update ``sweep``."""
    if not path.is_file():
        return
    status, signature, detail, edits = _fmt_rule_exercise(
        path, rule_cls, profile=profile
    )
    if status in {"skip-unparseable", "skip-non-tool", "skip-no-validate"}:
        return
    sweep.validated += 1
    if edits:
        sweep.touched += 1
        sweep.edits += edits
    if status == "ok":
        return
    if status == "non-idempotent":
        sweep.non_idempotent += 1
    elif status == "crash":
        sweep.crashed += 1
    relative = path.relative_to(repo_dir)
    if (display_name, str(relative)) in sweep.known_fixture_paths:
        return
    sweep.signatures[signature] += 1
    sweep.known_fixture_paths.add((display_name, str(relative)))
    dest = _retain(
        path, display_name.replace("/", "__"), regressions_dir=_FMT_REGRESSIONS
    )
    sweep.retained.append((dest.name, display_name, relative, version, signature))
    logger.warning(
        "%s [%s] %s\n  %s\n  retained -> %s", status.upper(), display_name, signature,
        relative, dest,
    )


def _sweep_fmt_rule(
    rule_cls: type[Rule],
    *,
    sources: tuple[str, ...],
    repo_filter: str | None,
    limit: int,
    profile: str | None,
) -> _FmtRuleSweep:
    """Sweep the corpus through one isolated fmt rule."""
    sweep = _FmtRuleSweep(
        code=rule_cls.meta.code,
        known_fixture_paths=_fmt_known_fixture_paths(regressions_dir=_FMT_REGRESSIONS),
    )
    seen_sha: set[str] = set()
    for _source_label, display_name, repo_dir, version in _iter_sources(
        sources, repo_filter=repo_filter
    ):
        for path in sorted(_iter_tool_xmls(repo_dir)):
            if limit and sweep.validated >= limit:
                break
            if not path.is_file():
                continue
            sha = _sha256_of(path)
            if sha in seen_sha:
                continue
            seen_sha.add(sha)
            _fmt_rule_process_path(
                path,
                display_name=display_name,
                repo_dir=repo_dir,
                version=version,
                profile=profile,
                rule_cls=rule_cls,
                sweep=sweep,
            )
        if limit and sweep.validated >= limit:
            break
    return sweep


def _sweep_codemod_isolated(
    codemod_cls: type[CodemodCommand],
    *,
    sources: tuple[str, ...],
    repo_filter: str | None,
    limit: int,
) -> _CodemodSweepState:
    """Sweep the corpus through one isolated codemod (reuses the codemod exercise)."""
    codemod = codemod_cls()
    state = _CodemodSweepState(
        known_fixture_paths=_fmt_known_fixture_paths(
            regressions_dir=_CODEMOD_REGRESSIONS
        )
    )
    seen_sha: set[str] = set()
    for _source_label, display_name, repo_dir, version in _iter_sources(
        sources, repo_filter=repo_filter
    ):
        for path in sorted(_iter_tool_xmls(repo_dir)):
            if limit and state.eligible >= limit:
                break
            if not path.is_file():
                continue
            sha = _sha256_of(path)
            if sha in seen_sha:
                continue
            seen_sha.add(sha)
            _codemod_process_path(
                path,
                display_name=display_name,
                repo_dir=repo_dir,
                version=version,
                codemod=codemod,
                state=state,
            )
        if limit and state.eligible >= limit:
            break
    return state


def _rule_format_fmt_table(sweeps: list[_FmtRuleSweep]) -> list[str]:
    """Render the isolated fmt-rule results as a markdown table."""
    lines = [
        "## fmt rules (isolated)",
        "",
        (
            "Each rule applied alone to every validated tool, then applied again. "
            "*Tools touched* emitted at least one edit; *non-idempotent* / "
            "*crashed* are retained as fmt regression fixtures."
        ),
        "",
        "| Rule | Tools validated | Tools touched | Edits | Non-idempotent | Crashed |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for sweep in sorted(sweeps, key=lambda s: s.code):
        lines.append(
            f"| {sweep.code} | {sweep.validated:,} | {sweep.touched:,} | "
            f"{sweep.edits:,} | {sweep.non_idempotent:,} | {sweep.crashed:,} |"
        )
    return lines


def _rule_format_codemod_table(rows: list[tuple[str, str, _CodemodSweepState]]) -> list[str]:
    """Render the isolated codemod results as a markdown table."""
    lines = [
        "## codemods (isolated)",
        "",
        (
            "Each codemod applied alone to every eligible tool, checked for "
            "idempotence and post-codemod validity. *Non-idempotent*, "
            "*post-validate-failed*, and crashes are retained as codemod "
            "regression fixtures; *no-repair* (the codemod legitimately could not "
            "act) is not a failure."
        ),
        "",
        (
            "| Rule | Codemod | Eligible | Modified | Idempotent | Non-idempotent | "
            "Post-validate-failed | No-repair | Crashed |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for code, name, state in sorted(rows, key=lambda r: r[0]):
        lines.append(
            f"| {code} | {name} | {state.eligible:,} | {state.modified:,} | "
            f"{state.idempotent:,} | {state.non_idempotent:,} | "
            f"{state.post_validate_failed:,} | {state.no_repair:,} | {state.crashed:,} |"
        )
    return lines


def _rule_format_upgrade_discovery(state: _CodemodSweepState) -> list[str]:
    """Render UpgradeToLatest's isolated reach / sticking-point / per-step QA."""
    latest = latest_profile()
    stuck = {
        ver: count
        for ver, count in state.final_profiles.items()
        if ver != latest and Version(ver) < Version(latest)
    }
    lines = [
        "## Upgrade discovery (GTX012 `UpgradeToLatest`, isolated)",
        "",
        (
            f"Post-apply landing profile over the {state.eligible:,} eligible tools. "
            f"A tool below the latest profile (`{latest}`) is a sticking point "
            f"still needing an `upgrade_vN` codemod."
        ),
        "",
        f"- reached latest (`{latest}`): {state.final_profiles.get(latest, 0):,}",
        f"- below latest: {sum(stuck.values()):,}",
    ]
    if stuck:
        lines.append("")
        lines.append("| Sticking version | Tools |")
        lines.append("|---|---:|")
        for ver in sorted(stuck, key=Version):
            lines.append(f"| {ver} | {stuck[ver]:,} |")
    if state.upgrade_steps:
        lines.append("")
        lines.append("Per-step advances (tools each `upgrade_vN` moved past):")
        lines.append("")
        lines.append("| From version | Tools advanced |")
        lines.append("|---|---:|")
        for ver in sorted(state.upgrade_steps, key=Version):
            lines.append(f"| {ver} | {state.upgrade_steps[ver]:,} |")
    return lines


def _rule_format_reference_table() -> list[str]:
    """The GTX glossary for the per-rule isolation stat page."""
    return _gtx_reference_table(
        "What each GTX rule does, across both tiers. The isolation tables below "
        "report how each rule behaves when run alone."
    )


def _rule_stats_lines(
    *,
    profile: str | None,
    source: str,
    fmt_sweeps: list[_FmtRuleSweep],
    codemod_rows: list[tuple[str, str, _CodemodSweepState]],
    upgrade_state: _CodemodSweepState | None,
) -> list[str]:
    """Build the per-rule isolation stats markdown (pure; no I/O)."""
    fmt_gate = f"profile `{profile}`" if profile else "any vendored profile"
    corpus_note = (
        "the combined corpus (github + toolshed, sha256-deduplicated)"
        if source == "combined"
        else f"the {source} corpus"
    )
    lines: list[str] = [
        "# Corpus per-rule isolation statistics",
        "",
        (
            f"Generated by `python -m scripts.corpus_check rules` on "
            f"{date.today().isoformat()}. Each GTX rule is run **in isolation** "
            f"(no other rules) across {corpus_note} to surface per-rule "
            f"misbehaviour. fmt rules are gated on validation under {fmt_gate} "
            f"and checked for idempotence + no-crash only; codemods "
            f"use their own eligibility and are checked for idempotence + "
            f"post-codemod validity. Failures are retained as regression "
            f"fixtures in the owning tier."
        ),
        "",
        (
            "Regenerated by every full run of `corpus_check.py rules` unless "
            "`--no-stats` is given; partial sweeps (`--limit` or `--repo`) do "
            "not regenerate it."
        ),
        "",
    ]
    lines.extend(_rule_format_reference_table())
    lines.append("")
    lines.extend(_rule_format_fmt_table(fmt_sweeps))
    lines.append("")
    lines.extend(_rule_format_codemod_table(codemod_rows))
    if upgrade_state is not None:
        lines.append("")
        lines.extend(_rule_format_upgrade_discovery(upgrade_state))
    lines.append("")
    return lines


def _rule_write_stats(
    *,
    profile: str | None,
    source: str,
    fmt_sweeps: list[_FmtRuleSweep],
    codemod_rows: list[tuple[str, str, _CodemodSweepState]],
    upgrade_state: _CodemodSweepState | None,
) -> None:
    """Write the per-rule isolation statistics artifact to ``docs/``."""
    _RULE_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = _rule_stats_lines(
        profile=profile,
        source=source,
        fmt_sweeps=fmt_sweeps,
        codemod_rows=codemod_rows,
        upgrade_state=upgrade_state,
    )
    _RULE_STATS_FILE.write_text("\n".join(lines), encoding="utf-8")


def _rules_main(argv: list[str]) -> int:
    """Sweep every rule in isolation across the corpus; write per-rule stats."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.corpus_check rules",
        description=(
            "Run each GTX rule (fmt + codemod) in isolation across the corpus, "
            "retaining failures as regression fixtures and writing "
            "docs/corpus_rule_stats.md."
        ),
    )
    parser.add_argument(
        "--source",
        choices=("github", "toolshed", "combined"),
        default="combined",
        help="corpus to sweep (default: combined — github + toolshed, deduped)",
    )
    parser.add_argument(
        "--repo", help="sweep only this repository (by name); --source github only"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="stop each rule after N tools (0 sweeps everything)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "fmt-rule validity gate: if given, only tools valid under this exact "
            "profile; default (omitted) gates on validity under ANY vendored "
            "profile"
        ),
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="do not (re)write docs/corpus_rule_stats.md",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.repo is not None and args.source != "github":
        logger.error("--repo is only supported with --source github, not %r", args.source)
        return 1
    if args.repo is not None:
        known_names = {name for name, _ in _corpus_sources()}
        if args.repo not in known_names:
            logger.error("unknown --repo %r; known: %s", args.repo, ", ".join(sorted(known_names)))
            return 1

    sources = ("github", "toolshed") if args.source == "combined" else (args.source,)
    if "toolshed" in sources and not _TOOLSHED_ROOT.exists():
        logger.error(
            "no toolshed corpus at %s; populate it via scripts/fetch_toolshed.py",
            _TOOLSHED_ROOT.relative_to(_REPO_ROOT),
        )
        return 1

    _CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
    _FMT_REGRESSIONS.mkdir(parents=True, exist_ok=True)
    _CODEMOD_REGRESSIONS.mkdir(parents=True, exist_ok=True)

    fmt_sweeps: list[_FmtRuleSweep] = []
    for rule_cls in all_rules():
        logger.info("isolating fmt rule %s ...", rule_cls.meta.code)
        sweep = _sweep_fmt_rule(
            rule_cls,
            sources=sources,
            repo_filter=args.repo,
            limit=args.limit,
            profile=args.profile,
        )
        logger.info(
            "  %s: %d validated, %d touched, %d edits, %d non-idempotent, %d crashed",
            sweep.code, sweep.validated, sweep.touched, sweep.edits,
            sweep.non_idempotent, sweep.crashed,
        )
        if sweep.retained:
            _append_provenance(sweep.retained, regressions_dir=_FMT_REGRESSIONS)
        fmt_sweeps.append(sweep)

    codemod_rows: list[tuple[str, str, _CodemodSweepState]] = []
    upgrade_state: _CodemodSweepState | None = None
    for codemod_cls in coded_codemods():
        name = codemod_cls.__name__
        logger.info("isolating codemod %s (%s) ...", codemod_cls.meta.code, name)
        state = _sweep_codemod_isolated(
            codemod_cls, sources=sources, repo_filter=args.repo, limit=args.limit
        )
        logger.info(
            "  %s: %d eligible, %d modified, %d non-idempotent, "
            "%d post-validate-failed, %d crashed",
            codemod_cls.meta.code, state.eligible, state.modified,
            state.non_idempotent, state.post_validate_failed, state.crashed,
        )
        if state.retained:
            _append_provenance(state.retained, regressions_dir=_CODEMOD_REGRESSIONS)
        if codemod_cls is UpgradeToLatest:
            upgrade_state = state
        codemod_rows.append((codemod_cls.meta.code, name, state))

    if args.no_stats or args.limit or args.repo is not None:
        logger.info("partial or --no-stats run: not regenerating corpus_rule_stats.md")
        return 0
    _rule_write_stats(
        profile=args.profile,
        source=args.source,
        fmt_sweeps=fmt_sweeps,
        codemod_rows=codemod_rows,
        upgrade_state=upgrade_state,
    )
    logger.info("per-rule stats -> %s", _RULE_STATS_FILE.relative_to(_REPO_ROOT))
    return 0


# =============================================================================
# check subcommand — unified detect (violation counts incl. detect-only IUC)
# =============================================================================
#
# What `galaxy-tool-refactor check` reports, swept across the corpus: per-code
# how many tools carry the finding (and the total findings). Unlike the `rules`
# isolation sweep (which counts every emitted edit, including no-ops, to QA each
# rule alone), this counts genuine per-occurrence violations from the same detect
# phases the CLI runs. Covers the detect-only IUC checks. Writes
# docs/corpus_check_stats.md.

from galaxy_tool_refactor_rules.violation import Violation  # noqa: E402
from galaxy_tool_xml_check.detect import all_checks  # noqa: E402
from galaxy_tool_xml_check.detect import detect_violations as _detect_advisory  # noqa: E402
from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS  # noqa: E402
from galaxy_tool_xml_codemod.module import Module  # noqa: E402
from galaxy_tool_xml_fmt.cli_support import is_tool_root  # noqa: E402

_CHECK_STATS_FILE = _REPO_ROOT / "docs" / "corpus_check_stats.md"

# Backtick-wrap ``<tag>`` tokens so GitHub renders them literally in a table
# cell (the shared reference renderer does the same for the glossary).
_CHECK_ANGLE_TOKEN = re.compile(r"(<[^>]+>)")


def _check_md_summary(text: str) -> str:
    """Backtick-wrap angle-bracket tokens in a rule summary for a markdown cell."""
    return _CHECK_ANGLE_TOKEN.sub(r"`\1`", text)


@dataclass
class _CheckRuleStat:
    """Per-code tally for the unified-detect (check) sweep."""

    code: str
    tier: str
    detect_only: bool
    summary: str
    flagged: int = 0  # tools carrying at least one finding of this code
    total: int = 0  # total findings of this code across the corpus


@dataclass
class _CheckSweepState:
    """Corpus-wide tallies for the check sweep."""

    tools: int = 0
    flagged_tools: int = 0
    fixable_flagged_tools: int = 0
    advisory_flagged_tools: int = 0
    crashed: int = 0
    registry: dict[str, _CheckRuleStat] = field(default_factory=dict)


def _check_rule_registry() -> dict[str, _CheckRuleStat]:
    """One stat row per code the ``check`` command can report (fmt + canonical
    codemods + advisory IUC), keyed by code."""
    registry: dict[str, _CheckRuleStat] = {}
    for rule_cls in all_rules():
        meta = rule_cls.meta
        registry[meta.code] = _CheckRuleStat(
            meta.code, "fmt", meta.detect_only, meta.summary
        )
    for codemod_cls in CANONICAL_CODEMODS:
        meta = codemod_cls.meta
        registry[meta.code] = _CheckRuleStat(
            meta.code, "codemod", meta.detect_only, meta.summary
        )
    for check_cls in all_checks():
        meta = check_cls.meta
        registry[meta.code] = _CheckRuleStat(
            meta.code, "check", meta.detect_only, meta.summary
        )
    return registry


def _check_detect(document: ToolDocument) -> list[Violation]:
    """Unified detect over one tool — canonical codemods + fmt + advisory IUC.

    Mirrors the app's report-only detect path — the registry facade's
    ``detect`` over the canonical + advisory selection, which the CLI's
    ``check`` command wraps (non-mutating; each phase reads the same document
    as-is — the same pre-repair caveat applies on the validates-nowhere
    population). Kept here rather than going through the facade so the
    maintainer script stays independent of the registry/app tiers.
    """
    module = Module(document)
    violations = [
        change.to_violation()
        for codemod_cls in CANONICAL_CODEMODS
        for change in codemod_cls().detect(module)
    ]
    violations.extend(detect_tool_document(document))
    violations.extend(_detect_advisory(document))
    violations.sort(key=lambda violation: (violation.sourceline, violation.code))
    return violations


def _check_process_path(path: Path, *, state: _CheckSweepState) -> None:
    """Run the unified detect on one file and roll the findings into ``state``."""
    if not path.is_file():
        return
    try:
        raw = path.read_bytes()
    except OSError:
        return
    if not is_tool_root(raw):
        return
    try:
        document = load_tool(raw)
    except ToolXmlSyntaxError:
        return
    if document.root.tag != "tool":
        return
    state.tools += 1
    try:
        violations = _check_detect(document)
    except Exception:  # noqa: BLE001 — diagnostic sweep: a crash is a finding
        state.crashed += 1
        logger.warning("CRASH on %s\n%s", path, traceback.format_exc())
        return
    if not violations:
        return
    state.flagged_tools += 1
    codes_here: set[str] = set()
    has_fixable = has_advisory = False
    for violation in violations:
        stat = state.registry.get(violation.code)
        if stat is None:
            continue  # a code outside the registry should not occur
        stat.total += 1
        codes_here.add(violation.code)
        if stat.detect_only:
            has_advisory = True
        else:
            has_fixable = True
    for code in codes_here:
        state.registry[code].flagged += 1
    if has_fixable:
        state.fixable_flagged_tools += 1
    if has_advisory:
        state.advisory_flagged_tools += 1


def _check_sweep(
    *, sources: tuple[str, ...], repo_filter: str | None, limit: int
) -> _CheckSweepState:
    """Sweep the corpus through the unified detect, tallying per-code findings."""
    state = _CheckSweepState(registry=_check_rule_registry())
    seen_sha: set[str] = set()
    for _source_label, _display_name, repo_dir, _version in _iter_sources(
        sources, repo_filter=repo_filter
    ):
        for path in sorted(_iter_tool_xmls(repo_dir)):
            if limit and state.tools >= limit:
                break
            if not path.is_file():
                continue
            sha = _sha256_of(path)
            if sha in seen_sha:
                continue
            seen_sha.add(sha)
            _check_process_path(path, state=state)
        if limit and state.tools >= limit:
            break
    return state


def _check_format_table(
    state: _CheckSweepState, *, detect_only: bool, heading: str, blurb: str
) -> list[str]:
    """Render the fixable or advisory per-code table."""
    rows = sorted(
        (stat for stat in state.registry.values() if stat.detect_only is detect_only),
        key=lambda stat: stat.code,
    )
    lines = [
        heading,
        "",
        blurb,
        "",
        "| Rule | Tier | Tools flagged | % of tools | Findings | What it flags |",
        "|---|---|---:|---:|---:|---|",
    ]
    tools = state.tools or 1
    for stat in rows:
        pct = 100 * stat.flagged / tools
        summary = _check_md_summary(stat.summary)
        lines.append(
            f"| {stat.code} | {stat.tier} | {stat.flagged:,} | {pct:.1f}% | "
            f"{stat.total:,} | {summary} |"
        )
    return lines


def _check_stats_lines(*, source: str, state: _CheckSweepState) -> list[str]:
    """Build the check-sweep stats markdown (pure; no I/O)."""
    corpus_note = (
        "the combined corpus (github + toolshed, sha256-deduplicated)"
        if source == "combined"
        else f"the {source} corpus"
    )
    lines: list[str] = [
        "# Corpus check (unified detect) statistics",
        "",
        (
            f"Generated by `python -m scripts.corpus_check check` on "
            f"{date.today().isoformat()}. Runs the exact detect phases the "
            f"`galaxy-tool-refactor check` command reports — the canonical "
            f"codemods + cosmetic fmt rules (*fixable*) plus the advisory IUC "
            f"best-practice checks (*advisory*, detect-only) — across "
            f"{corpus_note}, and counts, per rule, how many tools carry the "
            f"finding. Unlike the per-rule **isolation** page "
            f"(`corpus_rule_stats.md`, which counts every emitted edit to QA each "
            f"rule alone), these are genuine per-occurrence violation counts. "
            f"Every parseable `<tool>` is swept (no validity gate, matching "
            f"`check`)."
        ),
        "",
        (
            f"**{state.tools:,}** tools swept; **{state.flagged_tools:,}** have at "
            f"least one finding (**{state.fixable_flagged_tools:,}** a fixable "
            f"one, **{state.advisory_flagged_tools:,}** an advisory one); "
            f"{state.crashed:,} crashed."
        ),
        "",
        (
            "Regenerated by every full run of `corpus_check.py check` unless "
            "`--no-stats` is given; partial sweeps (`--limit` or `--repo`) do not "
            "regenerate it."
        ),
        "",
    ]
    lines.extend(
        _check_format_table(
            state,
            detect_only=False,
            heading="## Fixable rules (GTX — what `format` would change)",
            blurb=(
                "Structural canonical codemods and cosmetic fmt rules. A finding "
                "here means `format` would change the tool; `check` exits non-zero "
                "on any of these."
            ),
        )
    )
    lines.append("")
    lines.extend(
        _check_format_table(
            state,
            detect_only=True,
            heading="## Advisory checks (IUC — best practices)",
            blurb=(
                "Detect-only IUC best-practice checks. Advisory: `check` reports "
                "them but does not fail unless `--strict`. `IUC011`/`IUC012` are "
                "reserved placeholders (no detection yet), so they flag nothing."
            ),
        )
    )
    lines.append("")
    return lines


def _check_write_stats(*, source: str, state: _CheckSweepState) -> None:
    """Write the check-sweep statistics artifact to ``docs/``."""
    _CHECK_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = _check_stats_lines(source=source, state=state)
    _CHECK_STATS_FILE.write_text("\n".join(lines), encoding="utf-8")


def _check_main(argv: list[str]) -> int:
    """Sweep the corpus through the unified detect; write check violation stats."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.corpus_check check",
        description=(
            "Sweep the corpus through the unified detect phases the "
            "`galaxy-tool-refactor check` command runs (canonical codemods + fmt "
            "+ advisory IUC checks) and report per-rule violation counts, "
            "including the detect-only rules. Writes docs/corpus_check_stats.md."
        ),
    )
    parser.add_argument(
        "--source",
        choices=("github", "toolshed", "combined"),
        default="combined",
        help="corpus to sweep (default: combined — github + toolshed, deduped)",
    )
    parser.add_argument(
        "--repo", help="sweep only this repository (by name); --source github only"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="stop after N tools (0 sweeps everything)",
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="do not (re)write docs/corpus_check_stats.md",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.repo is not None and args.source != "github":
        logger.error(
            "--repo is only supported with --source github, not %r", args.source
        )
        return 1
    if args.repo is not None:
        known_names = {name for name, _ in _corpus_sources()}
        if args.repo not in known_names:
            logger.error(
                "unknown --repo %r; known: %s", args.repo, ", ".join(sorted(known_names))
            )
            return 1

    sources = ("github", "toolshed") if args.source == "combined" else (args.source,)
    if "toolshed" in sources and not _TOOLSHED_ROOT.exists():
        logger.error(
            "no toolshed corpus at %s; populate it via scripts/fetch_toolshed.py",
            _TOOLSHED_ROOT.relative_to(_REPO_ROOT),
        )
        return 1

    state = _check_sweep(sources=sources, repo_filter=args.repo, limit=args.limit)
    logger.info(
        "check sweep: %d tools; %d flagged (%d fixable, %d advisory); %d crashed",
        state.tools, state.flagged_tools, state.fixable_flagged_tools,
        state.advisory_flagged_tools, state.crashed,
    )
    for stat in sorted(state.registry.values(), key=lambda s: s.code):
        logger.info(
            "  %s [%s%s] %d tools, %d findings",
            stat.code, stat.tier, " advisory" if stat.detect_only else "",
            stat.flagged, stat.total,
        )
    if args.no_stats or args.limit or args.repo is not None:
        logger.info("partial or --no-stats run: not regenerating corpus_check_stats.md")
        return 0
    _check_write_stats(source=args.source, state=state)
    logger.info("check stats -> %s", _CHECK_STATS_FILE.relative_to(_REPO_ROOT))
    return 0


# =============================================================================
# Top-level dispatcher
# =============================================================================


def main(argv: list[str]) -> int:
    """Dispatch to the ``validate``, ``fmt``, ``codemod``, or ``rules`` subcommand."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.corpus_check",
        description="Sweep Galaxy tool repositories through the galaxy-tool-xml ecosystem.",
        add_help=False,
    )
    parser.add_argument(
        "subcommand",
        choices=("validate", "fmt", "codemod", "rules", "check"),
        help=(
            "validate: API invariants sweep; fmt: formatter idempotence "
            "sweep; codemod: one structural-codemod idempotence + validity "
            "sweep; rules: per-rule isolation QA sweep (every rule alone); "
            "check: unified-detect violation counts (incl. detect-only IUC)"
        ),
    )
    # Parse only the subcommand, pass the rest to the subcommand's own parser.
    if not argv or argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0
    args, remaining = parser.parse_known_args(argv)
    if args.subcommand == "validate":
        return _validate_main(remaining)
    if args.subcommand == "fmt":
        return _fmt_main(remaining)
    if args.subcommand == "codemod":
        return _codemod_main(remaining)
    if args.subcommand == "rules":
        return _rules_main(remaining)
    return _check_main(remaining)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
