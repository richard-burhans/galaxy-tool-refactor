# Capabilities — what is real today

> **TL;DR.** This page is the project's honesty backbone. Every capability is tagged
> **✅ Shipped**, **🟡 Partial** (works within a stated boundary), or **🔭 Roadmap**
> (not built yet). Each row cites the artifact that proves it. Every other page in
> this guide draws from here — so nothing elsewhere claims more than this table
> allows. Regenerate with the `repo-explainer` skill.

Sources are introspected, not recalled: rule/preset rows come from
`galaxy-tool-refactor rules` / `presets`; command rows from the CLI/MCP surface;
corpus numbers from the committed `docs/*_stats.md` artifacts.

## At a glance

Galaxy tool definitions are XML. This project **reads, validates, fixes, and upgrades
that XML** through one rule set, reachable three ways — as a Python **library**, a
**command line**, and an **MCP server** for agents.

## The capability matrix

### Parse & validate

| Capability | Tier | Status | Source |
|---|---|---|---|
| Parse tool XML preserving CDATA / comments / attribute order | `galaxy-tool-xml` | ✅ Shipped | `load_tool`/`parse_tool` |
| Profile-aware validation against the per-release Galaxy XSD | `galaxy-tool-xml` | ✅ Shipped | `validate_tool`, ~28 vendored XSDs |
| Find a tool's newest valid profile | `galaxy-tool-xml` | ✅ Shipped | `newest_valid_profile` |
| Near-miss typo suggestions | `galaxy-tool-xml` | ✅ Shipped | `corrections.py` |

### Fix (structural codemods + cosmetic formatting)

| Capability | Code | Status | Source |
|---|---|---|---|
| Canonical indentation / blank-line / empty-element formatting | GTR001, GTR003, GTR004 | ✅ Shipped | `cosmetic` preset |
| Reorder `<param>` / root `<tool>` attributes to IUC convention | GTR002, GTR005 | ✅ Shipped | `iuc` preset |
| Reorder `<tool>` child elements to IUC convention | GTR013 | ✅ Shipped | `iuc` preset |
| Repair near-miss typos so an invalid tool validates | GTR006 | ✅ Shipped | `iuc` preset |
| Normalize Python-style booleans (`True`→`true`) to `xs:boolean` | GTR017 | ✅ Shipped | `iuc` preset |
| Wrap pure-text `<command>` / `<help>` in CDATA | GTR018, GTR019 | ✅ Shipped | `iuc` preset |
| Single-quote the *provably*-single-valued Cheetah `$var`s in `<command>` | GTR020 | ✅ Shipped | `iuc` preset |

### Upgrade (profile bump + repair, opt-in & semantic)

| Capability | Code | Status | Source |
|---|---|---|---|
| Upgrade a tool to the newest profile it can structurally reach | — | 🟡 Partial | `upgrade` command |
| Bump an inline `@PROFILE@` macro token | GTR007 | ✅ Shipped | upgrade rule set |
| Bump an *imported* `@PROFILE@` token (only on importer consensus) | — | 🟡 Partial | `macro_profile` (registry) |
| Runtime-gated repairs (`format_source` guard, `format="input"`, `interpreter=`) | GTR014, GTR015, GTR016 | 🟡 Partial | upgrade rule set |
| Normalize literal `format`/`ftype` in *imported* macro files (opt-in `normalize-macros`) | — | ✅ Shipped | `macro_datatype` (registry); 15 tools unstuck (`docs/macro_format_residual_stats.md`) |

> 🟡 **The soundness boundary (read `soundness.md`).** `upgrade` guarantees the result
> is **structurally valid** at the new profile — it does **not** guarantee behaviour is
> preserved in general. Behaviour-affecting changes are only applied where per-tool
> detection proves them safe; otherwise they are reported, not made (`upgrade` surfaces a
> `behavior_preserving` flag — `true`/`false`/`null` — so callers can gate on it). GTR016 (interpreter)
> auto-fixes only the clean "bucket A" shape; GTR015 only the single top-level data input.
> Imported-macro write-back now covers the `@PROFILE@` token (by name, on importer
> consensus) **and** literal `format`/`ftype` normalization (the opt-in `normalize-macros`);
> both work by *locating the construct in its source file*. General provenance-based
> write-back of *arbitrary* macro-supplied content stays deferred (Phase 2b — sizing found
> **0** additional tools, so it is unjustified for datatypes today).

### Check (report-only advisory)

