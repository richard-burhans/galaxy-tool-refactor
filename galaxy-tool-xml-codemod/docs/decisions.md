# Decisions and Assumptions

A maintainer-facing record of every non-obvious assumption and design
decision in `galaxy-tool-xml-codemod`. Live document — extend when new
evidence arrives or an assumption changes.

The narrative architecture lives elsewhere: `CLAUDE.md` (current state),
`README.md` (intro), `PLAN.md` (milestone plan and open questions),
`docs/architecture.md` (forked from
`galaxy-tool-xml/docs/codemod-architecture.md`). This file is the
**why** for the choices those docs reflect.

Each entry should answer: *what we assume / chose · what the alternative
was · what evidence or constraint settled it*. Mirror the conventions of
`galaxy-tool-xml/docs/decisions.md`: § numbering, date stamps, and a
reproducible command for any data-driven claim.

---

## 1. `parse_module` signature is narrower than Tier 1's `Source`

**Date:** 2026-05-28 (M1 design).

- **What we chose:** `parse_module(source: Path | bytes | ToolDocument)`.
- **Alternative:** Mirror Tier 1's `Source = str | Path | bytes | BinaryIO`,
  add `ToolDocument`.
- **Why:** dignified-python prefers one clear call site per input form;
  mypy strict catches misuse at the call site. `BinaryIO` is unused —
  codemods don't stream. `str`-as-path is awkward because the LBYL
  `isinstance` ladder would have to disambiguate `str` (a path? raw
  XML?) from `bytes`. Callers with a string path wrap it:
  `parse_module(Path(s))`. Revisit if real callers complain.

## 2. `parse_module` is strict on bytes — matches `load_tool`

**Date:** 2026-05-28 (M1 design).

- **What we chose:** Any well-formedness error on `bytes` input raises
  `ToolXmlSyntaxError`. Implementation funnels both `Path` and `bytes`
  through `galaxy_tool_xml.binding.load_tool`.
- **Alternative:** Route bytes through the lenient `parse_tool` and
  raise only when recovery yields no document at all.
- **Why:** `parse_module`'s contract is "returns a `Module` or raises"
  — symmetric across input forms is simpler to teach. A
  partially-recovered tree with embedded syntax errors is a footgun for
  a refactoring tool, where the user expects the input to round-trip.
  `ToolXmlSyntaxError` is already a public Tier 1 type, so the API
  surface does not grow.

## 3. `parse_module(ToolDocument)` shares the document by reference

**Date:** 2026-05-28 (M1 design).

- **What we chose:** `parse_module(doc)` returns a `Module` whose
  `.document is doc` — no copy.
- **Alternative:** Defensive `copy.deepcopy(doc.tree)` inside
  `parse_module`.
- **Why:** Atomicity by deep-copy snapshot is the **harness's** job per
  `docs/architecture.md` § Atomicity. Splitting it between parser and
  harness creates two truths about who copies; pinning the policy to
  the harness keeps `parse_module` cheap and predictable. The harness
  takes a snapshot on entry, runs the codemod against the copy,
  discards on failure, promotes on success.

## 4. `Module` is a frozen dataclass with a public `document` field

**Date:** 2026-05-28 (M1 design).

- **What we chose:** `@dataclass(frozen=True)` with `document:
  ToolDocument` as a public field (no `_document` + getter property).
- **Alternative:** Plain `@dataclass` with `_document` private and a
  read-only `@property document(self)`.
- **Why:** `Module` has no invariant to defend — the wrapper is just a
  bag of three accessors (document, model, cursor). Frozen signals that
  the wrapper identity is stable for the life of a codemod run (the
  underlying lxml tree mutates in place; the `Module` does not get
  reassigned). Frozen also makes the dataclass hashable, useful for
  caches later.

## 5. `Module.model` is a plain `@property` — not cached

**Date:** 2026-05-28 (post-audit).

- **What we chose:** `@property` that re-binds the typed model against
  the current tree on every access.
