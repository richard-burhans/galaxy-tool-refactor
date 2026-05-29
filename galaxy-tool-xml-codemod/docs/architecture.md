# A LibCST-shaped codemod tool over `galaxy-tool-xml`

> **Historical design note — predates implementation.** This is a working
> copy of the original tier-2 design (package names "(name TBD)", "does not
> preserve whitespace", etc. reflect that draft). The shipped shape is
> recorded in `docs/decisions.md` and `PLAN.md`; consult those for current
> behaviour. Retained for design rationale.

## Context

The Galaxy tool tooling is being designed as **three separate packages**, each
with a single concern:

| Tier | Package | Status | Job |
|------|---------|--------|-----|
| 1 | `galaxy-tool-xml` | exists (this repo) | Parse · validate · typed view. No serializer. Mutable lxml tree is the source of truth. |
| 2 | `galaxy-tool-codemod` *(name TBD)* | new | LibCST-shaped framework for **structural refactors**. Does **not** preserve whitespace / quote style / shorthand. |
| 3 | `galaxy-tool-fmt` *(name TBD)* | new | `black`-like, opinionated. The **only** thing that writes XML to disk. Imposes canonical formatting on whatever tier 2 produced. |

Inversion vs. LibCST: LibCST has to do surgical edits *and* trivia
preservation in one library because Python has no universal autoformatter
downstream. Galaxy tooling does (tier 3), so tier 2 is free to drop trivia.
That's what lets the codemod tool be small.

This document recommends the codemod tool's API direction and the (small)
additive shape changes in this repo that smooth its job.

## TL;DR

**Build the codemod tool as a separate package depending on
`galaxy-tool-xml`. Its visitor concept is *inspired by* LibCST but the
surface is lxml-shaped: typed cursors that mutate in place, not
pure-functional reconstruction.** Reuse LibCST's *names* for the
codemod harness, context, matchers, and `CodemodTest`. Drop
`leave_X(original, updated) -> X`, `with_changes`, `RemoveFromParent`,
`FlattenSentinel`, and `MaybeSentinel` — those presuppose immutable
nodes and don't fit lxml. The node *taxonomy* diverges (Galaxy XML
elements, not Python grammar; and there are 28 of them, one per
vendored profile). The current `galaxy-tool-xml` already supplies the
foundational primitives the codemod tool needs; add 3 small,
non-breaking items here and put everything else in the new tool. Do
**not** vendor LibCST's trivia-preserving node model — tier 3 owns
trivia, and lxml's in-place mutation already preserves comments and
CDATA on every subtree the codemod does not touch.

## What `galaxy-tool-xml` supplies today (enough to start)

| Need | Available via | Where |
|------|---------------|-------|
| Tree access & mutation | `ToolDocument.tree` / `.root` + lxml API | `document.py:77,82` |
| Typed structural view (profile-bound) | `ToolDocument.model()` — xsdata dataclasses for the tool's own resolved profile | `document.py:102-116` |
| Cross-profile typing | `AnyTool` (tagged union of every per-profile `Tool`) + `tool_class(version)` registry | `models/any_tool.py`, `models/registry.py` |
| Profile resolution | `ToolDocument.profile`, `newest_valid_profile` | `document.py:97`, `binding.py:285` |
| Post-transform validation | `validate_tool` | `binding.py:200` |
| Macro handling | `has_macros`, `strip_macros`, `expand_from_tree`, `expand_from_path` | `macros.py` |
| Source lines for diagnostics | `element.sourceline` (lxml built-in) | n/a |
| Near-miss vocabulary (profile-bound) | `suggest_corrections` | `corrections.py` |

## The codemod tool: lxml-native, LibCST-inspired

### Public surface — concept-by-concept

Reuse LibCST's *concepts* (visitors, matchers, harness, test
assertions) where they're independent of immutability. Replace its
pure-functional reshape primitives with lxml-native cursor mutations.

