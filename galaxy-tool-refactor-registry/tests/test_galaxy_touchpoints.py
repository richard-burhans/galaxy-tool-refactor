"""Architecture guard: the Galaxy-code touchpoint inventory stays complete.

``docs/galaxy_reimplementations.md`` claims to be the **complete inventory** of
Galaxy code this workspace executes, and every reimplement-or-keep decision is
recorded there (the standing convention). This guard mechanizes the
completeness claim, so it cannot rot: it scans every hand-written source file
for ``galaxy.*`` imports (the `galaxy-util` / `galaxy-tool-util` surface) and
CT3 ``Cheetah`` imports (touchpoint 2's engine), and fails when the set of
importing files differs from the recorded touchpoints — in either direction. A
new import site needs a ledger entry (and a line here); a retired one needs
the ledger updated too.

Verified against the ledger 2026-07-02 (the galaxy-dep reimplementation
audit): the import surface is exactly touchpoints 1 (macro expansion), 2 (the
CT3 lexer), 5 (the opt-in test-validation binding), and the dev-only parity
oracles for touchpoints 3 and 4 in ``scripts/measure.py``.

Corpus-free and deterministic (pure file reads) → runs in CI / ``qa_gate.sh``.
Sibling of ``test_decision_citations.py`` / ``test_stat_artifact_coverage.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

# The workspace root is two levels up from this test file
# (<root>/galaxy-tool-refactor-registry/tests/<this file>).
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# Directories never scanned: machine-local scratch, envs, and the generated
# per-version models (build products, not hand-written code).
_SKIP_PARTS = {".local", ".venv", ".git", ".sbx", "node_modules", "models"}

_GALAXY_IMPORT = re.compile(r"^\s*(?:from|import)\s+galaxy\.", re.MULTILINE)
_CHEETAH_IMPORT = re.compile(r"^\s*(?:from|import)\s+Cheetah\b", re.MULTILINE)

# The recorded touchpoint files (docs/galaxy_reimplementations.md), workspace-
# relative. Growing either set requires a ledger entry first.
_GALAXY_TOUCHPOINTS = {
    # Touchpoint 1 — macro expansion (galaxy.util.xml_macros), KEEP.
    "galaxy-tool-source/src/galaxy_tool_source/macros.py",
    # Touchpoint 5 — the opt-in [test-validation] binding (GTR100/GTR101).
    "galaxy-tool-lint/src/galaxy_tool_lint/checks/test_validation.py",
    # Touchpoints 3 + 4 — the dev-only parity oracles (test-case-validation-
    # truth, datatype-validation-truth, test-param-qualification).
    "scripts/measure.py",
}
_CHEETAH_TOUCHPOINTS = {
    # Touchpoint 2 — the faithful CT3 lexer (galaxy-util[template]), KEEP.
    "galaxy-tool-source/src/galaxy_tool_source/cheetah_cdm.py",
}


def _source_files() -> list[Path]:
    """Every hand-written ``.py`` under the packages' ``src/`` trees + ``scripts/``."""
    files: list[Path] = []
    for src_dir in sorted(_WORKSPACE_ROOT.glob("galaxy-tool-*/src")):
        files.extend(
            path
            for path in sorted(src_dir.rglob("*.py"))
            if not (_SKIP_PARTS & set(path.parts))
        )
    files.extend(sorted((_WORKSPACE_ROOT / "scripts").glob("*.py")))
    return files


def _importing_files(pattern: re.Pattern[str]) -> set[str]:
    """Workspace-relative paths of source files with an import matching *pattern*."""
    return {
        path.relative_to(_WORKSPACE_ROOT).as_posix()
        for path in _source_files()
        if pattern.search(path.read_text(encoding="utf-8"))
    }


def test_galaxy_imports_match_the_recorded_touchpoints() -> None:
    actual = _importing_files(_GALAXY_IMPORT)
    assert actual == _GALAXY_TOUCHPOINTS, (
        "the galaxy.* import surface diverged from docs/galaxy_reimplementations.md:\n"
        f"  unrecorded import sites: {sorted(actual - _GALAXY_TOUCHPOINTS) or 'none'}\n"
        f"  recorded but no longer importing: "
        f"{sorted(_GALAXY_TOUCHPOINTS - actual) or 'none'}\n"
        "add or retire the touchpoint in the ledger, then update this guard."
    )


def test_cheetah_imports_match_the_recorded_touchpoint() -> None:
    actual = _importing_files(_CHEETAH_IMPORT)
    assert actual == _CHEETAH_TOUCHPOINTS, (
        "the CT3 (Cheetah) import surface diverged from "
        "docs/galaxy_reimplementations.md touchpoint 2:\n"
        f"  unrecorded import sites: "
        f"{sorted(actual - _CHEETAH_TOUCHPOINTS) or 'none'}\n"
        f"  recorded but no longer importing: "
        f"{sorted(_CHEETAH_TOUCHPOINTS - actual) or 'none'}\n"
        "add or retire the touchpoint in the ledger, then update this guard."
    )
