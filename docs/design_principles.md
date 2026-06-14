# Design principles — the two contracts

`galaxy-tool-refactor` exists to serve one overarching goal, stated by the
maintainer and refined here into two precise, enforceable contracts. Every rule,
warning, and document is held to them.

> **Fix everything we can prove preserves behavior; for everything else, point the
> author at detailed documentation explaining the issue and exactly what to do.**

## Contract 1 — a fix must be behavior-preserving *by construction*

A rule that **changes** a tool (a fixable fmt rule or a codemod) may ship only when
its behavior-preservation holds **by construction** — argued per tool, proven from
the structure of the change, never assumed from "the corpus didn't break"
(see [`behavior_preservation.md`](behavior_preservation.md) and the
construction-soundness standing rule). Anything that cannot meet that bar is **not**
auto-fixed; it is downgraded to an advisory check (Contract 2).

Precise criteria:

- Every **fixable** rule carries a construction-grade proof at
  `docs/proofs/<code>.md` (partition sub-codes included, e.g. `GTR020.1.md`).
- Every **runtime-gated** auto-fix and upgrade step is covered by the behavior-gate
  proof, [`docs/proofs/behavior-gate.md`](proofs/behavior-gate.md): the fix is
  applied only where executing it on a copy and re-detecting proves it safe for
  *that* tool.
- `upgrade` is minimal-bump by default: `profile=` moves only when validity strictly
  requires it; the behavior-preserving walk is the opt-in `--modernize`, capped at
  the behaviour ceiling (no un-cleared `must_fix` crossing) and the deployment
  ceiling.

**Enforcement (executable, in `qa_gate.sh`):**
`galaxy-tool-refactor-registry/tests/test_proof_documents.py` fails CI naming any
fixable rule without a proof doc, any orphan proof, or any auto-fix/upgrade step the
behavior-gate proof omits.

## Contract 2 — every non-fixable warning points to detailed docs

A finding the toolchain **cannot** auto-fix must do two things: say what is wrong in
constructive, Code-of-Conduct-respecting language (`Violation.message`), and point
the author at detailed documentation explaining the issue and what to do. The
documentation pointer is `RuleMeta.cite`.

Precise criteria:

- Every **advisory** (`detect_only`) rule carries a non-empty `RuleMeta.cite`.
- The pointer is **surfaced to the user**, not just held in metadata:
  - `check` closes with a deduplicated **References** block mapping each fired code
    to its citation URL, plus a pointer to the full `rules` reference.
  - `rules` prints each rule's `doc:<cite>`.
  - `upgrade` stop reports name the blocking code(s) and link to
    [`profile_boundaries.md`](profile_boundaries.md) (the per-boundary "now what"
    reference) — the model this contract generalizes.
- Messages follow the Galaxy Community Code of Conduct: welcoming, never
  author-blaming, always a constructive next step.

**Enforcement (executable, in `qa_gate.sh`):**
`galaxy-tool-refactor-registry/tests/test_advisory_citations.py` fails CI naming any
advisory rule without a `cite`. (The surfacing itself is covered by the CLI tests for
`check`'s References footer and `rules`' `doc:` field.)

## Why "by construction", not "by corpus"

A corpus sweep can only show a fix did not break the tools we happen to have. It
cannot show a fix is safe for a tool written tomorrow. Both contracts are therefore
enforced by per-rule guards that fail the build, not by corpus statistics — the
corpus is how we *size* and *spot-check*, never how we *prove*. See
[`behavior_preservation.md`](behavior_preservation.md) and the proofs index at
[`proofs/README.md`](proofs/README.md).
