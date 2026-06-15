# galaxy-tool-refactor-mcp

An **MCP server** that exposes the Galaxy tool refactoring framework to AI coding
agents. A tier-4 sibling of `galaxy-tool-refactor-cli`: both wrap the
`galaxy-tool-refactor-registry` facade (tier 3.6) for a different audience — the
CLI for humans at a terminal, this for agents over the Model Context Protocol.

## Shape

The facade is **library-first** (structured args in, structured results out, no
disk writes unless asked, introspectable), so the server is a *thin adapter*:

- **`service.py`** — protocol-agnostic. Pure functions that take XML as a `str`
  (plus `rulesets` / `select` / `ignore`) and return JSON-able `dict`s by calling the
  facade. No `mcp` import; fully unit-tested.
- **`server.py`** — the FastMCP binding. A small handler per tool delegates to
  `service`, and is the error boundary (facade `UnknownRuleset` / `UnknownRuleCode` /
  `UnknownProfile`
  and tier-1 `ToolXmlSyntaxError` → a clean MCP tool error).

## Tools

| MCP tool | What it does |
|---|---|
| `format_tool` | Apply a ruleset's fixable rules then format; returns canonical XML + advisory notes. |
| `upgrade_tool` | Repair then profile placement then format; minimal-bump by default (`profile=` moves only when strictly needed for validity; `modernize` opts into the behavior-preserving walk, capped at the lower of the behaviour ceiling and the deployment ceiling, the newest profile every major public Galaxy server runs; `allow_behavior_change` lifts the walk's behaviour gate only, `target_profile` caps the walk and may exceed the deployment ceiling); returns upgraded XML, steps applied, the behavior-preserving verdict, `baseline_profile`/`reached_profile`/`stopped_at`/`blocking_codes`/`auto_fixed_codes`, and notes. |
| `check_tool` | Report-only detect over the selected rules; returns the findings (each flagged fixable vs advisory). |
| `convert_help_tool` | Convert an RST `<help>` body to Markdown when provable (profile ≥ 24.2 + render-equivalence gate); returns converted XML or a skip reason. |
| `tokenize_version_tool` | Factor a literal `version="<base>+galaxy<suffix>"` into `@TOOL_VERSION@`/`@VERSION_SUFFIX@` tokens when the expansion-equality gate proves it byte-identical; returns tokenized XML or a skip reason. |
| `find_references_tool` | Read-only: every Cheetah `$name` reference site across the tool's templated sections (returns `{name, occurrences}`). Single-document — references inside imported macro files are the CLI `find-references`. |
| `rename_param_tool` | Rename a parameter across the tool atomically (returns `{old, new, changed, renamed, reason, formatted}`; `formatted` is `null` on a bail). Single-document — the cross-file/imported-macro rename is the CLI `rename-param`. |
| `list_rulesets` | The baked-in rulesets (name / codes / is_default / description). |
| `list_rules` | The baked-in rules (code / summary / family / fixable / rulesets). |

Agents supply content and receive content — the server **never writes to disk**.

## Run

```bash
uv run galaxy-tool-refactor-mcp   # serves over stdio
```

Point an MCP client (e.g. a coding agent) at that command. `list_rulesets` /
`list_rules` let the agent discover the available rulesets and rule codes at
runtime instead of hardcoding them.

See [`docs/decisions.md`](docs/decisions.md) D1 for the design, and
[`docs/vision.md`](docs/vision.md) for the longer-horizon agent-authored-rules
direction (Goal 2, still future).
