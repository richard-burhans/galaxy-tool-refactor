"""Architecture guard: the eight packages are versioned in lockstep.

They release as one set (``galaxy-tool-source/docs/decisions.md`` §27), so every
member must carry the *same* ``[project] version`` and pin its intra-workspace
dependencies to ``==<that version>`` — otherwise a published wheel would depend
on a bare, unversioned ``galaxy-tool-*`` name and pip could resolve a mismatched
release-mate. ``scripts/bump_version.py`` maintains this; this guard enforces it
(and fails naming the bump command, so a drift can't be merged).

Dependency-free line scan (no ``tomllib``) so it runs identically on every
Python in the CI matrix (3.10 has no ``tomllib``).
"""

from __future__ import annotations

import re
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# The nine workspace members — the eight code/tier packages plus the
# `galaxy-tool-refactor` front-door metapackage (its directory is `…-meta`). Kept
# explicit — a len() tripwire, like the other roster lists in the tree.
_MEMBERS = (
    "galaxy-tool-refactor-rules",
    "galaxy-tool-source",
    "galaxy-tool-codemod",
    "galaxy-tool-fmt",
    "galaxy-tool-lint",
    "galaxy-tool-refactor-registry",
    "galaxy-tool-refactor-cli",
    "galaxy-tool-refactor-mcp",
    "galaxy-tool-refactor-meta",
)

_VERSION_LINE = re.compile(r'^version\s*=\s*"(?P<value>[^"]+)"', re.MULTILINE)
_INTRA_DEP = re.compile(r'"(?P<name>galaxy-tool-[a-z0-9-]+)(?P<spec>[^"]*)"')


def _project_version(text: str) -> str:
    """The ``[project]`` table's ``version`` value (first such line)."""
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project:
            match = _VERSION_LINE.match(stripped)
            if match is not None:
                return match["value"]
    raise AssertionError("no [project] version found")


_OPTIONAL_ARRAY = re.compile(r"^[A-Za-z0-9_.-]+\s*=\s*\[")


def _intra_dep_specs(text: str) -> list[tuple[str, str]]:
    """Every ``galaxy-tool-*`` dependency as ``(name, specifier)`` — the specifier
    is ``""`` when the dep is bare.

    Covers both the ``[project] dependencies`` array and each
    ``[project.optional-dependencies]`` extra (a metapackage pins its ``[mcp]``
    extra there)."""
    section: str | None = None
    in_dependencies = False
    specs: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            in_dependencies = False
            continue
        if section == "project" and stripped.startswith("dependencies"):
            in_dependencies = "[" in stripped and "]" not in stripped
            continue
        if section == "project.optional-dependencies" and _OPTIONAL_ARRAY.match(
            stripped
        ):
            in_dependencies = "]" not in stripped
            continue
        if in_dependencies:
            if stripped == "]":
                in_dependencies = False
                continue
            match = _INTRA_DEP.search(stripped)
            if match is not None:
                specs.append((match["name"], match["spec"]))
    return specs


def _member_text(member: str) -> str:
    return (_WORKSPACE_ROOT / member / "pyproject.toml").read_text(encoding="utf-8")


def test_roster_matches_the_workspace() -> None:
    """The member list here equals the root pyproject's workspace members."""
    root = (_WORKSPACE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = set(re.findall(r'"(galaxy-tool-[a-z0-9-]+)"', root))
    assert declared == set(_MEMBERS), (
        "test_workspace_versions._MEMBERS is out of sync with the root "
        "pyproject [tool.uv.workspace] members"
    )
    assert len(_MEMBERS) == 9


def test_all_packages_share_one_version() -> None:
    versions = {member: _project_version(_member_text(member)) for member in _MEMBERS}
    distinct = set(versions.values())
    assert len(distinct) == 1, (
        f"workspace versions are not in lockstep: {versions}. Unify with "
        "`uv run python -m scripts.bump_version <version>`."
    )


def test_intra_deps_are_pinned_to_the_shared_version() -> None:
    """Every galaxy-tool-* dependency is pinned ``==<the shared version>``.

    A bare or differently-pinned intra-dep would publish a wheel that resolves a
    mismatched release-mate on PyPI.
    """
    shared = _project_version(_member_text(_MEMBERS[0]))
    expected = f"=={shared}"
    problems: list[str] = []
    for member in _MEMBERS:
        for name, spec in _intra_dep_specs(_member_text(member)):
            if spec != expected:
                problems.append(
                    f"{member}: {name!r} pinned {spec!r}, want {expected!r}"
                )
    assert not problems, "intra-dep pins drifted:\n" + "\n".join(problems) + (
        "\nRe-run `uv run python -m scripts.bump_version <version>`."
    )
