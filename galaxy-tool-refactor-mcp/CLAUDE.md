# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-refactor-mcp` is the **MCP server** tier (tier 4) of the Galaxy tool
refactoring framework — an agent-facing front-end over the registry facade, a
sibling of the user-facing CLI.

| Tier | Layer | Package |
|---|---|---|
| 0.5 | rule metadata | `galaxy-tool-refactor-rules` |
| 1 | parsing & validation | `galaxy-tool-source` |
| 2 | structure | `galaxy-tool-codemod` |
| 3 | formatting | `galaxy-tool-fmt` |
| 3.5 | advisory checks | `galaxy-tool-lint` |
| 3.6 | rule registry / rulesets | `galaxy-tool-refactor-registry` |
| 4 | app / CLI | `galaxy-tool-refactor-cli` |
| 4 | **MCP server** | `galaxy-tool-refactor-mcp` *(this repo)* |

It depends on the tier-3.6 facade (plus tier-1 for the `ToolXmlSyntaxError`
boundary type, and tier-0.5 for the `Violation` type — a `TYPE_CHECKING`-only
import in `service.py`, declared as a direct dep because it is imported directly)
and `mcp` (FastMCP). The lower tiers do **not** depend on it.

## Key invariants

- **Thin adapter, split in two.** `service.py` is the protocol-agnostic core
  (facade → JSON-able `dict`s, **no `mcp` import**, fully unit-tested);
  `server.py` is the FastMCP binding (a handler per tool that delegates to
  `service`). The split keeps the logic testable without a transport and the
  protocol shell minimal. This is *why* the facade is library-first.
- **Never writes to disk.** Agents supply XML content as a `str` and get content
  back; `write_path` is never passed. The XML `str` is encoded to `bytes` before
  the facade sees it, so it is parsed as content, never mistaken for a path.
- **`server.py` is the error boundary.** Its handlers translate the facade's typed
  `UnknownRuleset` / `UnknownRuleCode` and tier-1's `ToolXmlSyntaxError` into a
  plain `ValueError` whose message FastMCP returns as a tool error (the MCP
  analogue of the CLI's `click` boundary). `service.py` lets them propagate.
- **FastMCP introspects handler signatures at runtime** (`eval_str=True`), so a
  registered handler's annotations must be evaluable at import time — use builtin
  types (`list[str] | None`), not `TYPE_CHECKING`-only names.
- **Goal 1 only.** Agent-authored rules (`docs/vision.md` Goal 2) are out of
  scope; the server exposes the fixed registry.

## Coding standards

Hand-written code follows **dignified-python** (vendored at the workspace root
`.claude/skills/dignified-python/`): LBYL over try/except (exceptions only at the
MCP error boundary in `server.py`, chained `from e`); keyword-only args after the
first; absolute imports, no re-exports, no `__all__`; no import-time side effects.
`optimized-python` is a secondary reference; dignified-python governs on conflict.
New code lands tests-first.

## Commands

Run from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync`
- `uv run --package galaxy-tool-refactor-mcp pytest galaxy-tool-refactor-mcp/tests/`
- `uv run ruff check galaxy-tool-refactor-mcp/src galaxy-tool-refactor-mcp/tests`
- `uv run mypy --config-file galaxy-tool-refactor-mcp/pyproject.toml galaxy-tool-refactor-mcp/src`
- `uv run galaxy-tool-refactor-mcp` — serve over stdio

## Useful references

- `galaxy-tool-refactor-registry/src/galaxy_tool_refactor_registry/facade.py` —
  the `run` / `upgrade` / `detect` / `convert_help` / `tokenize_version` /
  `list_rulesets` / `list_rules` entry points `service.py` wraps; `results.py` for the structured result shapes serialised.
- `galaxy-tool-refactor-cli/src/galaxy_tool_refactor_cli/cli.py` — the sibling
  front-end over the same facade.
- `docs/decisions.md` D1–D3 — the design + the `convert_help_tool` /
  `tokenize_version_tool` additions; `docs/vision.md` — the agent-authored-rules
  future (Goal 2).