- **Alternative:** `@cached_property` for the original M1 design (xsdata
  binding is not free).
- **Why:** The cached property silently returned stale data after any
  codemod mutated the underlying tree. The next codemod author reading
  `module.model` after a sibling codemod's mutation would have seen
  pre-mutation values with no error. xsdata binding is cheap enough for
  tool-sized trees that the no-staleness contract wins over the small
  CPU saving. A caller that needs many model reads can capture the
  result locally.

## 6. Visitor dispatch by tag-PascalCase, not typed-model class

**Date:** 2026-05-28 (M3 design).

- **What we chose:** `_visit_method_name("param") → "visit_Param"` —
  string transformation of the XML tag.
- **Alternative:** Look up the typed-model class for the element's
  position in the tree and dispatch on that class name (so
  `<when>` inside `<conditional>` dispatches as
  `visit_ConditionalWhen`, `<when>` inside `<change_format>` as
  `visit_ChangeFormatWhen`, …).
- **Why:** The architecture targets typed-class dispatch long-term, but
  the two structural codemods we ship operate on tags
  (`<param>`, `<tool>`) where the typed-class name is unambiguous
  anyway. Per-position typed-class resolution is non-trivial work
  (`Cursor` needs to know its parent type), deferred until a codemod
  actually needs to distinguish per-context variants of a tag.
  Tag-PascalCase reads naturally and matches the long-term spelling for
  unambiguous tags.

## 7. `Cursor.reorder_attributes` raises on non-permutation

**Date:** 2026-05-28 (M2 design).

- **What we chose:** `ValueError` when `names` is not a permutation of
  the element's current attribute names.
- **Alternative:** Silent no-op (the behaviour of the deleted
  `galaxy-tool-xml-fmt` `ReorderAttributes` edit case).
- **Why:** A codemod that builds `names` from `canonical_order` cannot
  produce a non-permutation by construction — the only way to hit the
  error is a programmer bug. Raising surfaces the bug at the offending
  line; silent no-op buries it as "this codemod doesn't seem to reorder
  some tools." The cost of the defensive `set(names) != set(current)`
  check is negligible; the loud failure is worth it.

## 8. `MACRO_MODE` removed pending a real consumer

**Date:** 2026-05-28 (post-audit, M3 cleanup).

- **What we chose:** No `MACRO_MODE` ClassVar on `CodemodCommand`.
- **Alternative:** Keep the declared-but-unused ClassVar (the original
  M3 plan) so future codemods have a structured place to declare their
  macro-handling expectation.
- **Why:** YAGNI. The harness never read `MACRO_MODE`, so any codemod
  that set it would silently get the default (un-macro-aware) behaviour
  with no enforcement — a false sense of safety. Re-introduce the
  contract when a codemod that needs macro expansion / stripping is
  actually written, and when the harness has the logic to honour it.

## 9. Three-tier independence: fmt's library does not depend on codemod

**Date:** 2026-05-28 (architecture correction).

- **What we chose:** `galaxy-tool-xml-fmt` declares
  `galaxy-tool-xml-codemod` as an **optional extra** (`[canonical]`),
  not a hard dependency. fmt's library (`format_tool_document`) is
  cosmetic-only. fmt's CLI uses `importlib.util.find_spec` to detect
  the optional package at runtime and orchestrates
  `CANONICAL_CODEMODS` before its cosmetic rules when present.
- **Alternative:** Hard dependency from fmt → codemod; merge
  `MANDATORY_CODEMODS` into `format_tool_document`.
- **Why:** A user who only wants cosmetic formatting (the simplest
  install path: `xml + fmt`) must not be forced to pull in the codemod
  framework. The "default operation" — produce conformant XML — uses
  all three layers, but that's a workflow concern owned by the CLI, not
  a library contract. Keeping the layers independent means the codemod
  package can grow new structural rules without forcing fmt re-releases,
  and the fmt cosmetic pipeline can be consumed standalone (e.g. by
  other tools that already do their own structural canonicalisation).

