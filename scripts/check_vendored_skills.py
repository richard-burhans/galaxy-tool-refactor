"""Check the vendored third-party skills against their upstream sources.

Two skills under ``.claude/skills/`` are verbatim copies of external sources
(each records its provenance in a ``VENDORED.md``):

- ``dignified-python`` — the *governing* Python coding standard, vendored from
  the ``dagster-io/skills`` repository.
- ``optimized-python`` — a *reference* standard, wrapped from a public gist.

This script reports when an upstream source has moved past the revision we
vendored, so a maintainer can decide whether to **re-vendor**. Re-vendoring is a
deliberate choice, not an automatic one: upstream can soften or change the
governing standard (it did on 2026-06-13), so a human reviews the delta and
reconciles the dependent docs (``CLAUDE.md``, ``/pre-pr-audit``) before adopting
it. This script therefore only *detects and reports* drift; it never edits the
vendored files.

It is network-dependent (it queries the GitHub API via ``gh``), so it is **not**
part of the QA gate. Run it on demand with ``make check-skills`` or let the
weekly ``.github/workflows/vendored-skills.yml`` job run it and open a tracking
issue when drift appears.

Exit codes: ``0`` all sources in sync, ``1`` at least one source drifted,
``2`` at least one check could not be completed (network/tooling error).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class VendoredSource:
    """An upstream source we track for drift, plus the revision we vendored.

    ``baseline`` is the upstream revision our local copy was confirmed identical
    to. For a ``git`` source it is the latest commit that touched ``path`` on
    ``branch``; for a ``gist`` source it is the gist's latest history version.
    """

    skill: str
    kind: str  # "git" | "gist"
    baseline: str
    # git sources
    repo: str | None = None
    branch: str | None = None
    path: str | None = None
    # gist sources
    gist_id: str | None = None
    note: str = ""


# The provenance of record lives in each skill's VENDORED.md; this table is the
# machine-checkable mirror the drift job reads. Keep the two in sync when you
# re-vendor (update the baseline here and add a dated note to VENDORED.md).
VENDORED_SOURCES: tuple[VendoredSource, ...] = (
    VendoredSource(
        skill="dignified-python",
        kind="git",
        repo="dagster-io/skills",
        branch="master",
        path="skills/dignified-python/skills/dignified-python",
        baseline="f904a2a218b3b3dd85152dbd4747854ae88b4cab",
        note="last upstream change 2026-04-28; copy verified byte-identical 2026-06-20",
    ),
    VendoredSource(
        skill="optimized-python",
        kind="gist",
        gist_id="10b780671ee5d695b4369b987413b38f",
        baseline="f06ad4f1430a8d9f268b160a755dab817384c93c",
        note="gist last updated 2026-05-21; revision verified 2026-06-20",
    ),
)


class CheckError(RuntimeError):
    """A source could not be checked (network or tooling failure)."""


def _gh_api(endpoint: str) -> object:
    """Return the parsed JSON body of a ``gh api`` call.

    ``gh`` carries the GitHub credentials in both the sandbox (proxy-injected)
    and CI (``GITHUB_TOKEN``), so this needs no token handling of its own.
    """

    completed = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
        env={"GH_TOKEN": "x", **os.environ},
    )
    if completed.returncode != 0:
        raise CheckError(f"`gh api {endpoint}` failed: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def current_revision(source: VendoredSource) -> str:
    """Return the upstream revision a fresh vendoring would capture today."""

    if source.kind == "git":
        endpoint = (
            f"repos/{source.repo}/commits"
            f"?path={source.path}&sha={source.branch}&per_page=1"
        )
        commits = _gh_api(endpoint)
        if not isinstance(commits, list) or not commits:
            raise CheckError(f"no commits returned for {source.repo}:{source.path}")
        return str(commits[0]["sha"])

    if source.kind == "gist":
        gist = _gh_api(f"gists/{source.gist_id}")
        if not isinstance(gist, dict):
            raise CheckError(f"unexpected gist response for {source.gist_id}")
        return str(gist["history"][0]["version"])

    raise CheckError(f"unknown source kind: {source.kind!r}")


@dataclass(frozen=True, kw_only=True)
class CheckResult:
    source: VendoredSource
    status: str  # "ok" | "drift" | "error"
    current: str = ""
    detail: str = ""


def check_source(source: VendoredSource) -> CheckResult:
    try:
        current = current_revision(source)
    except CheckError as error:
        return CheckResult(source=source, status="error", detail=str(error))
    if current == source.baseline:
        return CheckResult(source=source, status="ok", current=current)
    return CheckResult(source=source, status="drift", current=current)


def _format_report(results: list[CheckResult]) -> str:
    lines = ["Vendored-skill upstream check", "=" * 32, ""]
    for result in results:
        source = result.source
        if result.status == "ok":
            lines.append(f"[ok]    {source.skill}: in sync ({source.baseline[:12]})")
        elif result.status == "drift":
            origin = source.repo or f"gist:{source.gist_id}"
            lines.append(f"[DRIFT] {source.skill}: upstream {origin} has moved")
            lines.append(f"          vendored: {source.baseline}")
            lines.append(f"          upstream: {result.current}")
            lines.append(
                "          -> review the delta and decide whether to re-vendor "
                f"(see .claude/skills/{source.skill}/VENDORED.md)"
            )
        else:
            lines.append(f"[error] {source.skill}: {result.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON instead of text"
    )
    args = parser.parse_args(argv)

    results = [check_source(source) for source in VENDORED_SOURCES]

    if args.json:
        payload = [
            {
                "skill": r.source.skill,
                "status": r.status,
                "baseline": r.source.baseline,
                "current": r.current,
                "detail": r.detail,
            }
            for r in results
        ]
        print(json.dumps(payload, indent=2))
    else:
        print(_format_report(results))

    if any(r.status == "error" for r in results):
        return 2
    if any(r.status == "drift" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
