# Design note: macro-aware `format`/`ftype` normalization

**Status:** **Phase 2a implemented (2026-06-03)** as the opt-in **option D** below —
the `galaxy-tool-refactor normalize-macros` command over
`galaxy_tool_refactor_registry.macro_datatype` (registry `docs/decisions.md` D8;
`docs/macro_handling_architecture.md` §6c). The reproducible residual is **15 tools**
(6 via a shared defining file, 9 sole-owned; `docs/macro_format_residual_stats.md`,
`scripts/measure.py macro-format-residual`) — the "~18" below was an ad-hoc
2026-05-29 by-shape estimate; the sound count (strict profile increase after
normalizing the bundle) is 15. The rest of this note records the option analysis that
led there. See `docs/decisions.md` §14 and `PLAN.md` (24.1 residual).

## Problem

After `Upgrade24_1` (normalize `format`/`ftype`; drop empties), the combined
discovery sweep reaches latest on 8,566 of 8,607 eligible tools. Of the 41 that
remain below latest, **~18 are blocked only because a coercible `format`/`ftype`
value lives in an imported macro file** rather than in the tool's own tree.

Concretely: `tools-ecology/gdal/gdal_merge.xml` validates at 24.1 but not 24.2
because an expanded `<data format="GTiff">` trips the 24.2 pattern facet
(`GTiff` → `gtiff` would pass). `GTiff` appears **zero times** in
`gdal_merge.xml`; it lives in `gdal_macros.xml`, which the tool `<import>`s.
`Upgrade24_1` lowercases `format`/`ftype` — but only on the tool's own tree, so
it never sees the value and the tool stays stuck. The give-away in the residual
is values that are still uppercase *after* a codemod that lowercases.

These are not bugs in the tool author's intent — `GTiff`, `Rdata`, `GenBank`,
`FASTA` are real datatypes whose canonical Galaxy extension is lowercase. The
fix is mechanical; it is just defined in the wrong file for the current tooling
to reach.

### Why it's unreachable today (the single-file model)

- A `CodemodCommand` runs against one `Module` — the **tool file's** unexpanded
  lxml tree. It never parses the macro files as documents of their own.
- Macros are a *validation-time* concern: `validate_tool` expands into a
  throwaway tree (`expand_from_tree`) that is validated and discarded; the
  expansion is never written back. So even codemods that ran on the expanded
  tree couldn't persist the change.
- fmt writes one file per input and **skips any file whose root is not
  `<tool>`** (`_looks_like_tool_root` in `cli.py`), so a `<macros>`-root file is
  never rewritten — by design, since fmt formats tools, not macro libraries.

So the offending value sits in a file that no part of the pipeline mutates.

### Empirical shape of the gap (corpus, 2026-05-29)

Reproduced ad hoc against the combined corpus (apply `Upgrade24_1`, validate at
24.2, locate residual coercible values in sibling `*.xml`):

- **18 tools** blocked by a coercible value in an imported file.
- The values concentrate in a few macro libraries: `gdal_macros.xml` is
  `<import>`ed by **4** sibling gdal tools (one edit would fix four — and affect
  four); `pampa_macros.xml` by 2; the rest are per-tool `macros.xml`/`macro.xml`
  singletons. Several tools are also duplicated across the github and toolshed
  sources, each copy carrying its own macro file.

The high-leverage case (`gdal_macros.xml`) is exactly the one that exposes the
core hazard below: a macro file is a **shared dependency**.

## Why this isn't a one-step `upgrade_vN`

Every other shipped upgrade codemod (`Upgrade19_01`, `Upgrade24_0`,
`Upgrade24_1`, `Upgrade25_1`) is a self-contained edit to a single tool tree.
Reaching macro-file values breaks two invariants at once:

1. **One file in, one file out.** The change must land in a *different* file
   from the tool being processed — and that file is shared.
2. **Shared blast radius.** Editing `gdal_macros.xml` changes the expansion of
   *every* tool that imports it, including tools not in the current run and
   tools not in the corpus. A per-tool codemod has no view of that fan-out.

## Options

### A. Status quo — report, don't auto-fix (lowest risk)

The discovery sweep already names every stuck tool and version. Maintainers
lowercase the macro value by hand (a one-character edit). The pipeline stays
strictly single-file; no new blast radius.

