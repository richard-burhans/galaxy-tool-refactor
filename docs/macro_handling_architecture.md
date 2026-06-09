# Macro handling across the tiers — research & planning

**Status:** research / planning (exploratory — *document & recommend*, commits to nothing
yet). **Date:** 2026-06-02. **Baseline:** multi-agent adversarial macro-handling audit (run
`wf_7caf3d25-e02`, 58 agents) — 0 high / 3 medium defects, 11 accepted-intentional, 12 refuted.

> **Why this doc.** The upgrade-soundness adversarial review found that our `consider`-code
> detectors read the **raw** tool tree while Galaxy's advisor runs **post-macro-expansion**,
> over-flagging tools whose construct comes only from a macro. That is one *symptom* of a
> broader question the maintainer raised: **macros — even when defined in separate imported
> files — should be expanded and (where appropriate) modified consistently along with the
> tool XML.** This doc establishes the current-state baseline, the inconsistencies a
> macro-handling audit confirmed, and the design options + a recommended phased direction.
> It re-sequences the adversarial-review remediation (the macro-expansion measure / detector
> port) under whatever it recommends.

---

## 1. Current-state baseline (verified)

Galaxy tool macros come in two physical forms — **inline** (`<macros><xml>/<token>/<macro>`
inside the tool, used via `<expand>`) and **imported** (`<macros><import>file.xml</import>`,
the definitions living in a separate `<macros>` file). The Galaxy XSD is a
*post-macro-expansion* schema, so a tool is only schema-valid after expansion.

### 1.1 The load-bearing fact: expansion is lossy

`galaxy-tool-xml/src/galaxy_tool_xml/macros.py` exposes the expander
(`expand_from_path` / `expand_from_tree`, wrapping Galaxy's
`xml_macros.load_with_references`). It returns a **throwaway** expanded `ElementTree` with
**no provenance** — no map from an expanded node back to the file (inline tool vs which
imported file) it came from. It is consumed only by `binding.py`'s `validate_tool` /
`newest_valid_profile` and then discarded; `ToolDocument.tree` is never mutated. There is no
publicly-exposed, reusable "expanded view."

Everything below follows from that: read/transform passes that need to *write back* cannot
use the expanded tree, so they run on the **raw** tree and reach only literally-present nodes.

### 1.2 Per-tier macro surface (raw vs expanded · inline vs imported · read vs write)

