# galaxy-tool-refactor-cli

The **app tier** of the Galaxy tool refactoring framework — the user-facing
`galaxy-tool-refactor` CLI, a thin front-end over the tier-3.6 rule-registry
facade (`galaxy-tool-refactor-registry`).

| Tier | Layer | Package |
|---|---|---|
| 0.5 | rule metadata | `galaxy-tool-refactor-rules` |
| 1 | parsing & validation | `galaxy-tool-xml` |
| 2 | structure | `galaxy-tool-xml-codemod` |
| 3 | formatting | `galaxy-tool-xml-fmt` |
| 3.5 | advisory checks | `galaxy-tool-xml-check` |
| 3.6 | rule registry / presets | `galaxy-tool-refactor-registry` |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` *(this package)* |

Rule orchestration lives in the registry facade; this package depends on it
(plus fmt's `cli_support` engine and tier-1 parsing) and exposes eight commands
(`format`, `upgrade`, `check`, `find-references`, `rename-param`, `presets`, `rules`,
`normalize-macros`):

```bash
# Safe, idempotent: apply a preset's fixable rules + cosmetic formatting.
# Default preset `iuc` = structural canonicalisation + cosmetic; never profile=.
galaxy-tool-refactor format tool.xml
galaxy-tool-refactor format --preset cosmetic tool.xml   # whitespace only
galaxy-tool-refactor format --ignore GTR002 tool.xml     # all but param-reorder
galaxy-tool-refactor format tools/                       # also formats <macros> files

# Opt-in, semantic: repair typos, then upgrade profile= to the latest reachable
# version (applying each step's structural migration), then format. Reports the
# steps applied and warns if a tool stalls. No --preset; --select/--ignore tune it.
galaxy-tool-refactor upgrade tool.xml

# Report-only linter: one `file:line  CODE  message` per finding, mutating
# nothing. Default (`iuc`) reports the fixable GTR rules; `--preset strict` adds
# the advisory checks (marked `(advisory)`). Exits non-zero on any fixable
# finding; advisory findings are informational unless --strict.
galaxy-tool-refactor check tool.xml
galaxy-tool-refactor check --preset strict tool.xml

# Introspection.
galaxy-tool-refactor presets
galaxy-tool-refactor rules

# Opt-in, repo-scoped: lowercase literal format/ftype in <macros>-root files (the
# macro-library fix the per-tool `upgrade` can't reach). Rewrites files other than
# the one named, so it is a separate command — never part of format/upgrade.
galaxy-tool-refactor normalize-macros macros/            # --check to preview
```

`format`/`upgrade`/`check` share rule selection — `--preset NAME`,
`--select CODE…`, `--ignore CODE…` (ruff-style precedence: `--ignore` ▸
`--select` ▸ `--preset`; `--select` replaces the preset's set; `upgrade` takes no
`--preset`). `format`/`upgrade` also honour `--check` (detect drift, exit
non-zero, don't write — distinct from the `check` *command*), `--diff`, and
`--quiet`; `check` honours `--quiet` and `--strict`. The typical modernization
flow is `upgrade` then `format`.

## Why a separate tier

Profile upgrade is semantic, fallible, and reports outcomes; canonicalisation +
formatting is safe and idempotent. Keeping them in separate, explicit commands
(rather than auto-upgrading inside "format my tool") lets users opt into
modernization deliberately. Rule orchestration sits *below* the CLI in the
registry facade — both because output is written via fmt's serializer (so the
orchestrator must sit above fmt) and so the MCP server reuses the same
core. See `docs/decisions.md` §D1 (the app tier), §D2 (`check`), §D3 (advisory
findings), §D4 (the registry facade + rule selection).

## Install / test

```bash
uv sync   # from the workspace root
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/
```