## 10. `CANONICAL_CODEMODS` (renamed from `MANDATORY_CODEMODS`)

**Date:** 2026-05-28 (architecture correction).

- **What we chose:** The public tuple is named `CANONICAL_CODEMODS` and
  lives in `canonical.py`.
- **Alternative:** Keep the original `MANDATORY_CODEMODS` /
  `mandatory.py` naming from the initial design.
- **Why:** "Mandatory" made sense when fmt's library hard-ran the set.
  After decision 9 (fmt no longer hard-depends), nothing forces these
  codemods to run — fmt's CLI runs them by default but a caller using
  fmt's library directly may not. "Canonical" reads correctly in the
  current shape: "these are the codemods that produce the canonical
  output you'll get when you run `galaxy-tool-xml-fmt` with the
  `[canonical]` extra installed."

## 11. `FixTypos` — a validation-driven repair codemod that overrides `apply`

**Date:** 2026-05-28.

- **What we chose:** A new codemod `FixTypos` (`codemods/fix_typos.py`)
  that rewrites near-miss typos so a well-formed-but-globally-invalid tool
  validates. It runs **first** in `CANONICAL_CODEMODS` (see §13 — it was
  briefly opt-in before the profile-update work folded it into the default
  pipeline). Its `newest_valid_profile is None` guard means it only acts on
  tools that validate nowhere, so making it canonical does not touch
  already-valid tools. It **overrides `apply`** instead of defining
  `visit_<Tag>` methods: it deep-copies the root on entry, then for each
  vendored profile newest-to-oldest restores from that snapshot, applies
  the corrections Tier-1's `suggest_corrections(..., profile=V)` reports
  (through `Cursor` primitives only — `rename_attribute`, `rename_tag`,
  `set_attribute`), and stops at the first profile that validates. If none
  validates it restores the snapshot, leaving the document byte-identical.
  It guards on `newest_valid_profile is None`, and never writes `profile=`.
- **Alternative:** Force the repair into the `visit_<Tag>` walk, or add a
  separate base class for validation-driven codemods.
- **Why:** The repair loop is whole-document and validation-feedback
  driven (try a profile, fix, re-validate, revert on miss) — it has no
  per-element uniform action, so the visitor walk is the wrong shape.
  `apply(module) -> None` is the only contract the sweep and fmt's CLI
  depend on, so overriding it keeps `FixTypos` a first-class
  `CodemodCommand` without a parallel hierarchy. The snapshot/revert lives
  inside the codemod, not a shared harness, because it is the first and so
  far only consumer — consistent with §8's "introduce shared machinery
  when a real consumer arrives." The guard makes the codemod idempotent by
  construction (after a repair the tool validates somewhere, so a re-run is
  an immediate no-op). Leaving `profile=` untouched keeps the job narrow
  (spelling, not version policy); the maintainer decides whether to bump
  the declared profile. This codemod is also what pulled M2's deferred
  `rename_tag` / `rename_attribute` mutation primitives into existence.

## 12. Per-codemod corpus-sweep eligibility hooks

**Date:** 2026-05-28.

- **What we chose:** Two classmethods on `CodemodCommand` —
  `corpus_eligible(document)` and `corpus_validation_profile(document)` —
  that default to the existing `corpus_test_profile` policy and are
  consulted by `scripts/corpus_check.py`'s `codemod` sweep.  `FixTypos`
  overrides both: eligible iff `newest_valid_profile is None`, and the
  post-apply validation profile is `newest_valid_profile` (the version the
  repaired tool now validates at). The sweep gained a `no-repair` outcome
  for an eligible tool the codemod could not bring to validity.
- **Alternative:** Special-case `FixTypos` in `corpus_check.py` with an
  `isinstance` branch, or a `--targets {valid,no-valid}` CLI flag.