| LibCST | Codemod tool analog | Why |
|--------|---------------------|-----|
| `cst.parse_module(source)` | `parse_module(source)` — returns a cursor over the tool root | Named `parse_module` (not `parse_tool`) to avoid a name clash with `galaxy_tool_xml.binding.parse_tool`. |
| `cst.CSTVisitor`, `cst.CSTTransformer` | `ToolVisitor` | One class — there is no transformer/visitor split when mutation is in-place. |
| `visit_X(node) -> bool \| None` | same, pre-order; return `False` to skip children. May mutate via cursor methods. | |
| `leave_X(original, updated) -> X` | — | Dropped. No `updated` to return when the cursor mutated in place; the walk just unwinds. |
| `node.with_changes(field=...)` | typed setters: `node.set_name("x")`, `node.set_attribute("type", "text")`, etc. — mutate the underlying lxml element | `with_changes` would have to either lie about returning a new instance or lie about being frozen. Typed setters are honest. |
| `cst.RemoveFromParent()` | `node.remove()` — cursor method, mutates immediately | Sentinel returns don't fit; a visitor that removes its own node must also return `False` to halt descent. |
| `cst.FlattenSentinel((a, b))` | `node.replace_with_siblings([a, b, c])` | Same reason. |
| `cst.codemod.CodemodCommand` | `CodemodCommand` | Concept transfers. |
| `cst.codemod.VisitorBasedCodemodCommand` | `VisitorBasedCodemodCommand` | Concept transfers. |
| `cst.codemod.CodemodContext` | `CodemodContext` | Concept transfers. |
| `cst.matchers.matches(node, m.Call(...))` | `matchers.matches(node, m.Param(...))` | Matcher language is independent of mutation model. |
| `CodemodTest.assertCodemod(before, after)` | same — renders the post-codemod tree via tier 3 for comparison | |
| `python -m libcst.tool codemod path.to.Foo target/` | `galaxy-tool-codemod apply path.to.Foo target/` | |

This is **not** a LibCST drop-in. A developer fluent in LibCST will
recognise the visitor concept, the matcher language, and the harness;
they will *not* find `with_changes`, `leave_X`, sentinel returns, or
pure-functional semantics. Document this loudly in the codemod tool's
authoring guide — it is the single biggest source of expectation
mismatch.

### Node taxonomy — per-XSD-type class explosion, ×28 profiles

The xsdata-generated typed model is shaped by **XSD complex types**:
xsdata emits one class per complex type, not per element tag. Because
the Galaxy XSD defines a distinct complex type for each parent context
in which `<when>` (or `<param>`, `<option>`, etc.) can appear, the
proliferation is *intrinsic to the schema*. `_codegen.py:59` sets
`unnest_classes=True` which makes the classes flat top-level (e.g.
`Param`, `Inputs`, `Conditional`, `ConfigFile`, `ChangeFormatWhen`,
`ActionsConditionalWhen`, `ConditionalWhen`); re-nesting them would
give shorter names but the multiplicity would remain.

A concrete consequence: there is no single `When` class.
`models/v23_2/galaxy.py` exposes three (`ChangeFormatWhen`,
`ActionsConditionalWhen`, `ConditionalWhen`). `models/v26_1/galaxy.py`
has 177 classes total, up from 100 in `v16_10`. The codemod tool sees
one model package per vendored profile (`models/v16_10` …
`models/v26_1`), via `tool_class(version)`, so a uniform cursor
surface either pins to one profile or normalises across all 28.

Two design responses:

  (a) the codemod tool **uses xsdata's class names directly** — accurate
      but means `visit_ChangeFormatWhen`, `visit_ActionsConditionalWhen`
      and friends, and either writes one codemod per profile or
      hard-codes a single profile per codemod; or
  (b) the codemod tool **builds a normalized cursor layer** that
      collapses parent-specialized types into single conceptual nodes
      (`When`, `Param`, etc.) with a `parent_context` accessor, and
      bridges the per-profile class differences. Real work to author
      and maintain — scaling the cursor layer across 28 profiles is
      its own design question, deferred here.

Recommend (b) as the long-term direction, (a) as an acceptable v0. This
design choice belongs in the codemod tool; `galaxy-tool-xml` exposes
the per-profile xsdata models (and `AnyTool`) and leaves the cursor
layer to tier 2.

### Galaxy-specific concerns (do not exist in LibCST)

- **Cheetah-aware reference resolution.** Most interesting refactors
  touch the `<command>` and `<configfile>` CDATA bodies (Cheetah
  templates). A refactor that renames `<param name="x">` must update
  every `${x}` in `<command>`. This needs a Cheetah parser. The codemod
  tool owns this — use Galaxy's own Cheetah utilities rather than
  writing one. LibCST's scope/metadata providers are the conceptual
  analog but the parser itself is Galaxy-specific.
- **Macro mode per codemod.** Some refactors target the pre-expansion
  source (rename a macro); others target the post-expansion structure
  (find every effective `<param>` regardless of origin). The codemod
  base class should declare its mode (`expand_first` vs. `source_only`)
  and the harness invokes `expand_from_tree`/`expand_from_path`
  accordingly. Mixing the two without provenance metadata (see additive
  item 2 below) is unsafe.

### Operational concerns

- **Multi-file edit orchestration.** A refactor that spans the tool +
  its imported macro files needs to load each as its own `ToolDocument`,
  mutate each, and hand each off to tier 3 for emit. The codemod tool
  coordinates; `galaxy-tool-xml` supplies the file list via additive
  item 1.

