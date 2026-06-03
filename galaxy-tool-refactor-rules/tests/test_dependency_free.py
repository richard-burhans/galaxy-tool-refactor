"""Guard: tier 0.5 (``galaxy-tool-refactor-rules``) must stay dependency-free.

The whole point of this tier is to be a shared primitive that the codemod and fmt
tiers can each carry without depending on each other (ARCHITECTURE.md §2; rules
``docs/decisions.md`` §D1). A single third-party or higher-tier import here would
re-couple the tiers it exists to keep apart. The invariant was prose-only — the
architecture audit (2026-06-03, `docs/architecture_audit.md`) flagged it as
unguarded — so this test enforces it: every import in the package's ``src`` must
resolve to the standard library or the package itself. A future commit that adds,
say, an ``lxml`` import fails here loudly.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import galaxy_tool_refactor_rules

_PACKAGE = "galaxy_tool_refactor_rules"
_PACKAGE_DIR = Path(galaxy_tool_refactor_rules.__file__).parent
# Top-level module names an import in this tier may reference: the standard
# library, ``__future__``, and the package itself. Nothing else.
_ALLOWED_ROOTS = set(sys.stdlib_module_names) | {_PACKAGE, "__future__"}


def _imported_roots(source: str, /) -> set[str]:
    """The top-level module names *source* imports absolutely.

    Relative imports (``from . import x``) are internal and carry no external
    coupling, so they are ignored.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_rules_tier_imports_only_stdlib_and_self() -> None:
    offenders: dict[str, set[str]] = {}
    for path in sorted(_PACKAGE_DIR.rglob("*.py")):
        external = _imported_roots(path.read_text(encoding="utf-8")) - _ALLOWED_ROOTS
        if external:
            offenders[str(path.relative_to(_PACKAGE_DIR))] = external
    assert not offenders, (
        "tier 0.5 must stay dependency-free (ARCHITECTURE.md §2), but these files "
        f"import non-stdlib, non-self modules: {offenders}"
    )


def test_guard_detects_a_planted_violation() -> None:
    """The scan would actually catch a forbidden import (not a vacuous pass)."""
    assert _imported_roots("import lxml.etree") == {"lxml"}
    assert _imported_roots("from galaxy_tool_xml.binding import load_tool") == {
        "galaxy_tool_xml"
    }
    # stdlib + self + a relative import are all allowed (subtract to empty).
    allowed = _imported_roots(
        "import sys\nfrom dataclasses import dataclass\n"
        "from galaxy_tool_refactor_rules.meta import RuleMeta\n"
        "from . import violation\n"
    )
    assert allowed - _ALLOWED_ROOTS == set()