- **Why:** The default policy excludes exactly `FixTypos`'s target
  population (tools that validate nowhere), so the sweep needed an
  inversion. Putting the policy on the codemod class keeps `corpus_check.py`
  codemod-agnostic (open/closed) and keeps the two structural codemods
  byte-for-byte unchanged. The validation profile must be computed *after*
  `apply`, because for `FixTypos` the validating version does not exist
  until the repair runs. A `no-repair` result is a legitimate outcome, not
  a regression, so it is counted but never retained as a fixture.
- **Reproduce:** `uv run python -m scripts.corpus_check codemod
  galaxy_tool_xml_codemod.codemods.fix_typos:FixTypos --limit 40` →
  40 eligible (5 repaired, 35 no-repair), 0 non-idempotent /
  post-validate-failed / crashed; the no-valid population is now swept
  (it was skipped wholesale before these hooks).

## 13. `UpdateProfile` + a canonical pipeline ordered repair → profile → reorder

**Date:** 2026-05-28.

- **What we chose:** A new codemod `UpdateProfile`
  (`codemods/update_profile.py`) that declares the newest profile the tool
  actually validates at — adding `profile=` when absent, bumping it up when
  a declared profile is older. It is **bump-up-only** (never lowers), a
  no-op when already correct, when the tool validates nowhere, and when the
  declared profile is not a parseable version (e.g. `@PROFILE@`). Both
  `FixTypos` and `UpdateProfile` join `CANONICAL_CODEMODS`, in the order
  `FixTypos → UpdateProfile → ReorderParamAttributes → ReorderToolAttributes`.
  Like `FixTypos` it is document-level and validation-driven, so it
  overrides `apply`; it needs no eligibility-hook override — the default
  ("validates somewhere") is exactly its population.
- **Alternative:** Always set `profile=` to `newest_valid_profile` even when
  that lowers the declared version; or keep both codemods opt-in.
- **Why:** The `profile` attribute is a runtime-compatibility contract, not
  just a schema selector, so lowering it could falsely claim compatibility
  with an older Galaxy — hence bump-up-only. The ordering is load-bearing:
  `FixTypos` must run first so a repaired tree is validatable before
  `UpdateProfile` reads its newest-valid profile, and `UpdateProfile` must
  precede `ReorderToolAttributes` so a freshly-added `profile=` (appended at
  the end by `set_attribute`) is moved into its documented slot. The two
  attribute reorderers run last, once structure and profile are settled.
  Making the set canonical (rather than opt-in) is a deliberate choice: the
  default "format my tool" workflow should repair typos when nothing else
  validates and keep the declared profile honest — and `FixTypos`'s guard
  plus `UpdateProfile`'s no-op cases mean a well-authored tool is untouched
  beyond attribute ordering. The whole pipeline stays idempotent: after one
  pass the tool validates and declares its newest valid profile, so every
  codemod no-ops on the second pass.
- **Reproduce:** `uv run python -m scripts.corpus_check codemod
  galaxy_tool_xml_codemod.codemods.update_profile:UpdateProfile --limit 200`
  → eligible tools validate post-apply, 0 non-idempotent / crashed.


## 14. Profile-version upgrades: `UpgradeToLatest` orchestrator + per-step codemods

**Date:** 2026-05-28.

> **Current state (2026-05-29).** Registry: `Upgrade19_01`, `Upgrade24_0`,
> `Upgrade24_1`, `Upgrade25_1`. Combined sweep (8 607 eligible) reaches latest on
> **8 566** (41 below); residual sticking points 24.1 (39, the macro-reachability
> ceiling + uncoercible values) and 21.05 / 21.09 (1 each, tool bugs). The
> dated bullets below are a historical → refreshed narrative; this summary is
> the live total.

