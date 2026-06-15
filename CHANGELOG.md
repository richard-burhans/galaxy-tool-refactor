# Changelog

All eight packages in this workspace are versioned and released **in lockstep**
(one version, published as a set — see `galaxy-tool-source/docs/decisions.md` §27).
This file is the single changelog for the whole release; per-package detail lives
in each package's `docs/decisions.md`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions are [Semantic Versioning](https://semver.org/) and, pre-1.0, the minor
is the breaking-change channel.

## [Unreleased]

### Added
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

[Unreleased]: https://github.com/richard-burhans/galaxy-tool-refactor/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/richard-burhans/galaxy-tool-refactor/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/richard-burhans/galaxy-tool-refactor/releases/tag/v0.2.0