- **Atomicity via deep-copy snapshot.** LibCST gets free atomicity from
  immutable nodes; lxml is mutation-oriented and that's the model we
  embrace. Atomicity comes from a snapshot, not from immutability:

  1. **Harness deep-copies** the root `ToolDocument.tree` on entry
     (`copy.deepcopy`, fast for tool-sized trees) and runs the codemod
     against the copy. On codemod failure (exception, or a post-codemod
     validation regression that breaks the configured drift policy),
     discard the copy; on success, the copy becomes the new source of
     truth handed to tier 3.
  2. **Cursor mutations apply immediately** to the (copied) lxml tree.
     `param.set_name("x")` does `param._element.set("name", "x")`;
     `param.remove()` does `parent.remove(param._element)` and signals
     the walk to stop descending. There is no "new node to return"
     because the change is already in the tree.

  **Consequence — preservation for free.** Every element the codemod
  does *not* touch keeps its CDATA, comments, attribute order, and
  `sourceline` exactly. This is the strongest argument against a
  pure-functional reconstruction model: that model would have to
  reinvent trivia carrying on every cursor type, or drop comments at
  the cursor boundary. With in-place mutation, the foundation
  library's existing preservation guarantee carries straight through.

  **Visitor-walk constraint.** A cursor that calls `.remove()` or
  `.replace_with_siblings(...)` on its own node must return `False`
  from its `visit_X` so the walk doesn't descend into a node that no
  longer exists in the tree. The framework should defensively detect
  orphaned cursors and raise rather than silently descend.

- **Post-transform validation + profile comparison.** The harness must
  run `validate_tool` after every codemod, and additionally compute
  before-vs.-after profile state, both already supported by
  `galaxy-tool-xml`:

  - `before = document.profile` (declared) and
    `before_valid = newest_valid_profile(document)` (actually required).
  - Run the codemod on the deep-copy.
  - `after_valid = newest_valid_profile(new_document)`.
  - Compare under a configurable **profile-drift mode**:
    - `warn` (default) — emit a warning when `after_valid` is newer
      than `before`, but leave the `profile=` attribute alone.
    - `auto-bump` — silently set the `profile=` attribute to
      `after_valid` (or to the codemod's own declared minimum).
    - `error` — fail the codemod if drift occurs.
    - `after_valid is None` → always fail; the codemod produced an
      un-validating tool.
    - `after_valid` older than `before` → never auto-downgrade;
      surface as informational only.

  Default to `warn` because the declared profile is a maintainer
  *contract* about minimum required Galaxy version, not a passive
  best-fit; silently bumping it can violate that contract. The
  comparison logic is the codemod harness's job — `galaxy-tool-xml`
  already supplies both `ToolDocument.profile` and
  `newest_valid_profile` (`binding.py:285`); no additive item here.

- **Codemod composition.** LibCST supports running codemods in
  sequence. The Galaxy harness should too, re-validating + checking
  profile drift between steps and surfacing which codemod in the
  pipeline introduced a regression.

- **Cursor ↔ lxml identity.** Each cursor holds a direct reference to
  its lxml element (`cursor._element`), so `sourceline`, attribute
  reads, and diff display are O(1). Within a single codemod run the
  mapping is stable as long as the cursor's element has not been
  removed. **Across passes** — particularly if tier 3 serialises and
  the next codemod re-parses — `id(element)`-keyed side tables break;
  multi-pass pipelines that need cross-pass provenance must use a
  stable key (an internal attribute, or a path-based locator
  recomputed per pass). See provenance side-table item 2 below.

- **Hand-off contract.** After a successful codemod run, the harness
  hands each mutated `ToolDocument` to tier 3, which serialises as the
  user's edit. The codemod tool itself **never** writes XML to disk as
  the user's edit; it may serialise internally (`assertCodemod` test
  comparisons, diff display) but those go through tier 3 too, so the
  formatting they show matches what the user would see on disk.

### Naming — resolved

The codemod tool's entry point is **`parse_module(source)`**, not
`parse_tool`. Reasons: (1) `galaxy_tool_xml.binding.parse_tool` already
exists with a different return type (`ParseResult`), and same-named
imports from different packages are a debugging tax; (2) `parse_module`
mirrors LibCST's `cst.parse_module`, where "module" is the closest
analog for "a single parseable unit" — even though we've otherwise
dropped the LibCST mirror, the name resonates with the developers
most likely to recognise the shape.

## What `galaxy-tool-xml` should add (small, additive, non-breaking)

