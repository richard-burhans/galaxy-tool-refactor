# ARCHITECTURE.md — galaxy-tool-refactor

A map of the **major abstractions** in this monorepo and the **contracts**
between them. It is the orientation document a new contributor reads first: what
each tier owns, the central types and entry points, and the cross-tier invariants
that keep the eight packages independent.

This file does **not** re-argue the *why behind the why* — each decision lives in
the owning package's `docs/decisions.md`, and the §-pointers in the
[Reference index](#reference-index) lead there. For build / test / lint commands
see the root [`CLAUDE.md`](CLAUDE.md); for the IUC best-practice coverage map see
[`docs/iuc_best_practices.md`](docs/iuc_best_practices.md); for the per-profile
upgrade map (what each profile bump requires, and the validity-vs-behaviour
soundness boundary) see [`docs/profile_upgrades.md`](docs/profile_upgrades.md); for
the per-rule behaviour-preservation claims, their adversarial verdicts, and the
open remediation backlog see
[`docs/behavior_preservation.md`](docs/behavior_preservation.md); the canonical
per-rule **proof documents** (coverage-guarded) are
[`docs/proofs/`](docs/proofs/README.md).

---

## 1. The tier stack

The project is a layered stack of independently-installable packages. The single
load-bearing rule:

> **Each tier depends only on lower tiers; no tier depends on a higher one.**
> Orchestration (running pipelines, composing rule families) lives in the
> **registry facade** (tier 3.6). The **CLI** (tier 4) is a thin front-end, and
> the **MCP server** (`galaxy-tool-refactor-mcp`) is a second thin front-end over
> the same facade.

| Tier | Layer | Package | Owns |
|---|---|---|---|
| 0.5 | **rule metadata** | `galaxy-tool-refactor-rules` | `RuleMeta` descriptor, `Violation` diagnostic, the `Ruleset` catalog, `render_rule_reference_table`. Dependency-free; shared by every higher tier. |
| 1 | **parsing & validation** | `galaxy-tool-source` | `ToolDocument` / `MacroDocument` (mutable lxml tree = source of truth), `load_tool` / `parse_tool` / `validate_tool`, `newest_valid_profile`, profile resolution, typed xsdata views. **No serializer.** |
| 2 | **structure** | `galaxy-tool-xml-codemod` | `CodemodCommand` visitor framework, `Cursor` mutation primitives, `Change` + `apply_changes`, the bundled codemods, `canonical_codemods()` / `AUTO_UPGRADE_CODEMODS` contracts. |
| 3 | **formatting** | `galaxy-tool-xml-fmt` | Cosmetic `Rule`s (indent / blank line / shorthand), the `Edit` union + `apply_edits`, `format_tool_document` + the net-diff `detect_tool_document`, the shared `cli_support` engine, the serializer. **The only tier that serialises canonical output XML.** |
| 3.5 | **advisory checks** | `galaxy-tool-xml-check` | Detect-only IUC best-practice + planemo-parity checks (69; `CheckRule`, `detect_violations`). Read-only LBYL queries. Depends only on tiers 1 + 0.5. |
| 3.6 | **rule registry / rulesets** | `galaxy-tool-refactor-registry` | `RuleHandle` (uniform adapter over all three families), the unified registry, declarative rule-sets, ruff-style selection, and the **library-first** `run` / `upgrade` / `detect` facade. Composes 0.5/1/2/3/3.5. |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` | The user-facing `galaxy-tool-refactor` CLI: `format` / `upgrade` / `check` / `find-references` / `rename-param` / `rulesets` / `rules` / `normalize-macros` / `convert-help` / `tokenize-version`. CLI plumbing only. |
| 4 | **MCP server** | `galaxy-tool-refactor-mcp` | An agent-facing MCP server over the facade (CLI sibling): a thin FastMCP binding (`server.py`) over a protocol-agnostic adapter (`service.py`, facade → JSON). Tools: `format_tool`/`upgrade_tool`/`check_tool`/`convert_help_tool`/`tokenize_version_tool`/`list_rulesets`/`list_rules`. Goal 1 of `docs/vision.md`; agent-authored rules (Goal 2) future. |

### Dependency direction

```
                 ┌─────────────────────────────────────────────┐
   tier 4        │  cli (galaxy-tool-refactor-cli)   mcp (server) │
                 └───────────────────┬─────────────────────────┬┘
                                     │ consumes facade         │
   tier 3.6           ┌─────────────▼──────────────┐           │
                      │ registry  (RuleHandle,      │◀──────────┘
                      │ rulesets, run/upgrade/detect)│
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
  `meta: ClassVar[RuleMeta]`. Fields: `code` (e.g. `"GTR001"`), `summary`,
  `since` / `until` (documentary), `cite`, `order` (per-family application order —
  both fmt rules and canonical codemods sort by it), `detect_only` (advisory vs
  fixable), `applies_to` (a subset of `{"tool", "macro"}`; default `{"tool"}` — a
  rule runs on a macro file only when it opts in), `parent` (partition-parent code,
  e.g. `"GTR020"` for `GTR020.1`/`.2`), `rulesets` (the named sets this rule belongs
  to — the maintainer's membership declaration; catalog in `rulesets.py`), and
  `planemo_linters` (the planemo `galaxy.tool_util.lint` linter class names this rule
  covers — the alias the registry indexes for name-based selection + parity-table
  generation; empty for our own rules).
- **`Ruleset` catalog** — `rulesets.py` — the dependency-free `Ruleset(name,
  description)` catalog + `DEFAULT_RULESET` that names the selectable sets;
  membership is declared per-rule (above) and the registry derives `name → codes`.
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

## 3. Tier 1 — `galaxy-tool-source` (parsing & validation)

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
- **Command-text analysis utilities** — `command_text.py` (read-only Cheetah/shell
  `$var` lexer, with character spans), `command_vars.py` (quoting-safety classifier:
  `provably_quotable`), `cdata.py` (`cdata_wrappable` / `needs_cdata` /
  `is_cdata_wrapped`). Pure string/element predicates that emit no XML. They sit in
  tier 1 so **both** the codemod fix sub-rules (tier 2) **and** the advisory check
  residuals (tier 3.5) share one definition — the partition's soundness seam (xml
  `docs/decisions.md` §16; registry D10).
- **Cheetah-mutation subsystem** — the read/edit layer over a tool's *templated*
  sections (`<command>` / inline `<configfile>` / attribute-Cheetah), all in tier 1,
  built on CT3 (a base dependency — the MIT-licensed faithful lexer; `cheetah_spans`
  still bails to the regex on the ~0.4% CT3 can't compile):
  - `cheetah_cdm.py` — a **faithful** Cheetah lexer, `cheetah_spans(text) ->
    list[CheetahSpan] | None`, recording disjoint source-ordered placeholder /
    directive / comment spans, so an edit can tell a live `$x` from one inside
    `#raw` / a `##` comment / an escaped `\$x` (xml `docs/decisions.md` §19).
  - `cheetah_refs.py` — the read-only reference model, `tool_cheetah_references(root)
    -> list[CheetahRef]`: every `$param` reference site across the templated
    sections; backs the CLI `find-references` (xml §18).
  - `cheetah_rename.py` — the first Cheetah **mutator**: rename a parameter across
    every live reference + the definition + `<tests>` mirrors + by-name cross-ref
    attributes, **atomically** (rewrite all or bail unchanged, with a reason). One
    planner (`_plan_rename`) feeds two renderings: `rename_param(root, *, old, new)
    -> RenameOutcome` mutates the lxml tree (used by the facade / CLI `rename-param`),
    and `rename_param_plan(source, *, old, new) -> RenamePlan` returns minimal
    `RenameEdit(start, end, replacement)` offsets over the **original source** for an
    editor / LSP `WorkspaceEdit` — no reflow; 96.8% corpus parity with the tree
    mutator, 0 mismatches (xml §20). Still **no serializer**: the tree rendering
    mutates in place, the offset rendering returns spans; the caller serialises.
    `rename_param` reads its mode (tool vs `<macros>`) from the root tag, so it renames
    inside a macro file too.
  - `bundle.py` — `ToolBundle` (a tool + its transitively-imported `MacroDocument`s,
    each with `source_path`) + `load_bundle(path)`, and `rename_param_in_bundle` — the
    **cross-file** rename: renames a parameter across the tool and its macros atomically
    (the silent-bug fix for a param referenced only in an imported macro — the real
    `pal2nal` case, 9 sites across 3 files). Pure mutation + per-member outcome with a
    `not-found` carve-out; the *shared-macro* safety lives one tier up in the registry
    gate (xml §21).
- **reStructuredText subsystem** — `rst.py`, the analogue of the Cheetah layer for the
  *other* embedded language in a tool: the `<help>` body (Galaxy renders it as RST to
  HTML server-side). `rst_is_invalid(text)` is the validity predicate (matches Galaxy's
  `rst_to_html(error=True)`); `repair_help_rst(text) -> str | None` is a **surgical,
  line-anchored** repair (docutils has no faithful RST writer and no source offsets, so —
  as with Cheetah — it edits the source text, never parse-and-reserialise) behind a strong
  render-equivalence gate. It is the shared seam of the **GTR089 partition**: the
  `GTR089.1` fix (tier 2) and `GTR089.2` advisory residual (tier 3.5) both call it. Adds a
  `docutils` base dependency (xml §23; codemod §37; check D31). Its sibling
  `rst_markdown.py` converts RST `<help>` to CommonMark behind the same kind of
  render-equivalence gate (docutils html4css1 vs markdown-it-py `js-default` — Galaxy's
  server vs client renderers; the `[markdown]` extra): `rst_to_commonmark` /
  `conversion_is_render_equivalent` / `convert_help_rst` power the GTR092 opt-in
  `convert-help` conversion and the `help-rst-md-convert` measure (xml §24; codemod §38).
- **`schema_content.text_bearing_tags()`** — `schema_content.py` — the
  schema-derived set of element tags whose content model admits text, unioned
  across all 28 vendored XSDs; the source of truth behind fmt's payload guard
  (GTR001/GTR004 whitespace soundness — fmt §D20, xml §25).

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
  - `canonical_codemods()` = `FixTypos` → `NormalizeBooleanValues` → `RepairHelpRst` →
    `TrimAttributeWhitespace` → `ReplaceOutputElement` → `DropRedundantParamName` →
    `ReorderParamAttributes` → `ReorderToolAttributes` → `ReorderToolChildren` →
    `WrapCommandCdata` → `WrapHelpCdata` → `SingleQuoteCommandVars` — the **safe,
    idempotent** format-time pipeline, **derived** from the codemods that declare
    the `"default"` ruleset, ordered by `meta.order` (the hardcoded tuple is gone).
    Never touches `profile=`. (`FixTypos` and
    `NormalizeBooleanValues` are validity-restoring no-ops unless the tool validates
    nowhere; the `Wrap…Cdata` codemods `GTR018.1`/`GTR019.1` wrap a pure-text
    `<command>`/`<help>` body in CDATA, `SingleQuoteCommandVars` `GTR020.1`
    single-quotes the provable command vars, and `RepairHelpRst` `GTR089.1` repairs
    deterministically-fixable invalid `<help>` RST behind a render-equivalence gate — all
    behaviour-preserving, codemod §29/§30/§37. Each is the fixable `.1` half of a partition
    practice, D10.)
  - `AUTO_UPGRADE_CODEMODS` = `FixTypos` → `NormalizeBooleanValues` →
    `UpgradeToLatest` — the **opt-in, semantic** profile-upgrade pipeline
    (repair-before-upgrade).
- **`RuntimeGatedFix`** — `codemods/_runtime_gated.py`, registry in
  `runtime_fixes.py` (`RUNTIME_GATED_FIXES` + `runtime_fixes_for(reached, *,
  baseline)`) — a detect-primitive codemod plus an `introduced_profile` marker, for
  Galaxy *runtime* behaviour changes the XSD does **not** enforce. The distinction:
  validity-gated upgrades (`upgrade_vN`, in `UpgradeToLatest`) advance only when
  `newest_valid_profile` improves; a runtime-gated fix is XSD-valid at every
  profile, so the facade's `upgrade` applies it once a tool *crosses* its
  introduction profile (`baseline < introduced_profile <= reached` — the
  crossing-gate, codemod §24: a tool already past the boundary is left alone, since
  Galaxy already applies the new behaviour there). Members
  (`FixInterpreter` GTR016 @16.04, `FixOutputFormatInput` GTR015 @16.04,
  `FixFromWorkDirWhitespace` GTR014 @21.09) are upgrade-only — in `coded_codemods()`,
  not `canonical_codemods()`.
- **`catalog.coded_codemods()`** — `catalog.py` — *every* GTR-coded codemod
  (including the single-step `Upgrade19_01`…`Upgrade25_1` and `UpdateProfile` that
  `UpgradeToLatest` drives internally, and the runtime-gated GTR014/GTR015/GTR016), for
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
  `Edit`s; it does not itself touch the tree). The three active rules: `GTR001`
  `CanonicalIndent` (`rule_indent.py`), `GTR003` `BlankLineBetweenSections`
  (`rule_blank_line.py`, tool-only), `GTR004` `EmptyElementShorthand`
  (`rule_empty_element.py`). *(GTR002/GTR005 — attribute order — moved to tier 2.)*
  GTR001 and GTR004 share the **schema-derived payload guard** (`payload.py` over
  tier-1 `schema_content`, fmt §D20): whitespace inside a text-bearing element is
  never rewritten, with two proof-carried exceptions (configfiles-context
  `<inputs>`, cleared `<macros>`).
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
  overwrite each other (GTR001 and GTR003 both rewrite top-level-child tails), the
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
  an `GTR` code); its single method `detect(document) -> Iterable[Violation]` is a
  non-mutating LBYL tree query.
