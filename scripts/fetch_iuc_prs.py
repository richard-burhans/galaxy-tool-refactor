#!/usr/bin/env python3
"""Build a PR corpus from open ``galaxyproject/tools-iuc`` pull requests.

A standalone maintenance script — Python standard library plus the ``gh`` CLI
for the GitHub API. ``.local/`` is gitignored; this script populates
``.local/pr-corpus/<owner>__<repo>/`` for the impact analysis in
``scripts/pr_impact.py``, parallel to ``fetch_toolshed.py``.

For every qualifying open PR it snapshots the affected tool's XML files at
**three refs** — ``base`` (the PR's target-branch SHA), ``first`` (the PR's
first-commit SHA, so ``first``→``head`` isolates the review-driven delta), and
``head`` — preserving each file's full repository path so ``<import>`` macro
references resolve unchanged. A ``manifest.json`` records every PR (kept and
dropped, with the drop reason) so the analysis and the audience docs can cite
exact counts.

The ``gh`` CLI authenticates through the sandbox proxy: commands are run with a
placeholder ``GH_TOKEN=x`` in the environment and the proxy injects real
credentials. ``gh auth status`` reporting "not logged in" is expected and does
not mean API calls fail.

A PR qualifies when it is open, not a draft, modifies at least one Galaxy tool
XML file, is not authored by a bot, and is not a pure version/dependency bump.
Default behaviour is additive: PRs already snapshotted on disk are skipped;
``--force`` re-downloads them. ``--limit N`` caps the sweep to the N
most-recently-updated qualifying PRs (``--limit 0`` fetches every one).

Usage::

    uv run python -m scripts.fetch_iuc_prs [--limit N] [--state open] \
        [--include-drafts] [--repo OWNER/NAME] [--force]
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path, PurePosixPath
from typing import cast

logger = logging.getLogger("fetch_iuc_prs")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PR_CORPUS_ROOT = _REPO_ROOT / ".local" / "pr-corpus"
_DEFAULT_REPO = "galaxyproject/tools-iuc"
_DEFAULT_LIMIT = 100
_REFS = ("base", "first", "head")
_UNKNOWN = "unknown"

# ``gh`` authenticates through the sandbox proxy when a placeholder token is
# present; the proxy swaps in real credentials at the network layer.
_GH_ENV_TOKEN = "x"

# Bot accounts whose PRs are mechanical and out of scope. ``[bot]``-suffixed
# logins are matched separately; ``planemo-autoupdate`` carries no suffix.
_BOT_LOGINS = frozenset({"planemo-autoupdate"})
_BOT_LOGIN_SUFFIX = "[bot]"

# Tokens/attributes that mark a changed line as a version/dependency bump.
_VERSION_MARKERS = (
    "@TOOL_VERSION@",
    "@VERSION@",
    "@GALAXY_VERSION@",
    "@VERSION_SUFFIX@",
)


def _gh_api_json(path: str, /, *, paginate: bool = False) -> object | None:
    """GET a ``gh api`` endpoint and return parsed JSON, or ``None`` on failure.

    LBYL boundary: ``gh`` is the only third-party process here, so a non-zero
    exit is logged and folded into ``None`` rather than raised — the sweep loop
    skips-and-records instead of crashing. ``paginate`` follows ``Link`` headers
    and concatenates the pages (required for the commits/files endpoints, which
    can exceed one page). Returned as ``object`` because ``json.loads`` yields
    any JSON value; callers LBYL-check the shape before structural access.
    """
    argv = ["gh", "api", "-X", "GET", path]
    if paginate:
        argv.append("--paginate")
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GH_TOKEN": _GH_ENV_TOKEN},
    )
    if result.returncode != 0:
        logger.warning(
            "gh api failed (%s): %s",
            path,
            result.stderr.strip() or "<no stderr>",
        )
        return None
    parsed: object = json.loads(result.stdout)
    return parsed


def _is_rate_limited() -> bool:
    """Return True when ``gh`` reports the core API rate limit is exhausted.

    The ``rate_limit`` endpoint is itself exempt from the limit, so polling it
    is free.
    """
    result = subprocess.run(
        ["gh", "api", "-X", "GET", "rate_limit"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GH_TOKEN": _GH_ENV_TOKEN},
    )
    if result.returncode != 0:
        return False
    payload = json.loads(result.stdout) if result.stdout else None
    if not isinstance(payload, dict):
        return False
    core = payload.get("resources", {})
    if not isinstance(core, dict):
        return False
    rest = core.get("core", {})
    if not isinstance(rest, dict):
        return False
    remaining = rest.get("remaining")
    return isinstance(remaining, int) and remaining <= 0


def list_open_prs(repo: str, /, *, state: str, limit: int) -> list[dict[str, object]]:
    """Return PR list items, most-recently-updated first, sliced to *limit*.

    Each item carries enough to filter without a per-PR metadata GET: ``number``,
    ``title``, ``draft``, ``user.login``, ``author_association``, ``labels``,
    ``base.sha``, ``head.sha``, ``updated_at``. ``limit == 0`` returns every PR.
    """
    payload = _gh_api_json(
        f"repos/{repo}/pulls?state={state}"
        f"&sort=updated&direction=desc&per_page=100",
        paginate=True,
    )
    if not isinstance(payload, list):
        return []
    prs = [item for item in payload if isinstance(item, dict)]
    return prs if limit == 0 else prs[:limit]


def pr_first_commit_sha(repo: str, number: int, /) -> str | None:
    """Return the SHA of the PR's first (oldest) commit, or ``None``.

    The commits endpoint lists commits chronologically (oldest first), so the
    first element is the PR's initial submission — the baseline whose delta to
    ``head`` is the review-driven change.
    """
    payload = _gh_api_json(f"repos/{repo}/pulls/{number}/commits", paginate=True)
    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    if not isinstance(first, dict):
        return None
    sha = first.get("sha")
    return sha if isinstance(sha, str) else None


def pr_files(repo: str, number: int, /) -> list[dict[str, object]]:
    """Return the PR's changed-file entries (``filename``/``status``/``patch``)."""
    payload = _gh_api_json(f"repos/{repo}/pulls/{number}/files", paginate=True)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def is_tool_xml_path(filename: str, /) -> bool:
    """Return True for a Galaxy tool XML: under ``tools/``, ``*.xml``, not test data."""
    path = PurePosixPath(filename)
    return (
        bool(path.parts)
        and path.parts[0] == "tools"
        and path.suffix == ".xml"
        and "test-data" not in path.parts
        and path.name != ".shed.yml"
    )


