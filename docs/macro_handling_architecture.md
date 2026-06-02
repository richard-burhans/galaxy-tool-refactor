# Macro handling across the tiers — research & planning

**Status:** research / planning (exploratory — *document & recommend*, commits to nothing
yet). **Date:** 2026-06-02.

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
| 2 | `profile_semantics.tripped_upgrade_codes` (`_DETECTORS`) | **raw** | ✓ | ✓ | read |
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
- `macro-profile-ownership` (`docs/macro_profile_ownership_stats.md`): profile tokens live
  102 inline / ~1,382 directly-imported / **0 deeper** in the chain; of shared
  profile-defining files, **46 agree on one target, 0 diverge** → in-place edit is safe
  today and fork machinery has no consumer. Imports: **0** use `..` or absolute paths.

**Implication:** the favourable corpus (no deeper chains, no divergent importers, no unsafe
paths, 83.5% unshared) means a consistent macro model can start simple — most complexity the
design *could* handle does not yet occur in practice.

---

## 3. The core limitation, restated

Because expansion is lossy + provenance-free, the project has a **single-file model**:
detect and edit the raw tool tree; reach macro-defined content only through narrow,
purpose-built side channels (`token_definitions` for the profile token). This is *coherent*
and was a deliberate v1 choice — but it is exactly what produces the §25 detection gap and
blocks any future codemod that must reason about macro-expanded content (interpreter in a
`<token>`, `format`/`ftype` in an imported `<macro>`, etc.).

---

## 4. Confirmed inconsistencies & gaps

*(Filled from the macro-handling architecture audit — adversarially verified, cited.
Pending audit completion.)*

## 5. Accepted / intentional design choices (recorded, not relitigated)

*(Filled from the audit — the deliberate v1 limitations to preserve.)*

## 6. Design options & recommendation

*(Filled after the audit. Spectrum: (i) provenance-tracking expanded view enabling
detect+codemod+write-back across inline & imported files; (ii) read-only expanded detection
only — the measure→port path; (iii) status quo + a written contract. Trade-offs + a
recommended phased roadmap, and how the adversarial-review remediation re-sequences under it.)*

## 7. Open questions / deferred

- **Sizing gap (multi-file bundles, §1.4):** there is **no standing measure** for the
  *per-tool* import-count distribution (how many macro files a tool pulls in, transitively).
  `macro-topology` counts imports *per file* (importers per macro file) but not the inverse.
  Recommend extending `macro-topology` with a `imports-per-tool` histogram (and a transitive
  vs direct split) before committing to a bundle model, so the multi-file population is
  reproducibly sized.
- Fork-on-divergence for shared macro files (no consumer today: 0/46 diverge).
- `<yield>` resolution / parameterised macros (32.6% of tools — preserve, defer editing).
- Macro-library normalisation (`format`/`ftype` in imported macros) — see
  `galaxy-tool-xml-codemod/docs/macro-aware-normalization.md` (current stance: report,
  don't auto-fix).
