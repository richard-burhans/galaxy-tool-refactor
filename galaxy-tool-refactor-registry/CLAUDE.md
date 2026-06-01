# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-refactor-registry` is the **rule-registry facade** tier (tier 3.6)
of the Galaxy tool refactoring framework: a unified, code-addressable view over
every baked-in rule, named presets, per-rule enable/disable, and a library-first
`run`/`upgrade`/`detect` API.

| Tier | Layer | Package |
|---|---|---|
| 0.5 | rule metadata | `galaxy-tool-refactor-rules` |
| 1 | parsing & validation | `galaxy-tool-xml` |
| 2 | structure | `galaxy-tool-xml-codemod` |
| 3 | formatting | `galaxy-tool-xml-fmt` |
| 3.5 | advisory checks | `galaxy-tool-xml-check` |
| 3.6 | **rule registry / presets** | `galaxy-tool-refactor-registry` *(this repo)* |
| 4 | app / CLI | `galaxy-tool-refactor-cli` |
| 4 | MCP server (future) | `galaxy-tool-refactor-mcp` |

It depends on the rule tiers (0.5 / 1 / 2 / 3 / 3.5); **the lower tiers do not
depend on it**, and it is the only orchestration layer below the app CLI. Both
the CLI and a future MCP server (`galaxy-tool-refactor-mcp`) sit on top of it.

## Key invariants

- **Library-first.** No `click` / `sys.exit` / printing in the call path; inputs
  are path / bytes / `ToolDocument`; outputs are structured (`FormatResult` /
  `UpgradeResult` / `DetectResult`); files are written only when a `write_path`
  is given. This is what lets the CLI and the MCP server be thin adapters.
- **fmt is still the only serializer.** All XML bytes come out of
  `format_tool_document_subset` / fmt's `to_bytes`; the facade never serialises
  XML itself.
- **One handle per code.** `RuleHandle` (`handle.py`) adapts each family's rule
  to a uniform `meta` / `family` / `fixable` / `detect` / `apply` shape; the
  registry asserts the GTX/IUC code namespace is collision-free.
- **Selectable ≠ all.** `registry()` is the selectable set (canonical codemods +
  cosmetic fmt + advisory checks). The upgrade-only codemods — GTX007–GTX012
  (validity-gated, internal to `UpgradeToLatest`) and GTX014–GTX015 (runtime-gated,
  applied by `upgrade`) — appear only in `all_handles()` /
  `list_rules(include_upgrade=True)`.
- **Apply ordering reproduces `format`.** Codemods in `CANONICAL_CODEMODS` order,
  then cosmetic fmt in `meta.order`. The `iuc` preset is byte-identical to the
  old `format` pipeline (a regression test pins this).
- **Presets and rules are developer-defined.** No user-defined rules/presets.

## Coding standards

Hand-written code follows **dignified-python** (vendored at the workspace root
`.claude/skills/dignified-python/`): LBYL over try/except (the facade has no
exception handling — it raises typed `UnknownRuleCode`/`UnknownPreset` from
`errors.py`, which the CLI catches at its boundary); `pathlib` with explicit
`encoding` for text I/O; keyword-only args after the first; absolute imports, no
re-exports, no `__all__`; no import-time side effects (`@cache` for the
registry/preset tables). `optimized-python` is a secondary reference;
dignified-python governs on conflict. New code lands tests-first.

## Commands

Run from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync`
- `uv run --package galaxy-tool-refactor-registry pytest galaxy-tool-refactor-registry/tests/`
- `uv run ruff check galaxy-tool-refactor-registry/src galaxy-tool-refactor-registry/tests`
- `uv run mypy --config-file galaxy-tool-refactor-registry/pyproject.toml galaxy-tool-refactor-registry/src`

## Module map

- `handle.py` — the `RuleHandle` adapter dataclass.
- `adapters.py` — wrap each family (codemod / fmt / check) into a `RuleHandle`;
  the family class enumerations.
- `registry.py` — `@cache`d `code -> RuleHandle` index (duplicate-code guard);
  `registry` / `all_handles` / `by_code` / `known_codes` / `advisory_codes`.
- `presets.py` — preset code sets (single source of truth), `DEFAULT_PRESET`.
- `resolve.py` — `resolve_codes` / `resolve_upgrade_codes` (ignore ▸ select ▸
  preset; select replaces).
- `apply.py` — `apply_selection` (phase-ordered apply).
- `facade.py` — `run` / `upgrade` / `detect` / `list_presets` / `list_rules`.
- `macro_profile.py` — Phase-3b imported-`@PROFILE@` upgrade: `profile_token_site`
  (one tool → defining file + target), the pure `plan_from_sites` (per-file
  importer agreement), and `apply_profile_token_plans` (bump the agreed files'
  tokens via `format_macro_document`, skip the rest). See `docs/decisions.md` D5.
- `results.py` — the structured result + introspection dataclasses.
- `errors.py` — `UnknownRuleCode` / `UnknownPreset`.

## Useful references

- `galaxy-tool-refactor-cli/src/galaxy_tool_refactor_cli/cli.py` — the CLI that
  consumes this facade.
- `galaxy-tool-refactor-mcp/docs/vision.md` — why library-first/introspectable.
- `galaxy-tool-xml-fmt/docs/decisions.md` §D15 — the per-rule subset seams.
