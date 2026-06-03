"""Architecture guard: the dependency direction holds at the *import* level.

The load-bearing rule of the stack (`ARCHITECTURE.md` §1) is **no tier depends on a
higher one**, and the sibling rule tiers (codemod / fmt / check) never import each
other. `ARCHITECTURE.md` §9 asserts this in prose and each `pyproject.toml` declares
it, but nothing failed if a *future* commit added a stray cross-tier import (e.g. fmt
importing codemod, or the CLI reaching into codemod instead of going through the
facade). This guard closes that gap.

It scans every package's `src/` for `import`/`from galaxy_tool_*` statements and
fails if any package imports a workspace package outside its **allowed** set — the
direct-dependency edges the architecture permits (which mirror the `pyproject.toml`
dependencies). It flags `TYPE_CHECKING` imports too: a type-only import of a *higher*
tier is still a layering violation. Corpus-free + deterministic → runs in CI /
`qa_gate.sh`. Companion to `test_serializer_allowlist.py` (same arch-test shape).

Adding a genuinely new cross-tier edge means updating both the `pyproject.toml` *and*
`_ALLOWED` here — the intended friction for a change to the architecture's shape.
"""

from __future__ import annotations

import re
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# Package directory -> import package name.
_PACKAGES: dict[str, str] = {
    "galaxy-tool-refactor-rules": "galaxy_tool_refactor_rules",
    "galaxy-tool-xml": "galaxy_tool_xml",
    "galaxy-tool-xml-codemod": "galaxy_tool_xml_codemod",
    "galaxy-tool-xml-fmt": "galaxy_tool_xml_fmt",
    "galaxy-tool-xml-check": "galaxy_tool_xml_check",
    "galaxy-tool-refactor-registry": "galaxy_tool_refactor_registry",
    "galaxy-tool-refactor-cli": "galaxy_tool_refactor_cli",
    "galaxy-tool-refactor-mcp": "galaxy_tool_refactor_mcp",
}
_ALL = frozenset(_PACKAGES.values())

# The cross-tier import edges the architecture permits (excluding self). Mirrors the
# `pyproject.toml` dependency declarations and the §1 dependency diagram.
_ALLOWED: dict[str, frozenset[str]] = {
    "galaxy_tool_refactor_rules": frozenset(),  # tier 0.5 — dependency-free
    "galaxy_tool_xml": frozenset(),  # tier 1 — no workspace deps
    "galaxy_tool_xml_codemod": frozenset(
        {"galaxy_tool_refactor_rules", "galaxy_tool_xml"}
    ),
    "galaxy_tool_xml_fmt": frozenset(
        {"galaxy_tool_refactor_rules", "galaxy_tool_xml"}
    ),
    "galaxy_tool_xml_check": frozenset(
        {"galaxy_tool_refactor_rules", "galaxy_tool_xml"}
    ),
    "galaxy_tool_refactor_registry": frozenset(
        {
            "galaxy_tool_refactor_rules",
            "galaxy_tool_xml",
            "galaxy_tool_xml_codemod",
            "galaxy_tool_xml_fmt",
            "galaxy_tool_xml_check",
        }
    ),
    # The CLI is a thin front-end: registry facade + fmt's cli_support engine + tier-1
    # parsing — never codemod / check directly (cli `docs/decisions.md` D4).
    "galaxy_tool_refactor_cli": frozenset(
        {"galaxy_tool_xml", "galaxy_tool_xml_fmt", "galaxy_tool_refactor_registry"}
    ),
    "galaxy_tool_refactor_mcp": frozenset(
        {
            "galaxy_tool_refactor_rules",
            "galaxy_tool_xml",
            "galaxy_tool_refactor_registry",
        }
    ),
}

_IMPORT = re.compile(
    r"^[ \t]*(?:from|import)[ \t]+(galaxy_tool_[a-z_]+)", re.MULTILINE
)


def _imported_packages(text: str, /) -> set[str]:
    """The workspace packages a source file imports (top-level package per import)."""
    return {match for match in _IMPORT.findall(text) if match in _ALL}


def imported_workspace_packages(pkg_import_name: str, /) -> set[str]:
    """Every workspace package imported anywhere in *pkg_import_name*'s ``src/``."""
    pkg_dir = next(d for d, name in _PACKAGES.items() if name == pkg_import_name)
    src = _WORKSPACE_ROOT / pkg_dir / "src"
    found: set[str] = set()
    for path in src.rglob("*.py"):
        found |= _imported_packages(path.read_text(encoding="utf-8"))
    return found - {pkg_import_name}


def test_import_regex_extracts_top_level_package() -> None:
    """The scanner reads the top-level package, distinguishing xml from xml_codemod."""
    text = (
        "from galaxy_tool_xml.binding import load_tool\n"
        "import galaxy_tool_xml_codemod.catalog\n"
        "    from galaxy_tool_refactor_rules.meta import RuleMeta  # indented\n"
    )
    assert _imported_packages(text) == {
        "galaxy_tool_xml",
        "galaxy_tool_xml_codemod",
        "galaxy_tool_refactor_rules",
    }


def test_packages_resolve_to_real_src_dirs() -> None:
    """Every mapped package has a real ``src/`` (a renamed package is a bug)."""
    for pkg_dir in _PACKAGES:
        assert (_WORKSPACE_ROOT / pkg_dir / "src").is_dir(), pkg_dir


def test_no_tier_imports_a_disallowed_package() -> None:
    """Each package imports only workspace packages its tier is allowed to (the
    dependency direction holds; siblings codemod/fmt/check never import each other;
    the CLI never reaches codemod/check directly)."""
    failures: list[str] = []
    for name in _ALL:
        illegal = imported_workspace_packages(name) - _ALLOWED[name]
        if illegal:
            failures.append(f"{name} imports disallowed {sorted(illegal)}")
    assert not failures, "Tier-boundary violation(s):\n  " + "\n  ".join(failures)