- **`all_checks()` / `detect_violations(document)`** — `detect.py` — the
  enumerated check set (an explicit list, sorted by code) and the aggregate runner
  (findings sorted by line). Mirrors codemod's `coded_codemods()` and fmt's
  `all_rules()` — the same explicit-list convention across all three rule families;
  `test_detect.py` pins the count (68) as the acknowledgement gate when the roster
  grows.
- **The checks** — the `checks/` sub-package (split by element/source area:
  `tool.py`, `partition.py`, `outputs.py`, `inputs.py`, `validators.py`,
  `tests.py`, `help.py`, with cross-module helpers in `_shared.py`) — flat
  advisories `GTR021`, `GTR023`–`GTR029`,
  `GTR033` are presence/shape queries (tests, id charset, version format,
  requirements, error handling, EDAM xrefs, help, description, requirement pinning).
  **Four are the advisory `.2` half of a partition practice** (registry D10, check
  D9/D31): `GTR018.2` / `GTR019.2` (the `<command>` / `<help>` CDATA *residual* — the
  mixed-content the `GTR018.1` / `GTR019.1` fix can't wrap), `GTR020.2` (the
  *non-provable* unquoted `$var` the `GTR020.1` fix can't safely quote), and `GTR089.2`
  (the invalid `<help>` RST the `GTR089.1` repair can't safely fix). Each reuses
  the shared tier-1 predicate its fix uses, so the partition is sound.
  **GTR032** (`CommandAndJoining`, `&&`-vs-lone-`&`) is a real detector since
  check D34 (the D3 no-op era ended when its revisit condition — the CT3 lexer —
  was met): the quote/redirect/pipe-aware classifier in `lone_amp.py` (shared
  with the `command-lone-amp` measure, which imports it) flags only the genuine
  *joining* class. **GTR034** (`UnusedParam`) is a
  *reference-usage* advisory (not presence/shape): an `<inputs>` `<param>` never
  referenced anywhere the tool uses it, via the tier-1 all-text identifier scan.
- **The planemo-parity wave — `GTR038`–`GTR091`** (54 rules, across the `checks/`
  submodules) — a
  reimplementation of every *mechanically-reimplementable* planemo (`galaxy.tool_util.lint`)
  linter as a detect-only advisory, grouped by Galaxy source area: citations/TODO
  (`GTR038`–`GTR039`), output correctness (`GTR040`–`GTR050`), embedded-expression
  validity (`GTR051`–`GTR053`), the whole `inputs.py` correctness surface — naming,
  static + dynamic select options, validators, conditionals, type/structure,
  display/idiom, option-filters (`GTR054`–`GTR079`) — the `tests.py` surface
  (`GTR080`–`GTR088`), and `<help>` reStructuredText validity (`GTR089`, which carries
  the `docutils` dependency — now split into the `GTR089.1` repair + `GTR089.2` residual
  partition, with the predicate in tier 1, xml §23; GTR035.2 — the name-whitespace
  residual of the GTR035 partition, check D33). The whole tier is now **69 checks**
  (`GTR018.2`/`GTR019.2`/`GTR020.2`/`GTR089.2` + the flat IUC advisories above + this
  wave). A recurring soundness rule across the wave: a check that would mis-fire when a
  `<macro>` injects the construct it inspects skips that tool (the tier-1
  `has_macros` raw-tree guard) — `detect()` reads the **un-expanded** tree.
  Per-group rationale + corpus counts: check `docs/decisions.md` D12–D31; the full
  planemo→GTR map: `docs/planemo_linter_parity.md`.
- **`command_text.py`** (in **tier 1**, `galaxy_tool_source.command_text`) — the
  read-only lexer `GTR020.2` reads `<command>` text through: a single character scan
  tracking `'…'` / `"…"` quote state **across newlines** and skipping Cheetah
  directive/comment lines, yielding each unquoted `$var` with its character span.
  It only classifies, never rewrites — a lighter read-only lexer, deliberately
  separate from the faithful `cheetah_cdm` lexer (§19) that the rename mutator uses,
  so it needs none of the mutation machinery. It moved to tier 1 (with `command_vars.py`, the quoting-safety
  classifier, and `cdata.py`, the CDATA-wrappability predicate) so the `GTR020.1` /
  `GTR018.1` / `GTR019.1` codemods (tier 2) can share them with these checks; see
  `galaxy-tool-source/docs/decisions.md` §16.

**Contract:** detect-only, LBYL, no mutation, no dependency on the mutating tiers.
Findings are advisory — informational unless the user opts into `--strict`.
*(check `docs/decisions.md` D1; GTR020.2/GTR032 data-backed in D3–D5; the partition
`.2` residual restriction in D9; the planemo-parity wave in D12–D30; IUC coverage map
in `docs/iuc_best_practices.md`; full planemo→GTR map in `docs/planemo_linter_parity.md`.)*

---

## 7. Tier 3.6 — `galaxy-tool-refactor-registry` (registry + facade)

The first tier that knows about all three rule families at once. **Library-first:**
no `click`, no `sys.exit`, no printing; inputs are path / bytes / `ToolDocument`;
outputs are structured dataclasses; files are written only when a `write_path` is
given. This is what lets both the CLI and the MCP server be thin adapters.

- **`RuleHandle`** — `handle.py` — the uniform, code-addressable adapter that
  papers over the three families' different native shapes (codemod yields
  `Change`s via a `Module`; fmt yields `Edit`s; check yields `Violation`s and
  never fixes). Fields: `meta`, `family` (`"codemod"` / `"fmt"` / `"check"`),
  `fixable`, `detect(document) -> list[Violation]`, `apply(document) -> None | None`
  (`None` exactly for advisory rules). `adapters.py` builds one handle per family.
- **`registry()` / `all_handles()` / `by_code` / `known_codes` / `advisory_codes`**
  — `registry.py` — the cached `code -> RuleHandle` index. `registry()` is the
  **selectable** set (canonical codemods + cosmetic fmt + advisory checks);
  `all_handles()` additionally includes the **non-selectable** codemods
  (GTR007–GTR012 + GTR093 — internal to `UpgradeToLatest` — plus the runtime-gated
  GTR014–GTR016, applied by the facade's `upgrade`, plus the opt-in-command-only
  GTR092, applied by `convert-help`; `adapters.non_selectable_codemods` /
  `OPT_IN_COMMAND_BY_CODE`).
  `_index()` asserts the GTR namespace is **collision-free** — a reused code
  fails loudly here.
- **Rulesets** — `rulesets.py` — named rule subsets, **derived from per-rule
  membership** (`RuleMeta.rulesets`, the tier-0.5 catalog of names+descriptions):
  `ruleset_codes()` groups the registry by each rule's declared set, so the
  mapping can never drift from the rules that exist. Seeded: `cosmetic` (fmt rules
  only), `default` (canonical codemods + cosmetic; the **default**, byte-identical
  to the standalone `format` pipeline — a regression test pins the facade against
  the live `canonical_codemods()` + fmt), `iuc` (mirrors `default` for now), and
  `strict` (`default` + every advisory check). A maintainer adds a ruleset by
  tagging its member rules + a catalog entry; no user-defined rulesets. The
  hardcoded `CANONICAL_CODEMODS` tuple is gone — membership lives on the rules.
- **Selection** — `resolve.py` — `resolve_codes(*, rulesets, select, ignore)` with
  **ruff-style precedence `--ignore` ▸ `--select` ▸ `--ruleset`**: the base is the
  **union** of the named rulesets (default `{"default"}`); `--select` *replaces*
  it (resets the base, not adds), then `--ignore` subtracts. A `--select`/`--ignore`
  token is a GTR code, a partition-parent code, **or a planemo linter name**
  (case-insensitive → the covering GTR code(s)). Unknown names raise typed
  `UnknownRuleset` / `UnknownRuleCode` (`errors.py`). `resolve_upgrade_codes`
  is the ruleset-less variant for `upgrade`.
- **Planemo aliases** — `planemo.py` (`planemo_index()`, the derived `planemo name
  → GTR codes` map) + `parity.py` (`render_parity_table()` — the generated GTR
  coverage table of `docs/planemo_linter_parity.md`). Both derive from each rule's
  `meta.planemo_linters`; a freshness test pins the committed table, and the alias
  set is reconciled against a vendored canonical linter list + the parity Summary
  count (`test_planemo_aliases.py`). (Registry D16–D17.)
- **`apply_selection`** — `apply.py` — applies a code set in `format`'s order:
  codemods first (by `meta.order`), then the cosmetic fmt rules as
  one batch through `format_tool_document_subset` (which serialises once).
  Advisory codes are skipped. Even a codemod-only selection ends in fmt — so
  **fmt stays the only serializer**.
- **The facade** — `facade.py` — the library-first entry points:
  - `run(source, *, codes, write_path=None) -> FormatResult` — apply the fixable
    rules; detect advisory ones on the pre-format tree and return them as notes
    (never mutating for them).
  - `upgrade(source, *, codes, write_path=None) -> UpgradeResult` — always run
    `UpgradeToLatest` (its purpose), `FixTypos` first if selected, then the
    runtime-gated fixes the tool *crosses* (GTR014–GTR016, §24), then the rest.
    Reports `steps_applied` / `missing_upgrade`, a per-tool **semantic warning**
    note (the crossed Galaxy behaviour codes that *apply* — codemod §23/§25), and
    `behavior_preserving: bool | None` — the affirmative verdict when the bump
    crosses no *applicable* behaviour code (codemod §23).
  - `detect(source, *, codes) -> DetectResult` — report-only; fmt rules detected
    as one net-effect group, codemod/advisory rules per-code.
  - `list_rulesets()` / `list_rules(*, include_upgrade=False)` — introspection.
  - Results live in `results.py` (`FormatResult`, `UpgradeResult`, `DetectResult`,
    `RuleInfo`, `RulesetInfo`).
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
codemod / check tiers directly. Ten subcommands (`format`, `upgrade`, `check`,
`find-references`, `rename-param`, `rulesets`, `rules`, `normalize-macros`,
`convert-help`, `tokenize-version`) —
`find-references` is a read-only query for a parameter's Cheetah `$var` reference sites
(`galaxy_tool_source.cheetah_refs`; cli `docs/decisions.md` §D8) and `rename-param` is its
mutating sibling (the first Cheetah mutator, `galaxy_tool_source.cheetah_rename`; cli §D9):

- **`format`** — apply a ruleset's (or selection's) fixable rules then cosmetic
  formatting; never changes `profile=`. Advisory rules in a selection are reported
  as notes, never applied. Macro files are cosmetically formatted (kind-applicable
  rules only). Wraps `facade.run` inside `cli_support.run`.
