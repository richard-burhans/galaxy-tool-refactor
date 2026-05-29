# Design note: macro-aware `format`/`ftype` normalization

**Status:** open question — not implemented. Recorded so the decision is
deliberate rather than defaulted. See `docs/decisions.md` §14 and `PLAN.md`
(24.1 residual).

## Problem

After `Upgrade24_1` (normalize `format`/`ftype`; drop empties), the combined
discovery sweep reaches latest on 8 566 of 8 607 eligible tools. Of the 41 that
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

## Recommendation

**Stay with A for now; reach for D only if macro-library normalization becomes
independently desirable.** The payoff is ~18 tools, concentrated in one shared
macro library plus scattered singletons, and every automated option requires the
pipeline to write files beyond the tool it was handed — a real expansion of the
tool's contract with cross-tool blast radius. That cost is not justified by the
current reach.

B and C are not recommended: B rewrites shared files as a side effect of
formatting a tool, and C needs expansion provenance the library does not track.
If a macro-library formatter is wanted for *other* reasons (consistent macro
formatting across a repo), revisit D and fold this normalization into it as an
explicit, opt-in, repo-scoped step — never into the per-tool canonical pipeline.

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
