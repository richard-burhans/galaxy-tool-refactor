# Architectural audit — galaxy-tool-refactor

## Re-audit 2026-06-16 — consolidation delta (PRs #259–#268), multi-agent escalation

**Audited commit:** `4555eeb` (main at audit time; the safe-fixes below land on the
audit branch). Delta since `007dd3d` (the 2026-06-15 baseline) is the **consolidation
wave** (10 commits, ~48 non-lockfile files): the single-source registry-facade
refactor (#259 — `is_canonical` / `fired_codes` joining `gate_codes` / `bulk_codes`,
all consumers importing the one definition), the MCP expansion (#260 — 7 → 9 tools,
`find_references_tool` + `rename_param_tool` in `service.py` / `server.py`), the 0.3.3
and 0.3.4 lockstep releases, the `upgrade` token-profile reporting fix (#262), the
`check` loads-from-path fix (#265), and CHANGELOG hygiene (#267/#268).

**Verdict — healthy; zero High, zero boundary violations, zero abstraction breaks.**
Escalated with a project-wide `Workflow`: 13 scouts (8 tier finders + 5 cross-cutting
dimension finders) → one adversarial refuter per finding → synthesis (**47 agents, 33
raw findings, 23 survived verification, 10 refuted**). The escalation was
**overwhelmingly confirmatory**: the load-bearing invariant (no tier depends on a
higher one; orchestration in the registry facade; CLI/MCP thin front-ends) holds
firm, the single-source `is_canonical`/`fired_codes` primitives are consumed (not
re-derived) by the forward gate / bulk normalizer / coverage tracker, the MCP
expansion stayed inside the documented single-document scope (mcp D7), and the
optional `[test-validation]` extra remains lazily isolated. The actionable surface is
**documentation drift only** — ten safe-fixes (nine docstring/prose, one mechanical
load-from-path parity) plus two test-coverage proposals. No code logic changed. All
machine-checked guards green in `qa_gate.sh`.

### Findings — applied this pass (safe-fixes)

- **[fixed] (Low) tier-0.5 `__init__.py` docstring omitted `Violation`.** The import
  guidance listed `RuleMeta` + `render_rule_reference_table` but not `Violation`
  (the package's third public primitive, per its own CLAUDE.md). Added it.
- **[fixed] (Low) tier-3.6 `__init__.py` miscategorised facade exports.** It listed
  `advisory_codes` / `known_codes` / `resolve_codes` *under the facade* (they live in
  `registry.py` / `resolve.py`) and omitted the newer facade entry points. Rewrote the
  surface list: facade = `run`/`upgrade`/`detect`/`find_references`/`rename_param`/
  `convert_help`/`tokenize_version`/`reconcile_lint_skip` + the single-source
  `is_canonical`/`fired_codes` + introspection; `advisory_codes`/`known_codes` under
  `registry`, `resolve_codes` under `resolve`.
- **[fixed] (Low) three fmt docstrings described GTR003 (blank lines) as active.**
  `format.py`, `cli.py`, and `detect.py` each listed blank lines / a GTR001↔GTR003
  overlap as live behaviour, but GTR003 is parked out of `all_rules()` (§D4). Reworded
  all three to match the authoritative `all_rules()` docstring; `detect.py` now frames
  the overlap as conditional on GTR003 shipping.
- **[fixed] (Low) `fmt/README.md` "three cosmetic rules ship" → two active.** Only
  GTR001 + GTR004 are in `all_rules()`; GTR003 is parked (the README's own table
  already marks it PARKED). Corrected the count.
- **[fixed] (Low) `payload.py` `<macros>` exception wording inverted the D18-help
  parallel.** It called `<macros>` "excepted (the D18-help style)" but the help
  exception *protects* whitespace whereas `<macros>` is excepted *out* of the
  protected set (its whitespace collapses to `<macros/>`). Reworded to state the
  inverse relationship explicitly (both are proof-carried exceptions, opposite
  directions). Code (`element_text_may_be_payload`) was already correct + tested.
- **[fixed] (Low→Medium-recount) root `README.md` "eight independently-installable
  packages".** The table enumerates nine installable distributions (the metapackage
  is `pip install`-able). Reframed to "eight packages plus a thin front-door
  metapackage — nine published distributions", matching `CONTRIBUTING.md`. (The prior
  audit fixed this count in `capabilities.md` but not the root README.)
- **[fixed] (Low) `ARCHITECTURE.md` §7 facade list omitted the #259 primitives.**
  Added an `is_canonical` / `fired_codes` bullet (the single-source canonical-form
  primitives shared with the auto-fix gate + coverage tracker).
- **[fixed] (Low) CLI `check` macro-file branch loaded from bytes.** `load_macros(original)`
  → `load_macros(target)`, mirroring the tool branch's #265 load-from-path fix. No
  behaviour change today (cosmetic macro checks don't resolve imports), but it removes
  the latent inconsistency and future-proofs a macro-file check that needs `source_path`.

### Findings — proposals (not applied; need a test or a decision)

- **[addressed] (Medium) no guard that the MCP server's registered tools match the
  service functions.** `server.py` registers 9 tools by hand against `service.py`; a
  future service op added without a server binding (or a rename) would drift silently.
  **Fixed in a same-session follow-up:**
  `test_server.py::test_server_tools_match_service_ops_exactly` derives the registered
  tool set (`build_server().list_tools()`) and the public service-op set (introspecting
  `service` for non-`_` module-level functions) independently and asserts equality.
  Verified it fails on a simulated unbound op; the existing hardcoded-roster test is
  kept as the explicit count pin.
- **[proposal] (Low) no guard on partition-fixture integrity across corpus sweeps.**
  `test_partition.py` pins the build-time partition validation but nothing pins the
  fixtures against the live partition groups. Low urgency.

### Findings — accepted / refuted (recorded so they are not re-litigated)

- **[accepted] `TokenizeVersion` (GTR094) omits an explicit `meta.order`.** Opt-in
  command codemods run via dedicated facade entry points (`tokenize_version` /
  `convert_help`), never in a sorted pipeline, so `order` is moot. The sibling
  GTR092's `order=90` is equally inert. Adding one would imply participation it does
  not have; left as-is.
- **[accepted] `apply.py` "fmt is the only serializer" has no *standalone* facade
  lock.** It is structurally enforced — `apply_selection` always routes output through
  `format_tool_document_subset`, pinned by `test_serializer_allowlist.py`. Not a gap.
- **[accepted] `CONTRIBUTING.md` / root `CLAUDE.md` "eight packages + metapackage".**
  Accurate framing (8 code packages + 1 front-door metapackage); left unchanged.
- **[accepted] codemod `CLAUDE.md` 12-codemod enumeration.** Factually accurate and in
  the right order; the `canonical_codemods()` derivation is documented in "Further
  reading" + pinned by `test_canonical_front_to_back_roster_is_pinned`. No change.
- **[refuted]** five MCP "positive confirmation" candidates (single-document scope,
  error-boundary mapping, 9-tool registration, current docs, green static checks) were
  re-confirmations of correct design, not findings.

## Re-audit 2026-06-15 — auto-fix-system delta (PRs #235-#257), multi-agent escalation

**Audited commit:** `007dd3d` (main at audit time; the safe-fixes below land on the
audit branch). Delta since `7511891` is the repository-scale **auto-fix system** and
its supporting surface (~80 non-lockfile files): the per-rule classification
`gate_eligibility.py` (tier 3.6, registry D26), the two halves
(`scripts/bulk_normalize.py` Half A, `scripts/forward_gate.py` + the published
composite Action Half B), the durable `scripts/coverage_tracker.py` (N6), the
re-accumulation measure `scripts/gate_reaccumulation.py`, the hidden `gate-suggest`
CLI command (`galaxy_tool_refactor_cli.gate_suggest`, cli §D20) the Action's suggest
mode calls, three new tier-3.5 checks (GTR098/099 datatypes pair, GTR100/101
test-validation bindings behind the opt-in `[test-validation]` extra, GTR102
boolean-gates), the tier-1 `command_conditionals.py` model behind GTR102, the 0.3.1 +
0.3.2 lockstep releases, and the blog/doc work.

**Verdict — healthy; zero High, zero boundary violations, zero abstraction breaks.**
Escalated with a 10-scout `Workflow` (6 tier + 4 dimension finders → one adversarial
refuter per finding → synthesis; **61 agents, ~1,688 ground-truth checks**). The
escalation was **overwhelmingly confirmatory**: the architecture absorbed the
auto-fix system without strain — clean tier boundaries, a total KeyError-guarded
eligibility partition, single-source rule-set wiring across all five integration
points, and **exemplary optional-extra isolation** (the `galaxy-tool-util`
`[test-validation]` extra is lazily imported and degrades to `[]` when absent, never
a base/runtime dep). The actionable surface is the usual documentation-drift wave
plus **one genuine code finding** (a tier-1 regex defined in triplicate). Adversarial
verification downgraded four Medium→Low candidates and refuted five outright. All
machine-checked guards green in `qa_gate.sh`.

### Findings — applied this pass (safe-fixes)

- **[fixed] (Medium) `ARCHITECTURE.md` stale CheckRule count 70 → 75.** `:383` ("pins
  the count (70)") and the tier-3.5 wave close ("now **70 checks**") contradicted the
  live gate (`galaxy-tool-lint/tests/test_detect.py` asserts 75) and the tier table
  (`:44`, already 75). Corrected both; the recurring count-drift signature (prior
  audit fixed 70→72; the GTR098-102 wave reopened it at 75).
- **[fixed] (Medium) `ARCHITECTURE.md` tier-3.5 prose omitted GTR098–GTR102.** Extended
  the wave close to cover the datatypes pair (GTR098/099, check D36), the opt-in
  test-validation bindings (GTR100/101, check D37), and boolean-gates (GTR102, check
  D38).
- **[fixed] (Medium) `docs/guide/capabilities.md` omitted the entire auto-fix system.**
  Added an "Auto-fix system (repository scale)" subsection (eligibility classification,
  Half A, Half B + suggest mode, coverage tracker, re-accumulation evidence) plus the
  missing GTR100/101 and GTR102 check rows.
- **[fixed] (Medium) `command_conditionals.py` absent from `ARCHITECTURE.md`.** Added
  a §3 tier-1 bullet (beside the command-text utilities) and a §11 reference-index
  row; cites galaxy-tool-lint D38.
- **[fixed] (Medium) `_CHEETAH_VAR` regex defined identically in three tier-1
  modules.** The single genuine code finding: byte-identical
  `re.compile(r"\$\{?[A-Za-z_][\w.]*\}?")` in `command_text.py`, `cheetah_refs.py`, and
  `command_conditionals.py` (the latter with no acknowledgement, the former two
  commenting "Mirrors …"). Extracted to `cheetah_cdm.CHEETAH_VAR_RE` (the shared lexer
  module all three already import — zero new import edges) and imported in all three;
  dropped the now-unused `import re` from two of them. Added a §11 index row.
- **[fixed] (Low) `gate_eligibility.py` absent from `ARCHITECTURE.md` tier-3.6.** Added
  a §7 bullet (the single-source-of-truth classifier) + a §11 index row (registry D26).
- **[fixed] (Low) CLI `__init__.py` docstring said "ten commands" and omitted
  `lint-skip`.** Now "eleven author-facing commands (plus one hidden CI helper,
  `gate-suggest`)" with the `lint-skip` bullet added.
- **[fixed] (Low) `scripts/gen_gate_eligibility.py` docstring misleading.** It said the
  table is rewritten "from rule metadata"; the bucket assignment is a hardcoded
  per-code dict (`_FIXABLE_BUCKETS`) keyed by `RuleMeta.code`. Reworded.
- **[fixed] (Low) `gate_suggest.py` module docstring overstated bulk-normalizer
  equivalence.** It claimed "the same provable fix the bulk normalizer applies"; the
  bulk pass applies a broader set (gate-eligible + bulk-only). Reworded to the
  gate-eligible subset, with the distinction stated.
- **[fixed] (Low) `gate_suggest._eligible_lines` → `_commentable_lines`.** Resolved the
  `eligible` polysemy (rule classification vs GitHub-commentable diff lines); the
  docstring already said "commentable".
- **[fixed] (Low) `capabilities.md` "eight packages" → "all nine packages"** for
  consistency with `bump_version` and the CHANGELOG.

### Findings — proposals (ALL ADDRESSED in a same-day follow-up)

> **Resolved 2026-06-15 (follow-up):** every proposal below was implemented. The
> registry now owns `gate_codes()` **and** `bulk_codes()` (`gate_eligibility.py`)
> plus `is_canonical()` / `fired_codes()` (`facade.py`); the forward gate, coverage
> tracker, bulk normalizer, and `gate-suggest` all import the single registry
> definition (no local re-derivation). A `gate_codes == GATE_ELIGIBLE` guard + a
> `bulk_codes ⊇ gate_codes` guard (`test_gate_eligibility.py`) and an
> `is_canonical`/`fired_codes` agreement test (`test_facade.py`) pin the cross-halves
> contract. `bulk_normalize.py --write` now reverts on an exception in the post-write
> re-check (+ test). The two coverage-gap tests (lexer-bail `[]`; both
> test-validation rules silent when the extra is absent) landed, and the two renames
> were applied (`collect`→`collect_suggestions`, `rationale`→`_rationale`).
> `qa_gate.sh` green. Original write-ups kept below.

- **[proposal] (Low) An `is_canonical()` helper in the registry (tier 3.6).**
  `gate_codes()` is reimplemented in `forward_gate.py`, `gate_suggest.py`,
  `coverage_tracker.py` (+ the Action's inline derivation), and "is this tool
  canonical?" uses detect-based vs bytes-identity mechanisms across them. Low real
  drift risk (all read the immutable `eligibility_groups()`). Refuter-corrected: the
  obvious `scripts/`-consolidation is **architecturally blocked** (the published CLI
  package cannot depend on unpublished `scripts/`); the right home is a registry
  helper — a design choice, left as a proposal.
- **[proposal] (Low) No test pins cross-halves gate-code agreement.** Nothing asserts
  `forward_gate.gate_codes() == gate_suggest.gate_codes() == coverage_tracker.gate_codes()`.
  Trivial one-liners over a heavily-tested constant, so a divergence is runtime-visible;
  a guard would make the implicit contract explicit.
- **[proposal] (Low) `bulk_normalize.py --write` exception path does not revert.** The
  normal validity/idempotence failure path reverts correctly; the exception handler if
  the post-write re-check *raises* does not. Runs on a throwaway copy and exceptions are
  rare, so Low; add an except-path revert + test.
- **[proposal] (Low) Test coverage gaps** — `command_boolean_conditionals()` lexer-bail
  `[]` contract (implementation correct, untested); `test_extra_absent_yields_nothing`
  asserts only `TestsCaseValidation`, not `TestsAssertionValidation` (both share the
  code path). Adding tests is a proposal per the audit policy.
- **[proposal] (Low) Minor naming/organization** — `gate_suggest.collect()` could read
  as `collect_suggestions()`; `gate_eligibility.rationale()` is a single-use internal
  helper that could be nested or documented as internal.
- **[accepted] (Low) "blessed" / "canonical form" prose synonyms for `GATE_ELIGIBLE`.**
  The code is unambiguous (one constant); the prose synonyms are readable in context.
  Recorded, not normalized.

### Independent re-confirmations (no action)

The load-bearing contracts held through the delta, each verified in source by multiple
scouts: **boundary integrity** (`command_conditionals`, `gate_eligibility`,
`gate_suggest`, and the whole `scripts/` harness import only downward/same-tier; no
tier-2/3.5 leak); **the `[test-validation]` optional-extra isolation** is exemplary
(lazy function-level import, `[]` when absent, mypy `ignore_missing_imports` for
`galaxy.*`); GTR100/101/102 follow the `CheckRule`/`RuleMeta` conventions
(`detect_only`, `cite`, ruleset membership); `all_checks()` is the explicit sorted
75-rule list guarded by `test_detect.py`; the
GATE_ELIGIBLE/BULK_ELIGIBLE_ONLY/BLOCKED_PENDING_IUC/ADVISORY_ONLY partition is total
and KeyError-guarded (`test_gate_eligibility.py`); **single source of truth** for the
gate rule set holds across all five integration points (bulk_normalize, forward_gate,
coverage_tracker, gate_suggest, the Action — all read `eligibility_groups()[GATE_ELIGIBLE]`
at runtime, no hardcoded lists); `bulk_normalize.py --write` happy-path safety
(validate → write → re-validate + idempotence → revert) is correct and tested; pathlib
+ explicit `encoding="utf-8"` and LBYL discipline are consistent across the new scripts;
the freshness tests (planemo parity, gate-eligibility, stat coverage) pass.

### Refuted candidates (do not re-litigate)

- "GTR102 test coverage incomplete" — `test_checks_boolean_gates.py` has all four
  contract tests; invariant fully met.
- "ARCHITECTURE.md undercounts CLI commands by omitting `gate-suggest`" — `gate-suggest`
  is intentionally hidden (cli §D20); the "eleven subcommands" framing is correct.
- "Root CLAUDE.md omits the `command-boolean-if` measure" — it is documented (0b6924d);
  the scout scanned too narrow a range.
- "`coverage_tracker.gate_codes()` `@cache` could go stale" — pure/parameterless over an
  immutable registry; textbook memoization.
- "`gate_codes()` should consolidate via `scripts/_shared.py`" — refuted as proposed
  (the published CLI package cannot import unpublished `scripts/`); a registry helper is
  the acceptable alternative, recorded as a proposal above.

## Re-audit 2026-06-14 — post 0.3.0 release (PRs #220-#234), single delta pass

**Audited commit:** `7511891` (main at audit time; the doc fixes below land on the
audit branch). Delta since `fcc7bdc` is the **0.3.0 release surface** (≈50 non-lockfile
files): the **GTR098/GTR099 datatypes pair** (#224 — faithful planemo ports over a
vendored `datatypes_conf.xml.sample`, no runtime `galaxy-tool-util`), the **GTR013
faithful `<expand>` resolution layer** over the pinning floor (#222 — tier-1
`top_level_expand_tags` → facade `gtr013_expand_ranks` → codemod `expand_ranks`
constructor arg), **GTR003 parked** (#225), **corpus_check parallelization** of all four
sweeps (#227/#228/#231 — multiprocessing map-reduce + `--jobs`), the **conventions
follow-up** (#229), **process hardening** (#230 — mypy at the 3.10 floor + require-clean
push), the **LBYL wording reconciliation** (#223), the **0.3.0 release** (#232), and the
**`docs/blog/`** source tree + second post (#226/#233/#234).

**Verdict — healthy; zero High, zero boundary violations.** A single deep delta pass
(weighted to the changed surface) plus the full-suite guard/doc sweeps, corroborated by
two read-only `Explore` scouts whose claims were re-verified in source. Both new feature
surfaces are tier-clean: GTR013's three-layer resolver flows tier-1 → tier-3.6 →
tier-2-constructor-arg (no inversion; pure pinning remains the standalone default), and
the datatypes pair is self-contained in tier-3.5 (vendored snapshot via
`importlib.resources`; `galaxy-tool-util` is a test-only drift oracle, not a runtime
dep). All machine-checked guards are green in `qa_gate.sh`. Findings are doc-freshness
only.

### Findings

- **[fixed] (Low) `ARCHITECTURE.md:43` CheckRule count stale (70 → 72).** The datatypes
  pair (#224) added GTR098/GTR099; the tier-3.5 row still read "70". Source: 72
  `class …(CheckRule)` subclasses in `galaxy-tool-lint/src/.../checks/`.
- **[fixed] (Low) `CLAUDE.md` command count stale ("ten" → "eleven").** The CLI registers
  11 `@main.command`s; the prose groups `rulesets`/`rules` into one bullet and
  undercounted. `docs/guide/usage/cli.md` already said 11.
- **[fixed] (Low) lint-skip auto-removable count lagged the #224 re-measure (149 → 160).**
  #224 re-ran `scripts.measure lint-skip-corpus` after tools-iuc joined the corpus and
  updated `CLAUDE.md` to 160/640 (25.0%), but `CHANGELOG.md:25` and
  `docs/guide/capabilities.md:48` still said 149. Re-ran the measure to confirm **160
  (25.0%)**; reconciled both (a measured value propagated, never hand-picked).
- **[fixed] (Low) `scripts/measure.py` `expand-reorder-resolution` blurb called the
  resolver "future".** It shipped in #222; per the generator-blurb timeless-facts
  convention, reworded to "the gap … closes over the pinning floor (both shipped)".
- **[fixed] (Low) `CHANGELOG.md` compare-links not bumped at the 0.3.0 release.** The
  footer still pointed `[Unreleased]` at `v0.2.0...HEAD` with no `[0.3.0]` entry; added
  the `[0.3.0]` compare link and repointed `[Unreleased]` to `v0.3.0...HEAD`.
- **[accepted] (resolved) #220's LBYL `[proposal]` is closed by #223.** The
  softened-stance re-wording flagged in the 2026-06-13 record was applied in #223;
  `CLAUDE.md` now reads "prefer LBYL for routine branching … and where the operation
  itself is the authoritative test (dignified-python's softened stance)". Recorded so it
  isn't re-litigated.
- **[accepted] (Low) galaxyls-binding docs cite `galaxy-tool-source` 0.2.0.**
  `docs/guide/leverage.md` + `capabilities.md` say the version-tokenization Code Action
  is "validated against the published 0.2.0". Accurate: that external binding pins
  `==0.2.0`, its upstream PR is user-held, and the pin bump is a galaxyls-side decision,
  not repo drift. Recorded so it isn't re-flagged until the binding is re-pinned.

## Re-audit 2026-06-13 — post behavior-preserving-upgrade arc + lint-skip + GTR020/GTR013 fixes + dignified-python re-vendor (PRs #195-#219), single pass

**Audited commit:** `fcc7bdc`. Delta since `2df9e4d` is **enormous** (138 files,
+12,908/-869): the whole **behavior-preserving upgrade arc** (#200-#208 — the
behavior gate, `UpgradeToValid`/GTR097 minimal-bump default, the deployment
ceiling, `poll_galaxy_servers.py`, the 24.2 test-case checker + `FixTestParamQualification`
GTR096), **lint-skip reconciliation** (#210, `lint_skip.py` + `reconcile_lint_skip`),
the **GTR020.1 file-scope** narrowing (#211/#213, tier-1 `io_file_names`/`is_io_file_ref`)
and the GTR020.1 boolean-quoting fix (#198), **no-XML-declaration** (#209) +
**trailing-newline** (#214) serializer fixes, **GTR013 `<expand>` pinning** (#215),
a wave of new `measure.py` slugs + the `corpus_check upgrade` subcommand, the
`--version` flag (#197), the AI-contribution policy doc (#196), and the
**dignified-python re-vendor** to the relocated, *softened* upstream (#217/#219).

**Verdict — healthy; zero High, zero boundary violations, the arc was absorbed
cleanly.** This was a **single deep pass** (the user asked to "start" the audit,
not to escalate), weighted to the changed surface plus the full-suite guard/doc
sweeps. All machine-checked guards are **green** in `qa_gate.sh` (decision-citation,
stat-artifact-coverage, research-note-citation, lockstep-version, ruleset-membership,
partition). Boundary integrity is clean: the new tier-3.6 modules import only
lower/same tiers (`deployment.py` = stdlib only; `lint_skip.py` = tier-2
`canonical_codemods` + same-tier registry; `errors.py` = none), and tier-1
`command_vars.py` (the GTR020 substrate) pulls in no higher tier. ARCHITECTURE.md
already reflected the minimal-bump default, the behavior gate, and
`reconcile_lint_skip` — the deep read corrected an unreliable batch-grep that had
falsely reported them missing (per the skill: verify in source, never trust a
summary, including one's own grep). The findings are doc-freshness only.

### Findings

- **[fixed] (Medium) ARCHITECTURE.md omitted the deployment ceiling.** The
  `modernize` walk is capped at the *lower* of the behaviour ceiling and the
  **deployment ceiling** (#208, `deployment.py`, registry D23), but the upgrade
  section described only `behavior_ceiling`. Added the deployment-ceiling cap +
  the `--target-profile` / `--allow-behavior-change` interactions to the behavior-gate
  bullet. (Zero matches for `deployment`/`25.1` before the fix.)
- **[proposal] (Medium) LBYL wording across `CLAUDE.md` ×9 + the `/pre-pr-audit`
  skill now overstates the *softened* dignified-python standard.** #219 re-vendored
  the standard from `dagster-io/skills`, which relaxed "Cornerstone: LBYL Over EAFP
  / NEVER use exceptions for control flow" to "Default Stance: Prefer Explicit
  Preconditions" (EAFP acceptable when the operation itself is the authoritative
  test or at a boundary). The repo's standards summaries still say "LBYL over
  try/except; exceptions only at the CLI + third-party boundaries." Not a hazard
  (strict-conforming code still conforms; the softer rule is a superset), and the
  exact re-wording is a standards-*voice* decision, so left as a proposal rather
  than re-worded unilaterally while flagged. Recommended phrasing: keep "prefer
  LBYL for routine branching" and extend the exceptions clause with "...and where
  the operation itself is the authoritative test." Already recorded in the skill's
  `VENDORED.md`.
- **[accepted] (Low) CLAUDE.md's measure list is curated, not exhaustive.** 16 of
  57 registered `measure.py` slugs are absent from the `Corpus scripts` list:
  `corpus-check` (the passthrough, documented under the `corpus_check` section, a
  known false-positive trap) + 15 *older* exploratory measures (`tool-id-vs-path`,
  `macro-usage`, `param-types`, `validity-distribution`, ...) that predate this
  delta. No documented-but-removed slugs. Pre-existing (not delta), and the list
  reads as a curated set of decision-backing measures; recorded so it isn't
  re-flagged. (Every *delta* measure — `expand-reorder-resolution`,
  `version-suffix-shape`, the upgrade/24.2 measures — is documented.)

### Coverage note
Single pass over a large delta: high-signal sweeps (guards, boundaries, the changed
abstractions in ARCHITECTURE.md, the full doc/measure/skill freshness sweep) rather
than a line-by-line read of all +12,908 lines. A quiet result on those targets is a
positive signal (skill guidance); escalation (multi-agent adversarial verification)
was not requested and is available for maximum confidence on the upgrade-arc
soundness gates specifically.



**Audited commit:** `2df9e4d`. Delta since `c46d579`: the version-tokenization
arc lands proper (PR #181 `version_tokens.py` shipped as a tier-1 module with the
`--macros-file` share/consensus path and `--adopt-suffix` identity-change variant),
the `galaxy-tool-xml → galaxy-tool-source` rename (#162/#164), the front-door
`galaxy-tool-refactor` metapackage (a ninth published distribution; #163), GTR095
(id/name/version missing-or-empty), the publishing/OSS infra wave (all nine dists on
PyPI 0.2.0), the `galaxy-blog-post` skill, and the doc/skill refresh wave
(#189/#192/#193/#194).

**Verdict — healthy; zero High, zero boundary violations, every survivor
doc/test class.** The escalation's priority adversarial lanes — the
version-tokenization soundness gates (expansion-equality for tokenize, adopt-suffix,
and shared-merge inertness), the 9-package lockstep + metapackage-extra pinning, and
the `OPT_IN_COMMAND_BY_CODE` partition — all came back **clean on the load-bearing
code**: every gate is present and integrated, the lockstep/partition contracts are
fully tripwire-guarded (`test_workspace_versions.py`, `test_ruleset_membership.py`),
and the two structural-soundness candidates that survived are **test-coverage gaps,
not correctness gaps** (the gates run; they just lack an isolating proof-by-execution
test). The dominant survivor cluster is mundane: a **count/enumeration drift wave**
from the tokenize-version + GTR090/091/095 + rename arcs that lagged across READMEs,
CLAUDE.md, ARCHITECTURE.md, and the parity doc. Two finders fed per-finding
adversarial refuters: **23 raw → 2 refuted → 21 survivors**, deduped to **11 distinct
NEW findings (10 applied as safe fixes, 1 backlog note) + 4 RE-CONFIRMATIONS of prior
guards**. Honest read: little is *structurally* new since `c46d579`; the arc was
absorbed cleanly, and this audit is mostly catching the documentation shadow it cast.

### Applied (safe-fix class, all doc/docstring) — `[fixed]`

1. **The tokenize-version/GTR090-091-095/rename enumeration-drift cluster** (the
   dominant survivor group — seven near-identical doc miscounts, collapsed):
   - `ARCHITECTURE.md:349` check count `(68)` → `(70)` (contradicted both
     `galaxy-tool-lint/tests/test_detect.py:13` `== 70` and its own §6 prose at
     line 382). Corroborated independently by the parity-doc finding.
   - `docs/planemo_linter_parity.md:203` `68 rules` → `70 rules` (stale since
     GTR090/091 + GTR095). Same invariant as the row above (the live `test_detect.py`
     tripwire) — independent corroboration count 2. **Main-loop follow-through:**
     the same prose block carried three more GTR095-induced (PR #166) stale counts the
     synthesis didn't reach — the sibling `check` line `69 → 70` (same `all_checks()`
     total, verified `len(all_checks()) == 70`), the `~7 → ~4` remaining-DETECT count,
     and the now-covered `id/name/version (XSD-required)` clause dropped (GTR095 closed
     that trio; reconciled against the freshness-tested Summary's `DETECT = 4`).
   - `galaxy-tool-refactor-cli/src/.../__init__.py:8` docstring `seven commands` →
     `ten`, plus the three missing entries (`rename-param`, `convert-help`,
     `tokenize-version`).
   - `galaxy-tool-refactor-cli/CLAUDE.md:25` `nine subcommands` → `ten` + a
     `tokenize-version` bullet (the count-miss and the missing-bullet were filed
     as two findings over the same line; merged).
   - `README.md:17` (root package-table CLI row) + `galaxy-tool-refactor-cli/README.md:18-20`
     (claims "ten", listed eight): both gained `convert-help` + `tokenize-version`.
     The CLI-README one *reconfirms* a prior audit's "eight → ten" fix (#157,
     `docs/architecture_audit.md:37`) that was applied to the count but not the
     enumeration — partial-fix follow-through.
   - `README.md:18` + `galaxy-tool-refactor-mcp/README.md:22-28` MCP tool lists:
     both gained `convert_help_tool` + `tokenize_version_tool` (server.py registers
     seven; these two opt-in tools were dropped from both surfaces — a systemic
     GTR092/GTR094-release drift, corroboration count 2).
2. **The tier-1 `version_tokens.py` documentation gap** (a genuine coherence
   gap, not a miscount): the module owns the tokenization decision, both soundness
   gates, the tree mutation, and the offset planner — the exact
   planner-feeds-two-renderings shape as the documented `cheetah_rename` (§20) — yet
   was absent from `ARCHITECTURE.md` §3 (tier-1 narrative) and the §11 reference
   index, though present in the public API and CLAUDE.md. Added a §3 bullet
   (after `schema_content`) and a §11 reference-index row, cross-referencing the
   `cheetah_rename` pattern.
3. **Metapackage documentation completeness** (two findings, one distribution):
   the ninth published distribution had prose at `ARCHITECTURE.md:45-48` but no
   §11 reference-index row and no decision citation. Added the row and the
   `§28` citation. (Note: the refuted recommendation mis-cited `§27` for lockstep;
   §28 is the correct and sole locus — applied as §28.)

### Recorded, not applied — `[proposal]`

- **Isolating proof-by-execution tests for two version-tokenization gates**
  (medium, test-coverage class — the gates *run*, they lack a pinning test):
  - `adopt_suffix_equality_holds` is called-and-asserted-True in
    `galaxy-tool-source/tests/test_version_tokens.py` but has no end-to-end fixture
    that expands before/after the `adopt_suffix` tree mutation and asserts the bytes
    match (the pattern `test_expansion_equality_holds` /
    `test_tokenize_version_plan_is_equal` establish for the tokenize variant).
  - `plan_shared_tokenization`'s expansion-equality bail in
    `galaxy-tool-refactor-registry/src/.../version_token_share.py` is exercised only
    on happy paths; no test constructs a non-target importer whose expansion *would*
    change and asserts the planner returns a skip_reason. The inertness guarantee
    (`test_merge_into_existing_inert`) is proven indirectly via "no bail" rather than
    a direct re-expansion equality assertion.
  These are **proposals, not fixes**: drift is structurally impossible without
  editing the shared tier-1 gate functions both callers reference by name, so the
  exposure is low — but a dedicated test would convert a silent gate into a guarded
  one and make the proof-by-execution discipline visible. Filed for the next codemod
  session (TDD lane). Three near-identical finder reports collapsed here.

### Re-confirmations of prior-audit guards (no action) — `[accepted]`

These survived verification as **already-correct and guarded** — independent
re-confirmation that the load-bearing contracts hold post-arc:

- **`OPT_IN_COMMAND_BY_CODE` partition** (registry D18/D19): the frozen
  `{GTR092, GTR094}` map is pinned by both `test_non_selectable_codemods_are_the_known_partition`
  (set-equality + len tripwire) and `test_opt_in_command_codes_are_not_selectable_anywhere`
  (each code in `all_handles()`, not in `registry()`, not in any ruleset). Confirms
  the third audit's named opt-in-command class extended cleanly to GTR094.
- **9-package lockstep + metapackage-extra pinning** (xml §28): the
  `test_workspace_versions.py` trio (`test_roster_matches_the_workspace` with
  `len(_MEMBERS) == 9`, `test_all_packages_share_one_version` == 0.2.0,
  `test_intra_deps_are_pinned_to_the_shared_version` scanning
  `[project.optional-dependencies]` for the `[mcp]` extra) fully guards the
  nine-distribution invariant.
- **SyntaxWarning guard adequacy** (registry `test_no_syntax_warnings.py`): the
  exclusion of xsdata-generated `models/v*/` is intentional and *backstopped* — a
  SyntaxWarning there fails at import time (`test_models.py` imports `AnyTool`,
  which imports every `v*/` model) before the guard runs; the hand-written
  `models/__init__.py` + `registry.py` ARE compiled. Partially-confirmed: real gap
  characterization, adequate protection.
- **`version-token-sharing` measure slug** (`scripts/measure.py`): registered,
  implemented, fixture-tested, and `--list`-discoverable; `measure.py` is a living
  registry, not a hand-enumeration needing a CLAUDE.md row per slug. No drift.

### Rejected candidates (died in adversarial verification)

- **"`test_workspace_versions` comment says 'eight code/tier packages' but
  includes the metapackage"** (low) — *refuted*: the comment reads "The nine
  workspace members — the eight code/tier packages plus the … metapackage," which is
  accurate and clear; the proposed reword is redundant with its own opening clause.
- **"tier-1 version_tokens has decision + gate shared across codemod/CLI but no
  single integration test"** (low) — *refuted by design*: both callers invoke the
  same tier-1 functions by reference, so drift is impossible without editing the
  shared code; the end-to-end contract is already covered by
  `test_tokenize_version_applies_and_serialises` (facade),
  `test_tokenize_version_command` (CLI), and `test_expansion_equality_holds`
  (codemod). Distinct from the surviving *gate-bail-isolation* proposals above,
  which target an untested *negative* path.
- **"architecture-audit / pre-pr-audit SKILL.md hard-code counts that may drift"**
  (low) — *not a finding*: both skills correctly delegate count-checking to
  introspection (CLAUDE.md, `measure.py --list`, server.py); the one literal
  ("nine packages") is an illustrative example paired with a delegation directive,
  not a requirement, and is currently accurate.
- **"no `tokenize-version` example page under `docs/examples/`"** (low) — *not a
  bug*: the feature is correctly Shipped in `capabilities.md` with decision refs +
  corpus stats; a user-walkthrough page paralleling `rename-param-demo.md` is an
  optional ergonomics nice-to-have, noted as backlog only.

## Re-audit 2026-06-10b — the proof-driven widening wave + ledger completion (PRs #157–#159 + the ledger-ranks-4-6 branch), with escalation

**Audited commit:** `c46d579` (the live `feat/ledger-ranks-4-6` branch — findings
applied on the branch before its PR). Delta from `c346a6d`: **#157** (the third
audit's remediation — the opt-in-command class named), **#158** (the GTR001
payload guard + the deferral ledger), **#159** (the 88-file wave: GTR016/GTR015
widenings, GTR093, the Upgrade_vN gap audit + `xsd-tightenings`, the complete
G-series, the proofs-tightening pass, `docs/proofs/` + its coverage tripwire,
the GTR004 schema derivation, the GTR035 partition), and the live branch
(GTR036 collection remap, the GTR032 detector + `lone_amp`, GTR094 +
`tokenize-version` — the tenth CLI command — + the seventh MCP tool, the
declined-list re-verification incl. the 18.01 deletion **refutation**).

**Verdict — healthy; zero High, zero boundary violations, and the escalation's
priority adversarial lanes all came back clean.** Nine finders (five tier-deep
+ four cross-cutting incl. a proofs-accuracy lane over all 27 proof documents)
fed per-finding adversarial refuters: **21 raw findings → 5 refuted → 16
survivors**, every survivor doc/test/cosmetic. The load-bearing surfaces this
wave shipped — the §39 verbatim-composition proof, the schema-derived payload
guard (fmt D20) and its two proof-carried exceptions, GTR094's
expansion-equality gate, the GTR035 partition wiring, the doubled
`OPT_IN_COMMAND_BY_CODE` invariants, and the proofs directory's accuracy
against the code it cites — produced **no surviving findings**: the strongest
corroboration this audit series has returned.

### Applied (single pass + escalation survivors, all safe-fix class)

1. **The GTR032-graduation propagation cluster** (the dominant survivor group —
   one shipped change, six docs that still described the no-op era):
   ARCHITECTURE.md prose + reference-index row, check `CLAUDE.md` + `README.md`,
   `docs/iuc_best_practices.md` (table row + heuristics paragraph), the
   capabilities matrix row (Roadmap → Shipped), the repo-explainer skill's
   "not yet implemented" example, and a vindicated-rationale annotation on
   registry D3 (the dated-entry convention).
2. **Count/roster propagation**: cli `README.md` "eight commands" → ten +
   `cli.py` module docstring; registry module docstring + `resolve.py` hint
   docstring gain GTR094; codemod `CLAUDE.md` partition count (five) +
   GTR035.1 codes + opt-in plural; capabilities GTR035.1 column + a GTR035.2
   advisory row.
3. **Symmetry/coverage**: `TokenizeVersionResult.skip_reason` gains the
   `= None` default (ConvertHelpResult symmetry); two facade-level
   `tokenize_version` tests added (mirroring `convert_help`'s).

### Recorded, not findings

- The corpus stats pages await the `.local` re-fetch (the scratch-loss
  incident; recovery running) — the two stat guards are red by design until
  the branch-end sweep, and the gate blocks any push until then. Working as
  intended.
- 5 refuted candidates (intentional/already-handled/mis-read) died in
  verification — the adversarial layer doing its job.

## Re-audit 2026-06-10 — post RST→Markdown conversion wave (PRs #152–#156)

**Audited commit:** `c346a6d` (main at audit time; the remediation below landed on
top). Delta scoped from the previous record's `e34a479`: **#152** (planemo-alias
M3 reconciliation — HAVE derivable from metadata), **#153** (the `help-rst-md-convert`
measure, R4), **#154** (GTR090/GTR091, the last infra-free planemo linters),
**#155** (tier-1 `rst_markdown` + **GTR092 `ConvertHelpToMarkdown`** + the
`convert-help` CLI command), **#156** (the MCP `convert_help_tool` + the GFM
table/line-block converter extension, 72.2 % → 73.4 % gated).

**Verdict — architecture sound; no High findings, no boundary violations.** The wave
introduced a genuinely new rule class — the **opt-in-command-only codemod** (no
ruleset, not selectable, applied solely by a dedicated command; previously the
no-ruleset set was exactly the upgrade pipeline) — and every finding was the
naming/doc/test shadow of that class, not a structural problem. Method: two
read-only delta scouts + source-verified triage (one session), remediation applied
after the in-flight #156 merged (this session). Triage downgraded the scouts' two
"High" claims to UX/doc after verifying by execution that `upgrade --select GTR015`
raises the same `UnknownRuleCode` as `--select GTR092` — the rejection is the
established contract for non-selectable codes, not a GTR092 regression.

### Applied

1. **Naming (B1–B3):** `adapters.upgrade_only_codemods()` →
   **`non_selectable_codemods()`** — the set stopped being upgrade-only when GTR092
   joined it. The hand-known opt-in map moved out of `parity.py`'s private
   `_OPT_IN_COMMAND_CODES` into **`adapters.OPT_IN_COMMAND_BY_CODE`**
   (code → dedicated command, today `{"GTR092": "convert-help"}`) so parity,
   resolve, and the tests share one source. Ripples: registry/parity call sites,
   the `rules --include-upgrade` help text, registry-module docstrings.
2. **Selection UX (B4/B5):** `UnknownRuleCode` gained an optional `hint`;
   `--select`/`--ignore` on a real-but-non-selectable code now says where the rule
   lives ("GTR092 is applied only by the dedicated `convert-help` command" /
   upgrade-pipeline wording) instead of a bare "unknown rule code".
3. **Contract tests (B6/B8/B9):** the vacuous
   `test_upgrade_only_codemods_declare_no_ruleset` (it asserted the set's own
   defining predicate) became the **partition tripwire** — non-selectable codes ==
   explicit `_UPGRADE_PIPELINE_CODES` ∪ `OPT_IN_COMMAND_BY_CODE` (the repo's
   hand-maintained-list convention), so a new no-ruleset codemod must be filed
   deliberately. Plus: opt-in codes appear in no ruleset and not in `registry()`
   (B6); `list_rules()` default excludes GTR092 like GTR012 (B8); the
   `--select GTR092` hint behaviour is pinned (B4/B5).
4. **Parity-doc guard (A1):** the Summary HAVE-count test pins the number but not
   the prose; a new test asserts the Summary's derivation note names every member
   of `_ALIASED_NOT_HAVE`/`_ALIAS_FREE_HAVE`, so the exception sets stay readable
   in the doc, not just in the test.
5. **Doc drift:** ARCHITECTURE.md's reference index had frozen at GTR089 — wave row
   extended to GTR038–GTR091 (54 checks, D12–D32) and a GTR092 row added; §7's
   `all_handles()` description and the registry CLAUDE.md "Selectable ≠ all"
   invariant now name the opt-in-command-only class.

### Accepted as-is

- **B7:** the codemod's hardcoded `_HELP_FORMAT_PROFILE = "24.2"` — pinned by the
  24.2-vs-24.1 XSD gate test; deriving it from schema introspection buys nothing
  (the XSD attribute's introduction version is a historical fact, not a moving
  target).

Scout A also clean-confirmed: zero measure↔tier-1 duplication after #155's move of
the converter into `rst_markdown.py` (the measure imports it), the `[markdown]`
extra/dev-dep/mypy wiring is coherent, and the GTR092 decision trail (xml §24,
codemod §38, registry D18, cli D12, mcp D2) agrees with the code.

## Re-audit 2026-06-09b — post declarative rulesets + planemo aliases + help-RST repair (PRs #146–#150) + escalation

**Audited commit:** `e34a479` (HEAD at audit time). This record establishes the
audited-commit convention (skill Phase 0): the next audit diffs `e34a479..HEAD`.

**Verdict — healthy; no boundary violations, no High findings.** A delta audit over the
five PRs since the previous record (same-day): **#146** moved rule-set membership into
declarative per-rule metadata (`RuleMeta.rulesets` + the tier-0.5 `Ruleset` catalog,
replacing both the registry's hardcoded preset sets and the hardcoded
`CANONICAL_CODEMODS` list), **#147/#148** added the planemo-alias surface (derived
`planemo_index()`, planemo-name `--select`/`--ignore` tokens, the generated parity
table), **#149/#150** shipped the help-RST work (three research measures; then
`GTR089.1 RepairHelpRst` — the fourth `.1`/`.2` partition, with the predicate + repair
in tier-1 `rst.py` and `docutils` promoted to a tier-1 base dependency). The
architecture absorbed all three shapes without strain; the finding surface was again
documentation drift, plus two contract-enforcement gaps opened by #146's
hardcoding-to-derivation move. Method: single deep pass, delta-weighted, then a
9-finder / adversarial-refuter escalation (4 delta-scoped tier scouts + 5
cross-dimension scouts incl. a documentation-adversary lane) — see the Escalation
section, which **corrected two of the single pass's own claims**. *Process note:
resumed across a session cut-over — the baseline refresh and most safe fixes landed
in the first session; this record, the planemo-alias guide sweep, and the escalation
in the second.*

### Dimension-by-dimension

1. **Boundary integrity ✅** — tier 0.5 gained the `Ruleset` catalog but stays
   stdlib-only (import sweep clean; `test_dependency_free.py` still guards it).
   `docutils` is declared exactly where it is imported — tier-1 `pyproject.toml`
   (`rst.py`); the check tier *dropped* its own declaration with an explanatory
   comment when GTR089's predicate moved down to tier 1, so #150 left no dangling
   dependency. The registry's new `planemo.py`/`parity.py` import only downward.
2. **Abstraction consistency ✅** — GTR089.1/.2 instantiates the partition pattern
   exactly as GTR018/019/020 do: one tier-1 predicate (`rst_is_invalid`), the fix in
   tier 2 (`RepairHelpRst`, in the default pipeline behind the render-equivalence
   gate), the residual advisory in tier 3.5 (`HelpRstResidual`), and the registry
   `_validate_partitions()` covering the new pair. Ruleset membership is now declared
   per-rule and *derived* everywhere it is consumed (registry ruleset sets **and**
   `canonical_codemods()`) — one convention, no second copy.
3. **Naming / vocabulary drift ✅ (three stragglers [fixed])** — the "preset"
   vocabulary is fully retired from *src*; in docs the single pass caught the MCP
   `docs/vision.md` (`list_presets` → `list_rulesets`, Low **[fixed]**) but
   **over-claimed "fully retired from src + docs"** — the escalation found two more
   in the dated decision logs (MCP D1, CLI D4; see Escalation M4/L1, both annotated
   **[fixed]**). Sub-rule labels in docs normalized to the partition halves they
   mean (`GTR020` → `GTR020.1` where the fix half is meant; capabilities/check-README)
   **[fixed]**.
4. **Contract-enforcement gaps — two, both [fixed]:**
   - **Canonical-roster acknowledgement gate — Medium [fixed].** #146 replaced the
     hardcoded `CANONICAL_CODEMODS` with derivation from `meta.rulesets`/`meta.order`,
     and the existing test re-derives the same way — tautological. That silently
     dropped the repo's explicit-list convention (cf. the N2 decline, previous
     record): an accidental retag or order edit would sail through. Added
     `test_canonical_front_to_back_roster_is_pinned` (the literal 12-code
     front-to-back pin = the deliberate-change gate) and
     `test_canonical_orders_are_unique` (a duplicate `meta.order` would silently
     tie-break on listing order) to `test_canonical.py`.
   - **Placeholder ruleset descriptions — Low [fixed].** `Ruleset("default",
     description="default")` / `("iuc", "iuc")` — user-facing through the `rulesets`
     CLI command and MCP `list_rulesets`. Wrote real descriptions and added the
     guard `assert description != name` to `test_rulesets.py`.
5. **Duplication / missed reuse ✅** — RST validity/repair logic exists once (tier-1
   `rst.py`) and is shared by both partition halves; the parity table and the alias
   index both derive from per-rule `meta.planemo_linters` — no second hand-maintained
   planemo map anywhere.
6. **Dead / reserved surface — one [fixed]** — `rst.py`'s `_apply_line_edits` carried
   a `"delete"` op that no planner path emits (leftover from a pre-merge repair
   design). Removed; the planner docstring now names only the two real ops
   (`replace`, `insert_before`).
7. **Doc / code agreement ⚠️→fixed** — the main finding surface; see below.

### Findings — documentation drift (all [fixed])

- **Roster enumerations missing GTR035–GTR037 — Medium [fixed] ×3.** The
  `canonical_codemods()` front-to-back enumerations in `ARCHITECTURE.md`, the codemod
  `CLAUDE.md`, and `canonical.py`'s own module docstring all listed 9 of the 12
  pipeline members — the planemo-parity fixes (`TrimAttributeWhitespace` /
  `ReplaceOutputElement` / `DropRedundantParamName`) never made it in, and #150's
  edit added `RepairHelpRst` on top without noticing. All three now list the full
  12-stage order (and the new pin test makes the *next* omission impossible to miss).
  Added "roster enumerations" to the skill's standard doc sweep.
- **GTR089 partition under-documented — Medium [fixed] ×4.** `ARCHITECTURE.md` said
  "three practices use this" (now four) and lacked the GTR089.1/.2 row, the `rst.py`
  and `bundle.py` ledger rows, and the `Ruleset`/planemo ledger rows;
  `docs/guide/capabilities.md` had no GTR089.1 fix row and still labelled the
  advisory GTR089 (not `.2`); `docs/iuc_best_practices.md` didn't mention the
  partition and cited `D12–D30` (now D31); the check README lacked GTR089.2.
- **The planemo-alias feature (#147) was invisible in the guide — Medium [fixed].**
  `docs/guide/vs-planemo.md` — the audience doc whose whole job is the planemo
  relationship — mentioned neither the **110/146** linter coverage, the generated
  [parity table](planemo_linter_parity.md), nor name-based selection;
  `docs/guide/usage/cli.md`'s selection section didn't document planemo-name tokens.
  Both updated (claims verified against `resolve.py`/`planemo.py` and the parity
  summary table).
- **Skill self-drift (meta) [fixed].** The architecture-audit `SKILL.md` gained
  Phase 0 (delta scoping against the recorded audited commit), the
  skills-as-unguarded-docs sweep target, and the roster-enumeration sweep target;
  the Phase-0 "(see Conventions)" pointer initially dangled — the Conventions
  bullet it references is now written. And the canonical example of the
  skills-sweep target re-proved itself: the pre-pr-audit `SKILL.md` Step-6 comment
  still said "×7" (eight packages) — the catch had been *recorded* in the
  architecture-audit skill but the fix never applied; fixed during this PR's
  pre-PR audit.

### Accepted / intentional (not drift) [accepted]

- **`iuc` mirrors `default`.** A reserved divergence point, not duplication; its new
  description says so explicitly.
- **15 early exploratory measure slugs not individually listed in `CLAUDE.md`**
  (`tool-id-vs-path`, `validity-distribution`, `macro-usage`, …). Documented
  collectively via `scripts.measure --list`; every *decision-backing* slug (including
  #149's three `help-rst-*` measures) is individually documented. Longstanding, not
  delta drift — don't re-flag.

### Escalation (multi-agent adversarial verification)

9 finders (4 delta-scoped tier scouts + 5 cross-dimension scouts incl. a dedicated
documentation-adversary lane) → one adversarial refuter per finding → synthesis.
**11 candidates, 10 survived, 1 refuted; after dedup: 4 new Medium + 4 Low, 0 High,
no boundary or abstraction finding.** Every applied item below was **re-verified
against source by the main pass before applying** (the standing lesson). The
escalation's distinctive value was **two corrections to the single pass itself** (M3,
M4) — the second audit in a row where the documentation-adversary lane out-found the
tier scouts.

**New findings, applied [fixed]:**

- **M1 — the GTR089.1/.2 partition had no partition-soundness test — Medium [fixed]
  (2 independent scouts).** `test_partition.py` had per-partition soundness tests for
  GTR020 and GTR018 but none for the new GTR089 pair; nothing *tested* the
  shared-predicate claim ("the boundary can't drift", `checks/help.py`). Added
  `test_help_rst_partition_is_sound`: a repairable body (short title underline) →
  fix fires / advisory silent; an unrepairable one (unclosed inline markup,
  `repair_help_rst` → `None`) → fix silent / advisory fires. Verified the fixtures
  against tier-1 `test_rst.py` before writing.
- **M2 — `--select`/`--ignore` `--help` text omitted planemo linter names — Medium
  [fixed].** `resolve.py` accepts them (tested, guide-documented) but the primary UX
  surface still said "rule codes" with GTR-only examples (`cli.py`). Both help
  strings now say "GTR codes or planemo linter names" with a `HelpMissing` example.
- **M4 + L1 — "preset" survived in the dated decision logs — Medium/Low [fixed by
  annotation].** MCP `decisions.md` D1 (`list_presets`, `UnknownPreset`, "preset"
  ×5) and CLI `decisions.md` D4 (+ later mentions) predate #146. Per the repo's
  superseded-snapshot convention these are *historical records*, so each got a dated
  "**Renamed since (PR #146, registry D15)**" annotation mapping old → new tokens
  rather than a rewrite. **This corrects the single pass's §3 "fully retired from
  src + docs" claim** — its sweep had excluded `decisions.md` files.

**New findings, scoped to the safe part [fixed] with the rest left as [proposal]:**

- **M3 — the planemo-coverage figure 110/146 is unreconciled with rule metadata —
  Medium.** The parity Summary's hand-maintained **HAVE = 110** counts *linters*
  across slash-bundled table rows, while `meta.planemo_linters` yields **103 unique
  alias names** (re-derived live; `planemo_index()` agrees). Part of the gap is
  legitimate (XSD is covered by tier-1 validation, not a rule → correctly alias-free)
  but at least `CitationsNoValid` / `ToolIDWhitespace` are marked HAVE with no alias,
  and the single pass **propagated the unpinned 110 into `docs/guide/vs-planemo.md`**.
  **[fixed]:** the guide claim is de-coupled from the hand count (it now cites the
  parity table's rule-by-rule map of all 146 linters, no propagated number).
  **[proposal]:** reconcile properly — decide per missing linter whether to add the
  metadata alias (this *changes selection behaviour*: `--select CitationsNoValid`
  would start resolving) or to annotate it as alias-free coverage, then pin the
  Summary count with a test against `planemo_index()` + an explicit alias-free
  allowlist. Needs per-linter judgment; not applied.
  **Follow-up (2026-06-10): proposal applied** — 8 verified-covered aliases added,
  `BioToolsValid` re-marked HAVE\* (consistency with `EDAMTermsValid`),
  `ValidDatatypes` kept aliased-but-DETECT, Summary now metadata-derived (HAVE 111)
  and pinned by `test_planemo_aliases.py`. Registry `docs/decisions.md` D17.

**Low, recorded with no action:**

- **L2 — `planemo_index()` completeness** — the index is *derived*, so it cannot go
  stale (verifier-corrected framing); a typo'd alias already surfaces because the
  byte-pinned parity table regenerates from the same metadata, making the typo
  visible in the table diff. A stronger guard means vendoring planemo's canonical
  linter-name list → **[proposal]**, folded into M3's reconciliation.
  **Follow-up (2026-06-10): applied with M3** — canonical list vendored
  (`tests/data/planemo_linters_c6e0ee3.txt`), every alias checked against it.
- **L3 — parity freshness test "brittleness"** — refuter killed the sub-claims (the
  render includes all codes; the sort is stable); the residual (broken renderer +
  same-change regeneration) is genuinely low. **[accepted]**, no action.
- **L4 — adapter ruleset-membership asymmetry** (`adapters.py` filters codemods by
  truthy `meta.rulesets`; fmt/check adapters don't) — real observation, but the
  recommended guard **already shipped in #146**
  (`test_every_selectable_rule_declares_a_ruleset`). **[accepted]**, recorded so the
  next audit doesn't re-flag it.

**Re-confirmations:** a scout independently re-derived the duplicate-`meta.order`
tie-break risk and concluded the single pass's two new pin tests are the right and
sufficient guard — independent convergence on the #146 derivation move being sound.
No scout proposed a boundary or High finding anywhere.

**Refuted (do not re-litigate):** "ruleset-derivation has no orphaned-membership
guard" — `test_every_declared_ruleset_name_is_in_the_catalog` (shipped in #146)
asserts every rule's `meta.rulesets ⊆ ruleset_names()`, exactly covering the claimed
silent-drop.

**QA gate:** green (`bash scripts/qa_gate.sh` — ruff + mypy-strict + pytest ×8) after
the applied fixes, re-run after the escalation follow-ups.

**Verdict — healthy; boundaries hold, the abstraction absorbed the growth without strain.**
This covers the largest tier-3.5 addition to date: the **planemo-parity advisory wave**, which
roughly tripled `galaxy-tool-lint` — **52 new detect-only checks (`GTR038`–`GTR089`)**
reimplementing every mechanically-reimplementable `galaxy.tool_util.lint` linter (outputs,
the full `inputs.py` correctness surface, `tests.py`, validators, `<help>` RST), bringing the
tier to **66 checks total**. Method: a single deep pass across the seven dimensions, grounded
in source (`rules.py` / the `checks/` sub-package / `detect.py`, the registry adapters, the boundary tests),
then a 7-finder / adversarial-refuter escalation (per-tier + per-dimension + a dedicated
**documentation-adversary** lane tasked with disproving every present-tense doc claim).

**No boundary violations, no High findings.** The wave landed *inside* the existing
`CheckRule` ABC with zero changes to the cross-tier contracts: tier 3.5 still imports only
tiers 1 + 0.5 (+ external `lxml`/`packaging`/`docutils`); the registry still pulls checks via
the derived `all_checks()` enumeration (no hand-maintained second list); the collision guard,
partition validator, `detect_only` test, and read-only-purity test all still hold and now
cover 66 codes. The single real class of finding was **documentation drift** — four docs had
frozen their description of the check tier at the pre-wave `GTR034` high-water mark. All four
are fixed in this pass.

### Dimension-by-dimension

1. **Boundary integrity ✅** — `galaxy-tool-lint/pyproject.toml` declares only
   `galaxy-tool-refactor-rules` (0.5), `galaxy-tool-xml` (1), `lxml`, `packaging`, and the new
   `docutils>=0.21`; a grep of `src/` confirms imports match (no codemod/fmt/registry import).
   `docutils` is genuinely used (`checks/help.py`, GTR089 only) and present in `uv.lock` —
   not an unused declared coupling. Guarded by `test_tier_boundaries.py`.
2. **Abstraction consistency ✅** — all 52 new rules subclass the same `CheckRule` ABC, declare
   `meta: ClassVar[RuleMeta]` with `detect_only=True`, and implement one non-mutating
   `detect()`. The `.1/.2` partition family is untouched and still sound. No new rule needed a
   base-class change — strong evidence the abstraction was the right shape.
3. **Naming / vocabulary drift ✅** — uniform PascalCase verb/noun class names across the wave
   (`NoTodoText`, `CommandPresent`, `InputsPresent`, `HelpRstValid`, …); no drift from the
   older `GTR021`–`GTR037` cohort. Shared helpers (`_param_name`, `_iter_named_params`,
   `_select_params`, …) and lookup tables centralise logic rather than re-naming it per rule.
4. **Contract-enforcement gaps ✅ (well-guarded)** — `test_detect.py` pins the registry at
   `len == 66` with unique codes, `is_sorted_by_code`, `every_check_is_detect_only`, and a
   no-mutation purity test. The hardcoded `66` is the *intended* tripwire: adding a check
   without bumping it fails CI. The registry `_build_index()` raises on GTR-code collision and
   `_validate_partitions()` enforces the dotted `.1/.2` split — both with planted-violation
   tests.
5. **Duplication / missed reuse ✅** — no rule duplicates another's detect logic; the
   macro-skip soundness pattern is an intentional per-rule LBYL guard (`has_macros`), not a
   copy-pasted block that *should* be a helper (each rule's guard condition differs).
6. **Dead / reserved surface ✅** — `GTR032` (`CommandAndJoining`) remains a documented no-op
   stub (~1 tool corpus-wide, D3) — accepted, not drift. No new stubs.
7. **Doc / code agreement ⚠️→fixed** — see findings below; the four frozen-at-`GTR034` docs
   were the entire finding surface, now corrected.

### Findings

**Documentation drift — the check tier's description was frozen at the pre-wave `GTR034`
high-water mark in four places. All fixed this pass:**

- **`ARCHITECTURE.md` §6 + the "Rule codes at a glance" table + the tier-stack one-liner —
  Medium [fixed].** The Phase-1 baseline described only the flat IUC advisories and the `.2`
  partitions, stopping at `GTR034`; it never mentioned the `GTR038`–`GTR089` wave. Added a
  wave paragraph (grouped by source area, with the `has_macros` raw-tree soundness rule and
  the `docutils` dependency), a `GTR038–GTR089` row to the rule-code table, a count to the
  tier-stack row (66), and `D12–D30` + `planemo_linter_parity.md` to the §6 citation footer.
- **`galaxy-tool-lint/CLAUDE.md` "Scope" — Medium [fixed].** Listed only the pre-wave
  flat advisories + `.2` partitions. Added the planemo-parity-wave paragraph, the 66-check
  total, the macro-skip note, and the `D12–D30` / `planemo_linter_parity.md` pointers; also
  folded in `GTR034` (previously omitted from the flat-advisory list).
- **`docs/iuc_best_practices.md` BUILT table — Low [fixed].** This doc is legitimately
  *IUC-practice-scoped*, so the wave doesn't belong in its table — but a reader had no signal
  the tier had grown. Added a scope note distinguishing the IUC slice from the planemo-parity
  axis and pointing at `planemo_linter_parity.md` + `D12–D30`.

**Resolved disagreement (recorded so it isn't re-litigated):** an exploration scout reported
`galaxy-tool-lint/docs/decisions.md` stopped at **D21/GTR068** with `GTR069`–`089`
undocumented. Reading the file directly disproved it: it reaches **D30 (GTR089)** and fully
documents every wave group (D12–D30, each with corpus counts). The scout had truncated its
read. No fix needed — the decision log is current.

### Accepted / intentional (not drift) [accepted]

- **~~Monolithic `checks.py` (~3,170 lines, 66 rules).~~** Was intentional (rules ordered by
  GTR code, helpers before their users, no circular structure) and judged not a defect — but
  **this PR applied the split** below at the maintainer's request. The classes now live in the
  `checks/` sub-package; see "Applied follow-up".
- **`try/except` in `_is_pep440` and `_rst_is_invalid` (GTR089).** Sanctioned third-party
  boundary exceptions — `packaging.Version` and `docutils.core.publish_string` expose no LBYL
  validity predicate. Consistent with the dignified-python carve-out.
- **Hardcoded `len == 66` in `test_detect.py`.** A deliberate drift tripwire, not a stale
  literal.
- **Detect-only checks read the un-expanded tree**, so a practice met via a macro can still be
  flagged; the per-rule `has_macros` guard suppresses only the *unsound* cases. Advisory
  status keeps the residual false-positives tolerable.

### Applied follow-up (this PR — maintainer asked to apply the escalation proposals)

The escalation proposals were taken up after the audit, **but only after each was re-verified
against the code** — which is exactly why one (N2) was ultimately **declined**: verification
showed its premise was false, so applying it would have broken a cross-tier convention. Net:
**three applied (N3/N4/N5), one declined (N2).**

- **[applied] Split `checks.py` → `checks/` sub-package (N5).** Classes partitioned by
  element/source area into `tool.py` / `partition.py` / `outputs.py` / `inputs.py` /
  `validators.py` / `tests.py` / `help.py`, with cross-module helpers in `_shared.py`. Pure,
  behaviour-preserving code-move (done mechanically via an AST splitter; `ruff --fix` pruned the
  per-module import headers). The 81-test suite + mypy-strict + the `len == 66` tripwire all
  pass unchanged → the move altered no behaviour. Shrinks the repo's largest file (was 3,169
  lines) and localises future wave growth.
- **[reverted — kept explicit list] `all_checks()` enumeration (N2).** The finding proposed
  deriving the roster from `CheckRule.__subclasses__()`. Its justification — "tiers 2 + 3 already
  auto-register" — was verified **false**: `coded_codemods()` (tier 2) and `all_rules()` (tier 3)
  both use **explicit hardcoded lists**, so the explicit list is the *consistent* cross-tier
  convention and the reflection form would make the check tier the lone outlier (and adds an
  import-for-side-effect + stray-subclass-pollution fragility the explicit list avoids). It was
  briefly applied as an informed override, then **reverted to keep the three rule families
  consistent.** `all_checks()` stays an explicit list (now with grouped per-submodule imports);
  the `test_detect.py` `len == 66` assertion remains the acknowledgement gate. **Net: N2 is the
  one escalation finding intentionally declined — recorded so it isn't re-litigated.**
- **[applied] `_select_params` memoised with `lru_cache(maxsize=1)` (N4).** A literal "single
  multi-yield collector" would collapse seven GTR codes into one class (breaking the
  one-class-per-code design the audit + refuter endorsed), so instead the generator became a
  re-iterable tuple memoised for the current root only: the seven select checks (GTR058–GTR064)
  now walk the param subtree once per `detect_violations` pass and reuse it six times.
  `maxsize=1` bounds memory to one document and rules out `id`-reuse stale hits.
- **[applied] fmt cosmetic-only property test (N3).** `test_framework.py::
  test_format_preserves_structure_and_attributes` formats a structurally rich tool and asserts
  the document-ordered element sequence, every tag, and every element's attributes (names,
  values, order) are identical before/after — only whitespace/empty-element-shorthand may
  change. Pins fmt's remit so a future structural cosmetic rule fails loudly.

### Escalation (multi-agent adversarial verification)

9 finders (4 tier-scoped + 5 cross-dimension, incl. a dedicated **documentation-adversary**
lane tasked with disproving every present-tense doc claim/count/citation) → one adversarial
refuter per finding → synthesis. **31 surviving findings; after dedup: 4 new (1 Medium, 3 Low),
28 independent re-confirmations, 1 refuted.** No new High, and **no new boundary or
abstraction finding** — the planemo-parity wave was absorbed without architectural strain. The
escalation's main value was corroboration: the dependency-free, tier-boundary, partition-
soundness, and derived-enumeration contracts were each independently re-derived by 2–4 separate
scouts and all held at 66 checks.

**New findings:**
- **N1 — stale citation in the 2026-06-03 log entry — Medium [fixed].** Line ~325 cited the
  retired `GTR031` check at "71.5% in `corpus_check_stats.md`"; that code/number no longer
  exist in the (2026-06-06-regenerated) file — the advisory is now `GTR020.2` at 54.0%.
  Annotated as a superseded snapshot (the pedagogical point — measure ≠ check-firing-rate —
  still stands). The documentation-adversary lane found this; the 2026-06-05 pass had fixed the
  *codemod*-doc references to the retired codes but missed this audit-prose line.
- **N2 — `all_checks()` is a 66-entry hand-maintained list that could be `CheckRule.__subclasses__()` — Low [reverted / declined].**
  The finding claimed "tiers 2 + 3 already auto-register"; verification showed that is **false**
  (both use explicit lists), so deriving the check roster would make it the lone outlier. Briefly
  applied, then reverted to keep the three rule families consistent; the explicit list + `len == 66`
  gate stay. The one escalation finding intentionally declined. See "Applied follow-up".
- **N3 — fmt cosmetic-only scope is enforced by construction (the `Edit` union cannot rename
  tags / reorder children) but not by an explicit property test — Low [applied].** Added a
  structure-preservation property test (`test_framework.py`). See "Applied follow-up".
- **N4 — GTR058–GTR064 each re-walk `_select_params` (7×) — Low [applied, scoped down].**
  Refuter-downgraded (low-frequency small walks; per-rule isolation is intentional). Applied as
  an `lru_cache(maxsize=1)` memoisation that keeps all seven per-code rules intact rather than
  the finding's code-collapsing "single collector". See "Applied follow-up".

**Refuted (do not re-litigate):** "GTR077–079 should be consolidated" — each shares the
`_iter_option_filters` iterator but has genuinely distinct per-rule validation; consolidation
would obscure, not clarify. (Plus minor mislabels the refuters corrected in passing: the
`GTR020.2` class is `SingleQuotedCheetah` not "UnquotedVar"; the derived-enumeration N1-gap fix
was 2026-05-31 not -06-01; the immutability guards are the unit tests, not the corpus sweep.)

**Independent re-confirmations (recorded so they aren't re-litigated):** tier-0.5 dependency-
freedom (`test_dependency_free.py`); no upward/sibling imports in tiers 2/3.5
(`test_tier_boundaries.py`); fmt sole serializer (`test_serializer_allowlist.py`); partition
predicates defined once in tier 1 and shared by the `.1`/`.2` halves (`test_partition.py`);
`detect_only`/no-mutation/collision/`len == 66` all guarded; presets + upgrade-only set derived,
not hand-listed; CLI/MCP carry zero hardcoded rule codes. All re-validated at 66 checks.

---

## Re-audit 2026-06-05 — post Cheetah-mutation subsystem (PRs #95/#96/#98/#99/#100/#101) + escalation

**Verdict — healthy; boundaries hold, the new tier-1 abstractions are coherent.** This
covers the largest tier-1 addition since the last audit: the **Cheetah-mutation subsystem**
in `galaxy-tool-xml` — `cheetah_cdm` (faithful CT3 lexer), `cheetah_refs` (read-only
reference model), and `cheetah_rename` (the first Cheetah *mutator*: `rename_param` tree
rewrite + the new **Tier-B `rename_param_plan`** offset API, both rendered from one shared
`_plan_rename`). Method: a refreshed `ARCHITECTURE.md` baseline (the subsystem was entirely
undocumented) + a 6-finder / adversarial-refuter escalation (per-tier × 2, per-dimension × 4;
**24 raw findings → 23 surviving refutation, 1 refuted**).

**No boundary violations, no High findings.** The escalation positively *re-confirmed* the
load-bearing invariants: `cheetah_cdm`/`cheetah_refs`/`cheetah_rename` import only stdlib +
lxml + intra-tier-1 (`binding.parse_tool`, `cdata`) — no higher tier, no cycle; the
**no-serializer** contract holds for both renderings (`rename_param` mutates the tree;
`rename_param_plan` returns offsets; the facade serialises via fmt — guarded by the
serializer-allowlist test); the two renderings share one planner so they cannot diverge on
scope or bail reason (corpus parity 96.8%, **0 mismatches**, pinned by a synthetic-fixture
test in `test_measure.py`); the round-trip and atomic-bail contracts are unit-tested.

### Findings

**Phase-1 baseline drift — fixed:**
- `[fixed]` **`ARCHITECTURE.md` tier-1 omitted the entire Cheetah-mutation subsystem** and
  still called "M5" *deferred* (M5.1 `cheetah_cdm` + M5.3 `cheetah_rename` shipped). Added a
  tier-1 subsystem bullet (lexer / reference model / mutator + the two-rendering contract),
  corrected the stale `command_text` "deferred M5 lexer" note, and added three reference-index
  rows (`cheetah_cdm` §19, `cheetah_refs` §18, `cheetah_rename` §20).

**Medium — fixed:**
- `[fixed]` **`GTR034` (`UnusedParam`) absent from `ARCHITECTURE.md`** (merged #96): the
  reference-usage advisory check was missing from both the tier-3.5 prose and the rule-codes
  table. Added to both (flagged as reference-usage, distinct from the presence/shape advisories).

**Low — fixed (safe doc):**
- `[fixed]` **CLI `README.md` said "seven commands"** and omitted `rename-param` — corrected
  to eight, list updated.
- `[fixed]` **Root `README.md` CLI row + command bullets omitted `find-references` /
  `rename-param`** — added both; also corrected the stale `format` "byte-identical to the
  historical behaviour" claim (GTR020.1 made default `format` behaviour-preserving, not
  byte-identical; codemod §30).

**Re-confirmed (no change — validates the design):** facade `rename_param` routes serialisation
through fmt (`format_tool_document_subset`); the Tier-B parity classification in
`scripts/measure.py` correctly models the shared-planner taxonomy (shared bails agree; the four
offset-only bails are sound stricter declines); ARCHITECTURE/decisions/README numbers,
signatures, dataclass fields, and §18/19/20 cross-references all match the code.

**Accepted (intentional, documented):**
- `[accepted]` **`rename_param_plan` has no in-repo production caller** — it is the
  editor-oriented Tier-B API, reserved for the external galaxyls LSP binding (decisions xml
  §20; `docs/upgrade_research/lsp_rename_integration.md`; shipped downstream as
  galaxyproject/galaxy-language-server#331). It is exercised by unit tests and the
  `rename-coverage` parity measure, and listed in the package's public API. Not dead surface.

**Refuted:**
- `[refuted]` *"the 96.8% / 0-mismatch parity is corpus-only, not CI-enforced."* The
  `n_plan_mismatch == 0` classifier is pinned by a synthetic-fixture test in
  `test_measure.py::test_measure_rename_coverage_classifies` (engine-present and engine-absent
  paths), so the invariant is guarded in CI; the corpus sweep only scales it up.

**Low — fixed (test coverage):**
- `[fixed]` Added a dedicated unit test for the `locator-failed` plan-only bail
  (`test_raw_offset_map_locator_failed`: char mismatch, raw-runs-out, and literal-`<`
  cases), joining the already-pinned `parse-error` / `encoding` / `entity-content` cases.
  An `element.tail`-on-bail immutability test was considered and dropped — the mutator never
  rewrites `tail`, so there is no real gap.

## Re-audit 2026-06-04 — post GTR-namespace unify + partition sub-rules (PRs #86–#88) + full escalation

**Verdict — healthy; boundaries hold, the new abstractions are coherent.** A refreshed
`ARCHITECTURE.md` baseline plus a 12-finder / adversarial-refuter escalation (per-tier × 7 +
per-dimension × 5; **26 raw findings → 23 surviving refutation, 3 refuted**) over the state
after three merged PRs: #86 (`GTR020.1` provable-quote fix), #87 (unify every rule code under
one `GTR` prefix; fixability is a rule property, not the prefix), #88 (partition sub-rules — a
practice splits into a fixable `.1` + an advisory `.2`, the advisory restricted to the
complement of the fix via a *shared tier-1 predicate*).

**No boundary violations, no real High architecture findings.** The escalation positively
*re-confirmed* the load-bearing invariants: check (3.5) imports only tier 1 + 0.5 (the
residual restriction reuses tier-1 predicates, never the codemod tier); the three new tier-1
analysis modules (`command_text` / `command_vars` / `cdata`) import only stdlib + lxml; the
partition is modelled uniformly across all three practices; `display_code` is applied
consistently (CLI → parent, MCP → child, by design); no residual `GTX`/`IUC` *internal* code
survives in `src/`; the fix/advisory partition is disjoint + exhaustive and pinned by a
soundness test.

### Findings

**High — fixed:**
- `[fixed]` **Stale prose in the generated `corpus_check_stats.md`** (line 29) + its generator
  (`scripts/corpus_check.py`) called `GTR020.2` a "reserved placeholder (flags nothing)" — but
  it is the partition advisory residual that fires on 57.8% of tools; only `GTR032` is a
  reserved stub. Corrected both (generator prose + the deterministic page line).

**Low — fixed (safe):**
- `[fixed]` `Cursor.is_cdata_wrapped()` (tier 2) duplicated the tier-1
  `cdata.is_cdata_wrapped()` body → now **delegates** to the tier-1 predicate (one definition;
  the serializer-allowlist entry for `cursor.py` removed as it no longer re-serialises) +
  docstring updated.
- `[fixed]` `ARCHITECTURE.md` reference index lacked the three tier-1 analysis modules → rows
  added; tier-1 §3 module list added; xml `docs/decisions.md` **§16** extended to cover
  `cdata.py` (it previously documented only `command_text`/`command_vars`).
- `[fixed]` Present-tense references to the **retired** codes `GTR031`/`GTR022`/`GTR030` in the
  *live* codemod §29/§30 (and a now-false "flag *any* non-CDATA body" claim) → updated to the
  current `GTR020.2`/`GTR018.2`/`GTR019.2` + the partition restriction noted. (The check-tier
  D1–D8 journal keeps its pre-partition codes deliberately — their stats describe the
  *unrestricted* rules; D9/D10 bridge.)
- `[fixed]` The facade (`run`/`upgrade`/`detect`) didn't state `codes` must be pre-resolved
  (parents expanded) → module docstring now says so explicitly.
- `[fixed]` MCP `_violation_to_dict` didn't document the intentional CLI-parent / MCP-child
  code asymmetry (registry D10) → docstring added.

**Low — accepted (intentional; recorded so the next audit doesn't re-litigate):**
- `[accepted]` `Cursor.element` exposes the raw lxml element — a documented seam for tier-1
  predicates at the partition boundary; tier 2 already depends on tier 1. (Refuted as a
  "violation".)
- `[accepted]` MCP returns the precise child code while the CLI shows the parent — deliberate
  (agents need to distinguish fixable vs advisory; humans want one practice name).
- `[accepted]` `GTR032` reserved no-op stub (data-backed deferral, check D3); partition parent
  codes are selectable group keys, not rule handles.
- `[accepted]` GTR-code references in docstrings of rule-specific classes (e.g. `UnquotedVar`)
  — consistent house style.

**Proposal (not applied — adding a test/guard, per the safe-fix policy):**
- `[proposal]` No guard enforces the **partition code-format** invariant (a sub-rule's `code`
  must be `<parent>.N`). Today the exact-equality `test_partition.py` and code review catch a
  mistake loudly, so this is Low. A lightweight assertion in `_index()` (or a derived test that
  every `meta.parent` has exactly a `.1` fixable + `.2` advisory child whose codes start with
  the parent) would harden it against a future partition added without updating the test.

### Reproduction
`bash scripts/qa_gate.sh` (green). Workflow: 12 finders × adversarial refuters, run
2026-06-04.

---

## Re-audit 2026-06-03b — post macro-epic (PRs #79–#82) + full escalation

**Verdict — healthy; boundaries hold exactly as documented.** A fresh deep pass plus a
12-finder / adversarial-refuter escalation (per-tier × 8 + per-dimension × 5;
**15 raw findings → 14 surviving, 0 High, 1 refuted**) over the state after this session's
four merged PRs (upgrade-research accuracy #79, research-note guard #80, macro Phase-2a
`normalize-macros` #81, Phase-2b sizing #82). Every survivor was a doc-precision **Low** or a
contract-enforcement **test gap** — plus **one real bug**. No boundary violation; the
dependency direction and the facade-owns-orchestration rule are intact.

### New findings (this pass)

- **CLI `upgrade --diff` exit code ignored a pending macro bump — Medium [fixed].**
  `cli.py:280` was `(check and macro_pending)`; cli D6 says *both* preview modes (`--check`
  and `--diff`) must surface a pending imported-`@PROFILE@` bump. Now `((check or diff) and
  macro_pending)`, with regression test `test_upgrade_diff_reflects_pending_imported_token`.
- **No guard enforced the dependency direction — Medium [fixed].** §1/§9 assert "no tier
  imports a higher one" and that siblings codemod/fmt/check never import each other, but nothing
  failed on a future stray import. Added `galaxy-tool-refactor-registry/tests/test_tier_boundaries.py`:
  scans every package's `src/` for `galaxy_tool_*` imports and fails on any outside its allowed
  set (mirrors the `pyproject.toml` edges; the CLI is held to facade + fmt + xml, never
  codemod/check). Corpus-free, CI-run; companion to `test_serializer_allowlist.py`.
- **Doc-precision Lows [fixed]:** MCP tool names in `ARCHITECTURE.md` + root `CLAUDE.md` were
  `format`/`upgrade`/`check` → corrected to `format_tool`/`upgrade_tool`/`check_tool`; the rules
  `README.md` listed 6 of `RuleMeta`'s 8 fields and omitted `Violation` (both added); the rules
  `CLAUDE.md` called tier-4 a *direct* dependant (it reaches rules transitively via the facade);
  the check `__init__` public-surface line omitted `sort_violations`; the mcp `CLAUDE.md` omitted
  its (correct, `TYPE_CHECKING`-only) `rules` dep; the `ARCHITECTURE.md` Reference Index gained
  rows for `datatype_format` (shared tier-2 helper) and `macro_datatype` (registry, D8).

### Accepted / re-confirmed (not drift)

- `§N5`/`§N6` code comments resolve to *this* audit doc's note table (below), not
  `ARCHITECTURE.md` — the references are valid.
- mcp's `galaxy-tool-refactor-rules` dependency is a *direct* `TYPE_CHECKING` import of
  `Violation` (`service.py:34`) — correct hygiene, not an unused dep.
- The CLI imports fmt's `cli_support` / `detect` directly (not via the facade) — the established
  intentional asymmetry (macro files have no codemods; the facade stays the *rule*-orchestration
  path). Recorded, not changed.

### Refuted (do not re-litigate)

- "Inconsistent `sort_violations` usage in `facade.py`" — refuted: it is a stable shared
  `(sourceline, code)` sort and the facade's call sites are consistent.

### Proposals (not applied — maintainer decision)

- **Catalog-completeness guard** (every `CodemodCommand` subclass wired into `coded_codemods()`):
  valuable, but needs careful scoping (base classes + runtime-gated + upgrade-only codemods are
  not plain catalog entries), so left as a proposal rather than risk a wrong/flaky test.
- **Per-codemod *unit* idempotence tests** for GTR002/005/013: the corpus sweep already enforces
  idempotence; unit tests would be redundant belt-and-suspenders.

---

## Documentation audit 2026-06-03 (multi-agent escalation)

A companion deep **documentation** audit (7-area finders — root docs, stats numbers,
guide, upgrade_research, decisions, CLAUDE/README counts, src docstrings — + adversarial
refuters): **15 raw → 12 surviving, 3 refuted.** Theme: docs that missed the MCP +
`normalize-macros` updates, plus two stale code-range enumerations. **8 fixed, 4 refuted
on integration.**

**Fixed:**
- Guide: `capabilities.md` CLI list 5→6 (`+normalize-macros`) and MCP tools →
  `format_tool`/`upgrade_tool`/`check_tool`; `usage/mcp.md` (TL;DR, table, and the
  example call) → the `_tool` names.
- Root `README.md`: the CLI row + Quick-start gained `normalize-macros`; the MCP row →
  `*_tool` names.
- `docs/upgrade_research/README.md`: "auto-fixes only two codes (GTR014/GTR015)" →
  three (GTR014/GTR015/GTR016).
- Registry `decisions.md`: the D2 collision-free enumeration (canonical codemods now
  `…/017/018/019`, runtime-gated `014–016`, checks `GTR021–GTR033`) and D3's runtime-gated
  range `GTR014–GTR016` — refreshed to the current namespace.

**Refuted on integration (not stale):**
- "seven tiers" in root/codemod/fmt CLAUDE.md is **correct** — there are 7 tier-*numbers*
  (0.5/1/2/3/3.5/3.6/4); tier 4 has two *packages* (CLI + MCP). "Eight tiers" would be an
  error; "eight packages" is the package count.
- `iuc_best_practices.md`'s **73.2%** unquoted-`$var` figure is the `command-unquoted-var`
  *measure*, a deliberately different metric from the then-`GTR031` *check* firing rate
  (71.5% in `corpus_check_stats.md` at the time of this entry); the doc cites it correctly.
  *(2026-06-09 note: `GTR031` was subsequently split into the `GTR020.1` fix + `GTR020.2`
  advisory; the advisory's firing rate is now `GTR020.2` at 54.0% in the regenerated
  `corpus_check_stats.md`. The 73.2%-vs-check-rate point stands; only the code/number are
  superseded.)*

Three workflow-refuted (macro_profile_ownership measurement-semantics; capabilities ~73%
artifact-exists; a dated check-tier `decisions.md` record) are not re-litigated.

---

## Re-audit 2026-06-03 (single deep pass + multi-agent escalation)

**Verdict — the architecture is healthy; the boundaries still hold exactly as
documented.** Since the 2026-05-31 pass a session of 9 merged PRs landed a whole
new tier-4 package (`galaxy-tool-refactor-mcp`), the GTR031 command-text check + a
read-only `command_text.py` lexer, the `UpgradeResult.behavior_preserving` verdict,
a `set_e` detector tightening, runtime-gated GTR016, and a `cli_support`
import-resolution fix. Re-measured against the (now refreshed) baseline: **no High
findings, no boundary violations.** The new `mcp` package is a clean thin adapter —
`service.py` calls only the facade + `resolve` (+ tier-1's `ToolXmlSyntaxError` for
its error boundary), `server.py` adds the FastMCP binding. The drift was
**documentation lag** (now corrected) plus one honest-manifest fix.

### New findings (this re-audit)

- **1.x — codemod imported `packaging` without declaring it — Medium [fixed].**
  `profile_semantics.py:73` and `runtime_fixes.py:26` use `packaging.version`, but
  `galaxy-tool-codemod/pyproject.toml` declared only `rules` / `xml` / `lxml` —
  it worked solely via transitive resolution through `galaxy-tool-xml`. The
  manifest didn't encode a real, used coupling (the exact failure mode the prior
  pass flagged for `click`). Added `packaging>=23` (matching xml/check); re-synced;
  codemod tests green.
- **7.x — `ARCHITECTURE.md` documentation drift — Medium [fixed].** Corrected in
  Phase 1: GTR031 was still called a "reserved stub" (it ships as
  `SingleQuotedCheetah`); the `command_text.py` lexer was unmentioned in tier 3.5;
  `behavior_preserving` was missing from the tier-3.6 result shape; §9 listed
  runtime-gated GTR `014–015` though GTR016 is also runtime-gated. The
  reference-index decision-section citations were re-verified — all resolve.
- **6.x — the audit skill's own worked example is stale — Low [proposal].**
  `.claude/skills/architecture-audit/SKILL.md`'s tier table says "(+ future
  `-mcp`)"; mcp has shipped. (Skill tooling, not project `src/` — left as a noted
  proposal.)

### Re-confirmed from the 2026-05-31 pass (still true)

- **Boundary integrity ✅** — re-verified by import + manifest scan across all 8
  packages: no sibling cross-imports (codemod ⊥ fmt ⊥ check), nothing below 3.6
  imports the registry, the CLI and MCP import only the facade (+ tier-1).
- The registry's declared `galaxy-tool-refactor-rules` dependency is **type-only**
  (all five imports of `Violation` / `RuleMeta` are under `TYPE_CHECKING`) — a
  legitimate API-type dependency, *not* the unused-dep pattern. [accepted]
- The fmt-family `RuleHandle.apply` bypass (2.1 below) and the `apply`
  mutate-vs-describe asymmetry (§10) remain intentional and documented. [accepted]

### Reserved surface — intentional, not drift [accepted]

- GTR032 `CommandAndJoining` no-op stub — data-backed (~1 tool corpus-wide; check
  D3). The `command-iuc-heuristics` / `command-lone-amp` / `command-unquoted-var` /
  `iuc011-fixability` measures back the GTR031-ships / GTR032-deferred split.
- `Cursor.replace_with` — declared deferred in codemod `PLAN.md` (no consumer).
- MCP vision **Goal 2** (agent-authored rules) — recorded future; the server ships
  Goal 1 only.

### Escalation (multi-agent adversarial verification)

**15 finders** (8 per-tier + 7 per-dimension) → **17 candidate findings** → an
**adversarial refuter per finding**: **0 refuted, 12 confirmed/downgraded, 5
accepted-intentional** (32 agents). The single pass's structural conclusions
**hold** — no High, no boundary violations. Escalation's value was a cluster of
**documentation staleness in package READMEs / module docstrings** that the single
pass (focused on `ARCHITECTURE.md`) missed, now fixed, plus three test-coverage
gaps recorded as proposals. (0 refuted is itself a signal: the candidates were
predominantly genuine doc-drift, not inflated structural claims.)

**New, fixed this pass [fixed]:**
- **check `README.md` said GTR031 is "not yet implemented" and omitted the
  `command_text.py` lexer — Medium.** Stale since GTR031 shipped (#66); `decisions.md`
  D5 + `ARCHITECTURE.md` were correct, the package README was not. Corrected.
- **`registry.py` module docstring enumerated "GTR014–GTR015 runtime-gated" — Medium.**
  Omitted GTR016 (and GTR017 from the canonical list). Corrected to 014–016 / +017.
- **cli `__init__.py` docstring claimed a direct codemod-tier (tier 2) dependency —
  Medium.** The CLI consumes the facade, not codemod (cli D4); the import list proves
  it. Rewritten to match.
- **cli `check`: macro-file findings were unsorted while tool findings are
  line-sorted — Low.** `facade.detect` returns sorted violations; the macro branch
  did not. Added an inline `(sourceline, code)` sort for parity (cli tests green).
- **mcp `list_rules()` docstring omitted the `cite` field — Low.** Corrected.
- **mcp imported `Violation` (tier 0.5) under `TYPE_CHECKING` without declaring
  `galaxy-tool-refactor-rules` — Low.** Same type-only pattern the registry declares;
  added it for manifest honesty (re-synced).

**Proposals [proposal] (not applied — need a decision / a test):**
- **Tier-0.5 "stay dependency-free" invariant has no test guard — Medium.
  [resolved 2026-06-03].** `galaxy-tool-refactor-rules/tests/test_dependency_free.py`
  now AST-scans the package `src` and asserts every import resolves to the standard
  library or the package itself (a planted-violation test proves the scan isn't
  vacuous), so a future commit can't silently couple the shared-vocabulary tier.
- **`Correction` / `BooleanNormalization` (tier-1 public result dataclasses) are not
  `frozen=True` — Low. [resolved 2026-06-03].** Both verified never mutated; now
  `@dataclass(frozen=True)`, completing the frozen-result-type convention the prior
  pass (N3) began.
- **Codemods' `applies_to={"tool"}` default has no test guard — Low.
  [resolved 2026-06-03].** `test_catalog.py::test_every_codemod_is_tool_only` asserts
  every `coded_codemods()` entry has `applies_to == {"tool"}`, so a macro-applicable
  codemod can't land on the default and silently mutate macro files.
- **Duplicated `_version_or_none` (`profile_semantics.py` + `runtime_fixes.py`)
  — Low. [resolved 2026-06-03].** Consolidated into `galaxy_tool_codemod/
  _version.py::version_or_none`; both modules now import it.

**Re-confirmed intentional [accepted] (recorded so the next audit doesn't re-flag):**
- `CodemodCommand` / `RuntimeGatedFix` are plain classes, not ABCs — the tier-2
  deliberately differs from fmt/check (ARCHITECTURE §10; codemod §15/§24).
- `coarse_detect` for validation-driven codemods isn't independently test-pinned —
  the corpus parity gate covers detect/apply agreement (codemod §19).
- `upgrade_steps_applied` / `missing_upgrade` are base no-op hooks overridden only by
  `UpgradeToLatest` (codemod §14).
- `meta: ClassVar[RuleMeta]` presence is enforced by mypy-strict, not a runtime test.
- The registry's `galaxy-tool-refactor-rules` dependency is type-only
  (`TYPE_CHECKING` imports of `Violation` / `RuleMeta`).

---

**Date:** 2026-05-31  •  **Method:** single deep pass, reading every package's
`src/` + `pyproject.toml` + selected tests against the contracts written in
[`../ARCHITECTURE.md`](../ARCHITECTURE.md).  •  **Scope:** abstraction coherence
and boundary integrity, *not* a line-level bug hunt (see `/code-review` for that).

This audit measures the code against the just-written architecture baseline. The
**headline is reassuring**: the tier boundaries hold exactly as documented — no
sibling-tier cross-imports, no upward dependencies, the GTR namespace is
collision-guarded, and the load-bearing "apply order reproduces `format`" contract
is pinned by a regression test. The findings below are refinements, latent
footguns, and doc-precision gaps, not structural breakage.

Severity key: **High** = a violated invariant or a correctness hazard; **Medium**
= a latent inconsistency that will bite a future maintainer; **Low** = cosmetic /
documentation precision.

Each finding is tagged **[fixed]** (applied in this pass), **[proposal]** (left
for review — structural or needs a decision), or **[accepted]** (intentional;
recorded so it isn't re-litigated).

---

## Dimension 1 — Boundary integrity ✅

**Verdict: clean.** Verified by import grep + every `pyproject.toml` dependency list.

- No sibling cross-imports: fmt ⊥ codemod, codemod ⊥ fmt, check ⊥ {codemod, fmt}.
  (The single `galaxy_tool_codemod` hit inside fmt is a docstring in
  `format.py`, not an import.)
- Nothing below tier 3.6 imports the registry.
- The CLI (tier 4) imports the facade, fmt, and tier-1 parsing only — **not**
  codemod or check directly, exactly as its `CLAUDE.md` claims.

No findings.

---

## Dimension 2 — Abstraction consistency

### 2.1 `RuleHandle.apply` for the fmt family is defined but never invoked — **Medium** [fixed]

`adapters.fmt_handle` builds an `apply` closure that calls
`format_tool_document_subset(document, rule_classes=(cls,))` for a single rule.
But `apply.apply_selection` (`apply.py:55-59`) **bypasses** the fmt handles: it
collects all selected fmt rule classes and runs them as one batch through
`format_tool_document_subset`. So no facade code path ever calls a fmt handle's
`apply` — for the fmt family the uniform `RuleHandle.apply` interface is dead
within this repo.

The bypass is *correct and intentional*: fmt rules are order-sensitive (GTR001 and
GTR003 both rewrite top-level-child tails), so running them one-at-a-time via the
per-rule handle could leave non-canonical intermediate trivia — the same
incoherent-subset caveat `format_tool_document_subset` already documents. The
hazard is that a future consumer (e.g. the MCP server) sees a uniform
`handle.apply` and calls it per-rule, silently getting wrong output.

**Fix applied:** added a caveat comment to `fmt_handle.apply` pointing at the
batch path and the order-sensitivity, so the footgun is documented at the
definition site. The interface stays uniform (the alternative — making fmt
`apply` `None` — would break the `fixable ⇒ apply is not None` invariant).

### 2.2 The three rule base classes are deliberately non-uniform — **Low** [accepted]

`fmt.Rule` and `check.CheckRule` are `ABC`s with a single `@abstractmethod`
(`apply` / `detect` respectively); `codemod.CodemodCommand` is a *plain* base class
with concrete `detect`/`apply` and dynamic `detect_<Tag>` dispatch. All three
declare `meta: ClassVar[RuleMeta]` but none enforces that subclasses set it. This
asymmetry is inherent to the families' different mechanics (a codemod dispatches
per element; a fmt rule/ check is a whole-tree pass) and `RuleHandle` exists
precisely to normalise it. Recorded as intentional; no change.

### 2.3 "apply" is overloaded across families — **Low** [accepted]

`fmt.Rule.apply(tree)` *yields* `Edit`s (it describes — `apply_edits` mutates),
whereas `codemod.CodemodCommand.apply` and `RuleHandle.apply` *mutate*. Documented
in `ARCHITECTURE.md` §10. A rename (`Rule.apply` → `Rule.edits`) would be a clean
consistency win but is a public-API change touching every rule + its tests —
[proposal] below, not applied.

---

## Dimension 3 — Naming & vocabulary drift

### 3.1 Stale reference to a renamed CLI function — **Low** [fixed]

`scripts/corpus_check.py:3017` reads *"Mirrors the app CLI's
`_detect_violations`"*, but the CLI has no such function — detection there is the
inline `check_command` calling `facade.detect` (orchestration moved into the
facade when tier 3.6 landed). **Fix applied:** updated the comment to reference
the current `facade.detect` / `check_command` path.

### 3.2 Two unrelated `_detect_advisory` names — **Low** [accepted]

`facade._detect_advisory` (registry) and the import alias
`from galaxy_tool_lint.detect import detect_violations as _detect_advisory`
(`corpus_check.py:2951`) name two different things in two files. Confined to
distinct modules, no shadowing; not worth churn. Recorded.

---

## Dimension 4 — Contract-enforcement gaps

### 4.1 "fmt is the only serializer" is asserted in prose but not tested — **Medium** [proposal]

The invariant appears in three `CLAUDE.md`s and `ARCHITECTURE.md`, and the code
honours it (every output byte flows through `serializer.to_bytes`; `apply_selection`
always ends in `format_tool_document_subset`). But nothing *guards* it — a future
codemod that does `path.write_bytes(etree.tostring(...))` would pass CI.

A grep over `src/` finds these `etree.tostring` / `write_bytes` sites; all are
currently legitimate, which is exactly why they belong in an allowlist:

| Site | Why it's allowed |
|---|---|
| `fmt/serializer.py:to_bytes` | the sanctioned serialiser |
| `xml/document.py:157` | internal serialise-then-reparse to bind the typed model (not output) |
| `xml/macros.py:247` | serialise to a **temp dir** for macro expansion (throwaway, not output) — see 6.1 |
| `check/checks.py:67` | serialise one element to a `str` for content inspection (read-only) |
| `codemod/_coarse_detect.py:53,55` | before/after `tostring` to detect change (internal compare) |
| `codemod/cursor.py` | serialise one element to a `str` for read-only CDATA-wrap inspection (GTR018/019, added 2026-06-03) |
| `registry/facade.py:89,175`, `registry/macro_profile.py:188` | write **fmt-produced** bytes to disk |
| `cli/cli.py` (`rename-param`, `convert-help`) | write **fmt-produced** bytes from `facade.rename_param` / `facade.convert_help` to disk (convert-help writes after `make_backup` — an ordering the facade's `write_path` cannot express) |

**Proposal:** add an architecture test (in registry or a workspace-level
`tests/`) that greps `*/src/**` for `etree.tostring(` / `.write_bytes(` and fails
on any site not in the allowlist above. Left as a proposal because it needs a
decision on where the test lives and how the allowlist is encoded.

### 4.2 Positive: the byte-identity contract IS pinned — ✅ [accepted]

`registry/tests/test_facade.py::test_iuc_preset_is_byte_identical_to_today_format`
enforces "the `iuc` preset == the historical `format` pipeline, byte for byte"
(registry decisions D4). Good — this is the highest-blast-radius contract and it
is guarded.

---

## Dimension 5 — Duplication / missed reuse

### 5.1 Two advisory-aggregation runners — **Low** [accepted]

Tier 3.5 ships `detect.detect_violations(document)` (runs every check, sorts by
line); the facade re-implements the same aggregation per-handle in
`facade._detect_advisory`. They serve different callers (`detect_violations` is
used by `scripts/corpus_check.py`; the facade path filters by the *selected*
codes), so this is parallelism, not redundant duplication. The facade can't simply
call `detect_violations` because it must honour the code selection. Recorded; no
change.

### 5.2 `Change.to_violation` vs the fmt detect projection — **Low** [accepted]

Both tier-2 `Change.to_violation()` and the fmt net-diff `detect` construct
`Violation`s, but from genuinely different inputs (a `Change`'s static fields vs a
net trivia diff). No shared logic to extract. Recorded.

---

## Dimension 6 — Dead / reserved surface

### 6.1 Tier 1 serialises XML to a temp file — refines the "writes to disk" claim — **Low** [fixed in ARCHITECTURE.md]

`xml/macros.py:expand_from_tree` does `tool_path.write_bytes(etree.tostring(root))`
into a `TemporaryDirectory` so Galaxy's path-based macro expander can run. This is
a throwaway round-trip, not user-facing output — but it means the absolute claim
*"fmt is the only tier that writes XML to disk"* (codemod `CLAUDE.md`) is loose.
The precise invariant is *"fmt is the only tier that serialises **canonical
output** XML."* **Fix applied:** `ARCHITECTURE.md` now states the precise form and
notes the temp round-trip. (Aligning the codemod `CLAUDE.md` wording is 8.1 below.)

### 6.2 `detect_tool_document` (full) has no in-`src` caller — **Low** [accepted]

The whole-pipeline `detect_tool_document` is called only from fmt's own tests; all
production detection goes through `detect_tool_document_subset` (the facade) or
`detect_macro_document` (the CLI). It is the documented public pair to
`format_tool_document` and is tested, so it stays. Recorded.

### 6.3 `MacroModule` / `parse_macro_module` are reserved — **Low** [accepted]

Defined in codemod `module.py` / `parse.py`, used nowhere in `src` outside their
own package. This is the documented "Cursor is generic; the codemod base stays
tool-only until a macro-subject codemod needs it" reservation (codemod decisions
§20). Intentional reserved surface.

### 6.4 GTR031 / GTR032 stubs — ✅ [accepted]

Registered codes whose `detect` returns nothing, members of the `strict` preset so
they are auto-covered when implemented (check decisions; `iuc_best_practices.md`).
Documented reservation, not drift.

---

## Dimension 7 — Doc / code agreement

### 7.1 "writes XML to disk" imprecision — **Low** [fixed in ARCHITECTURE.md] [proposal for CLAUDE.md]

Covered in 6.1. `ARCHITECTURE.md` is corrected. **Proposal:** soften the same
phrasing in `galaxy-tool-codemod/CLAUDE.md` and the tier table in other
`CLAUDE.md`s from "writes XML to disk" to "serialises canonical XML" — left as a
proposal because those are owned package docs and the change, while safe, touches a
deliberately-chosen contract phrasing.

### 7.2 Otherwise: doc/code agreement is strong — ✅

The per-package `CLAUDE.md`s and `decisions.md`s matched the code on every spot
check (RuleMeta fields, the `RuleHandle` shape, preset membership, selection
precedence, the CANONICAL/AUTO_UPGRADE split, GTR code assignments). The
`decisions.md` section numbers cited from `ARCHITECTURE.md` all resolve.

---

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 2.1 | fmt-family `RuleHandle.apply` defined but never called; per-rule fmt apply is a footgun | Medium | fixed (caveat comment) |
| 4.1 | "fmt is the only serializer" not guarded by a test | Medium | proposal (allowlist arch-test) |
| 2.3 | `apply` overloaded (fmt yields vs codemod mutates) | Low | proposal (rename `Rule.apply`→`edits`) |
| 3.1 | stale `_detect_violations` reference in `corpus_check.py` | Low | fixed |
| 6.1 / 7.1 | "writes XML to disk" looser than reality (tier-1 temp round-trip) | Low | fixed in ARCHITECTURE.md; CLAUDE.md align = proposal |
| 2.2, 2.3, 3.2, 5.1, 5.2, 6.2, 6.3, 6.4 | intentional asymmetries / reserved surface | Low | accepted (recorded) |

**No High-severity findings. No boundary violations.** The architecture is
coherent and the documented contracts hold. Two items merit a maintainer
decision: whether to add the serializer-allowlist test (4.1) and whether to rename
`Rule.apply` for cross-family consistency (2.3).

### Applied in this pass (safe fixes)
1. `ARCHITECTURE.md` — precise "fmt is the only tier that *serialises* canonical
   XML" wording + the tier-1 temp-round-trip note (6.1 / 7.1).
2. `galaxy-tool-refactor-registry/src/.../adapters.py` — caveat comment on
   `fmt_handle.apply` (2.1).
3. `scripts/corpus_check.py` — corrected the stale `_detect_violations` comment (3.1).

### Left for review (proposals) — all resolved 2026-06-01
- ~~Add a serializer-allowlist architecture test (4.1).~~ **DONE**
- ~~Rename `fmt.Rule.apply` → `Rule.edits` for cross-family clarity (2.3).~~ **DONE**
- ~~Align the "writes XML to disk" wording in the package `CLAUDE.md`s (7.1).~~ **DONE**

> The full disposition (incl. the escalation-new items N3/N5/N6/N8 and the
> collision-guard test) is recorded under **Net outstanding proposals** below.

---

## Escalation — multi-agent re-derivation + adversarial verification (2026-05-31)

The single pass above was escalated: **10 finder agents** (6 tier-scoped + 4
cross-cutting dimension sweeps) independently re-derived findings from source
against the `ARCHITECTURE.md` baseline, each candidate then **adversarially
verified** by an agent prompted to *refute* it, and the survivors synthesised.
**61 agents total; 50 candidate findings → 47 survived verification, 3 refuted;
0 new High, 2 new Medium, 6 new Low, 18 independent re-confirmations.**

**Headline:** escalation **validated the original audit** — every load-bearing
invariant (single-source-of-truth tree, no-serializer-in-tier-1, deterministic
profile resolution, lenient xsdata binding, collision-guarded GTR namespace,
library-first facade) was independently re-derived and re-confirmed, and most
would-be Medium/High candidates were *downgraded* to Low because the code already
honours the contracts — only test/doc coverage lags. No new boundary violations,
no new correctness hazards.

### New findings it surfaced

| # | Finding | Severity | Status |
|---|---|---|---|
| N1 | `preset_names()` returned a hardcoded literal while `presets()` is derived — adding a 4th preset would silently drop it from `list_presets`/`list_rules` (`presets.py:52`). Violated the derived-not-hardcoded contract (registry D3). | Medium | **fixed** — now `tuple(presets())` |
| N2 | Tier-2 `codemod/pyproject.toml` declared an unused `click>=8` (zero `click` imports in `src/`) — contradicts the tier-independence dependency-encoding. | Medium | **fixed** — line removed |
| N7 | `corpus_check.py::_check_detect` returned unsorted violations though its docstring says it mirrors the facade's sorted `detect`. Zero practical impact (consumer is order-independent). | Low | **fixed** — sort added |
| N3 | Tier-1 result dataclasses (`XmlError`/`ParseResult`/`ValidationResult`/`MacroError`) are mutable while tier-0.5 results are frozen. Nothing mutates them; incidental. | Low | proposal (freeze or document) |
| N5 | `check` tier has no in-package "`detect_violations` doesn't mutate" test (the facade's cross-tier test exercises the code, so the contract *is* guarded). | Low | proposal (mirror fmt's purity test) |
| N6 | The `(sourceline, code)` sort key is duplicated at `check/detect.py:63`, `facade.py:67`, `facade.py:119`. | Low | proposal (shared helper in a registry/check util, not tier 0.5) |

Plus a cluster of doc-comment refinements (N8): `upgrade_command`'s docstring is
silent that macro files aren't cosmetically formatted; codemod `CLAUDE.md` names
`MacroModule`→`MacroDocument` but not `Module`→`ToolDocument`; `applies_to`
default is relied on implicitly by the 10 codemods. All Low / doc-only.

### Corroboration that raises confidence in earlier findings
- **§4.1 (serializer not test-guarded)** was independently re-derived — escalation
  endorses the *same* allowlist-architecture-test recommendation and the baseline's
  site inventory. Treat 4.1 as the priority proposal.
- **New-adjacent:** the GTR collision guard (`registry.py:48`) exists and is
  correct, but no test forces a *duplicate* to prove it fires — a natural companion
  to the 4.1 allowlist test.
- §2.2 (unenforced `meta`), §5.1 (advisory-aggregation parallelism), §5.2, §6.1/§7.1
  (writes-to-disk imprecision, still loose in the two package `CLAUDE.md`s), §6.3,
  §7.2 (doc/code agreement, full GTR table resolves) — all independently
  re-confirmed.

### Refuted (do not re-litigate)
- "check's macro path bypasses the facade without explanation" — *necessary*
  (`facade.detect` accepts only `Source | ToolDocument`, never `MacroDocument`);
  documented in cli D5 + inline comment.
- "`_upgrade_macro_profile_tokens` does redundant file reads" — the path reload is
  *required* so macro `<import>`s resolve via `source_path` (cli D6).
- A scout's claim about `Cursor` method names in `CLAUDE.md` — its evidence was
  factually wrong; the real (minor) issue is doc incompleteness, not a missing method.

### Escalation fixes applied (QA gate re-run, PASSED)
4. `galaxy-tool-refactor-registry/src/.../presets.py` — `preset_names()` derived
   from `presets()` (N1).
5. `galaxy-tool-codemod/pyproject.toml` — dropped unused `click` (N2);
   `uv.lock` re-synced.
6. `scripts/corpus_check.py` — parity sort in `_check_detect` (N7).

### Net outstanding proposals (maintainer decision)

All resolved on 2026-06-01 (branch `chore/architecture-audit-proposals`); kept
here as a record of what was decided and where it landed.

1. ~~**Serializer-allowlist architecture test** (4.1, corroborated) — highest
   value.~~ **DONE** —
   `galaxy-tool-refactor-registry/tests/test_serializer_allowlist.py` greps every
   `*/src/**` for `etree.tostring(` / `.write_bytes(` against the allowlist of
   sanctioned sites (and a companion test that flags stale allowlist entries).
2. ~~Collision-guard "duplicate fires" test (escalation-new).~~ **DONE** —
   extracted the pure `_build_index(entries)` helper out of the `@cache`d
   `registry._index()`; `test_registry.py::test_duplicate_code_raises` feeds it a
   duplicate code and asserts `ValueError`.
3. ~~Rename `fmt.Rule.apply` → `Rule.edits` (2.3).~~ **DONE** — `fmt.Rule.edits`
   now names the describe-only surface; `apply` consistently means "mutate in
   place" across families. ABC + 3 impls + 2 fmt callers + 2 corpus-script callers
   + `ARCHITECTURE.md` §5/§10 + fmt `decisions.md`.
4. ~~Freeze tier-1 result dataclasses (N3); add `check` purity test (N5); dedup
   sort helper (N6); align `CLAUDE.md` "writes to disk" wording (7.1); doc-comment
   touch-ups (N8).~~ **DONE** — `XmlError`/`ParseResult`/`ValidationResult`/
   `MacroError` are now `frozen=True`; `check/tests/test_detect.py` pins
   `detect_violations` purity; the `(sourceline, code)` key is now the shared
   `check.detect.sort_violations` (used by both facade sites); the four active
   tier tables say "serialises canonical output XML"; `upgrade_command` docstring
   and the codemod `CLAUDE.md` `Module`/`ToolDocument` symmetry are corrected.
   (The historical `galaxy-tool-codemod/docs/architecture.md` was left as-is —
   it is explicitly marked a pre-implementation design note.)

---

## Re-audit after the profile-upgrade batch (#34–#40, 2026-06-01)

**Method:** single deep pass (3 read-only Explore agents) refreshed against the
baseline, then an **escalation** — 10 finder scouts (one per tier + one per
cross-cutting dimension) re-deriving findings, each candidate adversarially
verified, then synthesised (**69 agents total; 58 candidates → 57 survived
verification, 1 refuted; counts after dedup: 1 doc-"High", 3 Medium, 5 Low, 11
independent re-confirmations, 2 refuted**).

**Headline:** the architecture **holds**. Escalation surfaced *no new structural
defect and no boundary violation* — every load-bearing invariant the prior pass
pinned was independently re-confirmed. The only new surface is a single root cause:
the `RuntimeGatedFix` family (GTR014/GTR015) landed **after** this baseline was
written, so prose/docstring/test *enumerations* of the upgrade-only set still said
"GTR007–GTR012". The code is correct everywhere (`upgrade_only_codemods()` derives
the set dynamically), so this was a documentation-and-test-spec lag, not a
behavioural break. All of it is now fixed.

### New findings (all applied this pass unless marked proposal)

| # | Finding | Dim | Sev | Status |
|---|---|---|---|---|
| R1 | `ARCHITECTURE.md` upgrade-only enumerations omitted the runtime-gated pair (line 273 omitted GTR015; contract §4 omitted GTR014/015) — internally contradicting the doc's own rule-codes table | doc/code | High* | **fixed** |
| R2 | `ARCHITECTURE.md` tier-2 prose + reference index had no `RuntimeGatedFix` family / validity-gated-vs-runtime-gated distinction; §-cite omitted §22–24 | doc/code | Medium | **fixed** (tier-2 bullet + 2 ref-index rows + cite §11–18, §22–24) |
| R3 | CLI `upgrade` docstring silent that runtime-gated fixes auto-mutate the tool | doc/code | Medium | **fixed** (cli.py upgrade docstring) |
| R4 | `test_registry.py` hardcoded the upgrade-only set `{GTR007..GTR012}` (omitted 014/015) with permissive `isdisjoint`/subset assertions — passed despite being incomplete; violates the derive-not-hardcode contract (registry D3) | contract-enforcement | Medium | **fixed** — both the selectable and upgrade-only sets now **derive** from `CANONICAL_CODEMODS` / `coded_codemods()` / `all_handles()−known_codes()` and assert equality, plus an explicit GTR014/015 wiring guard; `by_code` now checks 014/015 too |
| R5 | Docstring/comment enumeration cluster: `registry.py` module docstring + namespace list, `facade.list_rules` docstring, registry `CLAUDE.md` "Selectable ≠ all", `cli/__init__.py` ("two commands" → it has five), `runtime_fixes.py` ordering comment | doc/code | Low | **fixed** (all sites) |
| R6 | CLI declares an unused direct dependency on `galaxy-tool-refactor-rules` (reached only transitively via the facade) | boundary | Low | **fixed** (dropped from `dependencies` + `[tool.uv.sources]`; `uv sync` re-run) |
| R7 | No CLI-level end-to-end test for a runtime-gated fix during `upgrade` (the facade + codemod layers have it; the 24.1 migration is double-covered) | contract-enforcement | Low | **proposal** (low risk — facade test covers it) |
| R8 | `_is_newer` is byte-identical in `codemods/update_profile.py` and `registry/macro_profile.py` | duplication | Low | **proposal** (cross-tier; documented as mirrored; consolidating is optional and a tier-2-internal-only move) |

\* R1 is doc-only; rated High by the synthesis because the baseline *contract
statements* a contributor reasons from contradicted the same document's table.

### Independent re-confirmations (no action — recorded so they aren't re-litigated)

The escalation re-derived these from source and confirmed them: the
serializer-allowlist test (§4.1) and the collision-guard "duplicate fires" test;
the no-profile **16.01** runtime baseline (warning correctness depends on it) and
`resolve_profile(None) → 16.01 → 16.10`; the four frozen tier-1 result dataclasses
(note: a just-shipped fix, finding N3 — not a long-standing invariant); tier-0.5
dependency-freedom; fmt cosmetic-only + the `Rule.edits` describe-vs-mutate split;
check-tier purity + the GTR031/012 reserved stubs; and that the `RuntimeGatedFix`
*design* is sound (the `introduced_profile` marker is runtime-test-enforced, not
type-checker-enforced; membership in `coded_codemods()` keeps it collision-guarded;
the facade applies `runtime_fixes_for(reached, *, baseline)` after `UpgradeToLatest`
— crossing-gated since 2026-06-02, codemod §24).

### Refuted (do not re-litigate)

- "Stale `SEMANTIC_PROFILE_CHANGES` references" — the only hit is in
  `behavior-preserving-upgrade.md`, a design note that predates implementation;
  production code uses `PROFILE_UPGRADE_CODES`.
- "`runtime_fixes.py` is a third `_is_newer` duplication" — it is an inline
  `Version(...)` comparison over *pre-validated* vendored profile strings (no
  `InvalidVersion` guard), a different concern from the guarded helper.

### Applied this pass (safe fixes)
`ARCHITECTURE.md` (R1, R2, R5-partial), `galaxy-tool-refactor-cli/.../cli.py` +
`__init__.py` (R3, R5), `galaxy-tool-refactor-registry/.../registry.py` +
`facade.py` + `CLAUDE.md` (R5), `galaxy-tool-codemod/.../runtime_fixes.py`
comment (R5), `galaxy-tool-refactor-registry/tests/test_registry.py` (R4),
`galaxy-tool-refactor-cli/pyproject.toml` + `uv.lock` (R6). QA gate re-run.