- **What we chose:** A family of single-step upgrade codemods plus an
  orchestrator. `upgrades.py` holds `UPGRADE_CODEMODS` (a dict mapping a
  sticking version → the codemod that moves a tool one step past it) and
  `UpgradeToLatest`, which loops: run `UpdateProfile` (declare newest valid);
  if below the latest profile and a registered upgrade exists for the current
  version, apply it; repeat — stopping at the latest profile, at a version with
  no registered upgrade, or on a non-advancing round (`seen` guard +
  version-count bound). `UpgradeToLatest` joins `CANONICAL_CODEMODS` in
  `UpdateProfile`'s former slot (it subsumes `UpdateProfile`, running it each
  round): `FixTypos → UpgradeToLatest → Reorder*`. The first upgrade codemod is
  `Upgrade24_1` (§ below). The registry is grown **empirically**: the discovery
  sweep reports tools that do not reach latest and the version they stick at.
- **Discovery sweep:** the `codemod` sweep tallies a post-apply profile
  distribution (`_CodemodSweepState.final_profiles`) and a per-step upgrade
  count (`upgrade_steps`, fed by `CodemodCommand.upgrade_steps_applied()` which
  `UpgradeToLatest` overrides to report the from-versions it advanced). Run with
  `UpgradeToLatest`, every bucket below the latest profile is logged as a
  `STICKING POINT … need upgrade codemod for <version>` (the prioritized
  to-write list) and each `upgrade_vN` reports how many tools it advanced. The
  `codemod` subcommand gained `--source github|toolshed|combined` (combined is
  sha256-deduplicated) so discovery runs over the whole corpus. We keep looping
  (sweep → write `upgrade_vN` → sweep) until every upgradeable tool reaches
  latest. The initial full combined sweep (8 648 eligible) reached latest on
  8 575 with only `Upgrade24_1` (advancing 94; residual 24.1 (56), 19.01 (9),
  25.1 (5), 21.05/21.09/24.0 (1 each)); after the ftype extension and
  `Upgrade25_1` (below) it reaches latest on **8 583** — `Upgrade24_1` advances
  97, `Upgrade25_1` advances 5, leaving residual 24.1 (53), 19.01 (9),
  21.05/21.09/24.0 (1 each); 0 non-idempotent / post-validate-failed / crashed
  throughout.
  - **Refreshed 2026-05-29** (after deprecated-directory tools were excluded
    from the corpus — the discovery filter is `galaxy-tool-xml/docs/decisions.md`
    §6, refreshed measurements §10): the combined
    sweep now reports **8 607 eligible**, reaching latest on **8 542** (65 below
    latest). The 41-tool drop was entirely tools that already validated at
    latest — `Upgrade24_1` still advances 97, `Upgrade25_1` still 5, and the
    residual is unchanged (24.1 (53), 19.01 (9), 21.05/21.09/24.0 (1 each)), so
    the prioritized to-write list is unaffected. Still 0 non-idempotent /
    post-validate-failed / crashed.
  - **`Upgrade19_01` added (19.01 → 19.05).** The 19.01 residual (9 tools, all
    from `ucsb-phylogenetics/ucsb_phylogenetics`) stuck on 19.05 making `name`
    required on output `<data>`. `Upgrade19_01` (§ below) synthesizes a
    deterministic, collision-free `name` (`output`, `output2`, …) on every
    unnamed output `<data>`; the combined sweep now reaches latest on **8 551**
    (56 below latest) — `Upgrade19_01` advances 9, `Upgrade24_1` 97,
    `Upgrade25_1` 5, leaving residual 24.1 (53), 21.05/21.09/24.0 (1 each).
    Still 0 non-idempotent / no-repair / post-validate-failed / crashed.
  - **`Upgrade24_0` added (24.0 → 24.1).** The lone 24.0 tool (`phac-nml`
    `kat_filter`) stuck on 24.1 forbidding `<filter>` inside a `<collection>`'s
    child `<data>`. `Upgrade24_0` (§ below) hoists an all-or-nothing identical
    child filter up to the `<collection>` (it pulled in the deferred
    `Cursor.add_child` primitive); the sweep now reaches latest on **8 552**
    (55 below) — per-step 9 / 1 / 97 / 5 from 19.01 / 24.0 / 24.1 / 25.1,
    leaving residual 24.1 (53), 21.05/21.09 (1 each). Still 0 non-idempotent /
    no-repair / post-validate-failed / crashed.
  - **`Upgrade24_1` extended to drop empty `format`/`ftype`.** Investigating the
    53-tool 24.1 residual (all `format`/`ftype` pattern violations) split it into:
    14 tools with a reachable empty `format=""`/`ftype=""`; ~18 with a coercible
    value (`Rdata`, `GTiff`, `GenBank`) living in an **imported macro file** this
    codemod can't reach (it mutates only the tool's own tree); ~11 non-datatype
    junk (`?`, `plain text`, `$var`); ~9 single-token-context comma-lists; 2
    macro-file empties. Only the first is safely auto-fixable in the single-file
    model, so `Upgrade24_1` now *drops* a value that normalizes to empty (rather
    than leaving it). The sweep now reaches latest on **8 566** (41 below) —
    `Upgrade24_1` advances 111, leaving residual 24.1 (39), 21.05/21.09 (1 each).
    The macro-reachability ceiling (~18 tools) needs cross-file normalization —
    a separate architectural decision, written up in
    `docs/macro-aware-normalization.md` (recommendation: keep reporting these
    rather than reaching into shared macro files from the per-tool pipeline).
    Still 0 non-idempotent / no-repair / post-validate-failed / crashed.