- **Pro:** zero new risk; the fix is trivial for a human who owns the repo.
- **Con:** ~18 corpus tools stay below latest under the automated pipeline.

### B. Format macro files in place as their own documents

Teach fmt (or a sibling command) to also process `<macros>`-root files,
applying a macro-appropriate subset of normalization to `format`/`ftype`
attributes found there.

- **Pro:** fixes the value at its source; every importer benefits; one edit
  clears the `gdal_macros.xml` cluster of 4.
- **Con:** a macro file is not a tool tree — it is a bag of `<xml>` / `<token>`
  templates plus Cheetah. The visitor framework assumes a `<tool>` root and
  tool-shaped children; a macro-file pass needs its own, narrower model. And a
  value supplied *through* a token (`format="@FORMAT@"`, the token defined per
  importing tool) cannot be normalized in the macro — the literal there is a
  placeholder, not a datatype. Most damaging: rewriting a shared file from a
  run that was asked to format one tool is a surprising, hard-to-review side
  effect, and changes tools outside the run.

### C. Normalize the expanded tree, then write deltas back to source files

Expand, normalize on the expanded tree (so every value is reachable), then map
each changed attribute back to the file that defined it and rewrite those files.

- **Pro:** per-tool-correct; reaches both macro and tool values; handles
  token-supplied values because it edits the post-expansion result's *origin*.
- **Con:** requires provenance — which file/line each expanded node came from.
  `macros.py`/lxml expansion does not preserve that today; adding it is
  invasive. Still multi-file write with the same shared-file hazard as B (two
  tools sharing a macro each compute a rewrite, possibly conflicting), plus a
  token whose value differs per importer has no single correct macro-file edit.

### D. Opt-in, repo-level "normalize macro library" pass

A separate command (not part of the per-tool `CANONICAL_CODEMODS` pipeline)
that, given a repository, scans its macro files once and lowercases/strips
**literal** `format`/`ftype` attribute values (skipping `@TOKEN@` placeholders).
Run explicitly by a maintainer, once per macro file.

- **Pro:** clean separation from the per-tool flow; idempotent; fixes the shared
  case exactly once; the explicit, repo-scoped invocation makes the cross-file
  blast radius intentional rather than a side effect of formatting one tool.
- **Con:** still a cross-file editor with shared-importer reach; needs a
  macro-file parser/visitor (the narrower model from B); expands the project's
  surface area for a modest, concentrated payoff.

## Recommendation — superseded: option D shipped (2026-06-03)

The original recommendation was "stay with A; reach for D only if macro-library
normalization becomes independently desirable." We chose **D** after all, as the
first consumer of the macro write-back epic
(`docs/macro_handling_architecture.md` §6c): the opt-in, repo-scoped
`normalize-macros` command, **never** part of the per-tool canonical pipeline, so
the cross-file blast radius is an explicit, deliberate invocation rather than a side
effect of formatting one tool. The key enabler was recognising the edit is
**validity-safe without a gate** — lowercasing a literal `format`/`ftype` is the
exact canonicalization `Upgrade24_1` already applies tool-tree-wide, and it only
satisfies the 24.2 pattern facet, so it cannot regress any importer (registry
`docs/decisions.md` D8). That removes D's main worry (rewriting a shared file is now
provably safe for every importer), leaving only the need to make the invocation
explicit — which the separate command does.

B and C remain not done: B would rewrite shared files as a *side effect of formatting
a tool* (D fixes this by being a separate command); C needs the general expansion
provenance the library still does not track (Phase 2b, deferred). A token-supplied
value (`format="@FORMAT@"`) still has no single correct macro-file edit and is left
to Phase 2b.

### What would change the calculus

- The macro-unreachable count growing materially beyond ~18 (e.g. a new schema
  delta that bites macro-defined attributes broadly).
- An independent decision to format macro libraries (then D's parser/visitor
  cost is already paid and this normalization is a small addition).
- Provenance landing in `macros.py` for an unrelated reason (then C's main
  obstacle is gone).

Until one of those holds, the discovery sweep reporting these tools is the
right behaviour: it surfaces the gap without the pipeline silently reaching into
shared files.
