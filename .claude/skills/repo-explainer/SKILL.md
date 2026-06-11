---
name: repo-explainer
description: >
  Generate (or refresh) the honest, audience-targeted high-level guide for
  galaxy-tool-refactor under docs/guide/ — explainers for IUC maintainers/authors,
  tool-authoring agents, and PIs/non-technical leadership, plus library/CLI/MCP
  usage docs and an ecosystem leverage map. Distinct from ARCHITECTURE.md (which
  serves contributors). Use when asked to write, regenerate, or extend the
  user-facing / promotional documentation, the audience explainers, or the
  "how to use this as a library/CLI/MCP" guides. The two non-negotiable design
  rules are progressive disclosure ("don't overwhelm the reader") and honesty
  (every present-tense capability claim must trace to a real repo artifact).
---

# repo-explainer

Build the layered guide under `docs/guide/`. This skill is a **generator** — it is
idempotent and refreshable, because the documents are tuned over several iterations
(the maintainer reads them, has non-technical colleagues read them, and we adjust
the skill until the summaries land).

## Two non-negotiable principles

### 1. Don't overwhelm the reader → progressive disclosure

The north star is *the reader is never overwhelmed*. Acceptance test for every page:
**a reader can stop at any layer and feel complete, not shortchanged.**

Four disclosure layers, simple → complex:

| Layer | Content | Who stops here |
|---|---|---|
| **L0 Hook** | one sentence + one figure | everyone |
| **L1 Overview** | ½ page, no jargon, one figure | most PIs |
| **L2 Capabilities & examples** | real before/after, the actual commands | authors / reviewers / agents |
| **L3 Depth** | soundness/caveats, API/MCP reference, links into `ARCHITECTURE.md` + decisions docs | technical + agents |

Apply it **within** each document too: lead with a TL;DR callout, order headings
simple→complex, push lower layers behind `<details>` collapsibles and "Go deeper →"
links. One idea per screen. Figures carry the first explanation so prose can be
skipped. Detail is opt-in, never opt-out.

### 2. Honesty → a grounded capability matrix

Every present-tense capability claim must trace to a **real repo artifact**: a
registry rule code, a CLI/MCP command, or a committed number in `docs/*_stats.md`.
`docs/guide/capabilities.md` is the single source of truth: each capability tagged
**Shipped / Partial / Roadmap** with its source cited. Every other doc draws from it.