- **`Upgrade24_1` (24.1 → 24.2):** empirically the only 24.2 delta corpus tools
  trip on is the `format` attribute gaining a pattern facet — `FormatList`
  (`<param>`, comma-separated `[a-z0-9._-]` tokens) and `Format` (`<data>`, a
  single such token). 24.1-stuck tools fail on uppercase (`BAM`), spaces
  (`fa, fasta`, `txt `), or empty values. The codemod normalizes every `format`
  attribute (lowercase + strip whitespace per comma token) — semantics-
  preserving (Galaxy datatype extensions are lowercase; whitespace was never
  significant). It leaves what it cannot safely coerce: an empty value, or a
  `<data>` comma-list (which `Format` forbids and there is no basis to pick one
  datatype) — those stay stuck and the discovery sweep reports them.
- **`Upgrade19_01` (19.01 → 19.05):** 19.05 made `name` required on output
  `<data>`. The 9 corpus tools that stuck here declared their outputs as bare
  `<data from_work_dir="…"/>` and never referenced the output name (not in the
  command, not in a `<test>`), so the codemod synthesizes a deterministic,
  collision-free name (`output`, then `output2`, `output3`, … skipping any
  already in use) on each unnamed output `<data>`. Unlike `Upgrade24_1`'s
  value-normalization this is a *synthesis* — an unreferenced placeholder
  identity, not a recovery of author intent — which is the reason it was a
  judgment call (a one-repo corpus signal); the placeholder is safe because
  nothing references it, and it carries every one of the 9 tools to latest.
- **`Upgrade24_0` (24.0 → 24.1):** 24.1 stopped allowing `<filter>` inside a
  `<collection>`'s child `<data>` (a collection element admits only `actions` /
  `change_format`); a top-level output `<data><filter>` is still fine. The lone
  corpus tool (`kat_filter`) had a `paired` collection whose two `<data>`
  children carried the *same* filter — which is an all-or-nothing condition on
  the whole collection — so the codemod hoists one filter to the `<collection>`
  and drops the per-`<data>` ones (semantics-preserving). It refuses the cases
  where the restructure would not be equivalent: child filters that differ, a
  partially-filtered collection, or a collection that already has its own
  `<filter>` — those stay stuck and are reported. This was the first consumer of
  the previously-deferred `Cursor.add_child` primitive (the hoisted filter is a
  new element). Like 19.01 it was a judgment call on a one-tool corpus signal,
  taken because the restructure is clean and the tool is real (present in both
  github and toolshed).
