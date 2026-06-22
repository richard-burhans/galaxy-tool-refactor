# How this complements planemo

> **TL;DR.** [planemo](https://github.com/galaxyproject/planemo) is the community's
> command-line companion for *developing, linting, testing, and deploying* Galaxy (and
> CWL) tools and workflows. galaxy-tool-refactor doesn't replace any of that — it adds
> the part planemo doesn't focus on: **automatically *fixing* and *upgrading* tool XML**,
> in a canonical IUC style, with an agent-callable interface. They're siblings in the
> Galaxy family, meant to be used together.

## Where they overlap, and where they don't

| | planemo | galaxy-tool-refactor |
|---|---|---|
| Lint / report problems | ✅ (broad: tools, workflows, CWL) | ✅ advisory `check` (tool XML, IUC best practices) |
| **Auto-fix** style/structure | limited | ✅ canonical `format` (idempotent, behaviour-preserving) |
| **Upgrade** a tool's `profile=` with safe repairs | — | ✅ `upgrade` (bounded by [soundness](soundness.md)) |
| Run tool **tests** | ✅ | — |
| **Serve / deploy**, ToolShed publishing | ✅ | — |
| Workflows & CWL | ✅ | — (tool XML only) |
| **Agent / MCP** interface | — | ✅ MCP server + library |
| Evidence base | — | tuned against 9,373 real tools |

planemo *tells you what's wrong*; galaxy-tool-refactor can also *make the fix* and
*move the tool forward*. The overlap is only in detection, and even there the two have
different emphases (planemo is broad across artifact types; this project goes deep on
tool-XML structure and profile upgrades).

The detection overlap is *deliberate*: the `check` tier reimplements the
mechanically-reimplementable `planemo lint` tool-XML linters — the generated
[parity table](../planemo_linter_parity.md) maps all 146 planemo linters to their
GTR coverage rule-by-rule — and the CLI accepts **planemo linter names as rule
aliases** (`--select HelpMissing`, case-insensitive), so a planemo user can select
rules by the names they already know.

## How they fit together

- A maintainer can keep using planemo for testing and deployment, and reach for
  `format`/`upgrade` to do the mechanical cleanup and version bump.
- The most natural future link is for this engine to act as a **fix/upgrade backend**
  behind planemo or the planemo CI action — see the [leverage map](leverage.md). That
  integration is **not built yet**; it's a direction, not a claim.

## On positioning

planemo is a core Galaxy-community project maintained by people we work alongside. This
project is built to **strengthen** that ecosystem — same family, complementary job — not
to compete with it.
