# Leverage map — where this fits in the Galaxy ecosystem

> **TL;DR.** This project is a per-tool engine. Its value multiplies when it plugs into
> the places Galaxy tools are *written, reviewed, published, and catalogued*. This page
> maps those points — honestly tagged **Exists / Potential / Roadmap** — and lists the
> source repositories the `repo-explainer` skill draws on for examples and evidence.
> Nothing here claims an integration that has been built unless it says **Exists**.

## Integration points

Where the `format` / `upgrade` / `check` engine could deliver value, and how mature that
connection is today:

| Where | What it would do | Maturity |
|---|---|---|
| **AI agents (MCP)** | Agents call `format`/`upgrade`/`check`/`list_*` directly while authoring or reviewing tools. | **Exists** — the MCP server ships (vision Goal 1). |
| **`galaxy-mcp`** (sibling MCP) | Coexist in the agent ecosystem; complementary surface. | **Exists** (separate project) — positioning, not a built link. |
| **`galaxy-language-server`** (editor LSP) | Surface fixes as editor quick-fixes — reach authors at *write-time*, before a PR exists. | 🟡 **In progress** — the Tier-B rename API (`rename_param_plan`) shipped; a "Rename Symbol" + "Find References" binding is an open *draft* PR (galaxyproject/galaxy-language-server#331), gated on publishing `galaxy-tool-xml` to PyPI. |
| **`planemo` / `planemo-ci-action`** | Run as a fix/upgrade backend alongside planemo's lint/test; feed the Action that lints changed-tool PRs. | 🔭 **Potential** — the most concrete "streamline reviews" path. |
| **`gx-tool-db` / `galaxy_codex`** (tool catalogs) | Feed check/upgrade signals at catalog scale for community-wide tool-health views. | 🔭 **Potential**. |
| **Galaxy core / ToolShed** | Publish-time or load-time validation & repair. | 🔭 **Potential**. |
| **Batch fix-PR automation** | Walk a tool collection and open fix PRs in reviewable batches. | 🔭 **Roadmap** — engine exists; orchestration does not. |
| **Beyond Galaxy** (Dockstore, bio.tools, bioconda; CWL) | Tool-packaging & workflow ecosystems. | 🔭 **Roadmap**. |

See [vs planemo](vs-planemo.md) for why the planemo relationship is **complementary**.

## Source repositories (what the skill mines)

The `repo-explainer` skill draws real before/after examples and evidence from cloned
tool repositories. It buckets them by leverage and **never clones automatically** — see
the policy below.

| Repo | Bucket | Suggested depth | Why |
|---|---|---|---|
| `tools-iuc` | tool corpus (primary) | deep (history) | the canonical IUC tools + PR history for real examples |
| `tools-devteam` | tool corpus | deep | Galaxy-team tools |
| `usegalaxy-tools` | tool corpus | deep | the usegalaxy.* common set |
| `galaxy-tool-repository-template` | authoring | deep | the canonical "new tool" starting point |
| bgruening, tools-galaxyp, RECETOX, tools-ecology, tools-metabolomics, tools-artbio, phac-nml | tool corpus (other communities) | deep | breadth of authoring styles (already in `corpus_sources.json`) |
| `planemo`, `planemo-ci-action` | integration | deep (small) | positioning + the CI-review path |
| `galaxy-language-server` | integration | deep (small) | the editor quick-fix path |
| `galaxy-mcp` | integration | deep (small) | agent-ecosystem positioning |
| `gx-tool-db` | catalog | deep (small) | catalog-scale signals |
| `galaxy` (core) | reference | **shallow** (reuse `.local/galaxy-src`) | source-of-truth for runtime behaviour; large |
| `galaxy_codex` | catalog | shallow | large catalog repo |
| `training-material` | education | **never clone** (~42 GB) | link, or sparse-checkout a tutorial path only if needed |

## Clone policy (the skill never clones for you)

The `repo-explainer` skill is **side-effect-free by default**. On each run it:

1. **Inventories** what's present under `.local/corpus/` and whether each clone is shallow.
2. **Uses whatever is there** to generate the guide.
3. For an **absent or shallow high-leverage** source, **warns and prints the exact
   depth-tuned clone command, then asks** — it does not pull bytes unprompted.
4. **Flags the coverage gap in the output** (e.g. "examples limited: `planemo-ci-action`
   not present — clone to enrich") rather than fabricating or silently narrowing.

Pulling a large repo with history is an explicit, human-consented action.

<details>
<summary>Note: the leverage manifest vs. <code>corpus_sources.json</code></summary>

`corpus_sources.json` (workspace root) is the load-bearing seed list for the corpus
sweeps and is consumed by `scripts/corpus_check.py`. The bucket/leverage/depth metadata
above is kept here in the guide for now to avoid coupling the docs effort to that
load-bearing file; a later change can fold `purpose` / `leverage` / `depth` fields into
`corpus_sources.json` once the sweep tooling is updated to tolerate them.
</details>