- **Alternative:** direct-to-latest monolithic upgrade codemods; or making
  upgrades opt-in rather than canonical.
- **Why:** Single-step codemods keyed by from-version match how Galaxy's schema
  evolves (one release at a time) and keep each transform small and reviewable;
  the orchestrator chains them. Per-codemod corpus eligibility hooks (§12) carry
  over unchanged — `UpgradeToLatest`/`Upgrade24_1` use the default ("validates
  somewhere"). The whole pipeline stays idempotent: after one pass a tool
  validates at its newest reachable profile and declares it, so every codemod
  no-ops on the next pass. The set is canonical (user decision): the default
  "format my tool" workflow should bring a tool to the latest profile it can
  reach — and `FixTypos`'s guard plus the no-op cases mean a current,
  well-authored tool is untouched beyond attribute ordering.
- **Reproduce:** `uv run python -m scripts.corpus_check codemod
  galaxy_tool_xml_codemod.upgrades:UpgradeToLatest --source combined` → the
  full combined-corpus discovery run (numbers above), reporting each remaining
  `STICKING POINT` and the per-`upgrade_vN` advance counts.
- **Empirical growth (full combined sweep, 8 648 eligible):** `Upgrade24_1`
  was extended to also normalize `ftype` (24.2 pattern-restricts it like
  `format`); `Upgrade25_1` (25.1 → 26.0) drops the obsolete top-level
  `<trackster_conf>` element, which pulled in the deferred `Cursor.remove()`
  primitive; `Upgrade19_01` (19.01 → 19.05) names unnamed output `<data>`; and
  `Upgrade24_0` (24.0 → 24.1) hoists identical collection-child filters (pulling
  in the deferred `Cursor.add_child` primitive). The remaining sticking points
  are documented in `PLAN.md` as needed-but-deferred — the 24.1 residual needs
  macro-token / empty / multi-format handling, and the 21.05 / 21.09 singletons
  are tool bugs (an unsupported `has_size/@delta_frac`; an `output_collection`
  `type="pdf"`/`"tabular"`), so they are reported by the discovery sweep rather
  than auto-fixed.
- **Declined — collection-type whitespace normalization (`Upgrade22_1`).** The
  22.01 schema pattern-restricted `collection_type`/`type` to a `(list|paired)`
  grammar (broadened at 25.0 to add `paired_or_unpaired`/`record`). A codemod
  mirroring `Upgrade24_1`'s `format`/`ftype` whitespace fix was sized at exactly
  **one** corpus tool (`qiime2_core__tools__import_fastq`, `"list, list:paired"`),
  which is itself excluded from the sweep by the eligibility anchor — so it was
  not built (`Upgrade24_1` advances ~97; the bar is not one). Reproduced-by:
  `scripts/measure.py collection-type-normalization` (+ `test_measure.py`'s
  drift-guard against the latest XSD grammar); rationale in `PLAN.md`.
- **Runtime missing-upgrade reporting:** the discovery sweep only sees corpus
  tools. So `UpgradeToLatest` also reports at runtime — `logger.warning` plus a
  `missing_upgrade()` accessor — whenever it stalls at a sub-latest profile
  with no registered `upgrade_vN`. A user's tool (not in the corpus) run
  through fmt's canonical pipeline therefore surfaces the gap instead of being
  silently left below latest. A version that *has* a codemod which merely
  can't advance a particular tool is not reported as missing (that's an
  incomplete codemod / unfixable tool, not an absent one).

## 15. Codemods carry `RuleMeta` metadata + GTX codes; `coded_codemods()` catalog

**Date:** 2026-05-29.

- **What we chose:** Every bundled codemod now carries a
  `meta: ClassVar[RuleMeta]` GTX descriptor, mirroring the formatter tier. The
  descriptor type is imported from the shared, dependency-free
  `galaxy-tool-refactor-rules` package (tier 0.5), so the fmt and codemod tiers
  expose one uniform rule-metadata vocabulary. The two attribute-reorder
  codemods keep their existing codes (`GTX002`, `GTX005`); the validation-driven
  and upgrade codemods get new codes `GTX006`–`GTX012`
  (`FixTypos`, `UpdateProfile`, `Upgrade19_01`, `Upgrade24_0`, `Upgrade24_1`,
  `Upgrade25_1`, `UpgradeToLatest`).
