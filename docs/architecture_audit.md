# Architectural audit — galaxy-tool-refactor

## Re-audit 2026-06-09 — post planemo-parity check wave (GTR038–GTR089, PRs #124–#144) + escalation

**Verdict — healthy; boundaries hold, the abstraction absorbed the growth without strain.**
This covers the largest tier-3.5 addition to date: the **planemo-parity advisory wave**, which
roughly tripled `galaxy-tool-xml-check` — **52 new detect-only checks (`GTR038`–`GTR089`)**
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

1. **Boundary integrity ✅** — `galaxy-tool-xml-check/pyproject.toml` declares only
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
- **`galaxy-tool-xml-check/CLAUDE.md` "Scope" — Medium [fixed].** Listed only the pre-wave
  flat advisories + `.2` partitions. Added the planemo-parity-wave paragraph, the 66-check
  total, the macro-skip note, and the `D12–D30` / `planemo_linter_parity.md` pointers; also
  folded in `GTR034` (previously omitted from the flat-advisory list).
- **`docs/iuc_best_practices.md` BUILT table — Low [fixed].** This doc is legitimately
  *IUC-practice-scoped*, so the wave doesn't belong in its table — but a reader had no signal
  the tier had grown. Added a scope note distinguishing the IUC slice from the planemo-parity
  axis and pointing at `planemo_linter_parity.md` + `D12–D30`.

**Resolved disagreement (recorded so it isn't re-litigated):** an exploration scout reported
`galaxy-tool-xml-check/docs/decisions.md` stopped at **D21/GTR068** with `GTR069`–`089`
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
  `galaxy-tool-xml-codemod/pyproject.toml` declared only `rules` / `xml` / `lxml` —
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
  — Low. [resolved 2026-06-03].** Consolidated into `galaxy_tool_xml_codemod/
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
  (The single `galaxy_tool_xml_codemod` hit inside fmt is a docstring in
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
`from galaxy_tool_xml_check.detect import detect_violations as _detect_advisory`
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
| `cli/cli.py` (`rename-param`) | write **fmt-produced** bytes from `facade.rename_param` to disk |

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
phrasing in `galaxy-tool-xml-codemod/CLAUDE.md` and the tier table in other
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
5. `galaxy-tool-xml-codemod/pyproject.toml` — dropped unused `click` (N2);
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
   (The historical `galaxy-tool-xml-codemod/docs/architecture.md` was left as-is —
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
`facade.py` + `CLAUDE.md` (R5), `galaxy-tool-xml-codemod/.../runtime_fixes.py`
comment (R5), `galaxy-tool-refactor-registry/tests/test_registry.py` (R4),
`galaxy-tool-refactor-cli/pyproject.toml` + `uv.lock` (R6). QA gate re-run.