def is_bot_author(login: str, /) -> bool:
    """Return True when *login* is a known bot or ``[bot]``-suffixed account."""
    return login.endswith(_BOT_LOGIN_SUFFIX) or login in _BOT_LOGINS


def _patch_changed_lines(patch: str, /) -> list[str]:
    """Return the added/removed content lines of a unified diff *patch*.

    Hunk headers (``@@``) and file headers (``+++``/``---``) are excluded; the
    leading ``+``/``-`` marker is stripped so the caller sees content only.
    """
    changed: list[str] = []
    for line in patch.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            changed.append(line[1:])
    return changed


def _is_version_like_line(line: str, /) -> bool:
    """Return True when a changed line is purely a version/requirement bump."""
    stripped = line.strip()
    if not stripped:
        return True
    if any(marker in stripped for marker in _VERSION_MARKERS):
        return True
    lowered = stripped.lower()
    if "version=" in lowered or "<requirement" in lowered:
        return True
    # A bare ``X.Y.Z`` line is a token body (e.g. ``<token …>1.2.3</token>``
    # split across lines, or a version_command number).
    return all(char.isdigit() or char in "._-+" for char in stripped)


def is_version_bump_only(tool_xml_files: list[dict[str, object]], /) -> bool:
    """Return True when every tool-XML change is a version/dependency bump.

    Conservative: a file with no ``patch`` (too large to inline) counts as a
    substantive change, and any single non-version line keeps the PR. So this
    only drops PRs whose *entire* tool-XML delta is version churn.
    """
    saw_changed_line = False
    for entry in tool_xml_files:
        patch = entry.get("patch")
        if not isinstance(patch, str):
            return False  # large diff → treat as substantive (keep)
        for line in _patch_changed_lines(patch):
            saw_changed_line = True
            if not _is_version_like_line(line):
                return False
    return saw_changed_line


