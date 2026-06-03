# Using it from an MCP client (agents)

> **TL;DR.** The MCP server exposes the same engine to AI agents as five tools —
> `format_tool`, `upgrade_tool`, `check_tool`, `list_presets`, `list_rules` — over a thin FastMCP
> binding. Tools take the tool XML as a string and return JSON; nothing is written to
> disk. This is vision Goal 1, and it ships today.

## The five tools

| Tool | Input | Returns |
|---|---|---|
| `format_tool` | `xml`, optional `preset`/`select`/`ignore` | canonical XML + advisory notes |
| `upgrade_tool` | `xml`, optional `select`/`ignore` | upgraded XML, steps, `behavior_preserving`, notes |
| `check_tool` | `xml`, optional `preset`/`select`/`ignore` | report-only findings (never mutates) |
| `list_presets` | — | the baked-in presets (name / codes / default / description) |
| `list_rules` | optional `include_upgrade` | every rule (code / family / fixable / presets / cite) |

Selection mirrors the CLI and library: `preset` ∈ {`cosmetic`, `iuc`, `strict`},
plus `select` / `ignore` code lists (precedence `ignore` ▸ `select` ▸ `preset`).
`upgrade_tool` takes no preset — it's semantic.

## Shape of a call

An agent passes the XML in and gets structured JSON back, e.g. `check_tool`:

```text
// check_tool(xml="<tool …>…</tool>", preset="strict")
{
  "violations": [
    {"code": "GTR001", "line": 3,  "message": "Canonical 4-space indentation; no tabs."},
    {"code": "GTR025", "line": 1,  "message": "Tool should declare <requirements>."}
  ],
  "advisory_codes": ["GTR021", "GTR025", "…"]
}
```

`format_tool` returns the canonical XML; `upgrade_tool` returns the upgraded XML plus
`behavior_preserving` (`true`/`false`/`null`) so an agent can decide whether the bump
is safe to accept unattended — see [soundness](../soundness.md).

## Why it's a thin adapter

The MCP server (`server.py`) is a FastMCP binding over a protocol-agnostic adapter
(`service.py`) that turns the registry facade's structured results into JSON. The
facade does the work; the server just maps errors (`UnknownPreset`,
`UnknownRuleCode`, syntax errors) to agent-facing messages. Same engine as the CLI.

<details>
<summary>What's <em>not</em> here yet</summary>

Agents *calling* the tools is shipped. Agents *authoring their own rules* (new
codemods/checks discovered and run alongside the baked-in set) is vision **Goal 2** —
open design, not built. See `galaxy-tool-refactor-mcp/docs/vision.md` and the
[leverage map](../leverage.md).
</details>
