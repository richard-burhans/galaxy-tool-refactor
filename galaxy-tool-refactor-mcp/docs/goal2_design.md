# Goal 2 design proposal: agent-authored rules

**Status: design proposal (2026-07-02), nothing shipped.** The locked decision
("adding rules is a developer task; no user-defined rules") still governs every
released surface. This document answers the four open questions `docs/vision.md`
records for Goal 2, so that when the relaxation is wanted the design is ready and
argued — and so nothing shipped in the meantime forecloses it. Each answer is a
recommendation, not a commitment.

## The shape in one paragraph

Third-party rule packages register through a Python entry-point group and are
loaded **only** behind an explicit per-invocation opt-in. A plugin rule is the
same object a built-in is (a `CodemodCommand` / check with a `RuleMeta`, wrapped
into a `RuleHandle`), but it lives in a separate, visibly-marked namespace, joins
no built-in ruleset, and earns the right to *mutate* files by passing exactly the
QA ladder the built-ins pass (fixture tests, then the corpus idempotence +
post-validity sweep, then a behavior-preservation proof). Detect-only rules are
the low-stakes on-ramp; fixable rules are the earned tier.

## Q1 — Discovery: entry points, loaded only on opt-in

- **Mechanism.** A packaging entry-point group, `galaxy_tool_refactor.rules`.
  Each entry point names a zero-argument function returning the package's rule
  classes. The unified registry (`registry.py`) is the single integration
  point: when plugins are enabled it extends its `code -> RuleHandle` index
  with the discovered rules, through the same duplicate-code guard the
  built-ins pass.
- **Namespace.** The `GTR` prefix stays **curated** — it is this project's
  covenant (every GTR fix has a proof, every GTR advisory a documented
  residual). Plugin rules must use their own prefix (`<PLUGIN>NNN`, e.g.
  `ACME012`); the registry rejects a plugin rule minting a `GTR` code. Output
  surfaces (`check` findings, notes, `list_rules`) carry the providing
  package's name beside the code, so a finding is never mistaken for a
  first-party verdict.
- **Why entry points over a config file or a rules directory.** It reuses the
  packaging ecosystem's existing trust unit (a package you chose to install),
  keeps discovery declarative (no import-time scanning of arbitrary paths),
  and is the mechanism ruff/pytest/flake8 users already understand.

## Q2 — Authoring contract: the same contract the built-ins follow, written down

The seam already exists (vision.md): the codemod tier's detect-primitive
`CodemodCommand` and the registry's `RuleHandle`. The contract to document (and
hand back over MCP as a template):

- **A `RuleMeta`** with `code` (plugin prefix, see Q1), `summary`, `cite`
  (what convention or upstream behaviour justifies the rule), `detect_only`,
  and `rulesets=()` (a plugin rule may define *its own* rulesets but never
  joins a built-in one — `default`/`iuc`/`strict` stay first-party).
- **A detect phase** (`detect_*` tag-dispatch methods yielding `Violation`s)
  for every rule; **`apply` derived from detect** for a fixable one. The
  detect/fix pairing is the framework's core invariant: a fixable rule's
  `apply` must fix exactly what its `detect` reports (the registry's
  phase-ordered `apply_selection` and `check` both rely on it).
- **Idempotence** (`apply(apply(x)) == apply(x)`) and, for fixable rules,
  **behavior preservation by construction** — the same two governing
  contracts as `docs/design_principles.md`, restated in the template with the
  novel-tool standard: soundness must hold for tools the corpus has never
  seen, not just measured incidence.
- **Delivery.** A documented template (a minimal working rule package with one
  detect-only rule, one fixable rule, tests, and the sweep invocation) in the
  repo; later, an MCP `rule_template` tool that returns it, so an agent can
  scaffold without leaving the conversation (Phase C below).

## Q3 — QA gating: the built-ins' ladder, applied verbatim

A plugin rule earns each capability level by passing the same gates the
first-party rules pass — nothing weaker, nothing bespoke:

1. **Loadable (detect-only):** unit fixtures for the detect phase; the
   registry's structural checks (unique code, valid prefix, `RuleMeta`
   complete). Detect-only rules never mutate, so this level is cheap by
   design — the on-ramp.
2. **Fixable:** additionally, a green `scripts/corpus_check.py codemod
   <module>:<Class>` sweep — idempotence + post-codemod validity across the
   public corpus, zero failures, failures retained as fixtures (the standing
   convention). The sweep harness already takes a dotted class path, so it
   runs an out-of-tree rule today without modification.
3. **Trusted-to-recommend:** a written behavior-preservation argument in the
   plugin's own docs (the analog of `docs/proofs/`). First-party review is not
   assumed; the point is that the artifact exists and the claim is auditable.

Levels 2–3 are self-serve: the gates are runnable by the plugin author (or the
authoring agent) without any first-party involvement. What a plugin can never
acquire: membership in the gate-eligible set (the repo-scale auto-fix system's
blessed subset stays first-party) or a built-in ruleset.

## Q4 — Trust boundary: explicit, per-invocation, visible

- **Never auto-load.** Installing a plugin package must not change any
  behaviour. Loading requires an explicit opt-in at the surface in use:
  `--enable-plugins` on the CLI, `enable_plugins=True` on the facade, and an
  MCP server *startup* flag (never per-tool-call — the operator, not the
  conversing agent, decides whether third-party code can run).
- **Execution is the trust decision.** A loaded plugin's `detect`/`apply` is
  arbitrary Python; there is no sandbox worth pretending about in-process. The
  honest boundary is: you opted in to code you installed, exactly as with
  pytest/ruff plugins. The flag's help text says so plainly.
- **Blast-radius limits even after opt-in:** plugin rules never join built-in
  rulesets, never ride `format`/`upgrade` defaults (selection must name them
  or a plugin-defined ruleset), and every user-facing line they produce is
  attributed to the providing package.

## Phasing

- **Phase A — the plugin seam, detect-only.** Entry-point loading behind the
  opt-in, prefix enforcement, attribution in `check`/`list_rules`, the
  template package, and a guard test that the built-in surfaces are
  byte-identical with plugins absent. Smallest shippable slice; relaxes the
  locked decision only for *reporting*.
- **Phase B — fixable plugin rules.** The Q3 ladder for `apply`, sweep-gated;
  selection-only application.
- **Phase C — the MCP authoring loop.** `rule_template` (scaffold) and
  `validate_rule` (run the fixture + sweep gates on a candidate package and
  return structured results) tools, closing the agent's write-test-gate loop
  over MCP. Only after A/B are real.

## Non-goals

- No relaxation of the shipped default: without the opt-in flag, behaviour is
  byte-identical to today, and the locked decision stands.
- No `GTR` code minting outside this repo; no plugin entry into the
  gate-eligible subset or the built-in rulesets.
- No in-process sandboxing claims — the trust unit is the installed package
  plus the explicit flag, stated honestly.
