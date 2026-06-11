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

## Phase 0 — Scope the delta since the last audit

The audit doc records the **commit hash it audited** (see Conventions). Start by
diffing against it:

```bash
git log <last-audited-commit>..HEAD --stat --oneline
```

Weight the whole audit toward what changed — new modules, moved dependencies,
renamed/split rule codes, rewritten doc sections. A re-audit weeks after a clean
one is mostly a delta audit; the full-suite sweeps below still run, but the deep
reading concentrates on the changed surface. (If the audit doc predates this
convention or the delta is enormous, fall back to a full pass.) Launch one or two
read-only Explore agents to map the delta's abstraction/public-surface changes
before opening files yourself — then **verify their claims in source**.

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
file path exists. Decision-section citations **anchored to a `decisions.md`
path** are machine-checked by
`galaxy-tool-refactor-registry/tests/test_decision_citations.py` (in the gate)
— don't hand-grep those (header formats differ per package and manual greps
have produced false MISSINGs); eyeball only unanchored shorthand ("check D34"
with no path nearby). A citation to a phantom section is itself a finding.

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

### Documentation-suite freshness (standard sweep)

Dimension 7 is not just `ARCHITECTURE.md` / `decisions.md` — **always sweep the whole
user-facing documentation suite** against what shipped since the last audit. This is the
part most likely to silently rot. For each category, open the files and check every
present-tense claim / count / status marker / number against the code:

- **Guide** (`docs/guide/`) — the audience explainers and especially the
  **Shipped / Partial / Roadmap capability matrix** (`capabilities.md`) and the
  leverage/ecosystem map (`leverage.md`): does every shipped capability have a row at the
  right status? Is a now-shipped (or now-in-progress) item still tagged Roadmap/"not
  built"? Are CLI command counts/lists current? (`usage/cli.md`.)
- **Examples** (`docs/examples/`) — do the showcased commands, outputs, and numbers still
  match? Should a demo point at a newer sibling capability?
- **Research** (`docs/upgrade_research/`) — roadmap/spike **status markers**
  (planned / deferred / shipped) and cited percentages: anything that shipped but is still
  "future", or a number that moved, is a finding.
- **Stats** (`docs/*_stats.md`) — confirm the **stat-freshness guard test** is green
  (it pins *rule coverage* + *summary currency*, run in `qa_gate.sh`), then spot-check that
  a newly-added rule actually appears with a real corpus number.
- **Measurements** — `scripts/measure.py` registered slugs ↔ the `CLAUDE.md` measure list
  must agree (no undocumented slug, no documented-but-removed slug; new behaviour like a
  parity check is described).
- **The skills themselves** (`.claude/skills/*/SKILL.md`) — they carry present-tense repo
  claims (package counts, gate scope, tier vocabulary, worked-example tables) and **no
  guard test covers them**; sweep them like any other doc. (A real catch: the pre-pr-audit
  skill said "pytest ×7" after the workspace grew to eight packages.)
- **Generator-embedded prose** — the blurbs inside `scripts/corpus_check.py` /
  `scripts/measure.py` that *become* the stats pages. They are code, so no doc sweep's
  file list reaches them, and the drift guards check rule summaries, not blurbs. (A real
  catch: the check-stats blurb still called GTR032 "a reserved placeholder … flags
  nothing" after GTR032 graduated to a real detector — the audit fixed six docs and
  missed this seventh because it lives in a script.) **Convention: blurbs state only
  timeless facts**; per-rule status claims belong in `RuleMeta` summaries, which the
  summary-drift guard covers.
- **Pipeline / roster enumerations** — any doc that spells out an ordered member list
  (e.g. a `canonical_codemods()` front-to-back enumeration in `ARCHITECTURE.md`, a package
  `CLAUDE.md`/`README`, or the defining module's own docstring) rots when membership
  changes; cross-check each against the live derived value, not against each other.

**Known false-positive traps (don't re-flag)** — this list is **canonical**: the
pre-pr-audit skill links here instead of restating it, so amend it here only.
Corpus-`check`-backed stats pages
(`corpus_stats`, `combined`, `toolshed`, `corpus_format`, `corpus_check`, `corpus_rule`)
are documented under CLAUDE.md's **`corpus_check`** section, not the measure list — a
scan of only the measure list will wrongly call them "undocumented". Manually-regenerated
measure-backed stats pages carry **no "Generated on" header** by convention — that is not
drift, and you must **never fabricate a date or a corpus number** to fix it (regenerate
with the corpus, or leave it). Numbers in stats/research prose may only be changed by
re-running the standing measurement, never hand-edited.

### Conventions

- **Record the audited commit.** Each audit record names the commit hash it audited
  (`**Audited commit:** \`<short-hash>\``), so the next run's Phase 0 can diff
  `<hash>..HEAD` instead of reconstructing the delta from PR numbers.
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
| 1 | `galaxy-tool-source` | `ToolDocument` (lxml tree = source of truth), `load/parse/validate`; no serializer |
| 2 | `galaxy-tool-codemod` | `CodemodCommand`/`Cursor`/`Change`; CANONICAL vs AUTO_UPGRADE |
| 3 | `galaxy-tool-fmt` | cosmetic `Rule`/`Edit`; the only serializer of canonical output |
| 3.5 | `galaxy-tool-lint` | detect-only IUC `CheckRule`s |
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
