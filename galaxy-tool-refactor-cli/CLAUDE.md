# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-refactor-cli` is the **app tier** (tier 4) of the Galaxy tool
refactoring framework: the user-facing CLI front-end over the rule-registry
facade.

| Tier | Layer | Package |
|---|---|---|
| 0.5 | rule metadata | `galaxy-tool-refactor-rules` |
| 1 | parsing & validation | `galaxy-tool-source` |
| 2 | structure | `galaxy-tool-codemod` |
| 3 | formatting | `galaxy-tool-fmt` |
| 3.5 | advisory checks | `galaxy-tool-lint` |
| 3.6 | rule registry / rulesets | `galaxy-tool-refactor-registry` |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` *(this repo)* |

Rule orchestration lives in the tier-3.6 **registry facade**
(`galaxy-tool-refactor-registry`); this package depends on it (plus fmt's
`cli_support` engine and tier-1 parsing) and does CLI plumbing only — it no
longer imports the codemod / check tiers directly. It exposes the
`galaxy-tool-refactor` CLI with ten subcommands:

- `format` — apply a ruleset's fixable rules then cosmetic formatting. The default
  ruleset = `canonical_codemods()` (repair + attribute / element order + the
  CDATA wraps + GTR020 command-var single-quoting) + cosmetic. Safe, idempotent,
  never changes `profile=`. (GTR020 shifts default-`format` bytes vs the pre-GTR020
  historical output — behaviour-preserving; codemod `docs/decisions.md` §30.)
  Advisory rules in a selection are reported as notes, never applied. Also
  cosmetically formats macro-library files (`<macros>` root) — kind-applicable
  rules only (no codemods); selection governs tools (cli §D5).
- `upgrade` — repair, then iterative profile upgrade, then cosmetic formatting.
  Opt-in and semantic. No `--ruleset`; `--select`/`--ignore` adjust its rule set.
  Also bumps an imported `@PROFILE@` token in place when every profile-using
  importer in the run agrees on the target, else reports+skips (cli §D6); the
  inline-token case is GTR007's job.
- `check` — report-only linter (mutates nothing) over the selected rules' detect
  phases: `file:line  CODE  message` per finding. The default ruleset reports only
  *fixable* GTR findings; `--ruleset strict` adds the *advisory* checks (marked
  `(advisory)`). Fixable findings exit non-zero; advisory are informational unless
  `--strict`. Macro files are checked for cosmetic (fixable) drift too.
- `find-references` — read-only query (mutates nothing, not a rule): print every
  Cheetah `$NAME` reference site (`file:line  [section]  $ref`) across a tool **and its
  imported macro files** (`galaxy_tool_source.cheetah_refs` + the bundle); see
  `docs/decisions.md` §D8, §D10.
- `rename-param` — the mutating sibling of `find-references` (not a rule): rename a
  parameter OLD→NEW across every Cheetah section, by-name cross-ref attribute, and
  `<tests>` mirror, plus the definition — across the tool **and its imported macros**
  (the bundle), atomically. `--repo-root` proves a touched macro is sole-owned (a
  shared macro is skipped + reported, or — with `--across-importers` — renamed across
  every importer in lockstep when they all agree); `--check` previews; `--backup` keeps
  `.bak`s. First Cheetah mutator (M5.3) over `cheetah_rename` / `bundle_rename`; see
  `docs/decisions.md` §D9, §D10, §D11.
- `rulesets` / `rules` — introspection of the baked-in rulesets and rules.
- `convert-help` — opt-in: convert an RST `<help>` body to Markdown
  (`format="markdown"`, GTR092) when provable — profile ≥ 24.2 (XSD gate; the skip
  says "run `upgrade` first") + the tier-1 render-equivalence gate (needs the
  `galaxy-tool-source[markdown]` extra). Behaviour-changing by construction (swaps the
  rendering engine), so a deliberate, separate command — never part of
  `format`/`upgrade` (cli §D12; codemod §38).
- `normalize-macros` — opt-in, repo-scoped pass that lowercases literal
  `format`/`ftype` in `<macros>`-root files (the macro-library analog of 24.2
  normalization the per-tool `upgrade` cannot reach). Rewrites files other than the
  one named (a shared macro file affects every importer), so it is a deliberate,
  separate command — never part of `format`/`upgrade` (cli §D7;
  `galaxy-tool-codemod/docs/macro-aware-normalization.md`).
- `tokenize-version` — opt-in: factor a literal `version="<base>+galaxy<suffix>"`
  into `@TOOL_VERSION@`/`@VERSION_SUFFIX@` tokens shared with the matching package
  requirement, kept only when the expansion-equality gate proves the macro
  expansion byte-identical. A multi-element style restructure (and `--macros-file` /
  `--adopt-suffix` variants), so never part of `format`/`upgrade` (cli §D13–§D15;
  codemod §43; registry D19–D20).

Macro handling is **cosmetic-only and bundle-free for `format`/`check`** (macro
files are formatted/checked standalone as encountered — cosmetic formatting is safe
regardless of sharing; cli §D5). But `rename-param` / `find-references` **are
bundle-aware** (cli §D10): they operate over a tool *and its imported macro files*,
with a sole-owned `--repo-root` gate for the macro edits a rename makes (registry D12;
`galaxy-tool-source/docs/decisions.md` §21). All five mutating commands accept `--backup`
(`<file>.bak` before overwrite).

Selection (`--ruleset` / `--select` / `--ignore`) is shared by
`format`/`upgrade`/`check` (upgrade takes no `--ruleset`); precedence is ruff-style
(`--ignore` ▸ `--select` ▸ `--ruleset`, where `--select` replaces the ruleset set;
`--ruleset` is repeatable / comma-separated and takes the union of the named sets).
`format`/`upgrade` reuse fmt's `cli_support` engine (file walking,
`--check`/`--diff`/`--quiet`, drift detection, summary), wrapping `facade.run` /
`facade.upgrade` in the per-file transform; `check` runs its own report-only loop
(`cli_support.iter_targets`/`is_tool_root` + `facade.detect`). The facade — not
this package — composes the lower tiers, which is *why* the orchestration sits
below the CLI (so the MCP server reuses it). See `docs/decisions.md` §D1
(app tier), §D2 (`check`), §D3 (advisory findings), §D4 (registry facade +
selection); `galaxy-tool-refactor-registry/docs/decisions.md` D1–D4;
`galaxy-tool-fmt/docs/decisions.md` §D12.

## Coding standards

Hand-written code follows **dignified-python** (vendored at the workspace root
`.claude/skills/dignified-python/`): LBYL over try/except; exceptions only at
the CLI error boundary; `pathlib.Path` with explicit `encoding="utf-8"`;
keyword-only args after the first; absolute imports, no re-exports, no
`__all__`; no import-time side effects. `optimized-python` is a secondary
reference; **dignified-python governs on conflict**.

## Commands

Run from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync` — install dependencies
- `uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/` — run tests
- `uv run ruff check galaxy-tool-refactor-cli/src galaxy-tool-refactor-cli/tests` — lint
- `uv run mypy --config-file galaxy-tool-refactor-cli/pyproject.toml galaxy-tool-refactor-cli/src` — type-check (strict)
- `uv run galaxy-tool-refactor format <file>` / `uv run galaxy-tool-refactor upgrade <file>` — run the CLI

## Useful workspace references

- `galaxy-tool-refactor-registry/src/galaxy_tool_refactor_registry/facade.py` —
  the `run` / `upgrade` / `detect` / `list_rulesets` / `list_rules` entry points
  this CLI wraps; `resolve.py` for `resolve_codes` / `resolve_upgrade_codes`.
- `galaxy-tool-fmt/src/galaxy_tool_fmt/cli_support.py` — the shared
  file-processing engine (`run`, `iter_targets`, `is_tool_root`,
  `TransformOutcome`).
- `galaxy-tool-codemod/src/galaxy_tool_codemod/canonical.py` — the
  `canonical_codemods()` / `AUTO_UPGRADE_CODEMODS` contracts the facade consumes.
