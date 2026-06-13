# Capabilities — what is real today

> **TL;DR.** This page is the project's honesty backbone. Every capability is tagged
> **✅ Shipped**, **🟡 Partial** (works within a stated boundary), or **🔭 Roadmap**
> (not built yet). Each row cites the artifact that proves it. Every other page in
> this guide draws from here — so nothing elsewhere claims more than this table
> allows. Regenerate with the `repo-explainer` skill.

Sources are introspected, not recalled: rule/ruleset rows come from
`galaxy-tool-refactor rules` / `rulesets`; command rows from the CLI/MCP surface;
corpus numbers from the committed `docs/*_stats.md` artifacts.

## At a glance

Galaxy tool definitions are XML. This project **reads, validates, fixes, and upgrades
that XML** through one rule set, reachable three ways — as a Python **library**, a
**command line**, and an **MCP server** for agents.

## The capability matrix

### Parse & validate

| Capability | Tier | Status | Source |
|---|---|---|---|
| Parse tool XML preserving CDATA / comments / attribute order | `galaxy-tool-source` | ✅ Shipped | `load_tool`/`parse_tool` |
| Profile-aware validation against the per-release Galaxy XSD | `galaxy-tool-source` | ✅ Shipped | `validate_tool`, ~28 vendored XSDs |
| Find a tool's newest valid profile | `galaxy-tool-source` | ✅ Shipped | `newest_valid_profile` |
| Near-miss typo suggestions | `galaxy-tool-source` | ✅ Shipped | `corrections.py` |

### Fix (structural codemods + cosmetic formatting)

| Capability | Code | Status | Source |
|---|---|---|---|
| Canonical indentation / blank-line / empty-element formatting | GTR001, GTR003, GTR004 | ✅ Shipped | `cosmetic` ruleset |
| Reorder `<param>` / root `<tool>` attributes to IUC convention | GTR002, GTR005 | ✅ Shipped | `default` ruleset |
| Reorder `<tool>` child elements to IUC convention | GTR013 | ✅ Shipped | `default` ruleset |
| Repair near-miss typos so an invalid tool validates | GTR006 | ✅ Shipped | `default` ruleset |
| Normalize Python-style booleans (`True`→`true`) to `xs:boolean` | GTR017 | ✅ Shipped | `default` ruleset |
| Wrap pure-text `<command>` / `<help>` in CDATA | GTR018, GTR019 | ✅ Shipped | `default` ruleset |
| Single-quote the *provably*-single-valued Cheetah `$var`s in `<command>` | GTR020.1 | ✅ Shipped | `default` ruleset |
| Repair deterministically-fixable invalid `<help>` reStructuredText (short title underlines, missing blank lines) behind a behaviour-preserving gate | GTR089.1 | ✅ Shipped | `default` ruleset; planemo-parity *fix* (`HelpInvalidRST`) |
| Trim accidental whitespace from a `<requirement>` `version` (the `<tool>` `name` trim is the GTR035.2 advisory — display-contract, report-only) | GTR035.1 | ✅ Shipped | `default` ruleset; planemo-parity *fix* (`docs/examples/planemo_fixable_issues.md`) |
| Replace a deprecated `<output type="data">` with `<data>` | GTR036 | ✅ Shipped | `default` ruleset; planemo-parity *fix* |
| Drop a `<param>` `name` that its `argument` already implies | GTR037 | ✅ Shipped | `default` ruleset; planemo-parity *fix* |
| Convert an RST `<help>` to Markdown when provably render-equivalent (profile ≥ 24.2; repair-then-convert; opt-in `convert-help`, never `format`/`upgrade`) | GTR092 | ✅ Shipped | `convert-help` command; tier-1 `rst_markdown` gate; 73.4% of corpus RST helps convertible (`docs/upgrade_research/restructuredtext_codemods.md`) |
| Factor a literal `version="<base>+galaxy<suffix>"` into `@TOOL_VERSION@`/`@VERSION_SUFFIX@` tokens (opt-in `tokenize-version`; inline, or in a created / merged / directory-shared `--macros-file` (expansion-equality gated), or the identity-changing `--adopt-suffix` (controlled-change gated); never `format`/`upgrade`) | GTR094 | ✅ Shipped | `tokenize-version` command; codemod §43, cli §D13–D15, registry D20; 76 inline + 284 `--adopt-suffix` candidates (`scripts.measure version-tokenization`) |
| Prune planemo `.lint_skip` suppressions the toolchain can prove are resolved (opt-in `lint-skip`; apply the fixes, remove a line only when its linter is *completely covered* and clean on every tool in the directory; leaves the rest untouched and unmentioned) | — | ✅ Shipped | `lint-skip` command; cli §D19, registry D24; 149 of 640 corpus suppressions auto-removable (`scripts.measure lint-skip-corpus`; `docs/lint_skip.md`) |