def qualifies(
    pr: dict[str, object],
    files: list[dict[str, object]],
    /,
    *,
    include_drafts: bool,
) -> tuple[bool, str | None]:
    """Return ``(keep, drop_reason)`` for a PR; reason is ``None`` when kept.

    Filter order: draft → bot author → no tool XML → version-bump-only.
    """
    if not include_drafts and pr.get("draft") is True:
        return False, "draft"
    user = pr.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    if isinstance(login, str) and is_bot_author(login):
        return False, f"bot:{login}"
    tool_xml_files = [
        entry
        for entry in files
        if isinstance(entry.get("filename"), str)
        and is_tool_xml_path(str(entry["filename"]))
    ]
    if not tool_xml_files:
        return False, "no_tool_xml"
    if is_version_bump_only(tool_xml_files):
        return False, "version_bump_only"
    return True, None


def affected_tool_dirs(files: list[dict[str, object]], /) -> dict[str, list[str]]:
    """Map each affected tool directory to the sorted changed XML paths under it.

    The directory to snapshot is the parent of each changed tool XML (full
    repository path, e.g. ``tools/coverm``); snapshotting its whole ``*.xml``
    subtree captures sibling ``macros.xml`` / a ``macros/`` subdir for
    ``<import>`` resolution.
    """
    dirs: dict[str, list[str]] = {}
    for entry in files:
        filename = entry.get("filename")
        if not isinstance(filename, str) or not is_tool_xml_path(filename):
            continue
        tool_dir = str(PurePosixPath(filename).parent)
        dirs.setdefault(tool_dir, []).append(filename)
    return {tool_dir: sorted(paths) for tool_dir, paths in sorted(dirs.items())}


def _download_file(repo: str, repo_path: str, ref: str, dest: Path, /) -> bool:
    """Download one repo file at *ref* into *dest*; return success.

    Uses the contents API, which returns the file body base64-encoded for files
    under ~1 MB (tool XML always qualifies).
    """
    payload = _gh_api_json(f"repos/{repo}/contents/{repo_path}?ref={ref}")
    if not isinstance(payload, dict):
        return False
    if payload.get("encoding") != "base64":
        logger.warning("unexpected encoding for %s@%s", repo_path, ref)
        return False
    content = payload.get("content")
    if not isinstance(content, str):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(content))
    return True


def download_tree_xmls(repo: str, tool_dir: str, ref: str, ref_root: Path, /) -> list[str]:
    """Snapshot every ``*.xml`` under *tool_dir* at *ref* beneath *ref_root*.

    Files keep their full repository path under *ref_root* (so relative
    ``<import>`` paths resolve identically). ``test-data`` subdirectories are
    skipped. Returns the downloaded repository paths; an empty list means the
    directory does not exist at *ref* (e.g. a new tool has no ``base`` version).
    """
    listing = _gh_api_json(f"repos/{repo}/contents/{tool_dir}?ref={ref}")
    if not isinstance(listing, list):
        return []
    downloaded: list[str] = []
    for entry in listing:
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type")
        repo_path = entry.get("path")
        name = entry.get("name")
        if not isinstance(repo_path, str) or not isinstance(name, str):
            continue
        if entry_type == "dir":
            if name == "test-data":
                continue
            downloaded.extend(download_tree_xmls(repo, repo_path, ref, ref_root))
        elif entry_type == "file" and name.endswith(".xml"):
            dest = ref_root / repo_path
            if _download_file(repo, repo_path, ref, dest):
                downloaded.append(repo_path)
    return sorted(downloaded)


def _pr_dir(corpus_name: str, number: int, /) -> Path:
    """Return the on-disk directory for a PR's snapshots under *corpus_name*."""
    return _PR_CORPUS_ROOT / corpus_name / f"pr-{number}"


