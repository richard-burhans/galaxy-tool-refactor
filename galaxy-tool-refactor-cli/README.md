# galaxy-tool-refactor-cli

The **app tier** of the Galaxy tool refactoring framework — the user-facing
`galaxy-tool-refactor` CLI that composes the lower tiers into end-to-end
workflows.

| Tier | Layer | Package |
|---|---|---|
| 0.5 | rule metadata | `galaxy-tool-refactor-rules` |
| 1 | parsing & validation | `galaxy-tool-xml` |
| 2 | structure | `galaxy-tool-xml-codemod` |
| 3 | formatting | `galaxy-tool-xml-fmt` |
| 3.5 | advisory checks | `galaxy-tool-xml-check` |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` *(this package)* |

It depends on the codemod tier (structural transforms), the fmt tier (cosmetic
formatting + serialization), and the check tier (advisory IUC checks), and
exposes three commands:

```bash
# Safe, idempotent: structural canonicalisation + cosmetic formatting.
# Never changes profile=.
galaxy-tool-refactor format tool.xml

# Opt-in, semantic: repair typos, then upgrade profile= to the latest
# reachable version (applying each step's structural migration). Reports the
# steps applied and warns if a tool stalls below the latest profile.
galaxy-tool-refactor upgrade tool.xml

# Report-only linter: one `file:line  CODE  message` per finding, mutating
# nothing. Covers the fixable GTX rules (what `format` would change) plus the
# advisory IUC best-practice checks (marked `(advisory)`). Exits non-zero on
# any fixable finding; advisory findings are informational unless --strict.
galaxy-tool-refactor check tool.xml
```

`format` and `upgrade` honour `--check` (detect drift, exit non-zero, don't
write — distinct from the `check` *command*), `--diff` (preview), and `--quiet`;
`check` honours `--quiet` and `--strict`. The typical modernization flow is
`upgrade` then `format`; `check` previews what those would change plus
best-practice suggestions.

## Why a separate tier

Profile upgrade is semantic, fallible, and reports outcomes; canonicalisation +
formatting is safe and idempotent. Keeping them in separate, explicit commands
(rather than auto-upgrading inside "format my tool") lets users opt into
modernization deliberately. The app also writes output via fmt's serializer, so
it must sit *above* fmt — which is why orchestration lives here and not in the
codemod or fmt CLIs. See `docs/decisions.md` §D1 (the app tier), §D2 (the
report-only `check` command), and §D3 (advisory IUC findings in `check`).

## Install / test

```bash
uv sync   # from the workspace root
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/
```
