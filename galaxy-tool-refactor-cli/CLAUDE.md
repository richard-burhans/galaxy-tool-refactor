# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-refactor-cli` is the **app tier** (tier 4) of the Galaxy tool
refactoring framework: the user-facing CLI front-end over the rule-registry
facade.

| Tier | Layer | Package |
|---|---|---|
| 0.5 | rule metadata | `galaxy-tool-refactor-rules` |
| 1 | parsing & validation | `galaxy-tool-xml` |
| 2 | structure | `galaxy-tool-xml-codemod` |
| 3 | formatting | `galaxy-tool-xml-fmt` |
| 3.5 | advisory checks | `galaxy-tool-xml-check` |
| 3.6 | rule registry / presets | `galaxy-tool-refactor-registry` |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` *(this repo)* |

Rule orchestration lives in the tier-3.6 **registry facade**
(`galaxy-tool-refactor-registry`); this package depends on it (plus fmt's
`cli_support` engine and tier-1 parsing) and does CLI plumbing only — it no
longer imports the codemod / check tiers directly. It exposes the
`galaxy-tool-refactor` CLI with five subcommands:

- `format` — apply a preset's fixable rules then cosmetic formatting. Default
  preset `iuc` = `CANONICAL_CODEMODS` (repair + attribute / element order) +
  cosmetic — byte-identical to the historical behaviour. Safe, idempotent, never
  changes `profile=`. Advisory rules in a selection are reported as notes, never
  applied.
- `upgrade` — repair, then iterative profile upgrade, then cosmetic formatting.
  Opt-in and semantic. No `--preset`; `--select`/`--ignore` adjust its rule set.
- `check` — report-only linter (mutates nothing) over the selected rules' detect
  phases: `file:line  CODE  message` per finding. Default (`iuc`) reports only
  *fixable* GTX findings; `--preset strict` adds the *advisory* IUC checks (marked
  `(advisory)`). Fixable findings exit non-zero; advisory are informational unless
  `--strict`.
- `presets` / `rules` — introspection of the baked-in presets and rules.

Selection (`--preset` / `--select` / `--ignore`) is shared by
`format`/`upgrade`/`check` (upgrade takes no `--preset`); precedence is ruff-style
(`--ignore` ▸ `--select` ▸ `--preset`, where `--select` replaces the preset set).
`format`/`upgrade` reuse fmt's `cli_support` engine (file walking,
`--check`/`--diff`/`--quiet`, drift detection, summary), wrapping `facade.run` /
`facade.upgrade` in the per-file transform; `check` runs its own report-only loop
(`cli_support.iter_targets`/`is_tool_root` + `facade.detect`). The facade — not
this package — composes the lower tiers, which is *why* the orchestration sits
below the CLI (so a future MCP server can reuse it). See `docs/decisions.md` §D1
(app tier), §D2 (`check`), §D3 (advisory findings), §D4 (registry facade +
selection); `galaxy-tool-refactor-registry/docs/decisions.md` D1–D4;
`galaxy-tool-xml-fmt/docs/decisions.md` §D12.

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
  the `run` / `upgrade` / `detect` / `list_presets` / `list_rules` entry points
  this CLI wraps; `resolve.py` for `resolve_codes` / `resolve_upgrade_codes`.
- `galaxy-tool-xml-fmt/src/galaxy_tool_xml_fmt/cli_support.py` — the shared
  file-processing engine (`run`, `iter_targets`, `is_tool_root`,
  `TransformOutcome`).
- `galaxy-tool-xml-codemod/src/galaxy_tool_xml_codemod/canonical.py` — the
  `CANONICAL_CODEMODS` / `AUTO_UPGRADE_CODEMODS` contracts the facade consumes.
