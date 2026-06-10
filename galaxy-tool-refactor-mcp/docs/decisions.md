# Decisions — galaxy-tool-refactor-mcp

Each entry records a decision once it lands: a date, the decision, and the
rationale. Mirrors the conventions of the sibling packages' `docs/decisions.md`.

## D1 (2026-06-03) — The MCP server: a thin FastMCP adapter over the facade (vision Goal 1)

> **Renamed since (PR #146, registry D15):** presets became **rulesets** — the tool
> is now `list_rulesets`, the argument `ruleset`, the typed error `UnknownRuleset`.
> This entry keeps the original vocabulary as a historical record; the shipped
> surface is `server.py` / `service.py`.

### Decision

`galaxy-tool-refactor-mcp` becomes a real tier-4 package — an MCP server exposing
the registry facade to AI agents (Goal 1 of `docs/vision.md`). It is a sibling of
the CLI: both wrap the tier-3.6 facade for a different audience. Five tools:
`format_tool`, `upgrade_tool`, `check_tool`, `list_presets`, `list_rules`. Goal 2
(agent-authored rules) stays out of scope.

### Shape — split in two

- **`service.py` (protocol-agnostic).** Pure functions taking XML as a `str`
  (plus `preset` / `select` / `ignore`) and returning JSON-able `dict`s by calling
  `facade.run` / `upgrade` / `detect` / `list_presets` / `list_rules` and
  serialising the structured results. **No `mcp` import** — so the substance is
  unit-testable without a transport. This realises the vision's "thin adapter":
  the facade is library-first precisely so this layer is a mechanical mapping.
- **`server.py` (FastMCP binding).** `build_server()` registers a small handler
  per tool, each delegating to `service`. Factored out so tests introspect the
  registered tools (`await server.list_tools()`) without starting a transport;
  `main()` runs it over stdio.

### Rationale / boundaries

- **Never writes to disk.** Agents pass content and get content back —
  `write_path` is never used. The XML `str` is `encode("utf-8")`d to `bytes`
  before the facade, so it is always parsed as *content*, never a path.
- **`server.py` is the error boundary** (the MCP analogue of the CLI's `click`
  boundary): it maps the facade's typed `UnknownPreset` / `UnknownRuleCode` and
  tier-1's `ToolXmlSyntaxError` to a plain `ValueError` whose message FastMCP
  surfaces as a tool error, so a bad preset or malformed tool is a clean error
  result, not a crashed server. `service.py` lets the typed errors propagate.
- **Handler annotations are runtime-evaluable.** FastMCP builds each tool's input
  schema via `inspect.signature(..., eval_str=True)`, so a registered handler's
  annotations must resolve at import time. Handlers therefore use builtin
  `list[str] | None`, not a `TYPE_CHECKING`-only `Sequence` (which raised
  `InvalidSignature`). `service.py`, not introspected by FastMCP, keeps its
  `Sequence` typing.
- **Dependency.** `mcp>=1.2` (ships `py.typed`, so mypy-strict passes). Registered
  in the workspace; the qa-gate (`scripts/qa_gate.sh`) now covers eight packages.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-mcp pytest galaxy-tool-refactor-mcp/tests/
uv run galaxy-tool-refactor-mcp   # serve over stdio
```

## D2 (2026-06-10) — `convert_help_tool`: the opt-in conversion joins the surface

The sixth tool, mirroring the CLI's `convert-help` (cli D12) over the facade's
`convert_help` (registry D18): `convert_help_tool(xml) -> {converted, formatted,
skip_reason}`. The conversion's gates live below this tier (profile >= 24.2 +
render equivalence, codemod §38); the adapter only serialises the structured
outcome — `converted=False` with the codemod's own `skip_reason` is a normal
result, not an MCP error, so an agent can act on the reason (e.g. call
`upgrade_tool` first, exactly what the profile-gate message says). No
ruleset/select parameters: GTR092 is not selectable anywhere, by design.