- **`upgrade`** — repair → iterative profile upgrade → format. Opt-in, semantic;
  **no `--ruleset`** (`--select` / `--ignore` adjust its fixable set). Runs a
  whole-run phase first (`_upgrade_macro_profile_tokens`) that bumps agreed
  imported `@PROFILE@` tokens, then wraps `facade.upgrade` per file.
- **`check`** — report-only linter; one `file:line  CODE  message` per finding.
  Fixable findings fail the run; advisory findings (the `detect_only` checks, under
  `--ruleset strict`) are informational unless `--strict`. Wraps `facade.detect`.
- **`rulesets` / `rules`** — introspection over `facade.list_rulesets` /
  `list_rules`.
- **`normalize-macros`** — opt-in, repo-scoped: lowercase literal `format` /
  `ftype` in `<macros>`-root files (`macro_datatype.normalize_macro_files`). Not in
  the per-tool pipeline — it writes files other than the one named (cli §D7).
- **`convert-help`** — opt-in: RST `<help>` → Markdown when provable (profile ≥
  24.2 + the tier-1 render-equivalence gate). Swaps Galaxy's rendering engine, so
  never part of `format` / `upgrade`. Wraps `facade.convert_help` (cli §D12).
- **`tokenize-version`** — opt-in: factor a literal `version="<base>+galaxy<suffix>"`
  into `@TOOL_VERSION@`/`@VERSION_SUFFIX@`, kept only when the expansion-equality
  gate proves the macro expansion byte-identical. Wraps `facade.tokenize_version`
  (cli §D13, registry D19).

