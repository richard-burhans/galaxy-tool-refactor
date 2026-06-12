# galaxy-tool-refactor-cli

The **app tier** of the Galaxy tool refactoring framework — the user-facing
`galaxy-tool-refactor` CLI, a thin front-end over the tier-3.6 rule-registry
facade (`galaxy-tool-refactor-registry`).

| Tier | Layer | Package |
|---|---|---|
| 0.5 | rule metadata | `galaxy-tool-refactor-rules` |
| 1 | parsing & validation | `galaxy-tool-source` |
| 2 | structure | `galaxy-tool-codemod` |
| 3 | formatting | `galaxy-tool-fmt` |
| 3.5 | advisory checks | `galaxy-tool-lint` |
| 3.6 | rule registry / rulesets | `galaxy-tool-refactor-registry` |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` *(this package)* |

Rule orchestration lives in the registry facade; this package depends on it
(plus fmt's `cli_support` engine and tier-1 parsing) and exposes ten commands
(`format`, `upgrade`, `check`, `find-references`, `rename-param`, `rulesets`, `rules`,
`normalize-macros`, `convert-help`, `tokenize-version`):

```bash
# Safe, idempotent: apply a ruleset's fixable rules + cosmetic formatting.
# Default ruleset = structural canonicalisation + cosmetic; never profile=.
galaxy-tool-refactor format tool.xml
galaxy-tool-refactor format --ruleset cosmetic tool.xml  # whitespace only
galaxy-tool-refactor format --ignore GTR002 tool.xml     # all but param-reorder
galaxy-tool-refactor format tools/                       # also formats <macros> files

# Opt-in, semantic: repair typos, then place profile=, then format.
# Minimal-bump by default: profile= moves only when strictly needed for
# validity (kept when the repaired tool validates at its baseline, undeclared
# stays undeclared, else the minimum valid profile at or above the baseline).
# --modernize opts into the behavior-preserving walk: upgrade profile= as far
# as behaviour provably stays the same, stopping at the behaviour ceiling
# with a report naming the blocking code(s) and pointing at
# docs/profile_boundaries.md. No --ruleset; --select/--ignore tune it.
galaxy-tool-refactor upgrade tool.xml
galaxy-tool-refactor upgrade --modernize tool.xml              # gated walk to the ceiling
galaxy-tool-refactor upgrade --modernize --allow-behavior-change tool.xml  # historical walk-to-latest
galaxy-tool-refactor upgrade --target-profile 23.0 tool.xml    # explicit cap (implies the walk)

# Report-only linter: one `file:line  CODE  message` per finding, mutating
# nothing. The default ruleset reports the fixable GTR rules; `--ruleset strict` adds
# the advisory checks (marked `(advisory)`). Exits non-zero on any fixable
# finding; advisory findings are informational unless --strict.
galaxy-tool-refactor check tool.xml
galaxy-tool-refactor check --ruleset strict tool.xml

# Introspection.
galaxy-tool-refactor rulesets
galaxy-tool-refactor rules

# Opt-in, repo-scoped: lowercase literal format/ftype in <macros>-root files (the
# macro-library fix the per-tool `upgrade` can't reach). Rewrites files other than
# the one named, so it is a separate command — never part of format/upgrade.
galaxy-tool-refactor normalize-macros macros/            # --check to preview
```

`format`/`upgrade`/`check` share rule selection — `--ruleset NAME`
(repeatable / comma-separated — the union of the named sets),
`--select CODE…`, `--ignore CODE…` (ruff-style precedence: `--ignore` ▸
`--select` ▸ `--ruleset`; `--select` replaces the rulesets' set; `upgrade` takes no
`--ruleset`). `format`/`upgrade` also honour `--check` (detect drift, exit
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

End-user install (the metapackage is the front door; it pulls this CLI):

```bash
pip install galaxy-tool-refactor          # provides the `galaxy-tool-refactor` command
pip install galaxy-tool-refactor-cli      # or this package directly
```

For development, from the workspace root:

```bash
uv sync
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/
```
