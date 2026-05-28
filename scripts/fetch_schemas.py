#!/usr/bin/env python3
"""Download Galaxy release tool XSDs, vendor them, and document their provenance.

A standalone maintenance script — Python standard library only, so it runs
before ``uv sync``. The vendored XSDs are internal, permanent assets: committed
to the repository and normally downloaded once each.

Default run: *additive* — downloads ``galaxy.xsd`` for every Galaxy release not
already vendored, leaving existing files, commits, and dates untouched.
With ``--force``: re-downloads every release XSD, refreshing every file, commit
SHA, retrieval date, and the provenance document.

If the GitHub branch list cannot be retrieved the run falls back to the XSDs
already vendored in ``schema/`` (warns, changes nothing, exits 0) — unless no
XSDs are vendored yet, in which case it exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

logger = logging.getLogger("fetch_schemas")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA_DIR = _REPO_ROOT / "galaxy-tool-xml" / "src" / "galaxy_tool_xml" / "schema"
_MANIFEST_PATH = _SCHEMA_DIR / "manifest.json"
_PROVENANCE_PATH = _SCHEMA_DIR / "PROVENANCE.md"

_MATCHING_REFS_URL = (
    "https://api.github.com/repos/galaxyproject/galaxy"
    "/git/matching-refs/heads/release_?per_page=100"
)
_RAW_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/galaxyproject/galaxy/{branch}/{path}"
)
# Galaxy moved the XSD around release 20.09; try the modern path first.
_XSD_PATHS = (
    "lib/galaxy/tool_util/xsd/galaxy.xsd",
    "lib/galaxy/tools/xsd/galaxy.xsd",
)
_VERSION_RE = re.compile(r"^\d+\.\d+$")
_USER_AGENT = "galaxy-tool-xml-fetch-schemas"
_HTTP_TIMEOUT = 30


def version_sort_key(version: str) -> tuple[int, int]:
    """Order a ``MAJOR.MINOR`` version string numerically."""
    major, minor = version.split(".")
    return int(major), int(minor)


def _next_link(link_header: str | None) -> str | None:
    """Extract the ``rel="next"`` URL from an HTTP ``Link`` header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = [segment.strip() for segment in part.split(";")]
        if len(segments) < 2:
            continue
        url_part, rel_part = segments[0], segments[1]
        if (
            rel_part == 'rel="next"'
            and url_part.startswith("<")
            and url_part.endswith(">")
        ):
            return url_part[1:-1]
    return None


def _api_get(url: str) -> tuple[bytes, str | None]:
    """GET a GitHub API URL; return ``(body, next_link)``. Raises on failure."""
    request = urllib.request.Request(url)  # noqa: S310 — fixed https GitHub host
    request.add_header("User-Agent", _USER_AGENT)
    request.add_header("Accept", "application/vnd.github+json")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:  # noqa: S310
        return response.read(), response.headers.get("Link")


def list_release_branches() -> list[dict[str, str]]:
    """Return ``{version, branch, commit}`` for every ``release_*`` branch.

    Raises ``urllib.error.URLError`` / ``TimeoutError`` / ``json.JSONDecodeError``
    if the GitHub API cannot be reached or returns an unusable response.
    """
    branches: list[dict[str, str]] = []
    url: str | None = _MATCHING_REFS_URL
    while url:
        body, next_link = _api_get(url)
        for ref in json.loads(body):
            name = ref["ref"].removeprefix("refs/heads/")
            branches.append(
                {
                    "version": name.removeprefix("release_"),
                    "branch": name,
                    "commit": ref["object"]["sha"],
                }
            )
        url = next_link
    return branches


def _try_download(url: str) -> bytes | None:
    """Download ``url``; return its bytes, or ``None`` on 404 / network error."""
    request = urllib.request.Request(url)  # noqa: S310 — fixed https GitHub host
    request.add_header("User-Agent", _USER_AGENT)
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:  # noqa: S310
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code != 404:
            logger.warning("download failed (HTTP %s): %s", error.code, url)
        return None
    except (urllib.error.URLError, TimeoutError) as error:
        logger.warning("download failed (%s): %s", error, url)
        return None


def download_xsd(branch: str) -> tuple[str, bytes] | None:
    """Fetch ``galaxy.xsd`` for a release branch; return ``(path_in_repo, bytes)``."""
    for path in _XSD_PATHS:
        content = _try_download(_RAW_URL_TEMPLATE.format(branch=branch, path=path))
        if content is not None:
            return path, content
    return None