### Upgrade (repair + profile placement, opt-in & semantic)

| Capability | Code | Status | Source |
|---|---|---|---|
| Repair, then bump `profile=` only when strictly needed for validity (the minimal-bump default: a valid tool keeps its declaration, undeclared stays undeclared, else the minimum valid profile) | GTR097 | ✅ Shipped | `upgrade` command; proof `docs/proofs/GTR097.md`; corpus contract sweep `corpus_check upgrade` (0 violations, both modes) |
| Upgrade a tool as far as behaviour provably stays the same (the opt-in `--modernize` walk, also capped at the deployment ceiling, the newest profile every major public Galaxy server runs; `--allow-behavior-change` lifts the behaviour gate, an explicit `--target-profile` exceeds the deployment ceiling) | — | ✅ Shipped | `upgrade --modernize`; gate proof `docs/proofs/behavior-gate.md`; ceiling drift guard `registry tests/test_deployment.py`; corpus contract sweep `corpus_check upgrade` (0 violations) |
| Bump an inline `@PROFILE@` macro token | GTR007 | ✅ Shipped | upgrade rule set |
| Bump an *imported* `@PROFILE@` token (only on importer consensus) | — | 🟡 Partial | `macro_profile` (registry) |
| Runtime-gated repairs (`format_source` guard, `format="input"`, `interpreter=`) | GTR014, GTR015, GTR016 | 🟡 Partial | upgrade rule set |
| Normalize literal `format`/`ftype` in *imported* macro files (opt-in `normalize-macros`) | — | ✅ Shipped | `macro_datatype` (registry); 15 tools unstuck (`docs/macro_format_residual_stats.md`) |

> 🟡 **The soundness boundary (read `soundness.md`).** The default `upgrade` bumps
> only when validity strictly requires it; the `--modernize` walk stops at
> the **behaviour ceiling**: it never crosses a Galaxy `must_fix` change that applies
> to the tool unless a bundled fix provably clears it on that tool (verified by
> re-detection); the stop report links to `docs/profile_boundaries.md`. The result is
> **structurally valid** at the profile it declares. Crossing further is the explicit
> `--modernize --allow-behavior-change`. Behaviour-affecting changes are only applied where
> per-tool detection proves them safe; otherwise they are reported, not made
> (`upgrade` surfaces `behavior_preserving`, `true`/`false`/`null`, plus
> `stopped_at`/`blocking_codes`/`auto_fixed_codes` so callers can gate on them). GTR016 (interpreter)
> auto-fixes any non-empty interpreter whose command leads with a literal script
> ("bucket A", widened 2026-06-10); GTR015 the sole data input — top-level or
> conditional/section-nested via a qualified `format_source`.
> Imported-macro write-back now covers the `@PROFILE@` token (by name, on importer
> consensus) **and** literal `format`/`ftype` normalization (the opt-in `normalize-macros`);
> both work by *locating the construct in its source file*. General provenance-based
> write-back of *arbitrary* macro-supplied content stays deferred (Phase 2b — sizing found
> **0** additional tools, so it is unjustified for datatypes today).

### Check (report-only advisory)