def _snapshot_pr(
    repo: str,
    corpus_name: str,
    pr: dict[str, object],
    files: list[dict[str, object]],
    /,
) -> dict[str, object] | None:
    """Snapshot one kept PR's three refs; return its manifest entry or ``None``.

    ``None`` signals a transient fetch failure (recorded by the caller). The
    caller decides whether to call this (it skips PRs already on disk unless
    ``--force``), so this always downloads fresh.
    """
    number = cast(int, pr["number"])
    pr_dir = _pr_dir(corpus_name, number)
    base_sha = _nested_sha(pr, "base")
    head_sha = _nested_sha(pr, "head")
    first_sha = pr_first_commit_sha(repo, number)
    if base_sha is None or head_sha is None or first_sha is None:
        return None
    if pr_dir.exists():
        _rmtree(pr_dir)

    tool_dirs = affected_tool_dirs(files)
    ref_shas = {"base": base_sha, "first": first_sha, "head": head_sha}
    snapshot: dict[str, object] = {}
    for ref, sha in ref_shas.items():
        ref_root = pr_dir / ref
        present_files: list[str] = []
        for tool_dir in tool_dirs:
            present_files.extend(download_tree_xmls(repo, tool_dir, sha, ref_root))
        snapshot[ref] = {
            "present": bool(present_files),
            "files": sorted(set(present_files)),
        }

    changed_xml = sorted(
        str(entry["filename"])
        for entry in files
        if isinstance(entry.get("filename"), str)
        and is_tool_xml_path(str(entry["filename"]))
    )
    base_present = bool(snapshot["base"]["present"])  # type: ignore[index]
    return {
        "number": number,
        "title": pr.get("title"),
        "author": _nested_login(pr),
        "author_association": pr.get("author_association"),
        "labels": _label_names(pr),
        "draft": pr.get("draft"),
        "base_sha": base_sha,
        "first_sha": first_sha,
        "head_sha": head_sha,
        "new_tool": not base_present,
        "single_commit": first_sha == head_sha,
        "affected_tool_dirs": list(tool_dirs),
        "changed_xml_files": changed_xml,
        "snapshot": snapshot,
        "status": "ok",
        "drop_reason": None,
        "state": pr.get("state"),
        "merged_at": pr.get("merged_at"),
        "updated_at": pr.get("updated_at"),
    }


def _rmtree(path: Path, /) -> None:
    """Remove a directory tree before a fresh snapshot."""
    shutil.rmtree(path)


def _nested_sha(pr: dict[str, object], key: str, /) -> str | None:
    """Return ``pr[key].sha`` if present and a string."""
    section = pr.get(key)
    if not isinstance(section, dict):
        return None
    sha = section.get("sha")
    return sha if isinstance(sha, str) else None


def _nested_login(pr: dict[str, object], /) -> str | None:
    """Return ``pr.user.login`` if present and a string."""
    user = pr.get("user")
    if not isinstance(user, dict):
        return None
    login = user.get("login")
    return login if isinstance(login, str) else None


def _label_names(pr: dict[str, object], /) -> list[str]:
    """Return the PR's label names."""
    labels = pr.get("labels")
    if not isinstance(labels, list):
        return []
    return [
        str(label["name"])
        for label in labels
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    ]


def _manifest_path(corpus_name: str, /) -> Path:
    """Return the manifest path for the *corpus_name* PR corpus."""
    return _PR_CORPUS_ROOT / corpus_name / "manifest.json"


def _load_manifest(corpus_name: str, /) -> dict[str, dict[str, object]]:
    """Return the existing per-PR manifest map (keyed by PR number string)."""
    path = _manifest_path(corpus_name)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    prs = raw.get("pull_requests")
    if not isinstance(prs, dict):
        return {}
    return {key: entry for key, entry in prs.items() if isinstance(entry, dict)}