def load_existing_schemas() -> dict[str, dict[str, str]]:
    """Load the ``schemas`` section of ``manifest.json``, or ``{}``.

    The ``latest`` key in the on-disk manifest is denormalized from
    ``schemas`` at write time, so the read path only consumes the
    per-version entries. Returning the schemas dict directly avoids the
    ``object``-typed envelope the previous shape forced on callers.
    """
    if not _MANIFEST_PATH.exists():
        return {}
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        return {}
    schemas = manifest.get("schemas")
    if not isinstance(schemas, dict):
        return {}
    return {
        key: dict(value) for key, value in schemas.items() if isinstance(value, dict)
    }


def write_manifest(schemas: dict[str, dict[str, str]]) -> None:
    """Write ``manifest.json`` deterministically (sorted keys)."""
    latest = max(schemas, key=version_sort_key) if schemas else None
    manifest = {"latest": latest, "schemas": schemas}
    _MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_provenance(schemas: dict[str, dict[str, str]]) -> None:
    """Regenerate ``PROVENANCE.md`` from the manifest entries."""
    rows = sorted(
        schemas.values(),
        key=lambda entry: version_sort_key(entry["version"]),
        reverse=True,
    )
    lines = [
        "# Vendored Galaxy Tool XSDs — Provenance",
        "",
        "This directory holds vendored copies of Galaxy's tool definition schema",
        "(`galaxy.xsd`), one `galaxy-<version>.xsd` file per Galaxy release that ships",
        "it. They are internal, permanent assets of this repository.",
        "",
        "## Methodology",
        "",
        "`scripts/fetch_schemas.py` lists the `release_*` branches of",
        "`galaxyproject/galaxy` via the GitHub REST `git/matching-refs` endpoint, then",
        "downloads `galaxy.xsd` from each branch — trying",
        "`lib/galaxy/tool_util/xsd/galaxy.xsd` first and the older",
        "`lib/galaxy/tools/xsd/galaxy.xsd` second. Releases that ship neither (they",
        "predate the XSD) are skipped. Each commit SHA below is the branch head at",
        "retrieval time.",
        "",
        "## Vendored schemas",
        "",
        "| Version | Release branch | Commit | Path in repo | Source URL | Retrieved |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in rows:
        source_url = _RAW_URL_TEMPLATE.format(
            branch=entry["release_branch"], path=entry["path_in_repo"]
        )
        lines.append(
            f"| {entry['version']} | {entry['release_branch']} | {entry['commit']} "
            f"| `{entry['path_in_repo']}` | {source_url} | {entry['retrieved']} |"
        )
    lines += [
        "",
        "## Third-party attribution",
        "",
        "These XSD files are extracted verbatim from the Galaxy project",
        "(`galaxyproject/galaxy`, <https://github.com/galaxyproject/galaxy>) and",
        "remain subject to that project's license. They are redistributed here",
        "unmodified as a convenience for offline, profile-aware validation.",
        "",
    ]
    _PROVENANCE_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    """Run the fetch; return a process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download every release XSD, refreshing files, commits, and dates",
    )
    args = parser.parse_args()

    _SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    existing_schemas = load_existing_schemas()

    branches: list[dict[str, str]] | None
    try:
        branches = list_release_branches()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        logger.warning("could not list Galaxy release branches: %s", error)
        branches = None

    if branches is None:
        vendored = sorted(_SCHEMA_DIR.glob("galaxy-*.xsd"))
        if not vendored:
            logger.error(
                "GitHub API unreachable and no XSDs are vendored yet — cannot proceed."
            )
            return 1
        logger.warning(
            "GitHub API unreachable — keeping %d vendored XSD(s); "
            "manifest.json and PROVENANCE.md left untouched.",
            len(vendored),
        )
        return 0

    candidates = sorted(
        (b for b in branches if _VERSION_RE.match(b["version"])),
        key=lambda b: version_sort_key(b["version"]),
    )
    today = date.today().isoformat()
    schemas = dict(existing_schemas)

    for branch_info in candidates:
        version = branch_info["version"]
        if not args.force and version in existing_schemas:
            continue
        result = download_xsd(branch_info["branch"])
        if result is None:
            logger.info("release %s ships no galaxy.xsd — skipped", version)
            continue
        path_in_repo, content = result
        file_name = f"galaxy-{version}.xsd"
        (_SCHEMA_DIR / file_name).write_bytes(content)
        schemas[version] = {
            "version": version,
            "release_branch": branch_info["branch"],
            "commit": branch_info["commit"],
            "path_in_repo": path_in_repo,
            "file": file_name,
            "retrieved": today,
        }
        logger.info("vendored galaxy-%s.xsd (%s)", version, path_in_repo)

    if not schemas:
        logger.error(
            "no Galaxy release shipped a usable galaxy.xsd — nothing vendored."
        )
        return 1

    write_manifest(schemas)
    write_provenance(schemas)
    logger.info(
        "collection holds %d XSD(s); latest is %s",
        len(schemas),
        max(schemas, key=version_sort_key),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