Goal: anything the codemod tool would otherwise reach into private
internals for, expose as a real public API. Public-API budget in
`README.md:52-60` is unchanged except for additions.

| # | Item | Critical file | Now / later |
|---|------|---------------|-------------|
| 1 | **Macro file resolution** — given a `ToolDocument`, return the set of `Path`s involved (the tool + every transitively-imported macro file). Codemods that touch macros need this to know which files to edit. | `src/galaxy_tool_xml/macros.py` | **now** |
| 2 | **Macro provenance per element** — for each element in an expanded tree, record which source file (and which macro definition) it came from. Lets codemods decide "edit the macro vs. inline vs. refuse." Side table keyed by a stable identifier: `id(element)` is fine within a single process but breaks across a tier-3 round-trip, so the API should accept either a cursor (in-process) or a path-based locator (cross-process). | `src/galaxy_tool_xml/macros.py` | later (wait for a codemod that needs it) |
| 3 | **Document the trivia contract** in `README.md` Architecture section. Codemod authors need to know what survives the parse → mutate → re-parse cycle (structure, attrs & order, comments, CDATA, text, encoding, `sourceline`) and what does not (indentation, blank lines, quote style, empty-element shorthand, attribute spacing, macro provenance until item 2 ships). | `README.md` | **now** |
| 4 | **Pin the trivia contract in tests** — extend `scripts/corpus_check.py::check_roundtrip` with explicit asserts for each preserved item, so a regression in `galaxy-tool-xml` cannot silently break the codemod tool's assumptions. | `scripts/corpus_check.py` | **now** |

Visitor/transformer base classes do **not** live in this repo — they
belong in the codemod tool, on top of the typed model, because the visitor
API needs `with_changes`/`RemoveFromParent`/etc. and those are codemod-tool
concepts. `galaxy-tool-xml` provides the *node taxonomy*; the codemod tool
provides the *traversal/mutation framework*.

## Risks

- **Not a LibCST drop-in.** The visitor concept and matcher language
  are inspired by LibCST, but `with_changes`, `leave_X`,
  `RemoveFromParent`-as-sentinel, `FlattenSentinel`, and pure-
  functional semantics are *gone* — replaced by typed cursor
  mutations. Document this in the codemod tool's authoring guide; it
  is the single biggest source of expectation mismatch for
  LibCST-fluent developers.
- **Cheetah parsing is the long pole.** Most interesting refactors cross
  the XML→Cheetah boundary. Treat the Cheetah reference resolver as a
  first-class subsystem of the codemod tool, not an afterthought. A v1
  can ship with only refactors that stay inside XML (rename attribute,
  reorder children) and grow into Cheetah later.
- **Per-XSD-type class names hurt cursor ergonomics.** The
  `When`-becomes-many-classes issue is intrinsic to the XSD — no
  codegen knob can flatten it. The normalized cursor layer (option b
  in Node taxonomy) is the long-term answer; document the tradeoff in
  the authoring guide.
- **Macros are leaky.** Item 2 is the structural fix; until it lands,
  codemods must declare a macro mode and the harness must enforce it.
- **Trivia loss is one-way.** A codemod run + format pass *will*
  rewrite the user's indentation/quote style on every file it touches,
  even if the codemod is a no-op. This is the design — document it
  prominently in tier 2 / tier 3 so users aren't surprised by diffs
  larger than the requested refactor.
- **Profile-bump policy is a judgment call.** Even with the drift modes
  above, choosing the default (`warn`) means some users will be
  surprised that a codemod ran cleanly but their tool no longer
  validates at its declared profile. Document the modes and the
  defaults loudly in the codemod tool's CLI help.

## Verification

Two independent prototypes before the codemod tool's API is locked in:

1. **Foundation sufficiency** — pick one realistic refactor (e.g. rename
   a `<param>`'s `name=` and every Cheetah reference in `<command>`),
   prototype it as a script depending on `galaxy-tool-xml` only.
   Confirm the prototype needs nothing beyond: the lxml tree, the typed
   model, macro file resolution (item 1), and a Cheetah parser it
   brings itself. Any other gap → fold into this document before splitting
   tier 2 out.
2. **Ergonomics check** — give a developer who knows lxml (and doesn't
   know Galaxy's tool XSD) a short codemod spec and the codemod tool's
   API doc, and watch them write the codemod. Friction points are the
   real backlog for tier 2's API polish. Especially watch for confusion
   around the per-XSD-type class names (Node taxonomy section) and
   around the cursor-mutation visitor protocol (no `leave_X`, no
   return-value sentinels).

Concrete in-repo work proposed by this document: items 1, 3, 4 from "What
`galaxy-tool-xml` should add" — all additive, none breaking the public
API in `README.md:52-60`.
