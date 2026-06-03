---
name: architecture-audit
description: >
  Deep architectural audit of a codebase: establish a written baseline of the major
  abstractions and cross-tier contracts, then measure the actual code against it to
  surface boundary leaks, abstraction inconsistencies, naming drift, unenforced
  contracts, duplication, and dead surface. Use when asked to audit the architecture,
  check that abstractions are consistent / make sense, find architectural issues, or
  review whether the design still holds — as opposed to a line-level bug hunt
  (use /code-review for bugs). Produces ARCHITECTURE.md + docs/architecture_audit.md,
  applies safe fixes, leaves structural changes as proposals, and can escalate to a
  multi-agent adversarial verification pass on request.
---

# Architecture audit

A repeatable method for auditing whether a codebase's abstractions are coherent and
its documented contracts actually hold. Two phases plus an optional escalation.

**The core idea:** you cannot judge "are the abstractions consistent?" without a
written statement of what each abstraction is *supposed* to be. So **write the
baseline first** — that act alone surfaces half the inconsistencies (you can't
describe a muddy boundary cleanly), and it gives the audit concrete invariants to
test instead of gut feel.

Default to a single deep pass. Escalate to the multi-agent workflow only when the
user opts into orchestration (they say "escalate", "be exhaustive", "use a
workflow", or ultracode is on).

---

## Phase 1 — Baseline (`ARCHITECTURE.md`)

Write (or refresh) a conceptual map of the major abstractions and the contracts
between them. Keep it a *map*, not a fork of the rationale — link to the per-package
`docs/decisions.md` / ADRs rather than restating them.

**Ground everything in source. Do not trust prior summaries or even sub-agent
reports** — they disagree on specifics (in this repo's first run, two explore
agents reported different shapes for the same `Change` dataclass; only reading
`change.py` settled it). Open the actual type/function definitions before you
describe them.

Capture, per layer/tier:
- the abstraction's **name + defining file path**, the problem it solves, its **key
  public API**, and how it relates to other layers;
- the **cross-cutting contracts** — the invariants that span the codebase
  (ownership/source-of-truth, dependency direction, any "X is the only thing that
  does Y", detect/fix or command/query splits, result-type conventions,
  idempotence/safety guarantees);
- a **dependency-direction diagram** (ASCII is fine);
- **known asymmetries** — intentional rough edges, stated honestly;
- a **reference index**: abstraction → file → the decision section that justifies it.

**Verify before you ship it:** every named symbol resolves to real code; every
file path exists; every decision-section citation actually exists (grep the
`decisions.md` headers). A citation to a phantom section is itself a finding.

Add a one-line pointer to `ARCHITECTURE.md` from the root `CLAUDE.md` / `README`.

---

## Phase 2 — Single deep-pass audit (`docs/architecture_audit.md`)

Read every package's `src/` + dependency manifest + selected tests against the
Phase-1 baseline, across these **seven dimensions**:

1. **Boundary integrity** — does any layer import a higher layer or a sibling it
   shouldn't? Verify against *both* the dependency manifests **and** actual imports
   (a docstring mention of another package is not an import — don't false-positive).
   Watch for unused declared dependencies (a real finding: they encode a coupling
   that isn't real).
2. **Abstraction consistency** — do parallel families share the conventions the doc
   claims? Are the splits (detect/fix, command/query) uniform? Does any unifying
   adapter faithfully cover its variants or leak specifics?
3. **Naming / vocabulary drift** — the same concept named differently across layers;
   one verb meaning two things (e.g. an `apply` that *mutates* in one family and
   *describes* in another); type-name overloading.
4. **Contract-enforcement gaps** — invariants asserted in prose but not guarded by a
   test or lint. "The code currently honours it" is not enforcement: ask what stops
   a *future* commit from breaking it. These are usually real but **Low/Medium** —
   coverage gaps, not violations.
5. **Duplication / missed reuse** — parallel implementations that should share; but
   check whether a shared helper would violate a dependency rule (e.g. a
   dependency-free base tier can't host it).
6. **Dead / reserved surface** — stubs, unbuilt placeholders, public APIs with no
   caller. Distinguish *documented intentional reservation* (accept) from *drift*.
7. **Doc / code agreement** — including whether the `ARCHITECTURE.md` you just wrote
   matches reality. **Any place the code forced a hedge in your doc is a finding.**

### Conventions

- **Severity:** High = a violated invariant or correctness hazard; Medium = a latent
  inconsistency that will bite a maintainer; Low = cosmetic / doc / test-coverage.
- **Tag every finding:** `[fixed]` (applied this pass), `[proposal]` (structural or
  needs a decision — *not* applied), `[accepted]` (intentional; recorded so it isn't
  re-litigated). Recording the accepted/intentional ones is as valuable as the
  problems — it stops the next audit from re-flagging them.
- **Lead with the verdict.** State up front if boundaries hold and the headline is
  reassuring; an honest "the architecture is healthy, here are refinements" is a
  better outcome than manufacturing severity.

### Safe-fix policy

Apply immediately, in the same pass: doc corrections, comment/docstring fixes,
obvious local renames, dead-code/dead-dependency removal, missing pointer links, and
mechanical parity fixes (e.g. a missing sort that the docstring already promises).

Leave as **proposals**: moving code between layers, merging/splitting abstractions,
changing public signatures, adding tests, dependency-graph changes. List them; don't
apply them.

After any applied fix, **run the project's QA gate** (lint + type-check + tests; in
this repo `bash scripts/qa_gate.sh`) and report the result. If a fix touches a
dependency manifest, re-sync the lockfile first (`uv sync`).

---

## Escalation — multi-agent adversarial verification (opt-in)

When the user wants maximum confidence, escalate with a `Workflow`. The pattern
(template: [`escalation-workflow.template.js`](escalation-workflow.template.js)):

- **Find** — fan out finders: one per layer/tier (deep read of that package against
  the baseline) **and** one per cross-cutting dimension (swept across all packages).
  Give each the baseline **and the existing single-pass audit**, told to (a) hunt
  for what the single pass *missed* and (b) independently re-judge its claims. Use
  read-only `Explore` agents with a structured-output schema. An empty finding list
  is a valid, honest answer.
- **Verify** — pipeline each finding into an **adversarial refuter** whose default
  stance is skepticism: refute anything intentional-and-documented, already-handled,
  or factually wrong; confirm only after opening the cited code; downgrade severity
  when mis-scoped. This is where inflated findings die — expect most would-be
  Medium/High candidates to land at Low.
- **Synthesize** — dedup (independent corroboration from multiple scouts *raises*
  confidence), use corrected severities, and **separate three buckets**: new
  findings, independent re-confirmations of the single pass (this validates it), and
  refuted candidates (so they aren't re-litigated).

Then **you** (not the workflow) integrate: fold survivors into
`docs/architecture_audit.md`, apply newly-confirmed safe fixes, re-run the QA gate.

**What escalation is good at:** corroborating the single pass (raising confidence in
its load-bearing conclusions) and catching *drift-grade* issues a single reader
glosses — e.g. a hardcoded list that should be derived, an unused declared
dependency. It rarely overturns a careful single pass; treat a quiet result as a
positive signal, not a failure.

---

## Worked example — this repo (`galaxy-tool-refactor`)

A 7-tier stack; the load-bearing rule is *no tier depends on a higher one;
orchestration lives in the registry facade (3.6); the CLI/MCP are thin front-ends*:

| Tier | Package | Owns |
|---|---|---|
| 0.5 | `galaxy-tool-refactor-rules` | `RuleMeta`, `Violation` — dependency-free shared vocabulary |
| 1 | `galaxy-tool-xml` | `ToolDocument` (lxml tree = source of truth), `load/parse/validate`; no serializer |
| 2 | `galaxy-tool-xml-codemod` | `CodemodCommand`/`Cursor`/`Change`; CANONICAL vs AUTO_UPGRADE |
| 3 | `galaxy-tool-xml-fmt` | cosmetic `Rule`/`Edit`; the only serializer of canonical output |
| 3.5 | `galaxy-tool-xml-check` | detect-only IUC `CheckRule`s |
| 3.6 | `galaxy-tool-refactor-registry` | `RuleHandle`, presets, `run/upgrade/detect` facade |
| 4 | `galaxy-tool-refactor-cli` | thin user-facing CLI over the facade |
| 4 | `galaxy-tool-refactor-mcp` | thin agent-facing MCP server over the facade |

Outputs live at [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) and
[`docs/architecture_audit.md`](../../../docs/architecture_audit.md) — read them as a
concrete model of the format. The first run found **no High-severity issues / no
boundary violations**; the value was in precision (tightening an over-absolute "only
tier that writes to disk" claim into "only serializer of canonical output"),
footgun documentation (a uniform-interface method the facade deliberately bypasses),
and — via escalation — two drift fixes (a hardcoded preset-name list that should be
derived; an unused `click` dependency in a library tier).
