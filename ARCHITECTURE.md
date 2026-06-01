# ARCHITECTURE.md — galaxy-tool-refactor

A map of the **major abstractions** in this monorepo and the **contracts**
between them. It is the orientation document a new contributor reads first: what
each tier owns, the central types and entry points, and the cross-tier invariants
that keep the seven packages independent.

This file does **not** re-argue the *why behind the why* — each decision lives in
the owning package's `docs/decisions.md`, and the §-pointers in the
[Reference index](#reference-index) lead there. For build / test / lint commands
see the root [`CLAUDE.md`](CLAUDE.md); for the IUC best-practice coverage map see
[`docs/iuc_best_practices.md`](docs/iuc_best_practices.md); for the per-profile
upgrade map (what each profile bump requires, and the validity-vs-behaviour
soundness boundary) see [`docs/profile_upgrades.md`](docs/profile_upgrades.md).

---

## 1. The tier stack

The project is a layered stack of independently-installable packages. The single
load-bearing rule:

> **Each tier depends only on lower tiers; no tier depends on a higher one.**
> Orchestration (running pipelines, composing rule families) lives in the
> **registry facade** (tier 3.6). The **CLI** (tier 4) is a thin front-end, and a
> future **MCP server** is a second thin front-end over the same facade.

| Tier | Layer | Package | Owns |
|---|---|---|---|
| 0.5 | **rule metadata** | `galaxy-tool-refactor-rules` | `RuleMeta` descriptor, `Violation` diagnostic, `render_rule_reference_table`. Dependency-free; shared by every higher tier. |
| 1 | **parsing & validation** | `galaxy-tool-xml` | `ToolDocument` / `MacroDocument` (mutable lxml tree = source of truth), `load_tool` / `parse_tool` / `validate_tool`, `newest_valid_profile`, profile resolution, typed xsdata views. **No serializer.** |
| 2 | **structure** | `galaxy-tool-xml-codemod` | `CodemodCommand` visitor framework, `Cursor` mutation primitives, `Change` + `apply_changes`, the bundled codemods, `CANONICAL_CODEMODS` / `AUTO_UPGRADE_CODEMODS` contracts. |
| 3 | **formatting** | `galaxy-tool-xml-fmt` | Cosmetic `Rule`s (indent / blank line / shorthand), the `Edit` union + `apply_edits`, `format_tool_document` + the net-diff `detect_tool_document`, the shared `cli_support` engine, the serializer. **The only tier that serialises canonical output XML.** |
| 3.5 | **advisory checks** | `galaxy-tool-xml-check` | Detect-only IUC best-practice checks (`CheckRule`, `detect_violations`). Read-only LBYL queries. Depends only on tiers 1 + 0.5. |
| 3.6 | **rule registry / presets** | `galaxy-tool-refactor-registry` | `RuleHandle` (uniform adapter over all three families), the unified registry, named presets, ruff-style selection, and the **library-first** `run` / `upgrade` / `detect` facade. Composes 0.5/1/2/3/3.5. |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` | The user-facing `galaxy-tool-refactor` CLI: `format` / `upgrade` / `check` / `presets` / `rules`. CLI plumbing only. |
| 4 | **MCP server** *(future)* | `galaxy-tool-refactor-mcp` | Placeholder; an agent-facing server over the facade. Not a workspace member yet — see its `docs/vision.md`. |

### Dependency direction

```
                 ┌─────────────────────────────────────────────┐
   tier 4        │  cli (galaxy-tool-refactor-cli)   mcp (future)│
                 └───────────────────┬─────────────────────────┬┘
                                     │ consumes facade         │
   tier 3.6           ┌─────────────▼──────────────┐           │
                      │ registry  (RuleHandle,      │◀──────────┘
                      │ presets, run/upgrade/detect)│
                      └──┬─────────┬─────────┬──────┘
                         │ composes│         │
        ┌────────────────▼┐  ┌─────▼──────┐  ┌▼──────────────┐
 tier 2 │ codemod          │ 3│ fmt        │ 3.5│ check        │
        │ Change/Cursor    │  │ Edit/Rule  │  │ CheckRule     │
        └───────┬──────────┘  └────┬───────┘  └──────┬────────┘
                │   each carries RuleMeta + Violation │
                │           ┌────────────────────────┐│
        ────────┴───────────▼── tier 0.5 ────────────┴┘
                 │ rules (RuleMeta, Violation) │   ← dependency-free
                 └──────────────┬──────────────┘
                                │ all of 2/3/3.5 sit on
                 ┌──────────────▼──────────────┐
        tier 1   │ xml (ToolDocument, validate)│
                 └─────────────────────────────┘
```

Codemod (2), fmt (3), and check (3.5) are **independent siblings**: none imports
another. They share only tier 0.5's vocabulary and tier 1's tree. The registry
(3.6) is the *first* place the three families meet.

---

## 2. Tier 0.5 — `galaxy-tool-refactor-rules` (shared vocabulary)

A tiny, **dependency-free** package (no lxml, no other tier). Its whole purpose is
to be a shared primitive so codemod and fmt can each carry rule metadata without
depending on each other — the seam that keeps the tiers uncoupled.

- **`RuleMeta`** — `meta.py` — frozen descriptor every rule carries as
  `meta: ClassVar[RuleMeta]`. Fields: `code` (e.g. `"GTX001"`), `summary`,
  `since` / `until` (documentary), `cite`, `order` (fmt application order;
  codemods leave it default), `detect_only` (advisory vs fixable), `applies_to`
  (a subset of `{"tool", "macro"}`; default `{"tool"}` — a rule runs on a macro
  file only when it opts in).
- **`Violation`** — `violation.py` — the per-occurrence detect result: `code`,
  `sourceline` (1-based, `0` if synthesised), `xpath`, `message`. Pure data — the
  location is a plain `int` + `str`, never an lxml handle. This is the **read-only
  counterpart** to the mutating `Change` (tier 2) / `Edit` (tier 3); every detect
  phase and report surfaces findings as `Violation`s.
- **`render_rule_reference_table`** — `reference.py` — a pure markdown renderer
  for a cross-tier rule glossary (used by the corpus-stats generators).

**Contract:** stay dependency-free. Adding any import here would risk re-coupling
the tiers it exists to keep apart. *(rules `docs/decisions.md` §D1.)*

---

## 3. Tier 1 — `galaxy-tool-xml` (parsing & validation)

The foundation: parse Galaxy tool XML, validate it against the right per-release
schema, and expose a typed view — **without ever serialising**.

- **`ToolDocument`** — `document.py` — wraps the parsed lxml `ElementTree`, which
  is the **source of truth**. lxml alone round-trips CDATA, comments, attribute
  data and order faithfully, so a downstream formatter can mutate and re-emit it.
  There is deliberately **no serialize method** — exposing `tree` *is* the
  contract. Key surface: `tree`, `root`, `source_path`, `profile`, and
  `model(*, version=None)` (a derived, read-only xsdata typed view, re-bound from
  the live tree on each call).
- **`MacroDocument`** — `document.py` — the `<macros>`-file counterpart: a mutable
  tree with **no `profile` and no `model`** (a macro library has no standalone
  XSD). Codemods/formatters still mutate and re-serialise it.
- **Entry points** — `binding.py`:
  - `load_tool(source) -> ToolDocument` — strict; raises `ToolXmlSyntaxError`.
  - `parse_tool(source) -> ParseResult` — lenient; collects `XmlError`s, never
    raises. `load_macros(source) -> MacroDocument` is the macro-file analogue.
  - `validate_tool(target, *, profile=None, on_missing="nearest",
    macro_handling="expand") -> ValidationResult` — profile-aware XSD validation.
    The Galaxy XSD is *post-macro-expansion*, so validation expands into a
    **throwaway copy** — the source tree is never mutated.
  - `newest_valid_profile(target) -> str | None` — newest vendored profile the
    tool validates at, scanned newest→oldest (validity across releases is **not**
    contiguous, so no binary search). This is the hinge codemod upgrades turn on.
  - `Source = str | Path | bytes | BinaryIO`. Results are dataclasses
    (`ParseResult`, `ValidationResult`, `XmlError`) with `.well_formed` / `.valid`
    convenience properties — the **dataclass-result convention** the whole project
    follows: domain failures are returned, not raised.
- **Profile resolution** — `profiles.py` — `resolve_profile`, `available_profiles`,
  `compiled_schema` map a tool's `profile=` to one of ~28 vendored per-release
  XSDs. The generated typed models live under `models/` (build-time xsdata
  codegen; gitignored, exempt from lint/type-check).

**Contract:** the lxml tree is the single representation; tier 1 emits no XML.
*(xml `docs/decisions.md` §3 representation, §9 three-tier vision, §10 corpus
measurements.)*

---

## 4. Tier 2 — `galaxy-tool-xml-codemod` (structure)

Structural mutations: attribute order, element order, typo repair, profile
upgrades. A **detect-primitive** framework — each codemod reports exactly what it
will change.

- **`CodemodCommand`** — `codemod.py` — base class. A concrete codemod defines
  `detect_<TagPascalCase>` methods (`<param>` → `detect_Param`); the base
  `detect(module)` walks the tree in document order and yields the `Change`s those
  detectors return **without mutating**. `apply(module)` is *derived*: it
  materialises `detect(...)` then runs each `Change.mutate` thunk — so the change a
  codemod reports is exactly the change it applies. Validation-driven codemods
  (`FixTypos`, `UpgradeToLatest`) can't pre-compute a static change list (they
  branch on re-validation), so they override `apply` and supply a *coarse* detect.
  Corpus-sweep hooks: `corpus_eligible`, `corpus_validation_profile`,
  `upgrade_steps_applied`.
- **`Cursor`** — `cursor.py` — an lxml-backed navigation + **immediate-mutation**
  API: `children()` (skips Comment/PI), `get_attribute`, `attribute_names`,
  `set_attribute`, `delete_attribute`, `rename_attribute`, `rename_tag`,
  `reorder_attributes`, `reorder_children`, `remove`, `add_child`, `set_text`
  (token-aware, for `@PROFILE@` rewrites). Generic over any tree, so it also
  serves `MacroModule`.
- **`Module` / `parse_module`** — `module.py`, `parse.py` — frozen wrapper over a
  `ToolDocument` exposing `document`, `model`, and a fresh root `cursor`
  (`MacroModule` / `parse_macro_module` are the `<macros>` counterparts).
- **`Change` + `apply_changes`** — `change.py` — a `Change` is `code`,
  `sourceline`, `xpath`, `message` (the same shape as a `Violation`) plus a
  zero-arg `mutate` thunk (excluded from equality/repr). `to_violation()` projects
  it onto tier 0.5. `apply_changes(changes)` is the single dispatch site that runs
  the thunks. The cosmetic-tier analogue is fmt's pattern-matched `Edit`; the
  difference is that a `Change` carries its mutation as a **closure over a Cursor
  call** rather than re-enumerating every mutation kind.
- **Pipeline contracts** — `canonical.py`:
  - `CANONICAL_CODEMODS` = `FixTypos` → `ReorderParamAttributes` →
    `ReorderToolAttributes` → `ReorderToolChildren` — the **safe, idempotent**
    format-time pipeline. Never touches `profile=`.
  - `AUTO_UPGRADE_CODEMODS` = `FixTypos` → `UpgradeToLatest` — the **opt-in,
    semantic** profile-upgrade pipeline.
- **`RuntimeGatedFix`** — `codemods/_runtime_gated.py`, registry in
  `runtime_fixes.py` (`RUNTIME_GATED_FIXES` + `runtime_fixes_for(profile)`) — a
  detect-primitive codemod plus an `introduced_profile` marker, for Galaxy
  *runtime* behaviour changes the XSD does **not** enforce. The distinction:
  validity-gated upgrades (`upgrade_vN`, in `UpgradeToLatest`) advance only when
  `newest_valid_profile` improves; a runtime-gated fix is XSD-valid at every
  profile, so the facade's `upgrade` applies it once a tool *reaches* its
  introduction profile. Members (`FixFromWorkDirWhitespace` GTX014 @21.09,
  `FixOutputFormatInput` GTX015 @16.04) are upgrade-only — in `coded_codemods()`,
  not `CANONICAL_CODEMODS`.
- **`catalog.coded_codemods()`** — `catalog.py` — *every* GTX-coded codemod
  (including the single-step `Upgrade19_01`…`Upgrade25_1` and `UpdateProfile` that
  `UpgradeToLatest` drives internally, and the runtime-gated GTX014/GTX015), for
  the cross-tier registry.

**Contract:** detect is the primitive; apply is derived; mutations are idempotent
and the codemod tier never serialises (the facade routes output through fmt).
*(codemod `docs/decisions.md` §11–18, §22–24; the per-profile upgrade map + the
validity-vs-behaviour soundness boundary are in [`docs/profile_upgrades.md`](docs/profile_upgrades.md)
and codemod `docs/decisions.md` §22.)*

---

## 5. Tier 3 — `galaxy-tool-xml-fmt` (formatting)

Opinionated cosmetic formatting like `black`: one canonical style, no knobs. The
opinion lives here so lower tiers can ignore trivia. **This is the only tier that
serialises canonical output XML.** (Tier 1 does an internal serialise-then-reparse
and a throwaway temp-dir round-trip for macro expansion — neither is output.)

- **`Rule`** — `rules.py` — stateless ABC carrying `meta: ClassVar[RuleMeta]`; its
  single method `edits(tree) -> Iterable[Edit]` *describes* mutations (it yields
  `Edit`s; it does not itself touch the tree). The three active rules: `GTX001`
  `CanonicalIndent` (`rule_indent.py`), `GTX003` `BlankLineBetweenSections`
  (`rule_blank_line.py`, tool-only), `GTX004` `EmptyElementShorthand`
  (`rule_empty_element.py`). *(GTX002/GTX005 — attribute order — moved to tier 2.)*
- **`Edit` + `apply_edits`** — `edits.py` — a frozen discriminated union
  (`NoOp | SetText | SetTail | ClearText`); `apply_edits` is the **single place**
  the tree is mutated and the single place the CDATA whitespace-only guard is
  honoured (via `serializer.safe_set_text` / `safe_set_tail`). Rules stay pure;
  they describe, the dispatcher applies.
- **`format_tool_document` / `format_macro_document` / `format_tool_document_subset`**
  — `format.py` — run the kind-applicable rules (in `meta.order`) over the tree
  and serialise. `all_rules()` / `rules_for_kind(kind)` enumerate them; the
  `_subset` form is the per-rule seam the registry uses.
- **`detect_tool_document` / `_subset` / `detect_macro_document`** — `detect.py` —
  the non-mutating lint phase. Because fmt rules are *unconditional* and can
  overwrite each other (GTX001 and GTX003 both rewrite top-level-child tails), the
  only faithful signal is the **net effect** of the whole pipeline: detect formats
  a throwaway deep copy, records the last rule to touch each node, and diffs
  against the original — one `Violation` per net-changed node, attributed to the
  owning rule. An already-canonical document reports nothing.
- **`serializer.py`** — `to_bytes(tree)` (UTF-8 + XML declaration) plus the
  CDATA-safe whitespace setters. Every byte of XML the project writes flows
  through here.
- **`cli_support.py`** — the shared file-walking engine both fmt's own CLI and the
  app CLI consume: `run(paths, *, transform, action, options, macro_transform)`,
  `iter_targets`, `is_tool_root` / `is_macros_root`, `TransformOutcome`, `Action`,
  `RunOptions`, `Counts`. The caller supplies only the `transform` callback — the
  one thing that differs between CLIs.

**Contract:** cosmetic-only (trivia: whitespace, shorthand — *never* element order
or names); the library and CLI **do not depend on codemod**; fmt is the sole
serializer. *(fmt `docs/decisions.md` §D10 independence, §D12 cosmetic-only CLI,
§D15 per-rule subset seams, §D16 macro support.)*

---

## 6. Tier 3.5 — `galaxy-tool-xml-check` (advisory checks)

Read-only IUC best-practice checks that **report but never mutate**. Depends only
on tiers 1 + 0.5 — a sibling the app *composes*, not a consumer of the fixers.

- **`CheckRule`** — `rules.py` — ABC carrying `meta` (with `detect_only=True` and
  an `IUC` code); its single method `detect(document) -> Iterable[Violation]` is a
  non-mutating LBYL tree query.
- **`all_checks()` / `detect_violations(document)`** — `detect.py` — the
  enumerated check set (sorted by code) and the aggregate runner (findings sorted
  by line). Mirrors codemod's `coded_codemods()` and fmt's `all_rules()`.
- **The checks** — `checks.py` — IUC001–IUC010 are implemented presence/shape
  queries (tests, command-CDATA, id charset, version format, requirements, error
  handling, EDAM xrefs, help, description, help-CDATA). **IUC011 / IUC012**
  (single-quoted Cheetah, `&&`-vs-`&`) are **reserved stubs** — registered codes
  whose `detect` returns nothing until tuned.

**Contract:** detect-only, LBYL, no mutation, no dependency on the mutating tiers.
Findings are advisory — informational unless the user opts into `--strict`.
*(check `docs/decisions.md` §D1; coverage map in `docs/iuc_best_practices.md`.)*

---

## 7. Tier 3.6 — `galaxy-tool-refactor-registry` (registry + facade)

The first tier that knows about all three rule families at once. **Library-first:**
no `click`, no `sys.exit`, no printing; inputs are path / bytes / `ToolDocument`;
outputs are structured dataclasses; files are written only when a `write_path` is
given. This is what lets both the CLI and a future MCP server be thin adapters.

- **`RuleHandle`** — `handle.py` — the uniform, code-addressable adapter that
  papers over the three families' different native shapes (codemod yields
  `Change`s via a `Module`; fmt yields `Edit`s; check yields `Violation`s and
  never fixes). Fields: `meta`, `family` (`"codemod"` / `"fmt"` / `"check"`),
  `fixable`, `detect(document) -> list[Violation]`, `apply(document) -> None | None`
  (`None` exactly for advisory rules). `adapters.py` builds one handle per family.
- **`registry()` / `all_handles()` / `by_code` / `known_codes` / `advisory_codes`**
  — `registry.py` — the cached `code -> RuleHandle` index. `registry()` is the
  **selectable** set (canonical codemods + cosmetic fmt + advisory checks);
  `all_handles()` additionally includes the **upgrade-only** codemods
  (GTX007–GTX012 — internal to `UpgradeToLatest` — plus the runtime-gated
  GTX014–GTX015, applied by the facade's `upgrade`), which are not independently
  selectable.
  `_index()` asserts the GTX/IUC namespace is **collision-free** — a reused code
  fails loudly here.
- **Presets** — `presets.py` — named, developer-defined rule subsets, derived from
  the family registries (never a hand-maintained code list that can drift):
  `cosmetic` (fmt rules only), `iuc` (canonical codemods + cosmetic; the
  **default**, byte-identical to the historical `format`), `strict` (`iuc` + every
  advisory check). No user-defined presets.
- **Selection** — `resolve.py` — `resolve_codes(*, preset, select, ignore)` with
  **ruff-style precedence `--ignore` ▸ `--select` ▸ `--preset`**: `--select`
  *replaces* the preset's set (resets the base, not adds), then `--ignore`
  subtracts. Unknown names raise typed `UnknownPreset` / `UnknownRuleCode`
  (`errors.py`). `resolve_upgrade_codes` is the preset-less variant for `upgrade`.
- **`apply_selection`** — `apply.py` — applies a code set in `format`'s order:
  codemods first (in `CANONICAL_CODEMODS` order), then the cosmetic fmt rules as
  one batch through `format_tool_document_subset` (which serialises once).
  Advisory codes are skipped. Even a codemod-only selection ends in fmt — so
  **fmt stays the only serializer**.
- **The facade** — `facade.py` — the library-first entry points:
  - `run(source, *, codes, write_path=None) -> FormatResult` — apply the fixable
    rules; detect advisory ones on the pre-format tree and return them as notes
    (never mutating for them).
  - `upgrade(source, *, codes, write_path=None) -> UpgradeResult` — always run
    `UpgradeToLatest` (its purpose), `FixTypos` first if selected, then the rest;
    reports `steps_applied` / `missing_upgrade`.
  - `detect(source, *, codes) -> DetectResult` — report-only; fmt rules detected
    as one net-effect group, codemod/advisory rules per-code.
  - `list_presets()` / `list_rules(*, include_upgrade=False)` — introspection.
  - Results live in `results.py` (`FormatResult`, `UpgradeResult`, `DetectResult`,
    `RuleInfo`, `PresetInfo`).
- **`macro_profile.py`** — the Phase-3b imported-`@PROFILE@` upgrade. A tool whose
  `profile="@TOKEN@"` resolves to a token in an *imported* macro file can't be
  upgraded by editing the tool alone. `profile_token_site(document)` maps one tool
  to its `ProfileTokenSite` (defining file + token + target); the pure
  `plan_from_sites(sites)` groups by file and decides per-file **importer
  agreement**; `apply_profile_token_plans(plans, *, write)` bumps the token in
  place **only when every importer agrees** (else reports and skips). This spans a
  *set* of tools — orchestration — which is why it lives in this tier.

**Contract:** library-first; one handle per code; selectable ≠ all; apply order
reproduces `format` (pinned by a regression test); fmt is still the only
serializer. *(registry `docs/decisions.md` D1–D5.)*

---

## 8. Tier 4 — `galaxy-tool-refactor-cli` (app)

The user-facing `galaxy-tool-refactor` CLI (`cli.py`). **CLI plumbing only** — all
rule orchestration is delegated to the facade; this package no longer imports the
codemod / check tiers directly. Five subcommands:

- **`format`** — apply a preset's (or selection's) fixable rules then cosmetic
  formatting; never changes `profile=`. Advisory rules in a selection are reported
  as notes, never applied. Macro files are cosmetically formatted (kind-applicable
  rules only). Wraps `facade.run` inside `cli_support.run`.
- **`upgrade`** — repair → iterative profile upgrade → format. Opt-in, semantic;
  **no `--preset`** (`--select` / `--ignore` adjust its fixable set). Runs a
  whole-run phase first (`_upgrade_macro_profile_tokens`) that bumps agreed
  imported `@PROFILE@` tokens, then wraps `facade.upgrade` per file.
- **`check`** — report-only linter; one `file:line  CODE  message` per finding.
  Fixable (GTX) findings fail the run; advisory (IUC, under `--preset strict`) are
  informational unless `--strict`. Wraps `facade.detect`.
- **`presets` / `rules`** — introspection over `facade.list_presets` /
  `list_rules`.

Selection (`--preset` / `--select` / `--ignore`) is shared across
`format` / `upgrade` / `check` with the ruff-style precedence above. Exceptions
from the facade (`UnknownPreset` / `UnknownRuleCode`) are caught here at the CLI
boundary and re-raised as `click.BadParameter`.

**Future — `galaxy-tool-refactor-mcp`:** an agent-facing MCP server over the same
facade (discover rules/presets, run `format` / `upgrade` / `check` on supplied
content). Not implemented, not a workspace member yet; the facade's library-first
shape is what makes it a thin adapter. *(cli `docs/decisions.md` D1–D6;
mcp `docs/vision.md`.)*

---

## 9. Cross-cutting contracts

These invariants span tiers. They are the rules an architectural change must not
break.

1. **lxml tree is the source of truth; fmt is the only serializer of canonical
   output.** Tier 1 ships no serialize method; codemods mutate but hand off; the
   registry always ends in `format_tool_document_subset`. Every byte of *output*
   XML flows through fmt's `serializer.to_bytes`; the registry facade and CLI then
   write those fmt-produced bytes to disk. (One nuance — see
   [§10](#10-known-asymmetries): tier 1 does `etree.tostring` a tool into a
   *throwaway temp file* during macro expansion. That is an internal, non-canonical
   round-trip, not user-facing output, so it doesn't break the contract.)
   *(xml §3; fmt §D10; registry `apply.py`.)*
2. **Tier independence.** Codemod (2), fmt (3), and check (3.5) never import each
   other; check depends only on 1 + 0.5; nothing below 3.6 imports 3.6. The
   `pyproject.toml` dependency lists encode this. The three families first meet in
   the registry.
3. **Detect / fix split.** Every *fixable* rule has a non-mutating detect phase and
   a mutating fix; advisory rules have detect only. The shared report type is
   `Violation`; the fix is carried by `Change.mutate` (tier 2) or an `Edit` (tier
   3). Note the families implement this differently — see
   [§10](#10-known-asymmetries) — but the registry's `RuleHandle` normalises them
   to one `detect` / `apply` shape.
4. **GTX vs IUC code families.** GTX = fixable (codemod + fmt); IUC = advisory
   (`detect_only`). Codes are globally unique and collision-guarded by
   `registry._index()`. Upgrade-only GTX codes exist but are not user-selectable:
   007–012 (validity-gated, internal to `UpgradeToLatest`) and 014–015
   (runtime-gated, applied by the facade's `upgrade` — see §4 below).
5. **Dataclass-result convention.** Entry points return result dataclasses
   (`ParseResult`, `ValidationResult`, `FormatResult`, …) and don't raise on domain
   failures. Exceptions are reserved for the CLI boundary (chained `from e`) and
   third-party API edges with no LBYL form. Per dignified-python.
6. **Idempotence + validity preservation.** Codemods are idempotent and never
   regress XSD validity; fmt is idempotent (`format(format(x)) == format(x)`).
   These are proven by corpus sweeps, and crashes are retained as regression
   fixtures.
7. **Shared selection model.** `--preset` / `--select` / `--ignore` work
   identically across `format` / `upgrade` / `check` (upgrade rejects `--preset`),
   resolved once in `resolve.py`.
8. **Macro handling is cosmetic-only in v1** — except the consensus imported
   `@PROFILE@` token bump in `macro_profile.py`. Macro files have no codemods (the
   codemods are `applies_to={"tool"}`).

---

## 10. Known asymmetries

Honest notes a maintainer should know — these are *intentional* today but are the
natural places to look when reasoning about consistency.

- **"describe" vs "mutate" is named in the method.** fmt's `Rule.edits(tree)`
  *yields* `Edit`s (it describes; `apply_edits` mutates), whereas codemod's
  `CodemodCommand.apply` and the registry's `RuleHandle.apply` *mutate* — so
  `apply` consistently means "mutate in place" across the codebase, and the
  describe-only fmt surface is `edits`, not `apply`. The detect-vs-fix method
  surface also differs per family: codemod has both `detect` + `apply`; fmt's
  `Rule` has only the edit-yielding `edits` (its detect is the separate net-diff
  in `detect.py`); check's `CheckRule` has only `detect`. `RuleHandle` is the
  adapter that hides this.
- **Two advisory-aggregation paths.** Tier 3.5 ships `detect_violations()` (used by
  the corpus scripts), while the facade re-aggregates per-handle in
  `_detect_advisory`. Both are correct; they are parallel runners for different
  callers.
- **Cosmetic detect is net-effect, not per-rule.** A single-rule fmt subset can
  report churn a coherent subset would cancel; only the shipped presets (full
  GTX001/003/004 trio) are guaranteed idempotent. The same order-sensitivity means
  the registry's `apply_selection` deliberately **batches** the selected fmt rules
  through `format_tool_document_subset` rather than calling each fmt
  `RuleHandle.apply` one at a time — so a fmt handle's per-rule `apply` exists for
  interface uniformity but is not the path the facade uses.
- **fmt serialises to a throwaway temp file outside the canonical path.** Tier 1's
  `macros.expand_from_tree` writes `etree.tostring(root)` into a `TemporaryDirectory`
  so Galaxy's path-based macro expander can run; the result is discarded. So
  "fmt is the only serializer" is precisely "of *canonical output* bytes."

---

## 11. How the contracts are kept true — QA machinery

The invariants above are enforced by standing tooling, not goodwill (`scripts/`):

- **`corpus_check.py`** — corpus sweeps with five subcommands: `validate`
  (tier-1 invariants), `fmt` (tier-3 idempotence), `codemod <module>:<Class>`
  (one structural codemod's idempotence + post-validity), `rules` (every GTX rule
  in isolation), `check` (unified detect violation counts). Failures are retained
  as permanent regression fixtures.
- **`measure.py`** — decision-backing "standing measurements"; each subcommand
  answers one empirical question and writes a `docs/*_stats.md` artifact. Reproduced
  analyses live here (with a test), not in throwaway scripts.
- **`qa_gate.sh`** — the deterministic pre-push gate: ruff + mypy (strict, per
  package) + pytest across all seven packages. A `git push` hook blocks on
  failure. (A mechanical backstop — *not* a substitute for the full pre-PR audit.)
- **`fetch_schemas.py` / `fetch_toolshed.py` / `regenerate.py`** — vendor the XSDs,
  clone the corpus, and regenerate the per-version typed models.

---

## Reference index

Each abstraction → its file → the decision record that justifies it.

| Abstraction | File | Rationale |
|---|---|---|
| `RuleMeta`, `Violation` | `galaxy-tool-refactor-rules/src/.../meta.py`, `violation.py` | rules `docs/decisions.md` §D1 |
| `ToolDocument` / `MacroDocument` | `galaxy-tool-xml/src/.../document.py` | xml `docs/decisions.md` §3, §15 |
| `load_tool` / `validate_tool` / `newest_valid_profile` | `galaxy-tool-xml/src/.../binding.py` | xml `docs/decisions.md` §1, §10 |
| profile resolution | `galaxy-tool-xml/src/.../profiles.py` | xml `docs/decisions.md` §10 |
| `CodemodCommand`, `Cursor`, `Change` | `galaxy-tool-xml-codemod/src/.../codemod.py`, `cursor.py`, `change.py` | codemod `docs/decisions.md` §6, §19 |
| `CANONICAL_CODEMODS` / `AUTO_UPGRADE_CODEMODS` | `galaxy-tool-xml-codemod/src/.../canonical.py` | codemod `docs/decisions.md` §16 |
| upgrade codemods | `galaxy-tool-xml-codemod/src/.../upgrades.py`, `codemods/upgrade_*.py` | codemod `docs/decisions.md` §11–14 |
| `PROFILE_UPGRADE_CODES` / `upgrade_codes_crossed` / `upgrade_codes_applicable` | `galaxy-tool-xml-codemod/src/.../profile_semantics.py` | codemod `docs/decisions.md` §22–23, §25 |
| `RuntimeGatedFix` / `runtime_fixes_for` | `galaxy-tool-xml-codemod/src/.../codemods/_runtime_gated.py`, `runtime_fixes.py` | codemod `docs/decisions.md` §24 |
| `Rule`, `Edit`, serializer | `galaxy-tool-xml-fmt/src/.../rules.py`, `edits.py`, `serializer.py` | fmt `docs/decisions.md` §D3, §D11 |
| `format_*` / `detect_*` | `galaxy-tool-xml-fmt/src/.../format.py`, `detect.py` | fmt `docs/decisions.md` §D15 |
| `cli_support` engine | `galaxy-tool-xml-fmt/src/.../cli_support.py` | fmt `docs/decisions.md` §D12 |
| `CheckRule`, `detect_violations` | `galaxy-tool-xml-check/src/.../rules.py`, `detect.py` | check `docs/decisions.md` §D1; `docs/iuc_best_practices.md` |
| `RuleHandle`, registry | `galaxy-tool-refactor-registry/src/.../handle.py`, `registry.py` | registry `docs/decisions.md` D1–D2 |
| presets, `resolve_codes`, `apply_selection` | `galaxy-tool-refactor-registry/src/.../presets.py`, `resolve.py`, `apply.py` | registry `docs/decisions.md` D3–D4 |
| `run` / `upgrade` / `detect` facade | `galaxy-tool-refactor-registry/src/.../facade.py`, `results.py` | registry `docs/decisions.md` D1 |
| imported-`@PROFILE@` upgrade | `galaxy-tool-refactor-registry/src/.../macro_profile.py` | registry `docs/decisions.md` D5 |
| the CLI | `galaxy-tool-refactor-cli/src/.../cli.py` | cli `docs/decisions.md` D1–D6 |
| MCP direction (future) | `galaxy-tool-refactor-mcp/docs/vision.md` | — |

### Rule codes at a glance

| Code | Class | File | Family |
|---|---|---|---|
| GTX001 | `CanonicalIndent` | `galaxy-tool-xml-fmt/.../rule_indent.py` | fmt (cosmetic) |
| GTX002 | `ReorderParamAttributes` | `galaxy-tool-xml-codemod/.../reorder_param_attributes.py` | codemod (canonical) |
| GTX003 | `BlankLineBetweenSections` | `galaxy-tool-xml-fmt/.../rule_blank_line.py` | fmt (cosmetic, tool-only) |
| GTX004 | `EmptyElementShorthand` | `galaxy-tool-xml-fmt/.../rule_empty_element.py` | fmt (cosmetic) |
| GTX005 | `ReorderToolAttributes` | `galaxy-tool-xml-codemod/.../reorder_tool_attributes.py` | codemod (canonical) |
| GTX006 | `FixTypos` | `galaxy-tool-xml-codemod/.../fix_typos.py` | codemod (canonical, validation-driven) |
| GTX007 | `UpdateProfile` | `galaxy-tool-xml-codemod/.../update_profile.py` | codemod (upgrade-only) |
| GTX008–011 | `Upgrade19_01` … `Upgrade25_1` | `galaxy-tool-xml-codemod/.../upgrade_*.py` | codemod (upgrade-only) |
| GTX012 | `UpgradeToLatest` | `galaxy-tool-xml-codemod/.../upgrades.py` | codemod (upgrade-only orchestrator) |
| GTX013 | `ReorderToolChildren` | `galaxy-tool-xml-codemod/.../reorder_tool_children.py` | codemod (canonical) |
| GTX014 | `FixFromWorkDirWhitespace` | `galaxy-tool-xml-codemod/.../fix_from_work_dir_whitespace.py` | codemod (upgrade-only, runtime-gated) |
| GTX015 | `FixOutputFormatInput` | `galaxy-tool-xml-codemod/.../fix_output_format_input.py` | codemod (upgrade-only, runtime-gated) |
| IUC001–010 | `TestsPresent` … `HelpCdata` | `galaxy-tool-xml-check/.../checks.py` | check (advisory) |
| IUC011–012 | `SingleQuotedCheetah`, `CommandAndJoining` | `galaxy-tool-xml-check/.../checks.py` | check (advisory, reserved stubs) |
