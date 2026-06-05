# Bringing `rename-param` to the editor — galaxy-language-server integration design

> **Status: design note (2026-06-05). Steps 1–2 + cross-file are shipped** —
> the Tier-B API (`galaxy_tool_xml.cheetah_rename.rename_param_plan`, 96.8% corpus parity,
> 0 mismatches; `galaxy-tool-xml/docs/decisions.md` §20) **and** the galaxyls binding,
> including **cross-file** rename across imported macro files (upstream PR
> galaxyproject/galaxy-language-server#331, head `richard-burhans:feat/rename-param`). The
> one remaining gap is the **shared-macro gate** in the editor — see
> [Known limitation](#known-limitation--no-shared-macro-gate-in-the-editor-future-work)
> below. A grounded plan for exposing the
> M5.3 parameter-rename capability (`galaxy_tool_xml.cheetah_rename`, shipped in
> `galaxy-tool-xml/docs/decisions.md` §20) as an **in-editor refactor** through the
> [galaxy-language-server](https://github.com/galaxyproject/galaxy-language-server)
> (galaxyls) — i.e. "right-click a `<param>`, *Rename Symbol*, watch every `$param`
> reference update." All galaxyls citations are against the cloned tree at commit
> `725e48e` (read locally, per the clone-over-websearch standing practice).

## The opportunity

We have, in `galaxy-tool-xml`, the hard part of an editor rename that no XML editor
has: a *semantically correct* notion of where a Galaxy parameter is referenced —
through `#if` directives and dotted `$p.metadata.x` accesses, output labels, by-name
cross-reference attributes, and `<tests>` mirrors — that **refuses to touch** a
`$p` inside `#raw` / `##` / `\$p` / `<help>` prose, and is **atomic** (rewrites
everything or nothing). The CLI `rename-param` already proves it at corpus scale
(93.1% of definitions rename cleanly). The same engine behind an LSP `rename` request
is a compelling, very visual demo.

## What galaxyls already has (and what it lacks)

galaxyls is a **pygls** server (Python ≥3.10) whose deps —
`lxml`, `anytree`, `galaxy-tool-util==26` (`server/requirements.txt`) — *align*
with `galaxy-tool-xml` (lxml-based, Python ≥3.10, `galaxy-util>=24,<27`): no
version conflict, same XML stack.

Already present:

- **An XML document model with position lookup.** `XmlDocument.get_node_at(offset)`
  (`server/galaxyls/services/xml/document.py`) maps a cursor offset to the deepest
  `XmlElement` / `XmlAttribute`; `XmlAttribute` carries its source position, and the
  document exposes `offset_at_position` / element→`Range` helpers. This is the
  offset↔`Position` machinery a rename needs, and we do **not** have it.
- **`TextEdit` / `WorkspaceEdit` plumbing.** The formatter
  (`services/format.py`) returns a whole-document `TextEdit`; the macro-extract
  refactor (`services/tools/refactor.py`) returns a multi-file
  `WorkspaceEdit(changes={uri: [TextEdit, …]})`. The patterns for both
  whole-document and minimal edits already exist.
- **Parameter awareness — but only for *insertion*.** `ParamReferencesProvider`
  (`services/references.py`) builds `$param` / `${cond.param}` strings from
  `<param name>` for the *Insert Param Reference* command. There is **no** "find all
  references" and **no** rename.

Not present (confirmed against `server/galaxyls/server.py` @ `725e48e`): the server
registers completion, hover, **formatting**, definition, document-link, **code-action**
(only `RefactorExtract`), and document-symbol — but **no `textDocument/rename`,
`textDocument/prepareRename`, or `textDocument/references`.**

**Conclusion:** galaxyls owns the *editor mechanics* (offsets, ranges, `WorkspaceEdit`,
document sync); `galaxy-tool-xml` owns the *semantics* (faithful Cheetah lexing, the
real-reference model, the atomic bail logic). The integration is gluing the two — and
the only nontrivial new code is on our side.

## Two integration tiers

### Tier A — whole-document rename (fast, coarse)

The minimum viable path, almost entirely on galaxyls's side:

1. Add `galaxy-tool-xml[cheetah-cdm]` to galaxyls deps.
2. Register `textDocument/prepareRename` + `textDocument/rename`.
3. On `rename`: read the document text, call our `facade.rename_param(text, old=…,
   new=…)`, and return **one whole-document `TextEdit`** with the serialised result
   (galaxyls's formatter already returns exactly this shape).

Pros: a day of work, no new API in our repo. Cons: our facade serialises through fmt
(the only serializer), so the edit **reformats the whole file** (attribute-quote
normalisation, an added XML declaration). Acceptable for a project that already runs
our formatter; jarring as a standalone "rename one symbol" gesture (a clean rename
should not reflow the document).

### Tier B — minimal-diff rename (the right LSP feel; the real work, on our side)

An editor rename should touch **only the renamed tokens**. That needs `rename` to
yield a set of precise `(offset, length, replacement)` edits over the *original*
source, not a reserialised tree. So the core deliverable is a **TextEdit-oriented
rename API in tier 1**, alongside today's tree-mutating one:

```python
# galaxy_tool_xml/cheetah_rename.py (new, sketch)
@dataclass(frozen=True)
class RenameEdit:
    start: int          # character offset into the original document
    end: int            # exclusive
    replacement: str    # the new identifier (just the segment, e.g. "aligned_reads")

@dataclass(frozen=True)
class RenamePlan:
    edits: tuple[RenameEdit, ...]   # disjoint, document-ordered; empty on a bail
    renamed: int
    bailed: bool
    reason: str | None

def rename_param_plan(source: bytes | str, *, old: str, new: str) -> RenamePlan: ...
```

galaxyls then converts each `RenameEdit` offset to a `Range` (it has
`position_at_offset`) and emits a minimal `WorkspaceEdit` — only the renamed tokens
change, every byte else is preserved.

**What's new vs. today's primitive.** The current `rename_param` already computes exact
offsets for the **text sections** (`_segment_edits` returns absolute spans inside
`<command>` / `<configfile>` / attribute-Cheetah values). What it does *not* yet expose
is the **raw source offset of attribute edits** — `name="old"`, `data_ref="old"`,
`label="…"`, the `<tests>` mirrors — because those are applied as lxml tree mutations,
and lxml gives an element's line but not an attribute value's column/offset. Closing
that is the bulk of Tier B:

- **Section-text edits** — already offset-precise; just translate section-local offsets
  to whole-document offsets (add the section element's start offset).
- **Attribute-value edits** — locate the value's source span. Two options: (a) a focused
  raw-text scan (find the element's start tag, then `attr\s*=\s*("|')` + the value), or
  (b) accept galaxyls's `XmlAttribute` position model as the locator and have our API
  return *logical* attribute edits (`element-path`, `attr`, `new-value`) that galaxyls
  resolves to offsets. (a) keeps the engine self-contained and editor-agnostic
  (good for the CLI `--diff` too); (b) is less code but couples us to galaxyls's model.
  Lean (a).

The atomic bail logic, the literal-attribute denylist, the `<tests>`/cross-ref model —
all reused unchanged. Tier B is "return the plan as offsets" + "locate attribute spans,"
not a re-think.

## Shared glue (either tier)

- **`prepareRename`** — accept the request only when the token under the cursor resolves
  to a real parameter: reuse `find_references` / `cheetah_refs` to confirm the
  `$param` / `<param name>` under the offset is a live reference, and **reject** a
  cursor inside `#raw` / a `##` comment / a `${SHELL_VAR}` / `<help>` text. This is the
  "is this renameable?" gate the faithful lexer already answers.
- **Bail UX** — when our rename bails (`shadowed`, `filter-bare-ref`, `mixed-content`,
  `cross-ref-residual`), return an LSP error/empty result with a human reason
  ("Can't safely rename `genome`: it is referenced by bare name in an output filter")
  rather than a silent no-op. The bail taxonomy (§20) maps directly to messages.
- **Scope = tool-local (v1).** Our rename operates on one tool tree and bails if a live
  reference resolves only inside an imported macro file. A cross-file rename (a param
  surfaced through a macro, or a `@TOKEN@`) needs the macro import graph and a
  multi-file `WorkspaceEdit`; galaxyls already does multi-file edits for macro-extract,
  so this is a natural — but separate — follow-on.

## Sequencing

1. **Tier-B API in this repo** — ✅ **shipped.** `rename_param_plan` returns `RenameEdit`s
   via raw-source locators + a decoded→raw walker (CDATA / entity aware, for both text
   bodies and attribute values) and a `sourceline`-aware start-tag anchor (multi-line
   tags). Pinned by unit tests (offsets round-trip: applying the plan re-parses to the same
   tree as `rename_param`) and the `rename-coverage` corpus parity check (same apply/bail
   verdict — 96.8%, 0 mismatches; the remaining 3.2% soundly decline as `locator-failed` on
   exotic anchoring). The load-bearing piece, with the engine.
2. **galaxyls PR** — ✅ **shipped (open, CI green).** Deps, `prepareRename` + `rename` +
   `references` features, offset→`Range` conversion, bail→diagnostic
   (galaxyproject/galaxy-language-server#331; gated only on publishing `galaxy-tool-xml`
   to PyPI to flip the dev pin to a version spec).
3. **(Optional) Tier A** as an interim if an editor demo is wanted — not needed; Tier B
   shipped.
4. **cross-file** rename via the macro import graph — ✅ **shipped** (the binding resolves
   `imported_macro_paths` and emits a multi-file `WorkspaceEdit`), **except** the
   shared-macro gate — see below.

## Open questions

- **Upstream vs. fork.** Is the goal a PR to galaxyls, or a downstream extension? A PR
  means galaxyls takes a `galaxy-tool-xml` dependency — worth confirming the maintainers
  want that coupling vs. galaxyls growing its own (weaker) rename.
- **Formatting policy for Tier A.** If the interim whole-document path ships, does the
  project want the rename to also canonicalise (it will), or must it stay minimal (then
  skip Tier A and wait for Tier B)?
- **`references` too?** `textDocument/references` (find-all-references in the editor) is
  a near-free win once `find_references` is wired — same offset machinery, read-only.
  Likely worth bundling with the rename PR.

## Known limitation — no shared-macro gate in the editor (future work)

The shipped galaxyls cross-file rename (#331) rewrites an imported macro **whenever the
open tool references the parameter through it**, with no check on whether *other* tools
also import that macro. For a **sole-owned** macro this is exactly right. For a **shared**
macro it is incomplete: the rename updates the open tool and the macro, but the macro's
*other* importers still define the old name — each would need the same rename, and they do
not appear in the `WorkspaceEdit` the user reviews. So an editor rename of a parameter
whose reference lives in a shared macro can leave sibling tools inconsistent.

This is the editor counterpart of the CLI's shared-macro gate, which the CLI **does**
enforce (`galaxy-tool-refactor-registry.bundle_rename`, registry `docs/decisions.md`
D12–D14):

- `rename-param --repo-root` skips a shared macro (sole-owned only), failing closed when
  the repo root does not cover it (D13);
- `rename-param --across-importers` renames every importer in lockstep when they all agree
  (the consensus path, D14).

**Why it is not in the editor yet.** The gate needs the *reverse* import map — which other
tools import a given macro — which is a workspace-wide question. The CLI builds it with
`build_importer_map(repo_root)`. That logic lives in the **registry tier**, which the
galaxyls binding deliberately does **not** depend on (it depends only on `galaxy-tool-xml`,
the parsing engine, to keep galaxyls' published metadata free of a heavyweight dep).

**Two ways to close it, if we choose to:**

1. **Lightweight in-binding scan.** Walk the LSP `workspace` root for tool files and resolve
   each one's `imported_macro_paths` (already available from `galaxy-tool-xml`) to build the
   reverse map in the binding — no new dependency, but it duplicates a slice of
   `build_importer_map`, and a workspace-wide walk on every rename has a latency cost worth
   caching/invalidating on file change.
2. **Depend on the registry.** Make `galaxy-tool-refactor-registry` an optional engine the
   same way `galaxy-tool-xml` is, and call `rename_param_bundle` / `rename_param_consensus`
   directly — full parity with the CLI (sole-owned skip + consensus), at the cost of a
   second optional dependency and adapting the registry's path/bytes I/O to LSP
   document/URI + offset edits (the registry returns serialized bytes, not minimal offset
   edits, so a minimal-`WorkspaceEdit` path would still need the per-file `rename_param_plan`).

Either way, the editor would also want to *surface* a shared-macro rename (e.g. a warning,
or a "rename across N importers?" prompt) rather than silently widen the edit. Until then,
the binding documents the caveat (in its module docstring and the galaxyls changelog), and
the **CLI is the safe path for shared macros**. No corpus sizing has been done for how often
an editor rename would hit a shared macro specifically (the CLI's `rename-macro-spread`
measure sizes the tool-driven case: 0.3% of corpus renames touch a shared macro).

## Provenance

galaxyls facts read from the local clone at
`https://github.com/galaxyproject/galaxy-language-server` @ `725e48e`
(`server/galaxyls/server.py`, `services/xml/document.py`, `services/references.py`,
`services/format.py`, `services/tools/refactor.py`, `server/requirements.txt`). The
rename engine is `galaxy_tool_xml.cheetah_rename` (`../galaxy-tool-xml/docs/decisions.md`
§20); the roadmap home is `cheetah_section_editing.md` (M5.3).
