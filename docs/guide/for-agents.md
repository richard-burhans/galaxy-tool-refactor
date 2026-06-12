# For AI agents (and people building them)

> **In one sentence:** this is a substrate for agents that work on Galaxy tools — call
> it over **MCP** (seven tools) or embed the **library**, and let it do the deterministic,
> verifiable parts (format, upgrade, check) while the agent does the reasoning.

## Why an agent wants this

An LLM can draft a tool wrapper, but it shouldn't *guess* whether the XML is valid, in
canonical form, or safe at a newer profile. This project answers those deterministically
and returns structured results — so the agent offloads the parts that must be *correct*,
not *plausible*. The **upgrade + validation framework is the most mature surface**: it's
backed by per-release XSDs and a 9,374-tool evidence base, and it tells you when a change
is provably safe.

## Two ways in

### MCP (tool calls)

Seven tools — `format_tool`, `upgrade_tool`, `check_tool`, `convert_help_tool`,
`tokenize_version_tool`, `list_rulesets`, `list_rules` —
take the tool XML as a string and return JSON. Nothing is written to disk. See
[usage/mcp](usage/mcp.md). The key signal for autonomy:

```text
// upgrade_tool(xml=...) ->
{ "formatted": "<tool … profile=\"24.1\">…", "behavior_preserving": true,
  "stopped_at": "24.1", "blocking_codes": ["24_2_fix_test_case_validation"],
  "auto_fixed_codes": [], "steps_applied": [...] }
```

The default is behavior-preserving: the walk stops at the behaviour ceiling, and
`stopped_at`/`blocking_codes` say where and why (each code maps to a section of
[`docs/profile_boundaries.md`](../profile_boundaries.md)). Crossing the boundary
requires passing `allow_behavior_change=true` explicitly. `behavior_preserving`
(`true`/`false`/`null`) lets an agent decide what to accept unattended versus
surface to a human — the honest contract is in [soundness](soundness.md).

### Library (embed it)

```python
from galaxy_tool_refactor_registry import facade, resolve
det = facade.detect(tool_path, codes=resolve.resolve_codes(rulesets=["strict"]))
for v in det.violations:
    ...  # v.code, v.line, v.message ; det.is_advisory(v)
```

Full surface and the path-vs-bytes gotcha: [usage/library](usage/library.md).

## A safe-by-default loop

1. `check` the draft → structured findings (fixable vs advisory).
2. `format` → canonical XML (behaviour-preserving; accept freely).
3. `upgrade` → the behaviour ceiling by default; **gate on `behavior_preserving`** —
   auto-accept `true`, escalate `false`/`null` and any non-empty `blocking_codes`
   (fix the tool per the boundary reference, or ask a human before passing
   `allow_behavior_change`).
4. Re-`check` to confirm.

The engine is deterministic and report-first, so an agent can stay conservative: prefer
the proven-safe action, surface the rest.

## Honest about the frontier

- **Agents calling the tools: shipped.** That's vision Goal 1.
- **Agents authoring their own rules** (new codemods/checks the framework discovers and
  runs alongside the baked-in set): vision **Goal 2 — open design, not built**
  (`galaxy-tool-refactor-mcp/docs/vision.md`).
- `upgrade`'s default stops rather than cross a breaking behaviour change it cannot
  prove fixed; with `allow_behavior_change` it is sound for *structural* validity
  only — never treat that bump as behaviour-neutral without checking
  `behavior_preserving` ([soundness](soundness.md)).

## Go deeper

[usage/mcp](usage/mcp.md) · [usage/library](usage/library.md) ·
[capabilities](capabilities.md) · [where this fits the ecosystem](leverage.md)
