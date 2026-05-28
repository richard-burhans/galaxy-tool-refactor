#!/usr/bin/env python3
"""Fetch latest revisions of every Galaxy ToolShed repository into ``corpus/``.

A standalone maintenance script — Python standard library for the API
listing, plus the ``hg`` binary shipped by the ``mercurial`` dev dependency
for cloning. ``corpus/`` is gitignored; this script populates it for deep
testing and stats work, parallel to ``fetch_schemas.py``.

The Galaxy ToolShed exposes content only over the Mercurial wire protocol
(its public API has no tarball or raw-file endpoint), so each repository is
fetched via ``hg clone``. The tip changeset is captured via ``hg id`` and
recorded in ``corpus/galaxy-toolshed/manifest.json``, then ``.hg/`` is
removed so each ``corpus/galaxy-toolshed/<owner>/<name>/`` directory holds
only the latest revision's files — matching the "latest version per tool"
rule used by the corpus stats path. The manifest is what
``scripts/corpus_check.py`` reads to label each toolshed repo with its
real changeset (e.g. ``f885abcfe3a0`` for ``iuc/kegalign``).

Default behaviour is additive: existing per-repo directories are reused and
their existing manifest entries are preserved. Use ``--force`` to remove
and re-clone everything (manifest entries for re-cloned repos refresh).
``--limit N`` caps the sweep for sampling; ``--skip-owners`` excludes
specific owners.

Usage::

    uv run python scripts/fetch_toolshed.py [--limit N] [--force] \
        [--skip-owners OWNER,OWNER,...]
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

logger = logging.getLogger("fetch_toolshed")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CORPUS_ROOT = _REPO_ROOT / "corpus"
_TOOLSHED_ROOT = _CORPUS_ROOT / "galaxy-toolshed"
_TOOLSHED_MANIFEST = _TOOLSHED_ROOT / "manifest.json"
_TOOLSHED_HOST = "https://toolshed.g2.bx.psu.edu"
_API_ENDPOINT = f"{_TOOLSHED_HOST}/api/repositories"
_USER_AGENT = "galaxy-tool-xml-fetch-toolshed"
_HTTP_TIMEOUT = 30
_PAGE_SIZE = 500
_PROGRESS_EVERY = 100
_UNKNOWN = "unknown"


def _api_get(url: str) -> object:
    """GET a ToolShed API URL and return the parsed JSON body.

    Returned as ``object`` rather than ``dict`` because ``json.loads`` can
    yield any JSON value; the caller is responsible for an ``isinstance``
    LBYL check before structural access.
    """
    request = urllib.request.Request(url)  # noqa: S310 — fixed toolshed host
    request.add_header("User-Agent", _USER_AGENT)
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:  # noqa: S310
        body = response.read()
    return json.loads(body)


def list_repositories(*, skip_owners: frozenset[str]) -> list[tuple[str, str]]:
    """Return ``(owner, name)`` for every non-deleted, non-deprecated repo.

    Pagination follows the ToolShed envelope's ``total_results`` until the
    last page is reached. Repos whose owner is in ``skip_owners`` are
    excluded inline so the returned list is the actual fetch target list.
    """
    repos: list[tuple[str, str]] = []
    page = 1
    while True:
        envelope = _api_get(
            f"{_API_ENDPOINT}"
            f"?deleted=false&deprecated=false"
            f"&page={page}&page_size={_PAGE_SIZE}"
        )
        if not isinstance(envelope, dict):
            break  # malformed response; nothing structured to unpack
        hits = envelope.get("hits") or []
        if not isinstance(hits, list) or not hits:
            break
        for repo in hits:
            if not isinstance(repo, dict):
                continue
            owner = repo.get("owner")
            name = repo.get("name")
            if not owner or not name or owner in skip_owners:
                continue
            repos.append((owner, name))
        total = envelope.get("total_results", 0)
        if not isinstance(total, int) or page * _PAGE_SIZE >= total:
            break
        page += 1
    return repos


def _hg_clone(url: str, dest: Path) -> bool:
    """Clone a Mercurial repo to ``dest`` quietly; return success."""
    result = subprocess.run(
        ["hg", "clone", "--quiet", url, str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.warning(
            "clone failed (%s): %s",
            url,
            result.stderr.strip() or "<no stderr>",
        )
        return False
    return True


def _hg_short_id(dest: Path) -> str | None:
    """Return ``dest``'s tip changeset as a short hash, or None on failure.

    Must be called while ``.hg/`` is still present. ``hg id -i`` prints
    the working-directory parent's short hash; on a fresh clone with no
    local edits that is the tip and carries no trailing ``+`` marker.
    """
    result = subprocess.run(
        ["hg", "id", "-i", str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.warning(
            "hg id failed (%s): %s",
            dest,
            result.stderr.strip() or "<no stderr>",
        )
        return None
    return result.stdout.strip() or None


def _fetch_one(owner: str, name: str, *, force: bool) -> tuple[str, str | None]:
    """Fetch one repo into the toolshed corpus tree.

    Returns ``(status, changeset)`` where ``status`` is ``"ok"`` on a
    fresh successful clone, ``"skipped"`` when the destination already
    exists (and ``force`` is false), or ``"failed"`` on a clone error.
    ``changeset`` is the short hash for ``"ok"`` outcomes and ``None``
    otherwise. A failed clone leaves no partial directory behind.
    """
    dest = _TOOLSHED_ROOT / owner / name
    if dest.exists():
        if not force:
            return "skipped", None
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{_TOOLSHED_HOST}/repos/{owner}/{name}"
    if not _hg_clone(url, dest):
        if dest.exists():
            shutil.rmtree(dest)
        return "failed", None
    changeset = _hg_short_id(dest)
    # Drop Mercurial history; we keep only the latest snapshot per
    # corpus-stats convention (and to save ~80% on disk). The changeset
    # had to be captured above before this point.
    hg_dir = dest / ".hg"
    if hg_dir.exists():
        shutil.rmtree(hg_dir)
    return "ok", changeset


def _load_manifest() -> dict[str, dict[str, str]]:
    """Return the existing manifest's ``repositories`` map, or empty.

    ``corpus/galaxy-toolshed/manifest.json`` records each cloned repo's
    tip changeset so ``scripts/corpus_check.py`` can label the toolshed
    rows with real versions instead of the literal string ``"latest"``.
    A missing or unparseable file is treated as an empty manifest — the
    sweep will populate it from scratch.
    """
    if not _TOOLSHED_MANIFEST.exists():
        return {}
    raw = json.loads(_TOOLSHED_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    repos = raw.get("repositories")
    if not isinstance(repos, dict):
        return {}
    return {
        key: {
            "changeset": str(entry.get("changeset", _UNKNOWN)),
            "retrieved": str(entry.get("retrieved", _UNKNOWN)),
        }
        for key, entry in repos.items()
        if isinstance(entry, dict)
    }


def _existing_clone_keys() -> set[str]:
    """Return ``owner/name`` keys for every existing toolshed clone on disk."""
    if not _TOOLSHED_ROOT.exists():
        return set()
    keys: set[str] = set()
    for owner_dir in _TOOLSHED_ROOT.iterdir():
        if not owner_dir.is_dir():
            continue
        for repo_dir in owner_dir.iterdir():
            if repo_dir.is_dir():
                keys.add(f"{owner_dir.name}/{repo_dir.name}")
    return keys


def _write_manifest(manifest: dict[str, dict[str, str]]) -> None:
    """Write the manifest with stable key order for diff-friendly reruns."""
    sorted_repos = {key: manifest[key] for key in sorted(manifest)}
    payload = {"repositories": sorted_repos}
    _TOOLSHED_MANIFEST.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _fetch_single_repo(spec: str) -> int:
    """Re-fetch one OWNER/NAME repository and update its manifest entry.

    The single-repo fast path: no API listing, no full-corpus prune, no
    backfill of unrelated entries — just force-re-clone the named repo
    and persist its changeset. Used when a maintainer needs to freshen a
    specific tool (e.g., to populate a previously-``unknown`` entry)
    without paying the network cost of ``--force`` on the whole corpus.
    """
    parts = spec.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        logger.error("--repo must be in 'OWNER/NAME' form, got %r", spec)
        return 1
    owner, name = parts
    _TOOLSHED_ROOT.mkdir(parents=True, exist_ok=True)
    outcome, changeset = _fetch_one(owner, name, force=True)
    if outcome != "ok":
        logger.error("re-fetch of %s did not succeed (outcome=%s)", spec, outcome)
        return 1
    manifest = _load_manifest()
    manifest[spec] = {
        "changeset": changeset or _UNKNOWN,
        "retrieved": date.today().isoformat(),
    }
    _write_manifest(manifest)
    logger.info(
        "re-fetched %s at %s; manifest -> %s",
        spec,
        changeset or _UNKNOWN,
        _TOOLSHED_MANIFEST.relative_to(_REPO_ROOT),
    )
    return 0


def main(argv: list[str]) -> int:
    """Fetch repositories; return a process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Fetch latest revisions of every Galaxy ToolShed repository."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="stop after N fresh clones (0 fetches every listed repository)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-clone every repository even if it's already on disk",
    )
    parser.add_argument(
        "--skip-owners",
        default="",
        help="comma-separated list of owner names to exclude (e.g. iuc,devteam)",
    )
    parser.add_argument(
        "--repo",
        default="",
        metavar="OWNER/NAME",
        help=(
            "re-fetch a single repository identified as OWNER/NAME (implies "
            "--force on it only). Updates that one manifest entry and leaves "
            "every other entry alone — useful for refreshing one repo's "
            "changeset without re-cloning the entire corpus. Incompatible "
            "with --limit and --skip-owners."
        ),
    )
    args = parser.parse_args(argv)

    if args.repo:
        if args.limit or args.skip_owners:
            logger.error("--repo is incompatible with --limit and --skip-owners")
            return 1
        return _fetch_single_repo(args.repo)

    skip_owners = frozenset(
        owner.strip() for owner in args.skip_owners.split(",") if owner.strip()
    )
    if skip_owners:
        logger.info("skipping owners: %s", ", ".join(sorted(skip_owners)))

    try:
        repos = list_repositories(skip_owners=skip_owners)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        logger.error("could not list toolshed repositories: %s", error)
        return 1

    logger.info("toolshed lists %d eligible repositories", len(repos))
    _TOOLSHED_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    today = date.today().isoformat()

    counts = {"ok": 0, "skipped": 0, "failed": 0}
    for owner, name in repos:
        outcome, changeset = _fetch_one(owner, name, force=args.force)
        counts[outcome] += 1
        if outcome == "ok":
            manifest[f"{owner}/{name}"] = {
                "changeset": changeset or _UNKNOWN,
                "retrieved": today,
            }
        processed = counts["ok"] + counts["failed"]
        if processed and processed % _PROGRESS_EVERY == 0:
            logger.info(
                "  ... %d cloned, %d skipped, %d failed",
                counts["ok"],
                counts["skipped"],
                counts["failed"],
            )
        if args.limit and counts["ok"] >= args.limit:
            logger.info("--limit %d reached, stopping", args.limit)
            break

    on_disk = _existing_clone_keys()
    stale = [key for key in manifest if key not in on_disk]
    for key in stale:
        del manifest[key]
    if stale:
        logger.info("pruned %d manifest entries with no clone on disk", len(stale))
    backfilled = 0
    for key in on_disk:
        if key not in manifest:
            manifest[key] = {"changeset": _UNKNOWN, "retrieved": _UNKNOWN}
            backfilled += 1
    if backfilled:
        logger.info(
            "manifest backfilled %d on-disk clones with no recorded changeset "
            "(re-run with --force to populate)",
            backfilled,
        )
    _write_manifest(manifest)

    logger.info(
        "fetch complete: %d cloned, %d skipped, %d failed (of %d processed); "
        "manifest -> %s",
        counts["ok"],
        counts["skipped"],
        counts["failed"],
        sum(counts.values()),
        _TOOLSHED_MANIFEST.relative_to(_REPO_ROOT),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
