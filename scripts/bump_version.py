#!/usr/bin/env python3
"""Set every workspace package to one lockstep version.

The eight packages are versioned in lockstep (one number, released as a set —
``galaxy-tool-source/docs/decisions.md`` §27, the naming/publishing decision).
This script is the single bump command: it rewrites each member's
``[project] version`` and pins every *intra-workspace* dependency
(``galaxy-tool-*``) to ``==<version>`` so a published wheel depends on exactly
its release-mates, never a bare unversioned name. Third-party deps
(``lxml>=5`` …) are left untouched.

Edits are line-scoped (not a TOML re-serialise) so comments and formatting are
preserved. Idempotent: re-running with the same version is a no-op. The
``test_workspace_versions`` guard enforces the invariant this script maintains.

    uv run python -m scripts.bump_version 0.2.0
    uv run python -m scripts.bump_version 0.2.0 --check   # verify, write nothing
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ROOT_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# A semantic version like 0.2.0 / 1.0.0rc1 — permissive enough for pre-releases.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+[0-9A-Za-z.+-]*$")

# A ``[project]``-section ``version = "…"`` assignment line.
_VERSION_LINE = re.compile(r'^(?P<prefix>version\s*=\s*")(?P<value>[^"]*)(?P<suffix>".*)$')

# An intra-workspace dependency entry inside the ``dependencies`` array — a
# quoted ``galaxy-tool-…`` requirement, optionally already carrying a specifier
# and/or a trailing comment. Third-party requirements never start ``galaxy-tool-``.
_INTRA_DEP = re.compile(
    r'^(?P<indent>\s*)"(?P<name>galaxy-tool-[a-z0-9-]+)(?P<spec>[^"]*)"(?P<rest>.*)$'
)


_MEMBER_ENTRY = re.compile(r'"(galaxy-tool-[a-z0-9-]+)"')


def _workspace_members() -> list[str]:
    """The workspace member directory names, from the root pyproject.

    A line scan of the ``[tool.uv.workspace] members`` array (no ``tomllib``, so
    this runs on Python 3.10 too — ``tomllib`` is 3.11+).
    """
    text = _ROOT_PYPROJECT.read_text(encoding="utf-8")
    in_members = False
    members: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("members"):
            in_members = "[" in stripped and "]" not in stripped
            continue
        if in_members:
            if stripped == "]":
                break
            match = _MEMBER_ENTRY.search(stripped)
            if match is not None:
                members.append(match.group(1))
    return members


def _bump_pyproject_text(text: str, *, version: str) -> str:
    """Return *text* with the ``[project]`` version and intra-deps set to *version*.

    Only the ``version =`` line inside the ``[project]`` table and the
    ``galaxy-tool-*`` lines inside the ``dependencies`` array are touched.
    """
    out: list[str] = []
    section: str | None = None
    in_dependencies = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            in_dependencies = False
        elif section == "project" and stripped.startswith("dependencies"):
            in_dependencies = "[" in stripped and "]" not in stripped
        elif in_dependencies and stripped == "]":
            in_dependencies = False

        if section == "project":
            version_match = _VERSION_LINE.match(line)
            if version_match is not None:
                out.append(
                    f"{version_match['prefix']}{version}{version_match['suffix']}"
                )
                continue
        if in_dependencies:
            dep_match = _INTRA_DEP.match(line)
            if dep_match is not None:
                out.append(
                    f'{dep_match["indent"]}"{dep_match["name"]}=={version}"'
                    f'{dep_match["rest"]}'
                )
                continue
        out.append(line)
    trailing_newline = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + trailing_newline


def _bump(*, version: str, check: bool) -> int:
    """Apply (or, with *check*, verify) the lockstep version across all members."""
    drifted: list[str] = []
    for member in _workspace_members():
        pyproject = _REPO_ROOT / member / "pyproject.toml"
        original = pyproject.read_text(encoding="utf-8")
        updated = _bump_pyproject_text(original, version=version)
        if updated == original:
            continue
        if check:
            drifted.append(member)
            continue
        pyproject.write_text(updated, encoding="utf-8")
        print(f"bumped {member} -> {version}")
    if check and drifted:
        print(
            f"version drift: {', '.join(drifted)} not at {version} "
            f"(or an intra-dep unpinned) — run: "
            f"uv run python -m scripts.bump_version {version}",
            file=sys.stderr,
        )
        return 1
    if check:
        print(f"all workspace packages are at {version} with pinned intra-deps")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="the lockstep version, e.g. 0.2.0")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every package is at VERSION (write nothing); non-zero on drift",
    )
    args = parser.parse_args(argv)
    if _VERSION_RE.fullmatch(args.version) is None:
        parser.error(f"not a version: {args.version!r}")
    return _bump(version=args.version, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