Selection (`--ruleset` / `--select` / `--ignore`) is shared across
`format` / `upgrade` / `check` with the ruff-style precedence above (`--ruleset`
unions the named sets). Exceptions from the facade (`UnknownRuleset` /
`UnknownRuleCode`) are caught here at the CLI boundary and re-raised as
`click.BadParameter`.

**`galaxy-tool-refactor-mcp`:** an agent-facing MCP server over the same facade
(discover rules/rulesets, run `format` / `upgrade` / `check` / `convert-help` /
`tokenize-version` on supplied content).
The facade's library-first shape is what makes it a thin adapter: a FastMCP
binding (`server.py`) over a protocol-agnostic `service.py` (facade → JSON). Goal 1
of the vision is shipped; agent-authored rules (Goal 2) remain future. *(cli
`docs/decisions.md` D1–D6; mcp `docs/decisions.md` D1, `docs/vision.md`.)*

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
4. **One unified `GTR` rule namespace.** Every rule — fmt cosmetic, structural
   codemod, and advisory check alike — carries a `GTR###` code; **fixability is a
   rule property** (`RuleHandle.fixable` / `RuleMeta.detect_only`), deliberately
   *not* encoded in the prefix (the old `GTX`=fixable / `IUC`=advisory split was
   incidental and was retired). Codes are globally unique and collision-guarded by
   `registry._index()`. Upgrade-only GTR codes exist but are not user-selectable:
   007–012 (validity-gated, internal to `UpgradeToLatest`) and 014–016
   (runtime-gated, applied by the facade's `upgrade` — see §4 below). The flat
   advisory checks enforce the external IUC best-practices standard.
   **Partition sub-rules.** A practice that splits into a provably-fixable part and
   an advisory residual is one **parent** code with two dotted sub-rules: `GTR020.1`
   (fix) + `GTR020.2` (advisory), under parent `GTR020`. The parent is a
   registry-level grouping (selectable — `--select GTR020` expands to both — but not
   itself a rule); each `.2` advisory's detect is restricted to the *complement* of
   its `.1` fix via a shared tier-1 predicate, so the two partition cleanly. Four
   practices use this: GTR018 / GTR019 (CDATA), GTR020 (quoting), and GTR089
   (help-RST repair). Registry D10.
5. **Dataclass-result convention.** Entry points return result dataclasses
   (`ParseResult`, `ValidationResult`, `FormatResult`, …) and don't raise on domain
   failures. Exceptions are reserved for the CLI boundary (chained `from e`) and
   third-party API edges with no LBYL form. Per dignified-python.
6. **Idempotence + validity preservation.** Codemods are idempotent and never
   regress XSD validity; fmt is idempotent (`format(format(x)) == format(x)`).
   These are proven by corpus sweeps, and crashes are retained as regression
   fixtures.
7. **Shared selection model.** `--ruleset` / `--select` / `--ignore` work
   identically across `format` / `upgrade` / `check` (upgrade rejects `--ruleset`),
   resolved once in `resolve.py`.
8. **Macro handling is cosmetic-only in v1, with two content exceptions.** Macro
   files have no codemods (the codemods are `applies_to={"tool"}`), but two operations
   edit *content* in an imported macro file by locating the construct in its own source
   ("locate-in-source", not expansion): the consensus imported `@PROFILE@` token bump
   (`macro_profile.py`) and **cross-file `rename-param`** — renaming a parameter across a
   tool and its imported macros (tier-1 `bundle.py` §3; registry `bundle_rename.py`
   gate). Both gate a *shared* macro (imported by >1 tool): `@PROFILE@` by importer
   consensus, rename by sole-ownership within a `--repo-root` (skip-and-report otherwise,
   or — opt-in — rename across every importer in lockstep via `rename_param_consensus`,
   registry D14).

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
  report churn a coherent subset would cancel; only the shipped rulesets (full
  GTR001/003/004 trio) are guaranteed idempotent. The same order-sensitivity means
  the registry's `apply_selection` deliberately **batches** the selected fmt rules
  through `format_tool_document_subset` rather than calling each fmt
  `RuleHandle.apply` one at a time — so a fmt handle's per-rule `apply` exists for
  interface uniformity but is not the path the facade uses.
- **fmt serialises to a throwaway temp file outside the canonical path.** Tier 1's
  `macros.expand_from_tree` writes `etree.tostring(root)` into a `TemporaryDirectory`
  so Galaxy's path-based macro expander can run; the result is discarded. So
  "fmt is the only serializer" is precisely "of *canonical output* bytes." A
  consequence: expansion resolves `<import>` against the document's
  `source_path.parent`, so an in-memory document loaded from bytes (no
  `source_path`) resolves imports against that throwaway temp dir and silently
  falls back to the raw tree. The CLI therefore loads each file *by path*
  (`cli_support._transform_file`), not from the bytes it already read.
- **Macro write-back is locate-in-source, not general expansion provenance.** Two
  edits the framework now propagates into an *imported* macro file both work by
  locating the construct *in its source file* (not via an expanded-node→source map):
  the `@PROFILE@` token bump (`macro_profile.py`, addressable by token name, with an
  importer-consensus gate) and — since 2026-06-03 (Phase 2a) — literal `format`/`ftype`
  normalization (`macro_datatype.py`, the opt-in `normalize-macros` command, gate-free
  because lowercasing is validity-safe; registry `docs/decisions.md` D8). Expansion
  (`macros.expand_*`) remains **lossy** — a throwaway tree with no element→source-file
  mapping — so an edit that needs *post-expansion attribution* (a token-supplied
  `format="@FORMAT@"`, an arbitrary expanded node) still has no mechanism. That general
  provenance layer (Phase 2b) is the load-bearing limitation behind full
  "consistent expand-and-modify", deferred until a consumer needs it
  (`galaxy-tool-xml-codemod/docs/macro-aware-normalization.md`,
  `docs/macro_handling_architecture.md` §4.2/§6; the literal-value payoff was 15 tools).

---

## 11. How the contracts are kept true — QA machinery

The invariants above are enforced by standing tooling, not goodwill (`scripts/`):

- **`corpus_check.py`** — corpus sweeps with five subcommands: `validate`
  (tier-1 invariants), `fmt` (tier-3 idempotence), `codemod <module>:<Class>`
  (one structural codemod's idempotence + post-validity), `rules` (every GTR rule
  in isolation), `check` (unified detect violation counts). Failures are retained
  as permanent regression fixtures.
- **`measure.py`** — decision-backing "standing measurements"; each subcommand
  answers one empirical question and writes a `docs/*_stats.md` artifact. Reproduced
  analyses live here (with a test), not in throwaway scripts.
- **`qa_gate.sh`** — the deterministic pre-push gate: ruff + mypy (strict, per
  package) + pytest across all eight packages. A `git push` hook blocks on
  failure. (A mechanical backstop — *not* a substitute for the full pre-PR audit.)
- **`fetch_schemas.py` / `fetch_toolshed.py` / `regenerate.py`** — vendor the XSDs,
  clone the corpus, and regenerate the per-version typed models.

---

## Reference index

Each abstraction → its file → the decision record that justifies it.

> **Naming note:** tier 1 was renamed `galaxy-tool-xml` → **`galaxy-tool-source`**
> (2026-06-10, pre-PyPI; xml `docs/decisions.md` §26). Dated records — decisions
> entries, audit records, research notes — keep the old name verbatim; the "xml"
> shorthand in the Rationale column refers to the renamed package.

| Abstraction | File | Rationale |
|---|---|---|
| `RuleMeta`, `Violation` | `galaxy-tool-refactor-rules/src/.../meta.py`, `violation.py` | rules `docs/decisions.md` §D1 |
| `ToolDocument` / `MacroDocument` | `galaxy-tool-source/src/.../document.py` | xml `docs/decisions.md` §3, §15 |
| `load_tool` / `validate_tool` / `newest_valid_profile` | `galaxy-tool-source/src/.../binding.py` | xml `docs/decisions.md` §1, §10 |
| profile resolution | `galaxy-tool-source/src/.../profiles.py` | xml `docs/decisions.md` §10 |
| `unquoted_cheetah_vars` (command lexer) | `galaxy-tool-source/src/.../command_text.py` | xml `docs/decisions.md` §16 |
| `provably_quotable` (quoting-safety classifier) | `galaxy-tool-source/src/.../command_vars.py` | xml `docs/decisions.md` §16 |
| `cdata_wrappable` / `needs_cdata` / `is_cdata_wrapped` | `galaxy-tool-source/src/.../cdata.py` | xml `docs/decisions.md` §16; registry D10 |
| `cheetah_spans` / `CheetahSpan` (faithful CT3 lexer) | `galaxy-tool-source/src/.../cheetah_cdm.py` | xml `docs/decisions.md` §19 |
| `tool_cheetah_references` / `CheetahRef` (reference model) | `galaxy-tool-source/src/.../cheetah_refs.py` | xml `docs/decisions.md` §18 |
| `rename_param` / `rename_param_plan` / `RenameOutcome` / `RenamePlan` | `galaxy-tool-source/src/.../cheetah_rename.py` | xml `docs/decisions.md` §20 |
| `ToolBundle` / `load_bundle` / `rename_param_in_bundle` | `galaxy-tool-source/src/.../bundle.py` | xml `docs/decisions.md` §21 |
| `rst_is_invalid` / `repair_help_rst` (help-RST predicate + repair) | `galaxy-tool-source/src/.../rst.py` | xml `docs/decisions.md` §23 |
| `CodemodCommand`, `Cursor`, `Change` | `galaxy-tool-xml-codemod/src/.../codemod.py`, `cursor.py`, `change.py` | codemod `docs/decisions.md` §6, §19 |
| `canonical_codemods()` / `AUTO_UPGRADE_CODEMODS` | `galaxy-tool-xml-codemod/src/.../canonical.py` | codemod `docs/decisions.md` §16, §36 |
| upgrade codemods | `galaxy-tool-xml-codemod/src/.../upgrades.py`, `codemods/upgrade_*.py` | codemod `docs/decisions.md` §11–14 |
| `PROFILE_UPGRADE_CODES` / `upgrade_codes_crossed` / `upgrade_codes_applicable` | `galaxy-tool-xml-codemod/src/.../profile_semantics.py` | codemod `docs/decisions.md` §22–23, §25 |
| `RuntimeGatedFix` / `runtime_fixes_for` | `galaxy-tool-xml-codemod/src/.../codemods/_runtime_gated.py`, `runtime_fixes.py` | codemod `docs/decisions.md` §24 |
| `normalize_datatype_attributes` (shared `format`/`ftype` helper, tier-2; reused by registry `macro_datatype`) | `galaxy-tool-xml-codemod/src/.../datatype_format.py` | codemod `docs/decisions.md` §14; registry D8 |
| `Rule`, `Edit`, serializer | `galaxy-tool-xml-fmt/src/.../rules.py`, `edits.py`, `serializer.py` | fmt `docs/decisions.md` §D3, §D11 |
| `format_*` / `detect_*` | `galaxy-tool-xml-fmt/src/.../format.py`, `detect.py` | fmt `docs/decisions.md` §D15 |
| `cli_support` engine | `galaxy-tool-xml-fmt/src/.../cli_support.py` | fmt `docs/decisions.md` §D12 |
| `CheckRule`, `detect_violations` | `galaxy-tool-xml-check/src/.../rules.py`, `detect.py` | check `docs/decisions.md` §D1; `docs/iuc_best_practices.md` |
| `RuleHandle`, registry | `galaxy-tool-refactor-registry/src/.../handle.py`, `registry.py` | registry `docs/decisions.md` D1–D2 |
| `Ruleset` catalog (names + descriptions) | `galaxy-tool-refactor-rules/src/.../rulesets.py` | rules `docs/decisions.md` §D4 |
| rulesets, `resolve_codes`, `apply_selection` | `galaxy-tool-refactor-registry/src/.../rulesets.py`, `resolve.py`, `apply.py` | registry `docs/decisions.md` D3–D4, D15 |
| planemo aliases + parity table | `galaxy-tool-refactor-registry/src/.../planemo.py`, `parity.py` | registry `docs/decisions.md` D16–D17 |
| `run` / `upgrade` / `detect` facade | `galaxy-tool-refactor-registry/src/.../facade.py`, `results.py` | registry `docs/decisions.md` D1 |
| imported-`@PROFILE@` upgrade | `galaxy-tool-refactor-registry/src/.../macro_profile.py` | registry `docs/decisions.md` D5 |
| imported-macro `format`/`ftype` normalization | `galaxy-tool-refactor-registry/src/.../macro_datatype.py` | registry `docs/decisions.md` D8 |
| the CLI | `galaxy-tool-refactor-cli/src/.../cli.py` | cli `docs/decisions.md` D1–D6 |
| the MCP server | `galaxy-tool-refactor-mcp/src/.../server.py` (+ `service.py`) | mcp `docs/decisions.md` D1 |

### Rule codes at a glance

| Code | Class | File | Family |
|---|---|---|---|
| GTR001 | `CanonicalIndent` | `galaxy-tool-xml-fmt/.../rule_indent.py` | fmt (cosmetic) |
| GTR002 | `ReorderParamAttributes` | `galaxy-tool-xml-codemod/.../reorder_param_attributes.py` | codemod (canonical) |
| GTR003 | `BlankLineBetweenSections` | `galaxy-tool-xml-fmt/.../rule_blank_line.py` | fmt (cosmetic, tool-only) |
| GTR004 | `EmptyElementShorthand` | `galaxy-tool-xml-fmt/.../rule_empty_element.py` | fmt (cosmetic) |
| GTR005 | `ReorderToolAttributes` | `galaxy-tool-xml-codemod/.../reorder_tool_attributes.py` | codemod (canonical) |
| GTR006 | `FixTypos` | `galaxy-tool-xml-codemod/.../fix_typos.py` | codemod (canonical, validation-driven) |
| GTR007 | `UpdateProfile` | `galaxy-tool-xml-codemod/.../update_profile.py` | codemod (upgrade-only) |
| GTR008–011, GTR093 | `Upgrade19_01` … `Upgrade25_1`, `Upgrade21_09` | `galaxy-tool-xml-codemod/.../upgrade_*.py` | codemod (upgrade-only) |
| GTR012 | `UpgradeToLatest` | `galaxy-tool-xml-codemod/.../upgrades.py` | codemod (upgrade-only orchestrator) |
| GTR013 | `ReorderToolChildren` | `galaxy-tool-xml-codemod/.../reorder_tool_children.py` | codemod (canonical) |
| GTR014 | `FixFromWorkDirWhitespace` | `galaxy-tool-xml-codemod/.../fix_from_work_dir_whitespace.py` | codemod (upgrade-only, runtime-gated) |
| GTR015 | `FixOutputFormatInput` | `galaxy-tool-xml-codemod/.../fix_output_format_input.py` | codemod (upgrade-only, runtime-gated) |
| GTR016 | `FixInterpreter` | `galaxy-tool-xml-codemod/.../fix_interpreter.py` | codemod (upgrade-only, runtime-gated) |
| GTR017 | `NormalizeBooleanValues` | `galaxy-tool-xml-codemod/.../normalize_boolean_values.py` | codemod (canonical, validation-driven) |
| GTR018.1 / .2 | `WrapCommandCdata` (fix) + command-CDATA residual (advisory) | codemod + check | **partition** GTR018 (§29, registry D10) |
| GTR019.1 / .2 | `WrapHelpCdata` (fix) + help-CDATA residual (advisory) | codemod + check | **partition** GTR019 (§29) |
| GTR020.1 / .2 | `SingleQuoteCommandVars` (fix) + single-quote residual (advisory) | codemod + check | **partition** GTR020 (§30, check D9) |
| GTR035.1 / .2 | `TrimAttributeWhitespace` (fix, requirement version) + `NameWhitespace` (advisory) | codemod + check | **partition** GTR035 (codemod §33 addendum, check D33) |
| GTR089.1 / .2 | `RepairHelpRst` (fix) + `HelpRstResidual` (advisory) | codemod + check | **partition** GTR089 (xml §23, codemod §37, check D31) |
| GTR021, GTR023–029 | `TestsPresent` … (presence/shape) | `galaxy-tool-xml-check/.../checks/tool.py` | check (flat advisory) |
| GTR032 | `CommandAndJoining` | `galaxy-tool-xml-check/.../checks/tool.py` (+ `lone_amp.py`) | check (advisory — D3 deferral ended by D34) |
| GTR033 | `RequirementVersionPinned` | `galaxy-tool-xml-check/.../checks/tool.py` | check (advisory — D7) |
| GTR034 | `UnusedParam` | `galaxy-tool-xml-check/.../checks/inputs.py` | check (advisory — reference-usage) |
| GTR038–GTR091 | planemo-parity wave (`NoTodoText`, `CommandPresent`, `InputsPresent`, … 54 input/output/test/validator/help checks; GTR089 is the partition row above) | `galaxy-tool-xml-check/.../checks/` (`tool`/`outputs`/`inputs`/`validators`/`tests`/`help`) | check (advisory — planemo parity, D12–D32) |
| GTR092 | `ConvertHelpToMarkdown` | `galaxy-tool-xml-codemod/.../convert_help_markdown.py` | codemod (opt-in `convert-help` command only — §38, registry D18) |
| GTR094 | `TokenizeVersion` | `galaxy-tool-xml-codemod/.../tokenize_version.py` | codemod (opt-in `tokenize-version` command only — §43, registry D19) |
