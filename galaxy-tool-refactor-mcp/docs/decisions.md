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

## D3 (2026-06-10) — `tokenize_version_tool`: the seventh tool

The GTR094 sibling of D2, same shape: `tokenize_version_tool(xml) ->
{tokenized, formatted, skip_reason}` over the facade's `tokenize_version`
(registry D19). One MCP-specific boundary, stated rather than hidden: every
MCP tool is **content-based** (agents supply XML strings; nothing touches
disk), so a tool whose `<macros>` imports files fails closed — the
expansion-equality gate cannot resolve imports without a source directory —
and the skip reason says to use the path-based CLI `tokenize-version` instead.
No ruleset/select parameters: GTR094, like GTR092, is not selectable anywhere.

## D4 (2026-06-12): `upgrade_tool` exposes the behavior gate

> **Superseded as the default (2026-06-12, D5):** the gated walk is now the
> opt-in `modernize=True` mode; the default bumps minimally. The gate's
> mechanics below are current.

Reproduced-by: `uv run --package galaxy-tool-refactor-mcp pytest
galaxy-tool-refactor-mcp/tests/test_service.py -k "behavior or target"`.

`upgrade_tool` gains `allow_behavior_change` and `target_profile` (the same
two escape hatches as the CLI; registry D21) and its result dict gains
`stopped_at`, `blocking_codes`, and `auto_fixed_codes`, so an agent can see
where and why the default walk stopped and decide deliberately whether to opt
past the boundary. `UnknownProfile` joins the `_guarded` error boundary in
`server.py` (translated to a clean tool error, like the other typed facade
errors). The default stays gated for agents too: an agent must pass
`allow_behavior_change=True` explicitly, mirroring the human flag, because an
unattended behaviour change is worse, not better.

## D5 (2026-06-12): `upgrade_tool` follows the minimal-bump default

Reproduced-by: `uv run --package galaxy-tool-refactor-mcp pytest
galaxy-tool-refactor-mcp/tests/test_service.py -k "modernize or minimal or
flag"`. Policy: registry D22, codemod decisions §50.

`upgrade_tool` gains `modernize` (the opt-in behavior-gated walk, the same
semantics as the CLI's `--modernize`; cli D17) and its result dict gains the
additive `baseline_profile` and `reached_profile` fields, so an agent can see
exactly where a tool started and landed without diffing the XML. The default
stays minimal for agents too: an unattended gratuitous profile bump is worse,
not better, mirroring D4's reasoning for the gate. `UpgradeFlagError`
(`allow_behavior_change` without a walk mode) joins the `_guarded` error
boundary in `server.py`, translated to a clean tool error like the other
typed facade errors.

## D6 (2026-06-12): `upgrade_tool` honors the deployment ceiling

Reproduced-by: `uv run --package galaxy-tool-refactor-mcp pytest
galaxy-tool-refactor-mcp/tests/test_service.py -k "deployment or modernize"`.
Policy: registry D23.

No new parameters. `modernize=true` walks to the deployment ceiling (the
newest profile every major public Galaxy server runs) unless the behaviour
gate stops it lower; `target_profile` may exceed the ceiling (the notes
mention it). The asymmetry is deliberate for agents: an unattended
`allow_behavior_change=true` walk still never lands on a profile the public
servers cannot install; exceeding the ceiling takes the explicit target.

## D7 (2026-06-15): `find_references_tool` + `rename_param_tool` — the 8th & 9th tools

Reproduced-by: `uv run --package galaxy-tool-refactor-mcp pytest
galaxy-tool-refactor-mcp/tests/test_service.py -k "find_references or rename_param"`.
Facade: `find_references` / `rename_param` (registry; the latter D11).

The MCP surface covered every *single-document* facade operation except the two
parameter ones, an incremental gap (not a deliberate exclusion) flagged by the
2026-06-15 architecture audit's MCP-vs-CLI delta. Closed it:

- **`find_references_tool(xml, name)`** → `{name, occurrences: [{section, sourceline,
  reference}]}` — read-only, over `facade.find_references`.
- **`rename_param_tool(xml, old, new)`** → `{old, new, changed, renamed, reason,
  formatted}` — the mutating sibling, over `facade.rename_param`; `formatted` is the
  new XML on success and `null` on a bail (with `reason`). Returns content like every
  MCP tool; never writes (`write_path` is not passed).

**Scope boundary (the principled part).** Both are **single-document**, matching the
in-memory `xml: str` model: they span only the tool supplied. The **cross-file**
variants — references/renames that reach an *imported macro file*, with the
sole-owned `--repo-root` gate — stay **CLI-only**, because they need filesystem
access a string-only call does not have (same reason `tokenize_version_tool` fails
closed on imported macros, D3). The two remaining CLI commands, `normalize-macros`
and `lint-skip`, are repo-scoped multi-file batch operations with no single-document
form, so they are deliberately not MCP tools. The server is now **9 tools**.