| Capability | Codes | Status | Source |
|---|---|---|---|
| IUC best-practice checks (tests, CDATA, id charset, version, requirements, error handling, EDAM, help, description, version pinning, citations, TODO-text) | GTR021–GTR033, GTR038, GTR039 | ✅ Shipped | `strict` ruleset |
| Output-correctness checks (unique names, valid placeholder names, collection `type`, `format_source`/`format` exclusivity) — planemo-parity advisory | GTR040–GTR043 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| Tool-level correctness checks (`<command>` present/non-empty, valid `profile` format, package requirement names its package, tool-version whitespace) — planemo-parity advisory | GTR044–GTR047 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| Output presence/format/label checks (`<outputs>` present, each output defines a format, no shared explicit labels) — planemo-parity advisory | GTR048–GTR050 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| Embedded-expression validity (`<container>` identifier shape, output `<filter>` is valid Python, `<stdio>` `<regex>` compiles) — planemo-parity advisory | GTR051–GTR053 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| Input parameter naming/identity (param declares a name, name is a valid placeholder, names unique, no input/output name clash) — planemo-parity advisory | GTR054–GTR057 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| Static `select` option correctness (options defined one valid way, every option has a value, options distinct) — planemo-parity advisory | GTR058–GTR060 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| Dynamic `select` `<options>` correctness (single `<options>`, defines a source, coherent `from_dataset`/`from_data_table`/`meta_file_key`, no deprecated mechanism) — planemo-parity advisory | GTR061–GTR064 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| `<validator>` form (type/attribute compatible with the param, expr/regex carry valid text) — planemo-parity advisory | GTR065–GTR067 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| `<validator>` required attributes (each validator type carries its required `min`/`max`/`table_name`/`metadata_name`/… ) — planemo-parity advisory | GTR068 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| `<conditional>` correctness (test param is a `select`, not optional/multiple, `<when>` blocks match the options) — planemo-parity advisory | GTR069–GTR071 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| Input type/structure (tool has inputs, param child elements valid for the type, `data` param `<options>` metadata-filtering valid) — planemo-parity advisory | GTR072–GTR074 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| Input display/idiom (boolean truevalue/falsevalue sane, select `display` agrees with `multiple`/`optional`) — planemo-parity advisory | GTR075–GTR076 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| `<options>/<filter>` validity (attribute schema per filter type, `regexp` value compiles, `ref`/`meta_ref` resolves) — planemo-parity advisory | GTR077–GTR079 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| `<test>` assertion well-formedness (single assert blocks, `has_n`/`has_size` quantifiers, output `compare`-attribute compatibility) — planemo-parity advisory | GTR080–GTR081 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| `<test>` output correspondence (each test output is named and matches a declared `<data>`/`<collection>` of the right kind) — planemo-parity advisory | GTR082–GTR083 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| `<test>` discovered-dataset coverage (a test of a `discover_datasets` output asserts count/elements) — planemo-parity advisory | GTR084 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| `<test>` parameters & expectations (test params name real inputs, `expect_failure` coherence, `expect_num_outputs` for filtered outputs, tests assert something) — planemo-parity advisory | GTR085–GTR088 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| `<help>` reStructuredText validity (via `docutils`, like Galaxy; `format="markdown"` skipped) — reports the invalid RST the GTR089.1 repair can't safely fix | GTR089.2 | ✅ Shipped | `strict` ruleset; deterministically-fixable subset auto-repaired by GTR089.1; `docs/planemo_linter_parity.md` |
| Output reference integrity (`structured_like`/`format_source` resolves to an input param, a qualified `a\|b` path, or a sibling output) — planemo-parity advisory | GTR090 | ✅ Shipped | `strict` ruleset; macro-using tools skipped; `docs/planemo_linter_parity.md` |
| `data` param declares the format(s) it accepts (else the generic `data` type matches everything) — planemo-parity advisory | GTR091 | ✅ Shipped | `strict` ruleset; `docs/planemo_linter_parity.md` |
| Tool declares a non-empty `id`/`name`/`version` (missing `id`/`name` also fail tier-1 XSD validation; a missing `version` silently defaults to `1.0.0` and empty strings are XSD-valid — this check is the only guard for those) — planemo-parity advisory | GTR095 | ✅ Shipped | `strict` ruleset; check D35; `docs/planemo_linter_parity.md` |
| Unquoted Cheetah `$var` in `<command>` — reports every occurrence; the *provable* subset is auto-fixed by GTR020.1, the residual stays advisory | GTR020.2 | ✅ Shipped | advisory; provable subset fixed (GTR020.1) |
| Input `<param>` never referenced anywhere the tool uses it | GTR034 | ✅ Shipped | `strict` ruleset; 189/467 tools (`docs/corpus_check_stats.md`) |
| Lone-`&` vs `&&` join | GTR032 | ✅ Shipped | `strict` ruleset, detect-only (check D34); quote/redirect/pipe-aware — flags only genuine joining |
| `<tool>` `name` edge whitespace (the GTR035 display-contract residual) | GTR035.2 | ✅ Shipped | `strict` ruleset, detect-only (check D33) |

### Inspect & refactor parameters (queries, not rules)

