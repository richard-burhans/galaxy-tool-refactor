# Architectural audit — galaxy-tool-refactor

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
- **Per-codemod *unit* idempotence tests** for GTX002/005/013: the corpus sweep already enforces
  idempotence; unit tests would be redundant belt-and-suspenders.

---

## Re-audit 2026-06-03 (single deep pass + multi-agent escalation)

**Verdict — the architecture is healthy; the boundaries still hold exactly as
documented.** Since the 2026-05-31 pass a session of 9 merged PRs landed a whole
new tier-4 package (`galaxy-tool-refactor-mcp`), the IUC011 command-text check + a
read-only `command_text.py` lexer, the `UpgradeResult.behavior_preserving` verdict,
a `set_e` detector tightening, runtime-gated GTX016, and a `cli_support`
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
  Phase 1: IUC011 was still called a "reserved stub" (it ships as
  `SingleQuotedCheetah`); the `command_text.py` lexer was unmentioned in tier 3.5;
  `behavior_preserving` was missing from the tier-3.6 result shape; §9 listed
  runtime-gated GTX `014–015` though GTX016 is also runtime-gated. The
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

- IUC012 `CommandAndJoining` no-op stub — data-backed (~1 tool corpus-wide; check
  D3). The `command-iuc-heuristics` / `command-lone-amp` / `command-unquoted-var` /
  `iuc011-fixability` measures back the IUC011-ships / IUC012-deferred split.
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
- **check `README.md` said IUC011 is "not yet implemented" and omitted the
  `command_text.py` lexer — Medium.** Stale since IUC011 shipped (#66); `decisions.md`
  D5 + `ARCHITECTURE.md` were correct, the package README was not. Corrected.
- **`registry.py` module docstring enumerated "GTX014–GTX015 runtime-gated" — Medium.**
  Omitted GTX016 (and GTX017 from the canonical list). Corrected to 014–016 / +017.
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
sibling-tier cross-imports, no upward dependencies, the GTX/IUC namespace is
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

The bypass is *correct and intentional*: fmt rules are order-sensitive (GTX001 and
GTX003 both rewrite top-level-child tails), so running them one-at-a-time via the
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
| `codemod/cursor.py` | serialise one element to a `str` for read-only CDATA-wrap inspection (GTX018/019, added 2026-06-03) |
| `registry/facade.py:89,175`, `registry/macro_profile.py:188` | write **fmt-produced** bytes to disk |

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

### 6.4 IUC011 / IUC012 stubs — ✅ [accepted]

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
precedence, the CANONICAL/AUTO_UPGRADE split, GTX/IUC code assignments). The
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
profile resolution, lenient xsdata binding, collision-guarded GTX/IUC namespace,
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
- **New-adjacent:** the GTX/IUC collision guard (`registry.py:48`) exists and is
  correct, but no test forces a *duplicate* to prove it fires — a natural companion
  to the 4.1 allowlist test.
- §2.2 (unenforced `meta`), §5.1 (advisory-aggregation parallelism), §5.2, §6.1/§7.1
  (writes-to-disk imprecision, still loose in the two package `CLAUDE.md`s), §6.3,
  §7.2 (doc/code agreement, full GTX/IUC table resolves) — all independently
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
the `RuntimeGatedFix` family (GTX014/GTX015) landed **after** this baseline was
written, so prose/docstring/test *enumerations* of the upgrade-only set still said
"GTX007–GTX012". The code is correct everywhere (`upgrade_only_codemods()` derives
the set dynamically), so this was a documentation-and-test-spec lag, not a
behavioural break. All of it is now fixed.

### New findings (all applied this pass unless marked proposal)

| # | Finding | Dim | Sev | Status |
|---|---|---|---|---|
| R1 | `ARCHITECTURE.md` upgrade-only enumerations omitted the runtime-gated pair (line 273 omitted GTX015; contract §4 omitted GTX014/015) — internally contradicting the doc's own rule-codes table | doc/code | High* | **fixed** |
| R2 | `ARCHITECTURE.md` tier-2 prose + reference index had no `RuntimeGatedFix` family / validity-gated-vs-runtime-gated distinction; §-cite omitted §22–24 | doc/code | Medium | **fixed** (tier-2 bullet + 2 ref-index rows + cite §11–18, §22–24) |
| R3 | CLI `upgrade` docstring silent that runtime-gated fixes auto-mutate the tool | doc/code | Medium | **fixed** (cli.py upgrade docstring) |
| R4 | `test_registry.py` hardcoded the upgrade-only set `{GTX007..GTX012}` (omitted 014/015) with permissive `isdisjoint`/subset assertions — passed despite being incomplete; violates the derive-not-hardcode contract (registry D3) | contract-enforcement | Medium | **fixed** — both the selectable and upgrade-only sets now **derive** from `CANONICAL_CODEMODS` / `coded_codemods()` / `all_handles()−known_codes()` and assert equality, plus an explicit GTX014/015 wiring guard; `by_code` now checks 014/015 too |
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
check-tier purity + the IUC011/012 reserved stubs; and that the `RuntimeGatedFix`
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