- **Why every codemod, not just the style rules:** the GTX namespace is now the
  project-wide registry of *every* tool-XML transformation, not only the
  IUC-style ones. A complete registry is what makes the cross-tier "Rule
  reference" table on the corpus-format stat page meaningful.
- **`catalog.coded_codemods()`** returns all GTX-coded codemods sorted by code.
  It is deliberately distinct from `CANONICAL_CODEMODS` (canonical.py): that
  tuple is the *ordered pipeline* fmt's CLI runs and omits the single-step
  `upgrade_vN` codemods (which `UpgradeToLatest` drives internally), whereas the
  catalog is the *full enumeration* for documentation/registry use.
- **Ordering note:** `RuleMeta.order` is unused here — codemod execution order is
  the `CANONICAL_CODEMODS` tuple and the `UPGRADE_CODEMODS` registry, not the
  metadata field (which the formatter tier uses). Codes are globally unique
  across both tiers, asserted by a test in fmt's corpus-check suite (it can
  import both tiers). See `galaxy-tool-xml-fmt/docs/decisions.md` §D11 and
  `galaxy-tool-refactor-rules/docs/decisions.md` §D1.
- **Reproduced-by:** `uv run --package galaxy-tool-xml-codemod pytest
  galaxy-tool-xml-codemod/tests/test_catalog.py`.

## 16. `CANONICAL_CODEMODS` narrowed; `AUTO_UPGRADE_CODEMODS` added

**Date:** 2026-05-29.

- **What we chose:** profile upgrade is no longer part of the canonical
  (format) pipeline. `CANONICAL_CODEMODS` is now `(FixTypos,
  ReorderParamAttributes, ReorderToolAttributes)` — `UpgradeToLatest` was
  removed from it. A second ordered contract, `AUTO_UPGRADE_CODEMODS =
  (FixTypos, UpgradeToLatest)`, defines the opt-in upgrade pipeline. Both live
  in `canonical.py`; the app tier (`galaxy-tool-refactor-cli`) consumes them —
  `format` runs the canonical set, `upgrade` runs the upgrade set.
- **Why:** profile upgrade is semantic and fallible (it changes `profile=`,
  applies lossy migrations, and can stall), unlike the safe/idempotent
  canonical transforms. It should be opt-in, not folded into "format my tool".
  Rationale and the user-facing split are in
  `galaxy-tool-refactor-cli/docs/decisions.md` §D1; the fmt CLI's matching
  return to cosmetic-only is `galaxy-tool-xml-fmt/docs/decisions.md` §D12.
- **`FixTypos` is in both pipelines.** It stays in the canonical pipeline
  (repair is safe and useful) and leads the upgrade pipeline as a precondition:
  `UpgradeToLatest` no-ops on a tool that validates nowhere, so a
  broken-and-outdated tool must be repaired before it can upgrade. `FixTypos` is
  idempotent, so its presence in both is harmless. `UpdateProfile` and the
  single-step `Upgrade*` codemods are not listed in either tuple directly —
  `UpgradeToLatest` orchestrates them (per §13–14), and the GTX catalog
  (`coded_codemods()`, §15) still enumerates all of them.
- **Coverage:** `test_canonical.py` pins both contracts' membership and order;
  `test_regressions.py` gained an `AUTO_UPGRADE_CODEMODS` idempotence replay so
  removing upgrade from the canonical replay does not lose upgrade-path
  coverage on retained fixtures.
- **Reproduced-by:** `uv run --package galaxy-tool-xml-codemod pytest
  galaxy-tool-xml-codemod/tests/test_canonical.py`.
