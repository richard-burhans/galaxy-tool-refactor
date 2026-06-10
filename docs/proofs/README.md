# Rule proofs — the canonical behaviour-preservation arguments

One document per **fixable** rule: the current, construction-grade,
source-cited argument for why applying the rule preserves behaviour (or which
narrower contract — validity restoration, structural-only, display-contract,
render-equivalence — it preserves instead). This is the *current-state* home
for proofs, the way `ARCHITECTURE.md` is for structure: the dated
`docs/decisions.md` entries record *why at the time*, the audit trail lives in
`../behavior_preservation.md` (verdicts, refutations, remediations), and rule
docstrings carry a summary pointing here.

**The bar** (the maintainer's standing principle): a fixable rule's claim must
hold **by construction for novel tools** — Galaxy-source or spec citations,
never corpus absence. Corpus incidence sizes impact; it never establishes
soundness.

Galaxy-source cites refer to the local clone `.local/galaxy-src` (`dev` @
`c6e0ee3`, 2026-06-01) unless a `release_*` branch is named; release branches
are fetched shallow into the same clone.

**Coverage is guarded:** `galaxy-tool-refactor-registry/tests/test_proof_documents.py`
fails CI naming any fixable rule without a `<code>.md` here, so a new fixable
rule cannot ship proofless.
