# galaxy-tool-refactor-registry

The **rule-registry facade** (tier 3.6) of the Galaxy tool refactoring framework:
a single, code-addressable view over every baked-in rule across the three rule
families — codemod (tier 2, structural GTX), fmt (tier 3, cosmetic GTX), and
check (tier 3.5, advisory IUC) — plus **named presets** and **per-rule
enable/disable**, behind a **library-first** API.

```
                 galaxy-tool-refactor-registry   (this package, tier 3.6)
                        ↑                       ↑
   galaxy-tool-refactor-cli (tier 4)     galaxy-tool-refactor-mcp (tier 4, future)
```

It depends on the rule tiers (0.5 / 1 / 2 / 3 / 3.5); the lower tiers do **not**
depend on it. It is the orchestration core the `galaxy-tool-refactor` CLI sits on
top of, and the intended core for a future MCP server
(`galaxy-tool-refactor-mcp`). All XML serialisation goes through fmt, preserving
"fmt is the only tier that writes/serialises XML".

## Why library-first

No `click` / `sys.exit` / printing in the call path; functions take a path, raw
`bytes`, or a `ToolDocument` and return **structured results**; files are written
only when a `write_path` is given; and the rule/preset catalogs are
introspectable (`list_rules()` / `list_presets()`). That shape lets both the CLI
and a future agent-facing MCP server be thin adapters over the same core. See
`../galaxy-tool-refactor-mcp/docs/vision.md`.

## Presets

| Preset | Contents | Notes |
|---|---|---|
| `cosmetic` | fmt cosmetic rules (GTX001/003/004) | whitespace / indent / shorthand only |
| `iuc` *(default)* | canonical codemods (GTX006/002/005/013) + cosmetic | today's `format` — the opinionated formatter |
| `strict` | `iuc` + advisory IUC checks | format + flag everything IUC cares about (report-only) |

Adding or changing rules and presets is a **developer** task — there are no
user-defined rules or presets.

## Selection

`resolve_codes(preset=…, select=…, ignore=…)` turns a preset name plus
`--select`/`--ignore` code lists into a concrete code set. Precedence is
ruff-style: `--ignore` ▸ `--select` ▸ `--preset` — an explicit `--select`
*replaces* the preset's set, then `--ignore` subtracts. Unknown preset names /
rule codes raise the typed `UnknownPreset` / `UnknownRuleCode`.

## Public API (by submodule import; no re-exports)

```python
from galaxy_tool_refactor_registry.facade import (
    run, upgrade, detect, list_presets, list_rules,
)
from galaxy_tool_refactor_registry.resolve import resolve_codes, resolve_upgrade_codes
from galaxy_tool_refactor_registry.registry import by_code, known_codes, advisory_codes
```

- `run(source, *, codes, write_path=None) -> FormatResult` — apply the fixable
  rules in the selection (codemods in canonical order, then cosmetic fmt),
  reporting advisory findings as notes.
- `upgrade(source, *, codes, write_path=None) -> UpgradeResult` — profile-upgrade
  plus the selected fixable rules.
- `detect(source, *, codes) -> DetectResult` — report-only over the selection.
- `by_code(code) -> RuleHandle` — the uniform, callable handle for one rule
  (`meta`, `family`, `fixable`, `detect(document)`, `apply(document)` or `None`).

## Develop

Run from the workspace root (`galaxy-tool-refactor/`):

```bash
uv run --package galaxy-tool-refactor-registry pytest galaxy-tool-refactor-registry/tests/
uv run ruff check galaxy-tool-refactor-registry/src galaxy-tool-refactor-registry/tests
uv run mypy --config-file galaxy-tool-refactor-registry/pyproject.toml galaxy-tool-refactor-registry/src
```
