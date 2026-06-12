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


def test_behavior_gate_proof_covers_every_auto_fix_and_upgrade_step() -> None:
    """The gate's soundness document must name every fix it credits, and the
    GTR012 composition every walk step it sequences: a new RuntimeGatedFix or
    upgrade_vN cannot join the gated walk without extending the argument."""
    from galaxy_tool_codemod.runtime_fixes import RUNTIME_GATED_FIXES
    from galaxy_tool_codemod.upgrades import UPGRADE_CODEMODS

    gate_doc = _PROOFS_DIR / "behavior-gate.md"
    assert gate_doc.is_file(), "docs/proofs/behavior-gate.md is missing"
    text = gate_doc.read_text(encoding="utf-8")
    missing = sorted(
        name
        for fix in RUNTIME_GATED_FIXES
        for name in (fix.meta.code, fix.upgrade_code)
        if name not in text
    )
    assert not missing, (
        f"behavior-gate.md does not mention: {missing}; extend the gate proof "
        "for the new auto-fix before shipping it"
    )
    composition = (_PROOFS_DIR / "GTR012.md").read_text(encoding="utf-8")
    unproven_steps = sorted(
        cls.meta.code
        for cls in UPGRADE_CODEMODS.values()
        if cls.meta.code not in composition
        or not (_PROOFS_DIR / f"{cls.meta.code}.md").is_file()
    )
    assert not unproven_steps, (
        f"upgrade step(s) missing from the GTR012 composition or without a "
        f"proof doc: {unproven_steps}"
    )
