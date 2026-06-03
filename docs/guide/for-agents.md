# For AI agents (and people building them)

> **In one sentence:** this is a substrate for agents that work on Galaxy tools — call
> it over **MCP** (five tools) or embed the **library**, and let it do the deterministic,
> verifiable parts (format, upgrade, check) while the agent does the reasoning.

## Why an agent wants this

An LLM can draft a tool wrapper, but it shouldn't *guess* whether the XML is valid, in
canonical form, or safe at a newer profile. This project answers those deterministically
and returns structured results — so the agent offloads the parts that must be *correct*,
not *plausible*. The **upgrade + validation framework is the most mature surface**: it's
backed by per-release XSDs and a 9,358-tool evidence base, and it tells you when a change
is provably safe.

## Two ways in

### MCP (tool calls)

Five tools — `format`, `upgrade`, `check`, `list_presets`, `list_rules` — take the tool
XML as a string and return JSON. Nothing is written to disk. See
[usage/mcp](usage/mcp.md). The key signal for autonomy:

```jsonc
// upgrade(xml=...) ->
{ "formatted": "<tool … profile=\"26.1\">…", "behavior_preserving": false, "steps_applied": [...] }
```

`behavior_preserving` (`true`/`false`/`null`) lets an agent decide what to accept
unattended versus surface to a human — the honest contract is in [soundness](soundness.md).

### Library (embed it)

```python
from galaxy_tool_refactor_registry import facade, resolve
det = facade.detect(tool_path, codes=resolve.resolve_codes(preset="strict"))
for v in det.violations:
    ...  # v.code, v.line, v.message ; det.is_advisory(v)
```

Full surface and the path-vs-bytes gotcha: [usage/library](usage/library.md).

## A safe-by-default loop

1. `check` the draft → structured findings (fixable vs advisory).
2. `format` → canonical XML (behaviour-preserving; accept freely).
3. `upgrade` → newest valid profile; **gate on `behavior_preserving`** — auto-accept
   `true`, escalate `false`/`null`.
4. Re-`check` to confirm.

The engine is deterministic and report-first, so an agent can stay conservative: prefer
the proven-safe action, surface the rest.

## Honest about the frontier

- **Agents calling the tools: shipped.** That's vision Goal 1.
- **Agents authoring their own rules** (new codemods/checks the framework discovers and
  runs alongside the baked-in set): vision **Goal 2 — open design, not built**
  (`galaxy-tool-refactor-mcp/docs/vision.md`).
- `upgrade` is sound for *structural* validity, not general behaviour — never treat a
  bump as behaviour-neutral without checking `behavior_preserving` ([soundness](soundness.md)).

## Go deeper

[usage/mcp](usage/mcp.md) · [usage/library](usage/library.md) ·
[capabilities](capabilities.md) · [where this fits the ecosystem](leverage.md)
