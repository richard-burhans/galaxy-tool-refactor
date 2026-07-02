# Using it from an MCP client (agents)

> **TL;DR.** The MCP server exposes the same engine to AI agents as nine tools:
> `format_tool`, `upgrade_tool`, `check_tool`, `convert_help_tool`,
> `tokenize_version_tool`, `find_references_tool`, `rename_param_tool`,
> `list_rulesets`, `list_rules`, over a thin FastMCP binding. Tools take the tool
> XML as a string and return JSON; nothing is written to disk. This is vision Goal 1,
> and it ships today.

## The nine tools

| Tool | Input | Returns |
|---|---|---|
| `format_tool` | `xml`, optional `rulesets`/`select`/`ignore` | canonical XML + advisory notes |
| `upgrade_tool` | `xml`, optional `select`/`ignore`, `modernize`, `allow_behavior_change`, `block_consider`, `target_profile` | upgraded XML, steps, `behavior_preserving`, `baseline_profile`/`reached_profile`, `stopped_at`, `blocking_codes`, `auto_fixed_codes`, notes |
| `check_tool` | `xml`, optional `rulesets`/`select`/`ignore` | report-only findings (never mutates) |
| `convert_help_tool` | `xml` | `{converted, formatted, skip_reason}`, opt-in RST→Markdown help conversion; a skip (e.g. "profile below 24.2, run `upgrade` first") is a normal result an agent can act on |
| `tokenize_version_tool` | `xml` | `{tokenized, formatted, skip_reason}`, opt-in @TOOL_VERSION@ extraction (expansion-equality gated); macro-importing tools fail closed (content-based, use the path-based CLI for those) |
| `find_references_tool` | `xml`, `name` | `{name, occurrences: [{section, sourceline, reference}]}`, read-only; this tool's own templated sections (imported-macro references are the path-based CLI) |
| `rename_param_tool` | `xml`, `old`, `new` | `{old, new, changed, renamed, reason, formatted}`, atomic single-document rename; `formatted` is `null` on a bail (the cross-file/imported-macro rename is the path-based CLI) |
| `list_rulesets` | (none) | the baked-in rulesets (name / codes / default / description) |
| `list_rules` | optional `include_upgrade` | every rule (code / family / fixable / rulesets / cite) |

Selection mirrors the CLI and library: `rulesets` is a list whose names ∈
{`cosmetic`, `default`, `iuc`, `strict`} (their union is the base set), plus
`select` / `ignore` code lists (precedence `ignore` ▸ `select` ▸ `rulesets`).
`upgrade_tool` takes no ruleset; it's semantic.

## Shape of a call

An agent passes the XML in and gets structured JSON back, e.g. `check_tool`:

```text
// check_tool(xml="<tool …>…</tool>", rulesets=["strict"])
{
  "violations": [
    {"code": "GTR001", "sourceline": 1, "xpath": "/tool/command",
     "message": "Canonical 4-space indentation; no tabs.", "advisory": false},
    {"code": "GTR025", "sourceline": 1, "xpath": "/tool",
     "message": "Tool should declare <requirements>.", "advisory": true}
  ]
}
```

Each finding carries `advisory` (`false` = a fixable rule, `true` = a report-only
best-practice check).