- **Roadmap items never appear above L1, and never in present tense.** They live in
  a walled "what this enables next" section. Known roadmap/aspiration items that must
  stay walled: the automated background bot that walks a tool repo and opens fix PRs;
  "replace/streamline IUC reviews"; agent-authored rules (MCP Goal 2); any
  integration not yet built (see the leverage map's Potential/Roadmap tiers).
- **Feature the soundness caveat, don't bury it.** `upgrade` guarantees *structural*
  validity after a profile bump, **not** general behaviour preservation — only where
  per-tool detection proves a change safe. State it up front in technical docs; one
  honest line for leadership. (See `docs/profile_upgrades.md` and the codemod
  decisions on validity-as-oracle.)
- The registry is honest about itself (e.g. per-rule detect/fix status comes straight from registry metadata).
  Trust introspection over recollection.

## Procedure

### Step 1 — Introspect the truth sources (ground every claim)

- `uv run galaxy-tool-refactor rulesets` and `… rules` — the live rule/ruleset set.
- `uv run galaxy-tool-refactor --help` and per-command `--help` — the CLI surface.
- MCP tools: enumerate the `@mcp.tool` functions in
  `galaxy-tool-refactor-mcp/src/.../server.py` (the authoritative set; do not hard-code
  a count). `list_rules(include_upgrade=True)` surfaces the upgrade-only codemods
  GTR007/014–016.
- **Editor / LSP bindings** (a recurring drift point that `leverage.md` and
  `capabilities.md` cite): check `.local/galaxy-language-server` for the built bindings
  (`rename_param_plan` for Rename Symbol / Find References; `tokenize_version_plan` for
  the version-tokenization Code Actions) and their upstream PR status
  (galaxyproject/galaxy-language-server#331 and any sibling). These are built locally or
  open PRs, not merged upstream: tag them Partial/Roadmap, never Shipped.
- Committed corpus numbers: `docs/*_stats.md` (never hand-type a corpus number —
  cite the artifact).
- Tiers/packages: `ARCHITECTURE.md`. Roadmap: each package's `docs/vision.md` +
  `docs/decisions.md` deferred sections, and `docs/macro_handling_architecture.md`.

### Step 2 — Inventory corpus sources (NEVER clone; warn & ask)

This skill **does not clone**. It inventories what is present under `.local/corpus/`
(and whether each clone is shallow — `test -f <repo>/.git/shallow`), buckets by
leverage (see `docs/guide/leverage.md`), and **uses whatever is there.**

For an **absent or shallow high-leverage** source, **warn and print the exact
depth-tuned clone command, then ask** before any heavy network/disk op — do not act
unprompted. Pulling bytes is an explicit, user-consented action.

Be honest about input coverage: if a source is missing, **flag the gap in the
generated output** ("before/after examples limited: `<repo>` not present — clone to
enrich") rather than fabricating or silently narrowing. The leverage map lists the
buckets and suggested depths; the giant `training-material` (~42 GB) is never cloned
(link or sparse-checkout only).

### Step 3 — Build the grounded capability inventory

Refresh `docs/guide/capabilities.md` from Step 1: every capability tagged
Shipped/Partial/Roadmap with its source artifact. This is the honesty backbone the
other docs cite.

### Step 4 — Mine real before/after examples (from present repos only)

Run `check`/`format`/`upgrade` on actual tools in the cloned repos (prefer
`tools-iuc`) and capture genuine diffs. Real examples beat invented ones — and are
more honest. Cite the tool's path. Use git history (where the clone is deep) for
"this is the kind of fix a reviewer asks for" provenance.

### Step 5 — Generate the layered docs + rough figures

Write/refresh under `docs/guide/` (see Layout). Figures are rough **Mermaid/ASCII**
(versionable, diffable) — refine to polished graphics later. Enforce both principles
on every page.

### Step 6 — Cross-pollination (only when the whole set exists)

Documents are built in slices, so a sharp example, a crisp phrasing, or a caveat often
surfaces in a *later* page than the one it most helps. Once all the slices exist, do a
deliberate **back-propagation pass**: re-read the set as a whole and fold each
late-discovered asset up into the earlier page where it lands best (e.g. a real
before/after found while writing `for-maintainers` may belong in `index`'s overview; a
caveat clarified in `soundness` may want a one-liner in `for-leadership`). Keep each
page's disclosure level intact — promote the *idea*, re-pitched for that page's layer,
not the raw text. This pass is intentionally last; don't pre-optimise earlier slices for
material that doesn't exist yet.

### Step 7 — Self-check before finishing

- No present-tense claim lacks a backing artifact (grep your draft against the matrix).
- No Roadmap item sits above L1 or reads as present tense.
- The soundness caveat is present and prominent in technical docs.
- Each page passes the "stop at any layer and feel complete" test.
- Coverage gaps from absent sources are flagged, not hidden.

## Layout (`docs/guide/`)

```
index.md          L0+L1 universal explainer · master pipeline figure · reading paths
for-maintainers.md  L1→L3 · IUC reviewers & authors · mined before/after examples
for-agents.md       L1→L3 · MCP + library substrate · upgrade/verify framework
for-leadership.md   L0→L1 · value-flow figure · walled roadmap · zero jargon
capabilities.md     the grounded Shipped/Partial/Roadmap matrix (single source)
vs-planemo.md       honest, COMPLEMENTARY positioning (planemo is a sibling project)
soundness.md        the upgrade structural-vs-behaviour boundary + caveats
leverage.md         ecosystem leverage map + source manifest + clone policy
usage/ library.md · cli.md · mcp.md   runnable examples per surface
```

`ARCHITECTURE.md` stays the contributor-facing map and is *linked from* L3, not
duplicated.
