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
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` *(this package)* |

It depends on the codemod tier (structural transforms) and the fmt tier
(cosmetic formatting + serialization), and exposes two commands:

```bash
# Safe, idempotent: structural canonicalisation + cosmetic formatting.
# Never changes profile=.
galaxy-tool-refactor format tool.xml

# Opt-in, semantic: repair typos, then upgrade profile= to the latest
# reachable version (applying each step's structural migration). Reports the
# steps applied and warns if a tool stalls below the latest profile.
galaxy-tool-refactor upgrade tool.xml
```

Both honour `--check` (detect drift, exit non-zero, don't write), `--diff`
(preview), and `--quiet`. The typical modernization flow is `upgrade` then
`format`.

## Why a separate tier

Profile upgrade is semantic, fallible, and reports outcomes; canonicalisation +
formatting is safe and idempotent. Keeping them in separate, explicit commands
(rather than auto-upgrading inside "format my tool") lets users opt into
modernization deliberately. The app also writes output via fmt's serializer, so
it must sit *above* fmt — which is why orchestration lives here and not in the
codemod or fmt CLIs. See `docs/decisions.md` §D1.

## Install / test

```bash
uv sync   # from the workspace root
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/
```