`format_tool` returns the canonical XML; `upgrade_tool` returns the upgraded XML plus
`behavior_preserving` (`true`/`false`/`null`), `baseline_profile`/`reached_profile`,
`stopped_at`, `blocking_codes`, and `auto_fixed_codes`. The default is
**minimal-bump for agents too**: `profile=` moves only when strictly needed for
validity, modernizing requires passing `modernize=true` explicitly, crossing
the modernize walk's behaviour ceiling additionally requires
`allow_behavior_change=true`, and the walk never passes the deployment ceiling
(the newest profile every major public Galaxy server runs) without an explicit
`target_profile`; an unattended behaviour change, or a profile no server can
install, is worse, not better. The blocking codes map to sections of
[`docs/profile_boundaries.md`](https://github.com/richard-burhans/galaxy-tool-refactor/blob/main/docs/profile_boundaries.md), so an agent can read
exactly what changed and decide deliberately; see [soundness](../soundness.md).

## An example per tool

Calls and responses are real, trimmed; the same demo tool drives them
(`<command>demo --in $input --out $output</command>`, an integer `1.0+galaxy0`
version, an RST `<help>`). `check_tool` is shown above.

<details open>
<summary><b>Fix &amp; upgrade: <code>format_tool</code>, <code>upgrade_tool</code></b></summary>

```text
// format_tool(xml="…$input…$output…")
{"formatted": "…<command><![CDATA[demo --in '$input' --out '$output']]></command>…",
 "advisory": [], "notes": []}                       // file vars quoted, body CDATA-wrapped, indented

// upgrade_tool(xml="…")
{"formatted": "…", "baseline_profile": "24.2", "reached_profile": "24.2",
 "steps_applied": [], "behavior_preserving": true, "stopped_at": null,
 "blocking_codes": [], "auto_fixed_codes": [], "notes": []}
```
</details>

<details>
<summary><b>Opt-in: <code>convert_help_tool</code>, <code>tokenize_version_tool</code></b></summary>

```text
// convert_help_tool(xml="…<help><![CDATA[\nDemo\n====\n\nA **bold** tool.\n]]>…")
{"converted": true,
 "formatted": "…<help format=\"markdown\"><![CDATA[# Demo\n\nA **bold** tool\\.\n]]>…",
 "skip_reason": null}                               // skip_reason is set (and converted=false) when not render-equivalent

// tokenize_version_tool(xml="…version=\"1.0+galaxy0\"…<requirement …>1.0…")
{"tokenized": true,
 "formatted": "…version=\"@TOOL_VERSION@+galaxy@VERSION_SUFFIX@\"…<macros><token name=\"@TOOL_VERSION@\">1.0</token>…",
 "skip_reason": null}
```
</details>

<details>
<summary><b>Query &amp; rename: <code>find_references_tool</code>, <code>rename_param_tool</code></b></summary>

```text
// find_references_tool(xml="…", name="input")
{"name": "input", "occurrences": [{"section": "command", "sourceline": 1, "reference": "$input"}]}

// rename_param_tool(xml="…", old="input", new="reads")
{"old": "input", "new": "reads", "changed": true, "renamed": 2, "reason": null,
 "formatted": "…<command>demo --in $reads --out $output</command>…<param name=\"reads\" …"}
```

On a bail, `changed` is `false`, `formatted` is `null`, and `reason` explains why.
</details>

<details>
<summary><b>Introspect: <code>list_rulesets</code>, <code>list_rules</code></b></summary>

```text
// list_rulesets()
[{"name": "cosmetic", "codes": ["GTR001", "GTR004"], "is_default": false, "description": "…"},
 {"name": "default",  "codes": ["GTR001", "GTR002", "…"], "is_default": true,  "description": "…"}, …]

// list_rules()  (optional include_upgrade=true adds the upgrade-only codemods)
[{"code": "GTR001", "summary": "Canonical 4-space indentation; no tabs.", "family": "fmt",
  "fixable": true, "rulesets": ["cosmetic", "default", "iuc", "strict"],
  "planemo_linters": [], "since": "0.0.1", "cite": "https://…"}, …]
```
</details>

## Why it's a thin adapter

The MCP server (`server.py`) is a FastMCP binding over a protocol-agnostic adapter
(`service.py`) that turns the registry facade's structured results into JSON. The
facade does the work; the server just maps errors (`UnknownRuleset`,
`UnknownRuleCode`, syntax errors) to agent-facing messages. Same engine as the CLI.

<details>
<summary>What's <em>not</em> here yet</summary>

Agents *calling* the tools is shipped. Agents *authoring their own rules* (new
codemods/checks discovered and run alongside the baked-in set) is vision **Goal 2**:
open design, not built. See `galaxy-tool-refactor-mcp/docs/vision.md` and the
[leverage map](../leverage.md).
</details>
