# Changelog

All nine packages in this workspace are versioned and released **in lockstep**
(one version, published as a set — see `galaxy-tool-source/docs/decisions.md` §27).
This file is the single changelog for the whole release; per-package detail lives
in each package's `docs/decisions.md`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions are [Semantic Versioning](https://semver.org/) and, pre-1.0, the minor
is the breaking-change channel.

## [Unreleased]

## [0.3.4] — 2026-06-16

### Fixed
- **`check` resolves a tool's imported macros** — `check` built the `ToolDocument`
  from the file's bytes, which drops `source_path`, so every macro-aware detect
  rule failed to stage the tool's imported `macros.xml` and logged
  `macro expansion failed for in-memory tree: … No such file or directory` once per
  rule (116 lines on a real tool) while silently falling back to the un-expanded
  tree. It now loads from the path (matching `format`/`upgrade`), so imports
  resolve: no warning noise, and macro-aware checks run on the macro-expanded tree.

## [0.3.3] — 2026-06-15

### Added
- **MCP server: two new tools (7 → 9)** — `find_references_tool` (read-only: every
  Cheetah `$name` reference site across a tool's templated sections) and
  `rename_param_tool` (atomic single-document rename). Both are single-document over
  the facade; the cross-file/imported-macro variants and the repo-scoped
  `normalize-macros` / `lint-skip` stay CLI-only by design (mcp `docs/decisions.md`
  D7). The MCP now covers every single-document CLI operation.
- **Registry facade: `gate_codes()` / `bulk_codes()` + `is_canonical()` /
  `fired_codes()`** — the single source of truth for the auto-fix gate's rule set and
  the detect-based "is this tool canonical?" query, now read by the forward gate, the
  coverage tracker, the bulk normalizer, and the `gate-suggest` command (no local
  re-derivation; guarded by cross-halves tests).

### Fixed
- **Forward-gate Action (block mode) now filters changed XML to actual `<tool>`
  documents** before running `check`, matching `scripts/forward_gate.py`. Previously a
  changed `macros.xml` or other non-tool XML under `tools/` could fail the gate on its
  cosmetic drift. Adopters should re-pin the Action to `@v0.3.3`.

### Changed
- Internal quality (escalated architecture audit + all its proposals): the
  conservative `$var` fallback regex de-duplicated to `cheetah_cdm.CHEETAH_VAR_RE`;
  `bulk_normalize.py --write` reverts on an exception in the post-write re-check; doc
  and docstring freshness across `ARCHITECTURE.md`, the capability matrix, and the CLI.

## [0.3.2] — 2026-06-15

### Added
- **Forward gate suggest mode** (`docs/forward_gate.md`): instead of failing a PR,
  the gate posts each behaviour-preserving canonical fix as a GitHub one-click
  "Commit suggestion" review comment, with the local `format` command and the IUC
  doc link; a change outside the PR's diff is summarized in the review body. The
  composite **Action** gains a `mode: block | suggest` input (suggest needs
  `permissions: pull-requests: write`). Shipped as a hidden
  `galaxy-tool-refactor gate-suggest` CLI command
  (`galaxy_tool_refactor_cli.gate_suggest`, cli decisions §D20) so the Action runs
  the pinned release rather than bundled CI shell — the same provenance guarantee
  block mode has.
- **Durable canonical-form coverage tracker** (auto-fix N6, `scripts/coverage_tracker.py`
  + `docs/coverage_tracker.md` + `docs/corpus_data/coverage_history.json`): record the
  percentage of a repository's tools already in canonical form over time, so a
  bulk-normalize + forward-gate adoption can be tracked.
- **`docs/data_sources.md`**: the mined data sources behind the auto-fix system and
  what each one enabled.

### Changed
- GitHub Actions bumped off the deprecated Node 20 runtime (#247/#188).
- The pre-push hook now allows a combined `git commit … && git push` in one command
  (it validates the working tree as committed rather than blocking on the
  not-yet-run commit).

## [0.3.1] — 2026-06-15

### Added
- **Repository-scale auto-fix system — Half A + Half B.** `scripts/bulk_normalize.py`
  (one-shot bulk normalizer applying the behaviour-preserving, IUC-blessed rule subset
  across a tool repository; `--write` asserts validity-preservation + idempotence per
  tool and reverts any tool that would fail, so the pass is safe by construction) and
  `scripts/forward_gate.py` + a published composite **GitHub Action**
  (`.github/actions/forward-gate/`) that fails a pull request whose changed tools are
  not in canonical form. Both halves read one classification so they cannot drift.
  Proven over the tools-iuc fork (2,131 tools, 100% canonical + idempotent after).
  See `docs/forward_gate.md`.
- **Per-rule auto-fix eligibility** (`galaxy_tool_refactor_registry.gate_eligibility`,
  registry decisions D26): classifies every selectable rule into gate-eligible /
  bulk-only / blocked-pending-iuc / advisory-only — the shared rule-set source both
  halves read. Generated, freshness-tested `docs/gate_eligibility.md` via
  `scripts/gen_gate_eligibility.py`.
- **Re-accumulation measure + conference artifacts.** `scripts/gate_reaccumulation.py`
  + `docs/gate_reaccumulation_stats.md` (96.7% of 452 recently merged tools-iuc PRs
  are still non-canonical in their merged state — the evidence for forward
  enforcement); `docs/iuc_conference_questions.md` §7 (the gate question) and
  `docs/iuc_conference_talking_points.md`.
- **`docs/design_principles.md`**: the two governing contracts written as precise,
  CI-enforced criteria — (1) a fix must be behavior-preserving *by construction*
  (guarded by `test_proof_documents.py`), and (2) every non-fixable warning points
  to detailed docs (now guarded by `test_advisory_citations.py`: every advisory rule
  must carry a `RuleMeta.cite`). The overarching-goal adherence pass.
- **`check` now closes with a `References` block** mapping each fired code to its
  documentation URL (deduplicated; plus a pointer to `rules`), so a finding the
  toolchain cannot auto-fix still tells the author where to read what to do —
  generalizing the `upgrade` → `profile_boundaries.md` pattern to `check`.
- **`rules` now prints each rule's `doc:<cite>`**, surfacing the documentation
  pointer that previously lived only in metadata.
- **GTR102 — boolean-as-conditional in `<command>`** (galaxy-tool-lint, lint
  decisions D38): a detect-only advisory flagging a `type="boolean"` parameter used
  as a conditional for *other* options inside a Cheetah `#if`/`#elif`/`#unless` (the
  command-side companion to GTR069's `<conditional>`-element check). Fires only when
  the `#if` body references a *different* input param; a bare `#if $bool` adding the
  boolean's own flag is left alone. Backed by the new tier-1
  `command_boolean_conditionals` (one source of truth, shared with the
  `command-boolean-if` sizing measure: 342 tools have the anti-pattern). In `strict`.
- **New `command-boolean-if` sizing measure** (`scripts.measure`): sizes the IUC
  "Booleans" anti-pattern in `<command>`, splitting boolean `#if` blocks into
  gates-other-params / constant-only / other. Backs GTR102.
- **GTR100 / GTR101 — test-validation bindings** (galaxy-tool-lint, lint decisions
  D37): the last two planemo `tests.py` linters (`TestsAssertionValidation`,
  `TestsCaseValidation`) are surfaced as an **opt-in binding** to Galaxy's own linters
  rather than a reimplementation — their pydantic validation models sit above the XSD
  and are not soundly portable (Galaxy generates its XSD *from* them; reimplementation
  ledger Touchpoint 5). When the opt-in `[test-validation]` extra (`galaxy-tool-util`)
  is installed and the document has a source path, the rules run Galaxy's real linter
  and surface its messages; otherwise they yield nothing. In the `strict` ruleset, and
  excluded from the `.lint_skip` removal gate (a clean result can mean the extra is
  absent). This completes the planemo advisory surface: parity HAVE 119 → **121**,
  DETECT → **0**.

### Changed
- **GTR032's D3 deferral note is marked superseded by D34** (galaxy-tool-lint
  decisions): GTR032 shipped as a real detector once a precise lexer existed; the stale
  "reserved no-op placeholder" present-tense claims are corrected.

### Fixed
- **GTR036 no longer breaks expression-tool outputs** (codemod decisions §34): it
  converted an expression tool's `<output type="data" … from="output">` to
  `<data from=…>`, but `from` is not valid on `<data>`, so the result failed XSD
  validation. It now skips any `<output>` carrying a `from` attribute (an expression
  output, routed by `from`). Found by the Half-A bulk-normalizer fork proof — the one
  validity regression across 2,131 tools-iuc tools.

## [0.3.0] — 2026-06-14

### Added
- **`lint-skip` command** (cli §D19, registry D24): a convenience that cleans up
  planemo `.lint_skip` sidecars. For each tool directory with a `.lint_skip` it
  applies the toolchain's fixes and removes a suppression line **only when it can
  prove the line is resolved** — the planemo linter must be completely covered
  (every covering GTR code is a faithful check-tier port or a canonical codemod,
  a *derived* set) and clean on every tool in the directory after the fix.
  Anything it cannot fix, cannot prove, or does not cover is left untouched and
  unmentioned (`check` reports the full picture). `--check` previews; `--backup`
  keeps `.bak`s. Corpus sizing: 160 of 640 suppressions auto-removable
  (`scripts.measure lint-skip-corpus`; `docs/lint_skip.md`).
- **GTR098 / GTR099 datatype checks** (galaxy-tool-lint, lint decisions D36):
  advisory `check`-tier ports of planemo's `ValidDatatypes` (GTR098 —
  `format`/`ftype`/`ext` must name a known Galaxy datatype) and
  `DatatypesCustomConf` (GTR099 — a tool should not ship a custom
  `datatypes_conf.xml`). GTR098 validates against a vendored snapshot of Galaxy's
  bundled `datatypes_conf.xml.sample` (no runtime `galaxy-tool-util` dependency),
  drift-guarded against the installed package and proven sound by a corpus parity
  oracle (`scripts.measure datatype-validation-truth`: 0 false positives over
  9,331 tools). In the `strict` ruleset.

### Changed
- **GTR003 (blank line between top-level sections) is parked** (fmt decisions §D4):
  the formatter no longer inserts a blank line between top-level `<tool>` children.
  The convention has no external (IUC) citation and a corpus sweep found only 13.3%
  of section boundaries (30% of tools) already use it, so it is suspended pending
  IUC input (`docs/iuc_conference_questions.md` §4). A `format` byte change: tools
  that had the blank line lose it; the rule remains in source for a one-line
  re-enable.
- **GTR020.1 quotes only input/output files now** (codemod decisions §52, tier-1
  §16; from the IUC review of featurecounts PR #8090). The auto-fixer is narrowed
  to the IUC rule's file scope — single `type="data"` inputs and `<data>` outputs
  — and no longer quotes selects, numbers, booleans, metadata attrs, or Galaxy
  built-ins. Those were safe no-ops to quote but outside the rule, and quoting
  some (a multi-flag select, an "extra options" idiom) was the "too aggressive"
  inconsistency reviewers flagged. A no-op-removal `format` byte shift (a tool's
  behaviour is unchanged); the text-param half stays advisory (GTR020.2), and the
  dropped kinds are now neither quoted nor flagged.
- **GTR020.1 single-quotes output `<data>` file variables** in `<command>`
  (codemod decisions §51, tier-1 §16). An output dataset path is the same
  single-token, Galaxy-controlled value as an input path, so quoting it is
  behaviour-preserving — this closes the output-file half of the IUC rule ("text
  parameters, input **and output files** must be single-quoted"); the text-param
  half necessarily stays advisory (GTR020.2). A default-`format` byte shift for
  tools with bare output vars (~5,697 corpus occurrences); idempotent.
- **The formatter emits no XML declaration** (fmt decisions §D21; from the IUC
  review of featurecounts PR #8090). `serializer.to_bytes` now passes
  `xml_declaration=False`, so canonical output omits `<?xml ...?>` (optional by
  the XML spec, and IUC removes it even when present). Drops the declaration
  from every output path in one place; a second deliberate default-`format`
  byte shift after GTR020.1, `format` idempotence unaffected.
- **`upgrade` is minimal-bump by default** (codemod decisions §50, registry
  D22, cli D17, mcp D5; from IUC maintainer feedback on featurecounts PR
  #8090). `profile=` moves only when strictly needed for validity: a tool
  that validates at its declared profile after repair keeps it byte-untouched,
  an undeclared tool stays undeclared, and an invalid tool moves to the
  minimum valid profile at or above its baseline (`UpgradeToValid`, GTR097).
  The behavior-gated walk below becomes the opt-in `--modernize` /
  `modernize=True`; `--allow-behavior-change` without a walk mode is a typed
  `UpgradeFlagError`. `UpgradeResult` gains additive
  `baseline_profile`/`reached_profile`; `stopped_at` is walk-mode-only.
  `corpus_check upgrade` gains `--mode minimal|modernize|both` and sweeps
  both contracts (0 violations over 9,331 corpus tools).
- **The deployment ceiling caps the modernize walk** (registry D23, cli D18,
  mcp D6). A walk with no explicit target never declares past the newest
  profile every major public Galaxy server runs (25.1; the newest vendored
  profile 26.1 is a pre-release no public server runs). The ceiling is
  vendored in registry `deployment.py` from the committed
  `docs/galaxy_server_versions.json` server-poll snapshot, drift-guarded by
  test, with a staleness note when the snapshot may lag a release.
  `allow_behavior_change` lifts the behaviour gate only; an explicit
  `target_profile` may exceed the ceiling (an informational note keeps the
  choice visible). The minimal-bump default is unaffected (a bump validity
  strictly needs always wins; zero corpus tools need one above the ceiling).
- **The behavior-gated walk** (now the opt-in `--modernize`; the behavior
  gate, codemod decisions §45, registry D21, cli D16, mcp D4). The walk stops at the
  behaviour ceiling: the newest vendored profile reachable without crossing a
  Galaxy `must_fix` behaviour change that applies to the tool and that no
  runtime-gated fix provably clears on that tool (auto-fixability is proven by
  executing the fix on a copy and re-detecting). Stop reports name the blocking
  code(s) and link to the new per-boundary reference. The historical
  walk-to-latest is the explicit `--allow-behavior-change`; `--target-profile
  PROFILE` caps the walk at a vendored profile. The whole-run imported
  `@PROFILE@` bump honors the same gate per importer. `behavior_preserving`
  now credits auto-fixed codes, and a credited fix gets a
  "fixed automatically" note instead of a must-fix warning.
- `newest_valid_profile`, `UpdateProfile`, and `UpgradeToLatest` accept a
  keyword-only `ceiling` (tier-1 decisions §31); defaults unchanged.
- A `@PROFILE@` profile declaration now resolves through the tool's token
  definitions before gating (an unresolvable token fails closed, with a note);
  across the corpus this places 9,371 of 9,373 baselines.

### Fixed
- **The formatter now ends output with a trailing newline** (fmt decisions
  §D22; found running `format` for real tools-iuc PRs). `serializer.to_bytes`
  appended none, so every formatted file lost its final `\n` while all
  tools-iuc tool XML files end with one. Fixed in the single serialisation
  chokepoint, so every output path gains it; idempotent.
- **GTR013 no longer floats opaque `<tool>` children to the end** (codemod
  decisions §53; found running `format` on the tools-iuc vg suite). Children
  whose tag is absent from the IUC order — notably a bare `<expand macro="…"/>`,
  whose expanded tag the codemod can't see — were sorted past every known
  element to the bottom, dropping `<expand macro="requirements"/>` to the end of
  the tool. They are now pinned to their original position while the known
  elements still sort into the slots around them; idempotent, validity-safe
  (`<tool>` is `xs:all`).

### Added
- `UpgradeResult` fields `stopped_at`, `blocking_codes`, and
  `auto_fixed_codes` (also in the MCP `upgrade_tool` result), and the typed
  `UnknownProfile` error for a bad `--target-profile`.
- **`docs/profile_boundaries.md`**: the user-facing per-boundary reference
  ("my upgrade stopped, now what"): per Galaxy behaviour code, what changes,
  what the toolchain does, Galaxy's own description, and the release link.
  Generated from the vendored catalogue + the auto-fix registry by
  `scripts/gen_profile_boundaries.py`; freshness-tested.
- **`docs/proofs/behavior-gate.md`**: the gate's construction-grade soundness
  argument, pinned to the live registries by the proof coverage guard.
- **`corpus_check upgrade`**: the upgrade contract sweep: runs the shipped
  `upgrade` over every corpus tool in one or both modes (`--mode
  minimal|modernize|both`), asserts each mode's contract (minimal:
  fail-closed / undeclared stays undeclared / kept-when-valid /
  minimum-when-bumped / validity / idempotence; modernize: fail-closed /
  gate-cap / no un-fixed `must_fix` crossing / validity / idempotence), and
  retains every violation (first full dual-mode sweep: 9,331 tools, **0
  violations** in both modes).
- The `upgrade-behavior-blocks` measure now consumes the shipped gate
  functions (one implementation for the live default and the published
  statistics).

## [0.2.0] — 2026-06-11

First lockstep release across all eight packages. (`galaxy-tool-source` was
previously published independently at 0.1.0; the workspace now shares one
version, so the others jump from 0.0.1 to 0.2.0 to align.)

### Changed
- **Renamed three packages** to drop `xml` (pre-publish, decisions §27):
  `galaxy-tool-xml-codemod` → `galaxy-tool-codemod`,
  `galaxy-tool-xml-fmt` → `galaxy-tool-fmt`,
  `galaxy-tool-xml-check` → **`galaxy-tool-lint`** (the import packages too). The
  CLI `check` subcommand verb is unchanged.
- **Lockstep versioning** across all eight packages; intra-workspace dependencies
  are pinned `==` to the shared version (maintained by `scripts/bump_version.py`,
  enforced by a registry guard test).

### Added
- **`galaxy-tool-refactor`** front-door metapackage: `pip install galaxy-tool-refactor`
  installs the CLI; the `[mcp]` extra adds the MCP server. (Ninth workspace
  distribution; lockstep-versioned, no code of its own.)
- **GTR095** (`galaxy-tool-lint`): the tool `id`/`name`/`version` missing-or-empty
  check — the half tier-1 XSD validation can't see (`version` is not XSD-required;
  empty strings are XSD-valid). Closes the last infra-free planemo DETECT gap.
- A corpus-completeness guard in `scripts/corpus_check.py` that refuses to
  regenerate stat pages from a partial corpus.

[Unreleased]: https://github.com/richard-burhans/galaxy-tool-refactor/compare/v0.3.4...HEAD
[0.3.4]: https://github.com/richard-burhans/galaxy-tool-refactor/compare/v0.3.3...v0.3.4
[0.3.0]: https://github.com/richard-burhans/galaxy-tool-refactor/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/richard-burhans/galaxy-tool-refactor/releases/tag/v0.2.0
