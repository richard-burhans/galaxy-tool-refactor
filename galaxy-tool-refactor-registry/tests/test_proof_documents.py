"""Every fixable rule must carry a proof document (docs/proofs/<code>.md).

The behaviour-preservation bar: a fixable rule's claim holds by construction,
recorded in a per-rule proof doc (``docs/proofs/README.md``). This guard makes
shipping a proofless fixable rule a CI failure naming the missing file.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_refactor_registry.registry import all_handles

_PROOFS_DIR = Path(__file__).resolve().parents[2] / "docs" / "proofs"


def test_every_fixable_rule_has_a_proof_document() -> None:
    missing = sorted(
        code
        for code, handle in all_handles().items()
        if handle.fixable and not (_PROOFS_DIR / f"{code}.md").is_file()
    )
    assert not missing, (
        f"fixable rule(s) without docs/proofs/<code>.md: {missing} — write the "
        "construction-grade proof (see docs/proofs/README.md) before shipping"
    )


def test_no_orphan_proof_documents() -> None:
    fixable = {code for code, handle in all_handles().items() if handle.fixable}
    orphans = sorted(
        path.stem
        for path in _PROOFS_DIR.glob("GTR*.md")
        if path.stem not in fixable
    )
    assert not orphans, f"proof doc(s) for unknown/non-fixable rules: {orphans}"