| Capability | Codes | Status | Source |
|---|---|---|---|
| IUC best-practice checks (tests, CDATA, id charset, version, requirements, error handling, EDAM, help, description, version pinning) | GTR021–GTR019.2, GTR033 | ✅ Shipped | `strict` preset |
| Unquoted Cheetah `$var` in `<command>` — reports every occurrence; the *provable* subset is auto-fixed by GTR020, the residual stays advisory | GTR020.2 | ✅ Shipped | advisory; provable subset fixed (GTR020) |
| Input `<param>` never referenced anywhere the tool uses it | GTR034 | ✅ Shipped | `strict` preset; 189/467 tools (`docs/corpus_check_stats.md`) |
| Lone-`&` vs `&&` join | GTR032 | 🔭 Roadmap | registry labels it "not yet implemented" |

### Inspect & refactor parameters (queries, not rules)

| Capability | Status | Source |
|---|---|---|
| Find every Cheetah `$param` reference across a tool **and its imported macro files** | ✅ Shipped | `find-references` (`galaxy_tool_xml.cheetah_refs` + the tool bundle) |
| Rename a parameter across the definition, every reference, by-name cross-ref attributes, and `<tests>` mirrors — **across a tool and its imported macro files**, atomically (rewrite all or skip with a reason) | ✅ Shipped | `rename-param`; 93.1% of definitions rename cleanly, and 1.5% reach into an imported macro the old single-file path silently left dangling (`galaxy_tool_xml.cheetah_rename` + `bundle`; `docs/rename_macro_spread_stats.md`) |
| Gate a cross-file rename that touches a macro **shared** by other tools (edit only when sole-owned within `--repo-root`, else skip + report) | ✅ Shipped | `rename-param --repo-root` (`galaxy_tool_refactor_registry.bundle_rename`) |
| Minimal-diff offset rename for editors (LSP `WorkspaceEdit`) | 🟡 Partial | `rename_param_plan` (Tier-B API) shipped — 96.8% parity, 0 mismatches; editor binding is a draft PR (see Roadmap) |

### Surfaces & orchestration

| Capability | Status | Source |
|---|---|---|
| Code-addressable rule registry + presets (`cosmetic`/`iuc`/`strict`) + `--select`/`--ignore` | ✅ Shipped | `galaxy-tool-refactor-registry` |
| CLI: `format` / `upgrade` / `check` / `find-references` / `rename-param` / `presets` / `rules` / `normalize-macros` | ✅ Shipped | `galaxy-tool-refactor` |
| MCP server for agents: `format_tool` / `upgrade_tool` / `check_tool` / `list_presets` / `list_rules` | ✅ Shipped | `galaxy-tool-refactor-mcp` (vision Goal 1) |
| Corpus evidence base: 9,358 unique tools, standing measurements | ✅ Shipped | `docs/*_stats.md`, `scripts/measure.py` |

## Roadmap (🔭 — not built; never stated elsewhere as present tense)

- **Automated background system** that walks a tool repo and opens fix PRs in batches.
- **Streamlining / partial automation of IUC PR review** — the per-tool engine exists
  today (`check`/`format`/`upgrade`); the *review-workflow integration* does not.
- **Agent-authored rules** — agents contributing new codemods/checks (MCP vision Goal 2).
- **Editor "Rename Symbol" via `galaxy-language-server`** — the foundational Tier-B offset
  API (`rename_param_plan`) shipped; the galaxyls binding is an open *draft* PR
  (galaxyproject/galaxy-language-server#331), gated on publishing `galaxy-tool-xml` to PyPI.
- **General macro-expansion provenance** — a side-table mapping each expanded node to its
  source file, to edit *arbitrary* macro-supplied content. The literal-`format`/`ftype`
  slice (Phase 2a) shipped via locate-in-source (`normalize-macros`); the general layer is
  gated/deferred — sizing found **0** additional tools (`docs/macro_handling_architecture.md`).
- **Ecosystem integrations** (editor/LSP quick-fixes, planemo/CI backend, catalog-scale
  health) — see the Potential/Roadmap tiers in `leverage.md`.

<details>
<summary>Why some rows are 🟡 Partial, in one line each</summary>

- **upgrade**: structural validity is sound; behaviour preservation is bounded to the
  provable cases (`soundness.md`).
- **imported `@PROFILE@`**: edited in place only when all importers agree the target;
  disagreement is reported, not forced.
- **GTR014/015/016**: deliberately conservative — they fix the shapes a static codemod
  can prove safe and leave the rest to detect/warn.
- **GTR020.2**: ~73% of tools carry an unquoted shell-line `$var`, but only a minority are
  provably safe to auto-quote, so it stays advisory (measure-backed, not a fixer).
</details>