| Capability | Status | Source |
|---|---|---|
| Find every Cheetah `$param` reference across a tool **and its imported macro files** | ✅ Shipped | `find-references` (`galaxy_tool_source.cheetah_refs` + the tool bundle) |
| Rename a parameter across the definition, every reference, by-name cross-ref attributes, `<tests>` mirrors, **and output `<filter>` Python expressions** — **across a tool and its imported macro files**, atomically (rewrite all or skip with a reason) | ✅ Shipped | `rename-param`; 96.3% of definitions rename cleanly, and 1.7% reach into an imported macro the old single-file path silently left dangling (`galaxy_tool_source.cheetah_rename` + `bundle`; `docs/rename_macro_spread_stats.md`) |
| Gate a cross-file rename that touches a macro **shared** by other tools (edit only when sole-owned within `--repo-root`, else skip + report) | ✅ Shipped | `rename-param --repo-root` (`galaxy_tool_refactor_registry.bundle_rename`) |
| Rename a parameter across **every importer** of a shared macro in lockstep (consensus — only when they all agree) | ✅ Shipped | `rename-param --across-importers` (`rename_param_consensus`) |
| Minimal-diff offset rename for editors (LSP `WorkspaceEdit`) | 🟡 Partial | `rename_param_plan` (Tier-B API) shipped — 96.8% parity, 0 mismatches; editor binding is an open PR (see Roadmap) |
| Version-tokenization Code Actions for editors (LSP `WorkspaceEdit` + `CreateFile`) | 🟡 Partial | `tokenize_version_plan` (Tier-B API) shipped; a galaxyls Code Action (define tokens inline, or extract to a new `macros.xml`) is built and validated against the published `galaxy-tool-source` 0.2.0, awaiting its upstream PR |

### Surfaces & orchestration

| Capability | Status | Source |
|---|---|---|
| Code-addressable rule registry + rulesets (`cosmetic`/`default`/`iuc`/`strict`) + `--select`/`--ignore` | ✅ Shipped | `galaxy-tool-refactor-registry` |
| CLI (eleven commands): `format` / `upgrade` / `check` / `find-references` / `rename-param` / `rulesets` / `rules` / `normalize-macros` / `convert-help` / `tokenize-version` / `lint-skip` | ✅ Shipped | `galaxy-tool-refactor` |
| MCP server for agents (seven tools): `format_tool` / `upgrade_tool` / `check_tool` / `convert_help_tool` / `tokenize_version_tool` / `list_rulesets` / `list_rules` | ✅ Shipped | `galaxy-tool-refactor-mcp` (vision Goal 1) |
| Front-door metapackage `galaxy-tool-refactor` (depends on the CLI, with an `[mcp]` extra for the server); the eight packages are lockstep-versioned with a tag-triggered Trusted-Publishing release. `pip install galaxy-tool-refactor` installs the CLI (the `[mcp]` extra adds the MCP server) | ✅ Shipped (live on PyPI) | `galaxy-tool-refactor-meta/`, `.github/workflows/release.yml` |
| Corpus evidence base: 9,374 unique tools, standing measurements | ✅ Shipped | `docs/*_stats.md`, `scripts/measure.py` |
| Behaviour-preservation proof ledger — every fixable rule adversarially audited; genuine breaks fixed (regression-pinned), over-claims documented | ✅ Shipped | `docs/behavior_preservation.md` (see `soundness.md`) |

## Roadmap (🔭 — not built; never stated elsewhere as present tense)

- **Automated background system** that walks a tool repo and opens fix PRs in batches.
- **Streamlining / partial automation of IUC PR review** — the per-tool engine exists
  today (`check`/`format`/`upgrade`); the *review-workflow integration* does not.
- **Agent-authored rules** — agents contributing new codemods/checks (MCP vision Goal 2).
- **Editor "Rename Symbol" + "Find References" via `galaxy-language-server`** — the
  foundational Tier-B offset API (`rename_param_plan`) shipped and `galaxy-tool-source`
  is [on PyPI](https://pypi.org/project/galaxy-tool-source/); the galaxyls binding is an
  **open PR** (galaxyproject/galaxy-language-server#331, CI-green against the PyPI
  release; cross-file across imported macros) — initial maintainer review addressed,
  awaiting follow-up.
- **Editor version-tokenization Code Actions via `galaxy-language-server`** over the
  `tokenize_version_plan` Tier-B API: "Define version tokens" (inline) and "Extract to
  `macros.xml`" (a `WorkspaceEdit` with a `CreateFile`). Built and validated against the
  published `galaxy-tool-source` 0.2.0; its upstream PR is the next step after #331.
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