| Tier | Surface | Tree | Inline | Imported | R/W |
|---|---|---|---|---|---|
| 1 | `macros.expand_from_path/_tree` (validation only) | **expanded** | ✓ | ✓ | read (new tree, discarded) |
| 1 | `macros.imported_macro_paths` / `token_definitions` | raw | ✓ | ✓ | read |
| 1 | `binding.validate_tool` / `newest_valid_profile` | **expanded** | ✓ | ✓ | read |
| 1 | `MacroDocument` (`load_macros`) | raw | — | ✓ (a macro file) | read/write (mutable, no profile/model) |
| 2 | `CodemodCommand.detect/apply` | raw | ✓ | ✓ | read/write (literally-present nodes only) |
| 2 | `profile_semantics.tripped_upgrade_codes` (`_DETECTORS`) | **expanded** (PR4; raw fallback) | ✓ | ✓ | read |
| 2 | `update_profile._upgrade_inline_profile_token` | raw | **inline only** | skipped | write (tool's own `<macros>`) |
| 3 | fmt `format_macro_document` | raw | ✓ | ✓ (standalone) | read/write (cosmetic only) |
| 3.6 | `macro_profile.apply_profile_token_plans` | raw | — | **imported only** | **write to disk** (the one write-back path) |
| 4 | CLI `format`/`upgrade`/`check` | raw | ✓ | ✓ (standalone / consensus pass) | orchestration |

### 1.3 Two observations that drive the design question

- **The `@PROFILE@` token bump is split in two:** an *inline* token is rewritten in tier-2
  (`update_profile`), an *imported* token in tier-3.6 (`macro_profile`), orchestrated
  separately by the CLI (a whole-run imported pass, then per-file tool upgrades).
- **Write-back to an imported file exists exactly once** (`macro_profile`), and it works by
  locating the token *by name* in the source file (via tier-1 `token_definitions`), editing
  in place only when all importers agree, never via the expanded tree. There is no general
  mechanism to take *any* expanded-tree finding/edit back to its defining file.

### 1.4 Design constraint: carry the whole import *bundle* (a tool can import many files)

A tool may `<import>` **multiple** macro files, and each imported file may itself `<import>`
others — so the set of source files behind one tool is a transitively-resolved **bundle**,
not a single sidecar. Any consistent expand-and-modify model must:

1. **carry all of them along** — load, and where edited, write back *every* file in the
   bundle, not just the tool and not just one macro file; and
2. **route each change to the correct file** — a finding on an expanded node must know which
   bundle member (the inline tool, or *which* imported file) defines it.

The enumeration half already exists and is sound: tier-1 `macros.imported_macro_paths`
returns the **full transitive, de-duplicated** list of existing imported files (resolving
each file's own imports against its own directory, skipping `..`/absolute/missing). The
missing half is **per-node provenance** — `token_definitions` carries a `source` path per
*token*, but expansion in general discards which bundle member produced which node. This
constraint is the crux of the design options in §6.

---

## 2. Corpus reality (reproducible standing measures)

All figures regenerate via `scripts/measure.py`; do not hand-edit.

- `macro-topology` (`docs/macro_corpus_stats.md`): **9,358** unique tools — 45.2% no macros,
  6.9% inline-only, **47.8% import a macro file**; `<expand>` 48.4%; `<yield>` 32.6% (named
  `<yield>` 0.5%, `<macro>` definitions 1.4% — both rare → v1 must *preserve* faithfully).
  Distinct imported files 3,368; shared (≥2 importers) **203**; max importers 137. Tools
  importing ≥1 *shared* file **1,545 (16.5%)**; tools with **no shared macro 7,813 (83.5%)**.
  Inverse (imports *per tool*): of the **4,476** tools importing ≥1 file, **96.2% pull in
  exactly one**, **3.8% (171) import ≥2**, and **3 (0.1%) have nested `<import>`s**; max
  bundle 43 files (the §7 bundle-sizing input).
- `macro-profile-ownership` (`docs/macro_profile_ownership_stats.md`): profile tokens live
  102 inline / ~1,382 directly-imported / **0 deeper** in the chain; of shared
  profile-defining files, **46 agree on one target, 0 diverge** → in-place edit is safe
  today and fork machinery has no consumer. Imports: **0** use `..` or absolute paths.

**Implication:** the favourable corpus (no deeper chains, no divergent importers, no unsafe
paths, 83.5% unshared) means a consistent macro model can start simple — most complexity the
design *could* handle does not yet occur in practice.

---

## 3. The core limitation, restated

Because expansion is lossy + provenance-free, the project has a **single-file model** for
*editing*: codemods mutate the raw tool tree and reach macro-defined content only through
narrow, purpose-built side channels (`token_definitions` for the profile token). Read-only
**detection** escapes this — it runs on a throwaway expanded view (PR4, no provenance
needed; §1.2). This is *coherent* and was a deliberate v1 choice — but the editing model
still blocks any future codemod that must *rewrite* macro-expanded content (interpreter in
a `<token>`, `format`/`ftype` in an imported `<macro>`, etc.).

---

## 4. Confirmed inconsistencies & gaps

From a multi-agent adversarial audit (8 scouts → 49 candidates → 37 survived verification →
deduped to ~10 distinct issues; **0 high, 3 medium defects**, the rest accepted-intentional
or polish). Severities are the *corrected* post-verification values.

### 4.1 [MEDIUM · doc-code] `upgrade`'s docstring contradicts what it does to a macro file
3 scouts converged. `cli.py:231-234` says *"that token bump is the only edit an imported
macro file receives … `upgrade` does not cosmetically reformat macro files."* But
`macro_profile.apply_profile_token_plans` (`macro_profile.py:175-177`) does
`token.text = …` then `macro_file.write_bytes(format_macro_document(document))` — which runs
the cosmetic rules (GTR001/GTR004) over the **whole** file. So the file *is* reformatted;
the bump is *not* the only edit. The behaviour is intentional and safe (fmt is the only
serializer; macro cosmetic formatting is idempotent) and the **registry** tier documents it
correctly (registry D5); only the **CLI** docstring + `cli/docs/decisions.md` D5/D6 assert
the opposite. **Fix: doc-only** (correct the CLI docstring + D5/D6; optionally assert the
written file is canonical in `test_upgrade_bumps_shared_imported_profile_token`).
**Resolved (2026-06-02):** the CLI docstring (`cli.py` ~220-245) now states the macro file
*is* reserialised through `format_macro_document` when the token is bumped.

### 4.2 [MEDIUM · write-back/provenance] Lossy expansion → no general macro write-back
4 scouts; the architectural root cause (§1.1, §3). `macros.expand_from_path/_tree`
(`macros.py:222-256`) return a throwaway tree with **no element→source mapping**, used only
for validation. So write-back exists in exactly one place and only because `@PROFILE@` is a
*named* construct addressable by token-name; **no** mechanism maps any other expanded node
(e.g. a `<format>` in an imported `<macro>`, or a typo'd `<xml name>`) back to its defining
file. Documented + deferred (`galaxy-tool-xml-codemod/PLAN.md`, `macro-aware-normalization.md`
Option A) — listed as a *gap* (not just a choice) because it is the load-bearing limitation the
"consistent expand-and-modify across inline + imported" goal must close (§6). Corpus payoff
today ~18 tools → deferral is reasonable. **Sub-item:** that write-back is token-name-specific
(not general) should be recorded as an explicit asymmetry in `ARCHITECTURE.md §10`.
**Resolved (2026-06-02):** recorded as an explicit asymmetry in `ARCHITECTURE.md §10`
("Macro write-back is token-name-specific, not general provenance"). The broader provenance
gap stays deferred.

### 4.3 [MEDIUM · provisional] Per-file transform loads from bytes, dropping `source_path`
1 scout, concrete contrast. `cli_support._transform_file` (`cli_support.py` ~:182) calls
`load_tool(bytes)` → `source_path = None`, even with the filesystem `path` in scope — whereas
the upgrade macro phase deliberately loads *from path* "so imports resolve." For any per-file
`format`/`upgrade` transform that needs imports resolved (macro expansion, future macro-aware
codemods) this silently loses import resolution. **Provisional** (borders code-review):
**verify** whether any per-file transform actually needs imports resolved; if so, pass `path`
to `load_tool`. The only survivor in the write-back cluster flagged *not* intentional.
**Resolved (2026-06-02) — confirmed a live bug, fixed.** Verified directly: the app CLI's
`upgrade`/`format` on an imported-macro tool demoted it to the raw (un-expanded) tree —
`<expand>` nodes made it XSD-invalid → `newest_valid_profile` returned `None` (nothing to
upgrade) and every validity/detection call logged "macro expansion failed". Fixed by loading
the per-file document from `path` (so `source_path` is set) in
`cli_support._transform_file` (fmt `docs/decisions.md` D17; regression test
`test_upgrade_resolves_imported_macros`).

## 5. Accepted / intentional design choices (recorded — do NOT relitigate)

All verified real and documented as deliberate v1 scope (corrected severity: low). The single
recurring theme is the **single-file (raw-tree) model**, rediscovered from many angles:

1. **Detection runs on the raw tree** (6+ scouts) — *resolved 2026-06-02 (PR4)*:
   `tripped_upgrade_codes` now detects on the macro-**expanded** tree
   (`expanded_detection_root`, raw fallback), mirroring Galaxy's post-expansion advisor,
   so the §25 over-flag/under-report gap is closed for the live warning. Codemods remain
   raw-tree (they write back and need the deferred provenance layer). Codemod §25.
2. **Split token paths** — inline `@PROFILE@` (tier-2 `update_profile`) vs imported (tier-3.6
   `macro_profile`, on importer consensus). Load-bearing & correct; both target the same
   `newest_valid_profile`, so divergence is structurally impossible.
3. `MacroModule`/`parse_macro_module` shipped without a consumer (defer-until-consumer, §20).
4. Codemods carry no `applies_to` (tool-only via type signature, not a ClassVar).
5. `RuleHandle` adapters tool-only; macros handled outside the registry (cosmetic-only v1).
6. Rule selection (`--select`/`--ignore`/`--ruleset`) doesn't apply to macro files.
7. `format`'s macro formatting is bundle-unaware (import-graph deferred to its consumer).
8. Detector fidelity: 3 Galaxy transcription bugs deliberately not mirrored; 2 codes
   approximated — all documented (`profile_semantics` docstring, §25).
9. Single-snapshot importer agreement (no re-validation after bump) — 0/46 divergent, idempotent.
10. Macro-phase-before-per-file ordering correct but only test/doc-enforced.
11. `codemod.py` comment vs §20 cover different aspects (aligned, not contradictory).

**Minor polish** (cheap, optional): note that `Cursor.set_text` is CDATA-unsafe (no guard,
vs fmt's `safe_set_text`) so a future caller doesn't misuse it on CDATA content (ties to the
CDATA contract, PR #52); reword its "token-aware" docstring; reciprocal cross-refs between
`update_profile.py` ↔ `macro_profile.py`; a belt-and-suspenders fixture proving inline &
imported `@PROFILE@` reach the same target.

## 6. Design options & recommendation

The maintainer's goal reduces to one question: **leave the single-file model, or replace it?**

- **(i) Provenance layer (the consistent expand-and-modify model).** `expand_*` returns a
  side-table mapping each expanded node → `(source_file, line, defining <macro>/<import>)`.
  Only this lets a codemod that detects an issue in *expanded* content decide "edit the macro
  source, not the tool," lets detection run post-expansion while attributing findings to the
  right file, and generalises write-back beyond `@PROFILE@`. Satisfies the **§1.4 bundle
  constraint** (the side-table spans all transitively-imported files). *Medium-lift,
  invasive* — cross-file blast radius on shared libraries (the exact hazard the
  consensus/shared-skip machinery already manages); corpus payoff ~18 tools today.
- **(ii) Read-only detection (chosen; PR2 + PR4 shipped).** Keep the raw-tree model for
  *write-back*, but run read-only **detection** on the macro-expanded view (no provenance
  needed). PR2 sized the gap (`macro-expansion-detection-gap`); PR4 ported
  `tripped_upgrade_codes` to `expanded_detection_root` (raw fallback). Sound, low-risk.
- **(iii) Status quo + a written contract.** Just document the single-file boundary crisply.

**Recommended posture (from the audit):**
- **(a)** Fix the two cheap real defects now — §4.1 (CLI docstring) and §4.3 (path-load, after
  verifying); record §4.2's token-name-specific write-back asymmetry in `ARCHITECTURE.md §10`.
- **(b)** Until a concrete consumer exists, **stay with read-only detection** (option ii):
  PR2's standing measure + PR4's expanded-aware detection (with raw fallback) have shipped
  and need *no* provenance layer.
- **(c)** Treat the **provenance layer (option i)** as a single, well-scoped **Phase-2 epic**,
  gated on a concrete consumer (the first imported-macro *structural* codemod, or
  post-expansion detection parity), built alongside the shared-file consensus/skip machinery
  and the §1.4 bundle model.
  - **Phase 2a shipped (2026-06-03):** the first consumer — imported-macro `format`/`ftype`
    normalization — landed *without* the provenance layer, by recognising the edit is a
    validity-safe canonicalization addressable by *locating the literal in its source file*
    (the `macro_profile` write-back shape), not by post-expansion attribution. It is the
    opt-in `normalize-macros` command over `galaxy_tool_refactor_registry.macro_datatype`
    (registry `docs/decisions.md` D8; `macro-aware-normalization.md`); 15 corpus tools
    (`docs/macro_format_residual_stats.md`). So general write-back is no longer *only*
    `@PROFILE@`: a second locate-in-source consumer now exists.
  - **Phase 2b (the general provenance layer) stays deferred — now data-backed (2026-06-03).**
    A sizing measure (`scripts/measure.py macro-token-datatype-residual`,
    `docs/macro_token_residual_stats.md`) found **0** tools where normalizing a
    *token-supplied* datatype value unsticks a profile beyond what 2a's literal
    normalization already achieves — so the token half of 2b has **zero** payoff, and
    there is no structural-only datatype residual either. 2a is therefore the *complete*
    datatype solution. The heavyweight expansion-provenance layer (M1) is unjustified for
    datatypes; its only future trigger is a *structural* codemod that must rewrite a
    macro-supplied element (none exists). Re-open M1 only then — design recorded in
    `~/.claude/plans/macro-provenance-2b-design.md`.
- **(d)** Keep the §5 polish items as low-priority maintainability tickets.

## 7. Open questions / deferred

- **Sizing gap (multi-file bundles, §1.4) — RESOLVED (2026-06-03).** `macro-topology` now
  also emits the inverse of the importer distribution: a **per-tool bundle-size histogram**
  with a transitive-vs-direct split (transitive via tier-1 `imported_macro_paths`). Of the
  **4,476** tools that import ≥1 macro file, **96.2% (4,305) pull in exactly one file**, only
  **171 (3.8%) import ≥2**, and just **3 (0.1%) have nested `<import>`s** (transitive bundle
  larger than direct); max bundle is 43 files. So the multi-file population a bundle model
  must handle is tiny — the consistent expand-and-modify model can start from the
  single-sidecar case. `Reproduced-by: scripts/measure.py macro-topology`
  (`docs/macro_corpus_stats.md`, "Imports per tool").
- Fork-on-divergence for shared macro files (no consumer today: 0/46 diverge).
- `<yield>` resolution / parameterised macros (32.6% of tools — preserve, defer editing).
- Macro-library normalisation (`format`/`ftype` in imported macros) — **shipped
  2026-06-03 (Phase 2a)** as the opt-in `normalize-macros` command; see
  `galaxy-tool-xml-codemod/docs/macro-aware-normalization.md` and registry
  `docs/decisions.md` D8. (Token-supplied values await Phase 2b.)
