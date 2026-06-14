"""Every advisory (detect-only) rule must carry a documentation citation.

The overarching-goal contract (``docs/design_principles.md``): a finding the
toolchain cannot auto-fix must point the author at detailed documentation. The
user-facing path is ``RuleMeta.cite`` — surfaced by ``check``'s closing
``References`` block and by the ``rules`` command. This guard makes shipping a
citeless advisory rule a CI failure, the companion to
``test_proof_documents.py`` (which guards the *fixable* half: a fixable rule
must carry a construction-grade proof).
"""

from __future__ import annotations

from galaxy_tool_refactor_registry.registry import all_handles


def test_every_advisory_rule_has_a_citation() -> None:
    missing = sorted(
        code
        for code, handle in all_handles().items()
        if not handle.fixable and not (handle.meta.cite or "").strip()
    )
    assert not missing, (
        f"advisory rule(s) without a RuleMeta.cite: {missing} — add the "
        "documentation URL the warning should point authors at (the overarching-goal "
        "contract; see docs/design_principles.md)"
    )
