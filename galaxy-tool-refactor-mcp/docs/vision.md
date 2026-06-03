# Vision: `galaxy-tool-refactor` for AI agents (MCP server + agent-authored rules)

**Status:** **Goal 1 (the MCP server) is shipped** — see `docs/decisions.md` D1;
this section now describes what was built. **Goal 2 (agent-authored rules)
remains forward-looking** — recorded so the facade does not foreclose it. The
current locked decision — "adding rules is a developer task; no user-defined
rules" — still governs; Goal 2 is the relaxation path if/when desired.

## Goal 1 — `galaxy-tool-refactor` as a tool for agents (the MCP server) — SHIPPED

The MCP server (this package) wraps the `galaxy-tool-refactor-registry`
facade so coding agents can:

- **Discover** what the tool can do: `list_presets()` → preset names +
  descriptions, `list_rules()` → code / summary / family / fixable-vs-advisory /
  which presets include each rule. These map directly onto MCP tool descriptions
  and enum-valued arguments, so an agent learns the available presets/rules at
  runtime instead of hardcoding them.
- **Run** `format` / `upgrade` / `check` over content the agent supplies (raw
  XML, not necessarily a path), with a chosen preset or explicit
  `--select`/`--ignore` code set, and receive **structured results**
  (`FormatResult` / `UpgradeResult` / `DetectResult`: formatted bytes, the
  `Violation`s found, upgrade steps applied, advisory notes).

This is *why* the facade is library-first and structured: the MCP server is a
thin adapter (structured args in, structured results out), never a subprocess
that scrapes CLI text. The facade already honors the needed shape — content-or-
path input, structured results, disk writes only on explicit request, and
introspection — so the server is mostly an MCP-protocol binding over it.

The server is a **tier-4 sibling of the CLI**: both depend on the registry
facade; orchestration stays in the facade so the CLI and the MCP server share one
core and cannot drift.

## Goal 2 — agents authoring their own codemod / fmt extensions

Longer-horizon: let a coding agent write a new rule — a
`CodemodCommand`/`Rule` subclass with its `detect`/`apply` + a `RuleMeta` — and
have the framework discover and run it alongside the baked-in rules.

The seam already exists: the codemod tier's **detect-primitive**
`CodemodCommand` and the registry's **`RuleHandle`** adapter are the natural
authoring/integration contract — an agent targets `detect()` (+ `apply()` for a
fixable rule) and a `RuleMeta` code, and the registry wraps it into a `RuleHandle`
exactly like a built-in.

Open questions to resolve **later** (do not solve now; just avoid foreclosing):

1. **Discovery.** Stay with the current hardcoded family registries
   (`coded_codemods()` / `all_rules()` / `all_checks()`, developer-only) or grow
   an entry-point/plugin mechanism so third-party rule packages register
   themselves. The unified registry is the single place that mechanism would
   plug into.
2. **Authoring contract.** Pin down the minimum an agent must supply (tag
   dispatch method names, `RuleMeta` fields, idempotence expectations) and
   surface it as documentation / a template the MCP server can hand back.
3. **QA gating.** How an agent-authored rule earns trust before it ships — the
   corpus idempotence / post-validity sweeps (`scripts/corpus_check.py`) are the
   existing gate; an authored rule would run the same `codemod`/`rules` sweep.
4. **Trust / sandboxing.** Running an agent-authored `apply` thunk executes
   third-party code. A plugin path needs a trust boundary (vetted packages,
   opt-in, or a sandbox) — out of scope until the plugin mechanism is real.

## Design constraints this places on the registry facade (honored today)

- Library-first: no `click` / `sys.exit` / stdout-scraping in the call path.
- Structured results and structured introspection (`list_presets`/`list_rules`).
- Content-or-path input; never writes to disk unless a `write_path` is given.
- The `RuleHandle` is the uniform, code-addressable unit an MCP tool or a plugin
  loader can enumerate and invoke without knowing which tier a rule came from.