def _write_manifest(
    corpus_name: str, repo: str, entries: dict[str, dict[str, object]], /
) -> None:
    """Write the manifest with PRs ordered numerically for diff-friendly reruns."""
    path = _manifest_path(corpus_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {
        key: entries[key]
        for key in sorted(entries, key=lambda value: int(value))
    }
    payload = {
        "repo": repo,
        "retrieved": date.today().isoformat(),
        "pull_requests": ordered,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    """Build the PR corpus; return a process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Snapshot open tools-iuc PRs into a three-ref PR corpus."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_DEFAULT_LIMIT,
        help="snapshot the N most-recently-updated qualifying PRs (0 = all)",
    )
    parser.add_argument("--state", default="open", help="PR state to list (open/closed)")
    parser.add_argument(
        "--merged-only",
        action="store_true",
        help="with --state closed, keep only merged PRs (drop closed-unmerged)",
    )
    parser.add_argument(
        "--include-drafts",
        action="store_true",
        help="keep draft PRs (dropped by default)",
    )
    parser.add_argument(
        "--repo",
        default=_DEFAULT_REPO,
        metavar="OWNER/NAME",
        help=f"repository to fetch PRs from (default {_DEFAULT_REPO})",
    )
    parser.add_argument(
        "--corpus-name",
        default="",
        metavar="NAME",
        help="corpus subdir under .local/pr-corpus (default: the repo slug)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download snapshots for PRs already on disk",
    )
    args = parser.parse_args(argv)

    corpus_name = args.corpus_name or args.repo.replace("/", "__")
    prs = list_open_prs(args.repo, state=args.state, limit=0)
    if not prs:
        logger.error("no %s PRs listed for %s", args.state, args.repo)
        return 1
    logger.info("%s lists %d %s PRs", args.repo, len(prs), args.state)

    manifest = _load_manifest(corpus_name)
    counts = {"ok": 0, "dropped": 0, "deferred": 0, "error": 0}
    kept = 0
    for pr in prs:
        number = pr.get("number")
        if not isinstance(number, int):
            continue
        if args.limit and kept >= args.limit:
            logger.info("--limit %d qualifying PRs reached, stopping", args.limit)
            break
        if args.merged_only and pr.get("merged_at") is None:
            continue  # closed-unmerged PR — not an accepted change
        files = pr_files(args.repo, number)
        keep, reason = qualifies(pr, files, include_drafts=args.include_drafts)
        if not keep:
            manifest[str(number)] = {
                "number": number,
                "title": pr.get("title"),
                "author": _nested_login(pr),
                "status": "dropped",
                "drop_reason": reason,
                "updated_at": pr.get("updated_at"),
            }
            counts["dropped"] += 1
            continue
        kept += 1
        existing = manifest.get(str(number))
        if (
            not args.force
            and _pr_dir(corpus_name, number).exists()
            and isinstance(existing, dict)
            and existing.get("status") == "ok"
        ):
            logger.info("PR #%d already snapshotted, reusing", number)
            counts["ok"] += 1
            continue
        if _is_rate_limited():
            logger.warning("API rate limit exhausted; deferring remaining PRs")
            manifest[str(number)] = {
                "number": number,
                "status": "deferred",
                "drop_reason": None,
                "updated_at": pr.get("updated_at"),
            }
            counts["deferred"] += 1
            break
        entry = _snapshot_pr(args.repo, corpus_name, pr, files)
        if entry is None:
            manifest[str(number)] = {
                "number": number,
                "title": pr.get("title"),
                "status": "error",
                "drop_reason": None,
                "updated_at": pr.get("updated_at"),
            }
            counts["error"] += 1
            continue
        manifest[str(number)] = entry
        counts["ok"] += 1
        logger.info(
            "PR #%d snapshotted (%d tool dir(s))",
            number,
            len(entry["affected_tool_dirs"]),  # type: ignore[arg-type]
        )

    _write_manifest(corpus_name, args.repo, manifest)
    logger.info(
        "fetch complete: %d ok, %d dropped, %d deferred, %d error; manifest -> %s",
        counts["ok"],
        counts["dropped"],
        counts["deferred"],
        counts["error"],
        _manifest_path(corpus_name).relative_to(_REPO_ROOT),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
