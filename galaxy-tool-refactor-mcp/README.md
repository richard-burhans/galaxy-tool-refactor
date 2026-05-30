# galaxy-tool-refactor-mcp (placeholder — not yet implemented)

> **Status: reserved / documentation-only.** This directory marks the intended
> home of a future **MCP server** that exposes `galaxy-tool-refactor` to AI
> coding agents. There is **no code here yet** and the package is **deliberately
> not registered** in the workspace `[tool.uv.workspace].members` — so `uv sync`
> and builds are unaffected until real content lands. See
> [`docs/vision.md`](docs/vision.md) for the design and the rationale that shapes
> the `galaxy-tool-refactor-registry` facade today.

## Where it sits

A tier-4 package, a **sibling of `galaxy-tool-refactor-cli`**: both compose the
lower tiers through the `galaxy-tool-refactor-registry` facade and wrap it for a
different audience — the CLI for humans at a terminal, this for agents over MCP.

```
                 galaxy-tool-refactor-registry   (tier 3.6 facade: unified rules + presets)
                        ↑                       ↑
   galaxy-tool-refactor-cli (tier 4)     galaxy-tool-refactor-mcp (tier 4, future)
   humans at a terminal                  AI agents over MCP
```

The facade is **library-first** (structured in/out, no `click`/`sys.exit`, writes
only on request, introspectable via `list_presets()` / `list_rules()`) precisely
so this server can be a thin adapter over it rather than a subprocess that
scrapes CLI text.

## When this is implemented

Add a `pyproject.toml` (mirroring the other tiers: hatchling, ruff/mypy, a
`galaxy-tool-refactor-registry` workspace dependency), a `src/` package, and then
register the package in the root `[tool.uv.workspace].members`.
