# Changelog

All eight packages in this workspace are versioned and released **in lockstep**
(one version, published as a set — see `galaxy-tool-source/docs/decisions.md` §27).
This file is the single changelog for the whole release; per-package detail lives
in each package's `docs/decisions.md`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions are [Semantic Versioning](https://semver.org/) and, pre-1.0, the minor
is the breaking-change channel.

## [Unreleased]

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
- **GTR095** (`galaxy-tool-lint`): the tool `id`/`name`/`version` missing-or-empty
  check — the half tier-1 XSD validation can't see (`version` is not XSD-required;
  empty strings are XSD-valid). Closes the last infra-free planemo DETECT gap.
- A corpus-completeness guard in `scripts/corpus_check.py` that refuses to
  regenerate stat pages from a partial corpus.

[Unreleased]: https://github.com/richard-burhans/galaxy-tool-refactor/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/richard-burhans/galaxy-tool-refactor/releases/tag/v0.2.0
