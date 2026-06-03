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
| Canonical indentation / blank-line / empty-element formatting | GTX001, GTX003, GTX004 | ✅ Shipped | `cosmetic` preset |
| Reorder `<param>` / root `<tool>` attributes to IUC convention | GTX002, GTX005 | ✅ Shipped | `iuc` preset |
| Reorder `<tool>` child elements to IUC convention | GTX013 | ✅ Shipped | `iuc` preset |
| Repair near-miss typos so an invalid tool validates | GTX006 | ✅ Shipped | `iuc` preset |
| Normalize Python-style booleans (`True`→`true`) to `xs:boolean` | GTX017 | ✅ Shipped | `iuc` preset |
| Wrap pure-text `<command>` / `<help>` in CDATA | GTX018, GTX019 | ✅ Shipped | `iuc` preset |

### Upgrade (profile bump + repair, opt-in & semantic)

| Capability | Code | Status | Source |
|---|---|---|---|
| Upgrade a tool to the newest profile it can structurally reach | — | 🟡 Partial | `upgrade` command |
| Bump an inline `@PROFILE@` macro token | GTX007 | ✅ Shipped | upgrade rule set |
| Bump an *imported* `@PROFILE@` token (only on importer consensus) | — | 🟡 Partial | `macro_profile` (registry) |
| Runtime-gated repairs (`format_source` guard, `format="input"`, `interpreter=`) | GTX014, GTX015, GTX016 | 🟡 Partial | upgrade rule set |

> 🟡 **The soundness boundary (read `soundness.md`).** `upgrade` guarantees the result
> is **structurally valid** at the new profile — it does **not** guarantee behaviour is
> preserved in general. Behaviour-affecting changes are only applied where per-tool
> detection proves them safe; otherwise they are reported, not made (`upgrade` surfaces a
> `behavior_preserving` flag — `true`/`false`/`null` — so callers can gate on it). GTX016 (interpreter)
> auto-fixes only the clean "bucket A" shape; GTX015 only the single top-level data input.
> Imported-macro write-back exists **only** for the `@PROFILE@` token by name — there is
> no general macro write-back yet.

### Check (report-only advisory)

| Capability | Codes | Status | Source |
|---|---|---|---|
| IUC best-practice checks (tests, CDATA, id charset, version, requirements, error handling, EDAM, help, description, version pinning) | IUC001–010, IUC013 | ✅ Shipped | `strict` preset |
| Unquoted Cheetah `$var` in `<command>` (advisory only) | IUC011 | 🟡 Partial | measure-backed; advisory, not auto-fixed |
| Lone-`&` vs `&&` join | IUC012 | 🔭 Roadmap | registry labels it "not yet implemented" |

### Surfaces & orchestration

| Capability | Status | Source |
|---|---|---|
| Code-addressable rule registry + presets (`cosmetic`/`iuc`/`strict`) + `--select`/`--ignore` | ✅ Shipped | `galaxy-tool-refactor-registry` |
| CLI: `format` / `upgrade` / `check` / `presets` / `rules` / `normalize-macros` | ✅ Shipped | `galaxy-tool-refactor` |
| MCP server for agents: `format_tool` / `upgrade_tool` / `check_tool` / `list_presets` / `list_rules` | ✅ Shipped | `galaxy-tool-refactor-mcp` (vision Goal 1) |
| Corpus evidence base: 9,358 unique tools, standing measurements | ✅ Shipped | `docs/*_stats.md`, `scripts/measure.py` |

## Roadmap (🔭 — not built; never stated elsewhere as present tense)

- **Automated background system** that walks a tool repo and opens fix PRs in batches.
- **Streamlining / partial automation of IUC PR review** — the per-tool engine exists
  today (`check`/`format`/`upgrade`); the *review-workflow integration* does not.
- **Agent-authored rules** — agents contributing new codemods/checks (MCP vision Goal 2).
- **General macro write-back** — the provenance layer behind editing imported-macro
  content beyond the profile token (a gated epic; see `docs/macro_handling_architecture.md`).
- **Ecosystem integrations** (editor/LSP quick-fixes, planemo/CI backend, catalog-scale
  health) — see the Potential/Roadmap tiers in `leverage.md`.

<details>
<summary>Why some rows are 🟡 Partial, in one line each</summary>

- **upgrade**: structural validity is sound; behaviour preservation is bounded to the
  provable cases (`soundness.md`).
- **imported `@PROFILE@`**: edited in place only when all importers agree the target;
  disagreement is reported, not forced.
- **GTX014/015/016**: deliberately conservative — they fix the shapes a static codemod
  can prove safe and leave the rest to detect/warn.
- **IUC011**: ~73% of tools carry an unquoted shell-line `$var`, but only a minority are
  provably safe to auto-quote, so it stays advisory (measure-backed, not a fixer).
</details>
