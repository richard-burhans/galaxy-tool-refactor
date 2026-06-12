# Changelog

All eight packages in this workspace are versioned and released **in lockstep**
(one version, published as a set — see `galaxy-tool-source/docs/decisions.md` §27).
This file is the single changelog for the whole release; per-package detail lives
in each package's `docs/decisions.md`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions are [Semantic Versioning](https://semver.org/) and, pre-1.0, the minor
is the breaking-change channel.

## [Unreleased]

### Changed
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

[Unreleased]: https://github.com/richard-burhans/galaxy-tool-refactor/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/richard-burhans/galaxy-tool-refactor/releases/tag/v0.2.0
