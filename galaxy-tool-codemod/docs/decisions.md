# Decisions and Assumptions

A maintainer-facing record of every non-obvious assumption and design
decision in `galaxy-tool-codemod`. Live document — extend when new
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

**Update (§19, 2026-05-30):** the detect/fix split renamed this mechanism
`visit_<Tag>` → `detect_<Tag>` (and made `detect` the primitive, with `apply`
derived); the dispatch-by-tag rationale below is otherwise unchanged. The
"two structural codemods" framing is the M3-era snapshot (the catalog now also
ships GTR013 and the validation-driven codemods).

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
  `galaxy-tool-fmt` `ReorderAttributes` edit case).
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

- **What we chose:** `galaxy-tool-fmt` declares
  `galaxy-tool-codemod` as an **optional extra** (`[canonical]`),
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
  output you'll get when you run `galaxy-tool-fmt` with the
  `[canonical]` extra installed."

> **Update 2026-05-29 (§9 + §10):** the `[canonical]` extra was removed
> and fmt's CLI reverted to cosmetic-only; cross-tier orchestration now
> lives in the tier-4 app (`galaxy-tool-refactor-cli`), whose `format`
> command runs `CANONICAL_CODEMODS` and `upgrade` command runs
> `AUTO_UPGRADE_CODEMODS`. The §9 independence principle (fmt never
> depends on codemod) and the §10 `CANONICAL_CODEMODS` name both still
> hold — only the *mechanism* (where the tuple is consumed) changed. See
> §16 and `galaxy-tool-fmt/docs/decisions.md` §D12.

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
- **Contract — validity-restoration, not runtime-preservation of invalid tools
  (behaviour-preservation GTR006).** The `newest_valid_profile is None` guard means
  `FixTypos` is a **no-op on every valid tool**, so it preserves the behaviour of any
  tool that currently works. On an **invalid** tool it *restores validity* by
  rewriting near-miss values to their canonical form (e.g. `format="RestructuredText"`
  → `restructuredtext`, `type="Docker"` → `docker`) — and because Galaxy reads several
  such attributes case-sensitively, repairing a broken value can change how the
  *previously-broken* tool behaves (e.g. server-side vs client-side `<help>`
  rendering). That is inherent to restoring validity, not a defect: the contract is
  "preserve valid tools, repair invalid ones", *not* "preserve the runtime of an
  invalid tool". The behaviour-preservation audit's refutation of GTR006 measured this
  rendering shift on an invalid input and so overreached; no scope change is warranted
  (no case-only near-miss fires on an otherwise-valid tool). See
  `../docs/behavior_preservation.md`.

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
  galaxy_tool_codemod.codemods.fix_typos:FixTypos` (combined source, the
  §18 default). **Refreshed 2026-05-30** over the full corpus: **708 eligible**
  (the validate-nowhere population), **39 repaired, 669 no-repair, 708
  idempotent, 0 non-idempotent / post-validate-failed / crashed**; of the 39
  repaired, 38 then validate at latest (26.1) and 1 stays at 24.1 (needs a 24.1
  upgrade codemod). The original entry quoted a `--limit 40` github sample (40
  eligible, 5 repaired, 35 no-repair) from 2026-05-28; the no-repair majority is
  expected and legitimate — most validate-nowhere tools are not mere typos. The
  no-valid population is swept here (it was skipped wholesale before these hooks).

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
  galaxy_tool_codemod.codemods.update_profile:UpdateProfile --limit 200`
  → eligible tools validate post-apply, 0 non-idempotent / crashed.


## 14. Profile-version upgrades: `UpgradeToLatest` orchestrator + per-step codemods

**Date:** 2026-05-28.

> **Current state (2026-05-29).** Registry: `Upgrade19_01`, `Upgrade24_0`,
> `Upgrade24_1`, `Upgrade25_1`. Combined sweep (8,607 eligible) reaches latest on
> **8,566** (41 below); residual sticking points 24.1 (39, the macro-reachability
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
  latest. The initial full combined sweep (8,648 eligible) reached latest on
  8,575 with only `Upgrade24_1` (advancing 94; residual 24.1 (56), 19.01 (9),
  25.1 (5), 21.05/21.09/24.0 (1 each)); after the ftype extension and
  `Upgrade25_1` (below) it reaches latest on **8,583** — `Upgrade24_1` advances
  97, `Upgrade25_1` advances 5, leaving residual 24.1 (53), 19.01 (9),
  21.05/21.09/24.0 (1 each); 0 non-idempotent / post-validate-failed / crashed
  throughout.
  - **Refreshed 2026-05-29** (after deprecated-directory tools were excluded
    from the corpus — the discovery filter is `galaxy-tool-xml/docs/decisions.md`
    §6, refreshed measurements §10): the combined
    sweep now reports **8,607 eligible**, reaching latest on **8,542** (65 below
    latest). The 41-tool drop was entirely tools that already validated at
    latest — `Upgrade24_1` still advances 97, `Upgrade25_1` still 5, and the
    residual is unchanged (24.1 (53), 19.01 (9), 21.05/21.09/24.0 (1 each)), so
    the prioritized to-write list is unaffected. Still 0 non-idempotent /
    post-validate-failed / crashed.
  - **`Upgrade19_01` added (19.01 → 19.05).** The 19.01 residual (9 tools, all
    from `ucsb-phylogenetics/ucsb_phylogenetics`) stuck on 19.05 making `name`
    required on output `<data>`. `Upgrade19_01` (§ below) synthesizes a
    deterministic, collision-free `name` (`output`, `output2`, …) on every
    unnamed output `<data>`; the combined sweep now reaches latest on **8,551**
    (56 below latest) — `Upgrade19_01` advances 9, `Upgrade24_1` 97,
    `Upgrade25_1` 5, leaving residual 24.1 (53), 21.05/21.09/24.0 (1 each).
    Still 0 non-idempotent / no-repair / post-validate-failed / crashed.
  - **`Upgrade24_0` added (24.0 → 24.1).** The lone 24.0 tool (`phac-nml`
    `kat_filter`) stuck on 24.1 forbidding `<filter>` inside a `<collection>`'s
    child `<data>`. `Upgrade24_0` (§ below) hoists an all-or-nothing identical
    child filter up to the `<collection>` (it pulled in the deferred
    `Cursor.add_child` primitive); the sweep now reaches latest on **8,552**
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
    than leaving it). The sweep now reaches latest on **8,566** (41 below) —
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
  galaxy_tool_codemod.upgrades:UpgradeToLatest --source combined` → the
  full combined-corpus discovery run (numbers above), reporting each remaining
  `STICKING POINT` and the per-`upgrade_vN` advance counts.
- **Empirical growth (full combined sweep, 8,648 eligible):** `Upgrade24_1`
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
- **`Upgrade24_0` (GTR009) mixed-content filter — behaviour-preserving by `.text`
  (2026-06-06).** The behavior-preservation audit flagged the collection-`<filter>`
  hoist as dropping condition text after a comment child (`<filter>cond_one <!-- x -->
  and cond_two</filter>` → `.text` `'cond_one '`). On re-verification this is **not** a
  bug: Galaxy evaluates an output filter via `eval(filter.text.strip())`
  (`galaxy/tools/execution_helpers.py:filter_output`) — `.text`, not `itertext` — so the
  post-comment tail is dead at runtime; Galaxy never evaluated it. The hoist reads the
  same `.text` Galaxy does, and the comparison `{found.text.strip()}` matches Galaxy's
  own notion of the condition, so the restructure is faithful. The adversarial
  refutation overreached (assumed `itertext` semantics). Pinned by
  `test_hoists_mixed_content_filter_by_galaxy_evaluated_text`; see
  `../docs/behavior_preservation.md`.

## 15. Codemods carry `RuleMeta` metadata + GTR codes; `coded_codemods()` catalog

**Date:** 2026-05-29.

- **What we chose:** Every bundled codemod now carries a
  `meta: ClassVar[RuleMeta]` GTR descriptor, mirroring the formatter tier. The
  descriptor type is imported from the shared, dependency-free
  `galaxy-tool-refactor-rules` package (tier 0.5), so the fmt and codemod tiers
  expose one uniform rule-metadata vocabulary. The two attribute-reorder
  codemods keep their existing codes (`GTR002`, `GTR005`); the validation-driven
  and upgrade codemods get new codes `GTR006`–`GTR012`
  (`FixTypos`, `UpdateProfile`, `Upgrade19_01`, `Upgrade24_0`, `Upgrade24_1`,
  `Upgrade25_1`, `UpgradeToLatest`).
- **Why every codemod, not just the style rules:** the GTR namespace is now the
  project-wide registry of *every* tool-XML transformation, not only the
  IUC-style ones. A complete registry is what makes the cross-tier "Rule
  reference" table on the corpus-format stat page meaningful.
- **`catalog.coded_codemods()`** returns all GTR-coded codemods sorted by code.
  It is deliberately distinct from `CANONICAL_CODEMODS` (canonical.py): that
  tuple is the *ordered pipeline* fmt's CLI runs and omits the single-step
  `upgrade_vN` codemods (which `UpgradeToLatest` drives internally), whereas the
  catalog is the *full enumeration* for documentation/registry use.
- **Ordering note:** `RuleMeta.order` is unused here — codemod execution order is
  the `CANONICAL_CODEMODS` tuple and the `UPGRADE_CODEMODS` registry, not the
  metadata field (which the formatter tier uses). Codes are globally unique
  across both tiers, asserted by a test in fmt's corpus-check suite (it can
  import both tiers). See `galaxy-tool-fmt/docs/decisions.md` §D11 and
  `galaxy-tool-refactor-rules/docs/decisions.md` §D1.
- **Reproduced-by:** `uv run --package galaxy-tool-codemod pytest
  galaxy-tool-codemod/tests/test_catalog.py`.

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
  return to cosmetic-only is `galaxy-tool-fmt/docs/decisions.md` §D12.
- **`FixTypos` is in both pipelines.** It stays in the canonical pipeline
  (repair is safe and useful) and leads the upgrade pipeline as a precondition:
  `UpgradeToLatest` no-ops on a tool that validates nowhere, so a
  broken-and-outdated tool must be repaired before it can upgrade. `FixTypos` is
  idempotent, so its presence in both is harmless. `UpdateProfile` and the
  single-step `Upgrade*` codemods are not listed in either tuple directly —
  `UpgradeToLatest` orchestrates them (per §13–14), and the GTR catalog
  (`coded_codemods()`, §15) still enumerates all of them.
- **Coverage:** `test_canonical.py` pins both contracts' membership and order;
  `test_regressions.py` gained an `AUTO_UPGRADE_CODEMODS` idempotence replay so
  removing upgrade from the canonical replay does not lose upgrade-path
  coverage on retained fixtures.
- **Reproduced-by:** `uv run --package galaxy-tool-codemod pytest
  galaxy-tool-codemod/tests/test_canonical.py`.

## 17. `ReorderToolChildren` (GTR013) + the `Cursor.reorder_children` primitive

**Date:** 2026-05-29.

- **What we chose:** a new structural codemod, `ReorderToolChildren` (GTR013),
  reorders the root `<tool>`'s child elements to the IUC convention
  (best-practice #52: `description, macros, edam_topics, edam_operations,
  xrefs, parallelism, requirements, code, stdio, version_command, command,
  environment_variables, configfiles, inputs, request_param_translation,
  outputs, tests, help, citations`). It is added to `CANONICAL_CODEMODS` (after
  the two attribute reorders), so the app's `format` command applies it. Tags
  outside the convention keep their relative position after the known ones.
- **Why it is validity-safe.** The Galaxy schema's `<tool>` content model is
  **`xs:all`** (order-free), not `xs:sequence` — verified against
  `galaxy-tool-xml/.../schema/galaxy-26.1.xsd`. Child-element order is therefore
  not XSD-enforced; reordering can never regress validity, and the IUC order is
  a pure convention. The codemod's real invariant is idempotence, proven over
  the corpus.
- **New primitive `Cursor.reorder_children(order)`.** A stable sort of the
  element children by `(rank-in-order, original-index)`; tags absent from
  `order` get a sentinel rank so they sort last, stably (no alphabetical guess,
  unlike `reorder_attributes` — there is no meaningful alphabetical order for
  elements). Re-appends each element via lxml, which *moves* an existing child;
  each element's `tail` travels with it, so inter-element whitespace is left
  for the cosmetic formatter to re-normalise. Returns early (no mutation) when
  the order is already correct, so already-clean tools never churn.
- **Comment-skip, not raise.** Unlike `reorder_attributes` (§7, raises on
  anomaly), `reorder_children` *skips* (no-op) when the element has any
  non-element child (Comment / ProcessingInstruction). Rationale:
  `Cursor.children()` deliberately hides those nodes, so only the primitive has
  raw-node visibility; and reordering elements past a free-floating comment
  would silently re-associate it with the wrong element. A comment is a normal
  tree state, not a codemod bug, so the safe response is to leave the element
  untouched. The cross-tier coverage map records this in
  `../../docs/iuc_best_practices.md`.
- **Corpus result (combined, 8,607 eligible tools):** 4,640 modified, 8,607
  idempotent, 0 non-idempotent, 0 post-validate-failed, 0 crashed — clean. So
  ~54% of validatable tools have out-of-order `<tool>` children today.
- **Reproduced-by:** `uv run --package galaxy-tool-codemod pytest
  galaxy-tool-codemod/tests/test_reorder_tool_children.py
  galaxy-tool-codemod/tests/test_cursor.py`; corpus gate `uv run python -m
  scripts.corpus_check codemod
  galaxy_tool_codemod.codemods.reorder_tool_children:ReorderToolChildren`
  (now defaults to `--source combined`, see §18).

## 18. `corpus_check codemod` defaults to `--source combined`

**Date:** 2026-05-29.

- **What we chose:** the `codemod` subcommand's `--source` now defaults to
  `combined` (github + toolshed, sha256-deduplicated), matching `fmt` and
  `rules`. Previously it defaulted to `github` (the ~3,957-tool cohort).
  `validate` keeps its `github` default (it drives the per-source stat pages).
- **Why:** a codemod's idempotence/validity invariants should be checked
  against the widest available corpus by default; the narrower github cohort
  was an artifact, not an intent. Consistency across the three rule-sweeping
  subcommands removes a footgun (a green github-only sweep reading as full
  coverage). Combined is ~8,607 eligible tools vs ~3,957 for github.

## 19. Detect/fix split — `Change`, `detect()`, and coarse validation-driven detect

**Date:** 2026-05-30.

- **What we chose (PR1 of the detect/fix rule-split effort):** every codemod now
  has a non-mutating **detect** phase alongside its **fix** phase, on the
  `ruff check` / `ruff format` model.
  - New `change.py`: a `Change` frozen dataclass carrying diagnostic data
    (`code`, `sourceline`, `xpath`, `message` — the same fields as tier-0.5
    `Violation`, projectable via `Change.to_violation()`) plus a zero-arg
    `mutate` thunk (excluded from equality/repr). `apply_changes` is the single
    dispatch site (runs each thunk).
  - `CodemodCommand` is now **detect-primitive**: `detect(module)` walks the tree
    dispatching `detect_<TagPascalCase>` and yields `Change`s without mutating;
    `apply` is derived (`apply_changes(list(self.detect(module)))`). The old
    imperative `visit_<Tag>` walk and its `False`-halt descent control are
    removed (no bundled codemod used the halt; the three reorderers were the only
    `visit_` users).
  - The three structural reorderers (GTR002/005/013) became `detect_<Tag>`
    methods yielding one located `Change` per out-of-order element. To keep the
    "would it change?" decision in **one** place, `Cursor` gained
    `would_reorder_attributes` / `would_reorder_children` predicates; the
    mutators are rewritten in terms of them, so detect and apply can never drift.
    `Cursor` also gained read-only `sourceline` / `xpath` accessors for the
    `Change` location.
  - The validation-driven codemods (`FixTypos`, `UpdateProfile`,
    `UpgradeToLatest`, the per-step `Upgrade*`) keep their bespoke `apply` and
    get a **coarse** `detect` (`codemods/_coarse_detect.py`): run the codemod on
    a deep copy, and if `etree.tostring` differs, yield a single root-level
    `Change`. They branch on re-validation, so no static per-occurrence change
    list exists; the per-occurrence lint value concentrates in the structural
    and (future) detect-only rules.
- **Why thunk-carrying `Change` rather than a declarative mutation union (à la
  fmt's `Edit`):** each reorderer makes exactly one `Cursor` call per element, so
  the closure *is* that call — verbatim reuse, one mutation site, the detect list
  is literally the report. A declarative union would re-enumerate every mutation
  kind for no present gain; revisit if a codemod needs inspectable mutation data.
- **Sweep parity gate:** `corpus_check codemod` now runs `detect()` (non-mutating)
  before `apply` on every tool and retains a `detect-parity-mismatch` finding if
  `bool(detected) != modified` (byte-diff). The invariant held across the corpus
  with no behavioural change — the three reorderers report the **same** modified
  counts as before the refactor.
- **Corpus result (combined, 8,607 eligible tools), 0 parity mismatches:**
  GTR002 6,075 modified · GTR005 1,020 · GTR013 4,640 — identical to §16–17
  baselines; FixTypos and UpgradeToLatest coarse-detect parity also clean.
- **Reproduced-by:** `uv run --package galaxy-tool-codemod pytest
  galaxy-tool-codemod/tests/` (`test_change.py`, `test_codemod.py`,
  `test_coarse_detect.py`, the reorderer suites, `test_cursor.py`); corpus gate
  `uv run python -m scripts.corpus_check codemod
  galaxy_tool_codemod.codemods.reorder_param_attributes:ReorderParamAttributes`
  (and the GTR005/GTR013/FixTypos/UpgradeToLatest specs). The effort (PR1–5)
  merged in #15.

## 20. `MacroModule` + `parse_macro_module` (codemods over macro files)

**Date:** 2026-05-30. Phase 2 of the macro-aware effort (codemod side).
Reproduced-by: `uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_parse.py galaxy-tool-codemod/tests/test_module.py`.

- **What we chose.** `MacroModule` (frozen, `module.py`) — the macro-file
  counterpart to `Module`: it wraps a tier-1 `MacroDocument` and exposes a fresh
  root `Cursor` over the `<macros>` element, but **no `model`** (a macro library
  has no typed model/profile). `parse_macro_module(source)` (`parse.py`) mirrors
  `parse_module`: strict on `Path`/`bytes` via `load_macros` (raises
  `ToolXmlSyntaxError`), shares a `MacroDocument` by reference. `Cursor` is
  already generic over any lxml element, so every mutation primitive
  (`set_attribute`, `reorder_children`, `remove`, …) works on a macro tree
  unchanged — pinned by `test_macro_module_cursor_navigates_and_mutates`.
- **What we deliberately did NOT do — generalise `CodemodCommand`.** The base
  `detect`/`apply` stay typed `module: Module` (tool-only). Widening them to
  `Module | MacroModule` would force the seven validation-driven codemods
  (`FixTypos`, `UpdateProfile`, `UpgradeToLatest`, the per-step `Upgrade*`) — all
  `applies_to={"tool"}` and all using `module.document` as a `ToolDocument`
  (`validate_tool` / `newest_valid_profile`) — to widen and `isinstance`-narrow,
  i.e. churn for a path nothing exercises. There is **no macro-subject codemod
  yet** (the macro-library normaliser and the token-aware `@PROFILE@` upgrade are
  later), so per the project's defer-until-consumer rule we ship only the
  `MacroModule` primitive. When a macro-subject codemod lands, introduce the
  generic base (or a `MacroCodemod`) then, with that codemod as the consumer.
- **`applies_to` already covers codemod selection.** Codemods carry `RuleMeta`
  with `applies_to` (default `{"tool"}`, tier-0.5 D3), so the registry/bundle can
  filter codemods by document kind without any base-class change.

## 21. Token-aware `UpdateProfile` for inline `@PROFILE@` (+ `Cursor.set_text`)

**Date:** 2026-05-30. Phase 3a of the macro-aware effort (single-file,
inline-token only). Reproduced-by: `uv run --package galaxy-tool-codemod
pytest galaxy-tool-codemod/tests/test_update_profile.py
galaxy-tool-codemod/tests/test_cursor.py` and `uv run --package
galaxy-tool-refactor-cli pytest
galaxy-tool-refactor-cli/tests/test_cli.py::test_upgrade_rewrites_inline_profile_token`.

- **The motivating case.** A tool declares `profile="@PROFILE@"` whose token
  expands to (say) `16.01`, but the tool actually validates at a newer release.
  We want future expansions to be current **without clobbering the
  `@PROFILE@` reference** — IUC's token convention keeps the version in one
  place. The old `UpdateProfile` was a deliberate no-op here
  (`profiles.is_newer_profile` returns `False` for the unparseable `@PROFILE@`
  literal, so the attribute was left alone). That was *safe* but did nothing.
- **What we chose.** `UpdateProfile.apply` now branches on the declaration: a
  parseable-and-stale literal is bumped as before; a `@TOKEN@` declaration is
  routed to `_upgrade_inline_profile_token`, which finds the matching
  `<macros><token name="@TOKEN@">` **defined inline in the tool's own
  `<macros>`** (via `_inline_token`, walking `module.cursor.children()`) and
  rewrites that token's text to the newest validating profile when it is stale.
  The `profile="@TOKEN@"` attribute is never replaced with a literal.
- **`Cursor.set_text` / `Cursor.text`.** The rewrite needs to read and replace
  an element's direct text content. `cursor.py` gains a `text` property
  (mirrors `get_attribute`'s `str`-or-`None` coercion) and a `set_text(value)`
  mutator that replaces `text` only — children, `tail`, and attributes are
  untouched. Generic, like every other `Cursor` primitive.
- **What we deliberately did NOT do — imported tokens.** A token defined in an
  *imported* macro file is left untouched here: `_inline_token` only inspects
  the tool's own `<macros>`, and the imported-token no-op is pinned by
  `test_leaves_imported_profile_token_untouched`. Editing an imported (possibly
  shared) macro file is the **bundle-aware Phase 3b step** — it needs the
  import-graph + shared-skip policy this single-file codemod intentionally
  doesn't carry (see the macro-aware plan; §20's defer-until-consumer rule).
  Idempotence and the imported/inline split are the regression guards.

## 22. Soundness of validity-as-oracle: structural upgrade, not behaviour preservation

**Date:** 2026-06-01. Reproduced-by: `uv run python -m scripts.corpus_check
codemod galaxy_tool_codemod.upgrades:UpgradeToLatest --source combined`
(2026-06-01: 8,607 eligible, 0 non-idempotent / post-validate-failed / crashed,
8,566 reach latest, residual 24.1 (39) + 21.05/21.09 (1 each, tool bugs)). The
per-transition delta map is `docs/profile_upgrades.md` (the profile-upgrade
ledger). This entry records *why the method is sound and where its boundary lies*
— a question raised about the whole `UpdateProfile`/`UpgradeToLatest` design.

- **The claim the design rests on.** `UpdateProfile` declares
  `newest_valid_profile`, and an `upgrade_vN` is written **only** for a version
  whose next-step XSD delta *blocks validation* (§14). The implicit premise: *a
  tool that validates under profile X needs no XML change to be a valid profile-X
  tool — just declare `profile="X"`.*
- **Sound for STRUCTURAL acceptability (this is what we claim).** If the XML
  satisfies X's XSD, then by definition no change is needed to satisfy X's XSD —
  tautological. The corpus sweep backs the operational form: across 8,607 tools
  the pipeline is idempotent, never produces a tool that fails post-validation,
  and every transition *except* the four breaking ones (19.01→19.05, 24.0→24.1,
  24.1→24.2, 25.1→26.0) carries every previously-valid tool forward untouched.
  That is the empirical proof that **additive** schema steps (the large majority —
  see the ledger) need no codemod: they remove and restrict nothing, so validity
  at the newer profile holds for free.
- **NOT sound for BEHAVIOURAL equivalence (the boundary).** Galaxy's `profile` is
  "a runtime-compatibility contract, not just a schema selector" (§13). Some
  profile bumps change *runtime defaults the XSD does not encode* — error/exit-code
  detection, `set -e` / Cheetah strictness, output-metadata inference, command-line
  quoting. A tool can validate under both the old and new profile and still
  *behave differently* once `profile=` is bumped. XSD-validity says nothing about
  whether behaviour was preserved.
- **Decision / scope.** `UpdateProfile` + `UpgradeToLatest` are a **structural
  revalidation + profile-declaration** tool: they bring `profile=` to the newest
  profile a tool *structurally satisfies* and apply only the XSD-forced structural
  migrations. They are **not** a behaviour-preserving upgrader, and they do not
  attempt to pin pre-bump runtime defaults. This is consistent with upgrade being
  **opt-in and semantic** (§16) — the user opts into the semantic act and is
  expected to review runtime behaviour. Semantic/runtime profile changes are
  **out of scope** for automatic upgrade; they are catalogued in the ledger's
  Semantic column so a future, evidence-driven decision can revisit them.
- **Why record it.** The structural-vs-behavioural distinction was load-bearing
  but unwritten; the four `upgrade_vN` codemods are each tied to a concrete XSD
  delta precisely because validity is the right oracle *for structure*. Writing
  the boundary down keeps a future contributor from mistaking "reaches latest,
  validates clean" for "behaves identically to before the bump."
- **Alternative (rejected for now).** Aspire to behaviour-preserving upgrades:
  enumerate every profile's runtime-default change and synthesise the
  behaviour-pinning attributes on bump. Much larger, needs a per-profile semantic
  catalogue (the ledger's Semantic column is the start), and risks over-editing
  well-authored tools. Deferred; revisit if there is demand and the semantic
  catalogue is complete enough to act on safely. **Investigated in
  `docs/behavior-preserving-upgrade.md`** (2026-06-01): Galaxy's `profile` is an
  all-or-nothing opt-in with no general per-behaviour opt-out, so full preservation
  is unachievable by XML edits; only a small subset (e.g. 17.09
  `provided_metadata_style="legacy"`) is pinnable. The §23 warning is the primary
  mechanism; auto-pinning would be a narrow opt-in enhancement at most.
- **Reproduce / refute.** The full method (three independent evidence
  sources — XSD diff, combined-corpus sweep, Galaxy profile docs — with the exact
  commands and the refutation paths for each) is documented in
  `docs/profile_upgrades.md` § "Methodology — how these conclusions were reached
  (and how to refute them)". In short: re-run the sweep — a non-idempotent or
  post-validate-failed result, or a new sticking point at a step we call additive,
  refutes the structural-soundness claim; a profile-gated runtime change missing
  from the ledger's Semantic column extends the boundary, not the soundness.

## 23. `PROFILE_UPGRADE_CODES` (Galaxy-vendored) + the `upgrade` profile-bump warning

**Date:** 2026-06-01 (data realigned to Galaxy's catalogue same day). Reproduced-by:
`uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_profile_semantics.py` and `uv run --package
galaxy-tool-refactor-registry pytest
galaxy-tool-refactor-registry/tests/test_facade.py -k upgrade`; corpus blast-radius
via `uv run python -m scripts.measure semantic-upgrade-boundaries`.

- **What we chose.** §22 says we *cannot* auto-preserve runtime behaviour across a
  profile bump — but we *can* warn. `profile_semantics.py` holds
  `PROFILE_UPGRADE_CODES` and the pure `upgrade_codes_crossed(from_profile,
  to_profile)`. The registry facade's `upgrade` captures the tool's runtime
  baseline **before** any rewrite (its declared `profile=`, or `16.01` when
  undeclared — Galaxy's runtime default) and the profile actually reached, and
  emits one advisory **note** of the form "*N of M crossed change(s) apply to this
  tool*" + a must-fix count (it never blocks or mutates for them). The "*N of M*"
  narrowing is the per-tool detection ported in §25.
- **Source of truth = Galaxy's own catalogue.** `PROFILE_UPGRADE_CODES` is a
  faithful mirror of `galaxyproject/galaxy`'s
  `lib/galaxy/tool_util/upgrade/upgrade_codes.json` (@ `b45c58a2`), keyed by
  Galaxy's code names (`16_04_exit_code`, …), carrying `level`
  (`must_fix`/`consider`), `niche`, the verbatim message, and the PR url. We mirror
  the `must_fix` + `consider` codes; Galaxy's `ready` note is omitted. **Two
  schema-doc behaviour changes Galaxy does NOT catalogue — 19.05 (Python 2→3) and
  25.1 (`<credentials>`) — are intentionally absent** so the map stays a strict
  mirror; revisit if Galaxy adds codes for them.
- **Range-aware AND detection-aware (§25).** `upgrade_codes_crossed` is the
  range filter (every code whose profile lies in the bumped interval);
  `upgrade_codes_applicable` narrows it to the codes whose per-tool detector
  fires, so the note reports only what applies to *this* tool — see §25.
- **The positive complement: a behaviour-preserving verdict (2026-06-02).** The
  warning's silence (no applicable code) was previously implicit — a tool that
  cleanly clears every crossed boundary just got *no* note, indistinguishable
  from "we didn't look". `crossed_and_applicable_codes(baseline, target, tripped)`
  is now the single source the warning and a new verdict both read, so they can
  never disagree on what applies. `upgrade_is_behavior_preserving` returns the
  affirmative: `True` when the bump crosses **no applicable** code, `False` when
  ≥1 applies, `None` when undetermined (an unparseable/macro-token profile — kept
  *distinct* from "parseable, crosses nothing", which is `True`). The facade
  surfaces it as `UpgradeResult.behavior_preserving` and, when the bump actually
  advanced the profile, an explicit clean-pass note ("*upgrade crosses no
  behaviour change that applies to this tool — behavior-preserving*"). This is the
  "prove the construct is absent ⇒ the tool is free to move past it" framing,
  made an explicit signal rather than mere absence. It is **conservative**: a tool
  whose only applicable code is auto-neutralised by a runtime-gated fix
  (GTR014/015/016, §24) is still reported `False` for now — under-claiming safety
  is the sound direction under §22; crediting auto-fixed codes is deferred.
- **Why a note in `upgrade`, not a check rule.** The risk is intrinsic to the
  *upgrade transition* (baseline → target), not a static property of a tool, so it
  has no meaning in `check`/`format` and needs no GTR code. It rides the
  `UpgradeResult.notes` channel, so the CLI surfaces it for free.
- **Baseline choices.** Undeclared `profile=` → `16.01` (matches Galaxy's default
  and tier-1's `resolve_profile(None)`; the highest-impact case). A macro-token
  (unparseable) profile → no warning rather than a misleading one; the target is
  `newest_valid_profile` so a rewritten inline token still measures to a literal.
- **Corpus blast radius (2026-06-01).** Of 8,608 considered tools, **94.2% cross ≥1
  code** on upgrade-to-latest (24.2 test-validation hits 92.3%); **0 tools have
  *every* crossed code cleanly pinnable** — empirical confirmation of §22 that
  behaviour-preserving upgrade is essentially never fully achievable.
- **Keep in sync.** `PROFILE_UPGRADE_CODES`, the ledger's Semantic column, and
  `docs/behavior-preserving-upgrade.md` are views of one fact set; re-vendor from
  `upgrade_codes.json` together (`test_profile_semantics.py` pins the shape).

## 24. Runtime-gated fixes: a detect-driven family the `upgrade` path applies

**Date:** 2026-06-01 (crossing-gate + format_source guard added 2026-06-02).
Reproduced-by: `uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_fix_from_work_dir_whitespace.py
galaxy-tool-codemod/tests/test_runtime_fixes.py
galaxy-tool-codemod/tests/test_fix_output_format_input.py`; crossing-gate at the
facade via `uv run --package galaxy-tool-refactor-registry pytest
galaxy-tool-refactor-registry/tests/test_facade.py -k "runtime or crossing"`; corpus
sizing via `uv run python -m scripts.corpus_check codemod
galaxy_tool_codemod.codemods.fix_from_work_dir_whitespace:FixFromWorkDirWhitespace`
and the format_source-guard breakdown via `uv run python -m scripts.measure
output-format-input`.

- **The gap.** Some Galaxy `must_fix` upgrade codes (§23) are **runtime** behaviours
  the XSD does **not** enforce — e.g. `21_09_fix_from_work_dir_whitespace`: from
  21.09 Galaxy quotes `from_work_dir`, so surrounding whitespace becomes literal,
  but a whitespace `from_work_dir` is XSD-valid at every profile. `UpgradeToLatest`
  is **validity-gated** (it advances only when `newest_valid_profile` improves), so
  applying such a fix changes nothing it can detect — it can't ride that loop.
- **What we chose.** A new **`RuntimeGatedFix`** family (`codemods/_runtime_gated.py`):
  an ordinary detect-primitive `CodemodCommand` plus an `introduced_profile`
  ClassVar. `runtime_fixes.py` holds the `RUNTIME_GATED_FIXES` registry and
  `runtime_fixes_for(reached, *, baseline)`. The **registry facade's `upgrade`**
  applies each fix the tool **crosses** — after `UpgradeToLatest`, before the
  cosmetic/reorder pass.
- **Crossing-gated, on *both* bounds (2026-06-02).** A fix applies only when
  `baseline < introduced_profile <= reached`, where `baseline` is the tool's
  pre-upgrade runtime baseline (a missing `profile=` resolves to `16.01`; a
  macro-token/unparseable baseline ⇒ apply **no** runtime fixes and let the §23
  warning report). Two tools are left untouched: one that **stalls below** a fix
  (Galaxy ran it under the old behaviour — pre-21.09 Galaxy stripped `from_work_dir`
  itself, so the fix is a no-op there), *and* one that **already declares** a profile
  at or above the fix's introduction. The original cut gated on `reached` only, which
  was a behaviour-*preservation* gap: an already-≥boundary tool with the deprecated
  construct currently runs under the *new* Galaxy behaviour (e.g. Galaxy disables
  `format="input"` from 16.04; quotes `from_work_dir` from 21.09), so rewriting it
  would *change* current behaviour, not preserve it. The lower bound closes that. For
  the two **shipped** fixes the gate skips **0** tools on the current corpus: 0 of the
  109 auto-fixable `format="input"` tools already declare profile ≥16.04 (`scripts/
  measure output-format-input`), and all 4 whitespace `from_work_dir` tools predate
  21.09 (profile 16.07) — so it is a soundness backstop with no behaviour change
  today. The real beneficiary is the planned GTR016 `interpreter=` fix: the
  adversarial review found bucket-A `interpreter=` tools that *already* declare ≥16.04
  (Galaxy ignores `interpreter=` for any profile ≠ 16.01), which the gate will
  correctly leave alone — to be sized by its own measure when GTR016 lands. (Surfaced
  by the upgrade-soundness adversarial review, 2026-06-02.)
- **Upgrade-only.** Runtime-gated fixes are in `coded_codemods()` (so the registry
  enumerates them and the GTR namespace stays collision-guarded) but **not** in
  `CANONICAL_CODEMODS` — they never run under `format` / the `iuc` preset and never
  change `profile=`. They surface only via `list_rules(include_upgrade=True)`.
  (Forks settled with the maintainer: upgrade-only path; a new family rather than
  extending `UpgradeToLatest`; first cut = the one pure-AUTO fix.)
- **Fix 1: `FixFromWorkDirWhitespace` (GTR014, 21.09).** A deterministic
  `value.strip()` on every `<data from_work_dir>` — semantics-preserving (whitespace
  was never significant pre-21.09 and is a bug at 21.09+). Plain detect-primitive
  (`detect_Data`), so it inherits detect-parity, idempotence, and the corpus sweep.
- **Fix 2: `FixOutputFormatInput` (GTR015, 16.04).** Replaces an output
  `<data format="input">` with `format_source="<input>"` — but **only** for a tool
  with exactly one *top-level* `<param type="data">` (then the source is
  unambiguous and an unqualified reference resolves). Tools with zero, two-or-more,
  or a *nested* single data input are left for the §23 warning. An output that
  **already carries a `format_source`** is also skipped (2026-06-02): `format="input"`
  is inert there — Galaxy's format_source branch wins at runtime
  (`tools/actions/__init__.py`) — so overwriting the author's source (which may point
  at a collection or a different input) would change behaviour. `scripts/measure
  output-format-input` sizes it: **6** co-present `format="input"` elements exist in the
  corpus but **0** fall in the auto-fixable subset (all 6 belong to tools with 0 or 2+
  data inputs, which GTR015 never fired on), so the guard is a soundness backstop, not
  a count change. It **overrides `detect`** (not the
  per-tag walk) because choosing `format_source` needs whole-tool context; `apply`
  still derives from `detect` (so detect/apply parity holds). Sized first via
  `scripts/measure.py output-format-input` (the measure-before-build rule).
- **Still deferred (warn-only, per §23 + `behavior-preserving-upgrade.md`).**
  `16_04_fix_interpreter` and `24_2_fix_test_case_validation` need author judgement
  (rewrite the command to call the runtime by path; correct a parameter model) —
  no safe mechanical form, so they stay advisory.
- **Corpus sizing (2026-06-01, `--source combined`, 8,607 eligible).**
  `FixFromWorkDirWhitespace` modifies **4**; `FixOutputFormatInput` modifies
  **79** (the single-top-level-data-input subset of the tools with a
  `format="input"` output — the rest reported, not guessed). All idempotent; 0
  non-idempotent / post-validate-failed / crashed (no regressions retained).


## 25. Per-tool detection for the `upgrade` semantic warning

**Date:** 2026-06-01. Reproduced-by: `uv run --package galaxy-tool-codemod
pytest galaxy-tool-codemod/tests/test_profile_semantics.py`; facade rewording
`uv run --package galaxy-tool-refactor-registry pytest
galaxy-tool-refactor-registry/tests/test_facade.py -k semantic`; corpus
noise-reduction via `uv run python -m scripts.measure upgrade-codes-applicability`;
raw-vs-expanded detector divergence via `uv run python -m scripts.measure
macro-expansion-detection-gap`.

- **The gap (§23).** The semantic note was *range-based*: it listed every
  `PROFILE_UPGRADE_CODES` entry whose profile lay in the bumped range. The corpus
  showed 94.2% of tools cross ≥1 code, so the note over-reported — most crossed
  codes don't actually trip a given tool. Galaxy's own advisor *detects* per-tool.
- **What we chose.** A `code → detector` table (`_DETECTORS` in
  `profile_semantics.py`), each a read-only LBYL query over the tool's lxml tree,
  ported from Galaxy's `lib/galaxy/tool_util/upgrade/__init__.py` @ `b45c58a2`.
  `tripped_upgrade_codes(document)` returns the codes that fire (range-independent);
  `upgrade_codes_applicable(...)` = `crossed ∩ tripped`. The facade captures
  `tripped` on the **pre-upgrade** tree (GTR014/GTR015 mutate the very features the
  detectors inspect) and the note becomes "*N of M crossed … apply to this tool*".
  `PROFILE_UPGRADE_CODES` stays a pure data mirror — detection is a separate layer.
- **We port Galaxy's *intent*, not its literal `b45c58a2` code**, which has
  transcription bugs that make several predicates non-functional upstream
  (documented in the module docstring): `17_09` queries a backtick-quoted attribute
  name; `21_09` calls `add("")`; a `_find_all` helper ignores its xpath argument and
  always returns `.//data[@from_work_dir]`, breaking `23_0` (which also targets
  `<input>` where Galaxy tool XML uses `<param>`). Two codes can't be a literal
  mirror: `24_2_fix_test_case_validation` needs Galaxy's parameter-model test-case
  validator (no port) → **approximated** by the necessary condition "ships a
  `<test>`"; `16_04_consider_implicit_extra_file_collection` Galaxy emits
  **unconditionally** → always-true detector.
- **Detection runs on the macro-expanded tree (2026-06-02, the expanded-view port).**
  `tripped_upgrade_codes` detects on `expanded_detection_root` (tier-1 read-only
  accessor, raw fallback when macros can't expand), mirroring Galaxy's advisors,
  which parse the tool *post-macro-expansion* — so a feature supplied only by an
  imported macro is now seen, closing the divergence sized below for the live
  `upgrade` warning. The corpus *diagnostic* measures (`upgrade-codes-applicability`,
  `upgrade-behavior-blocks`) deliberately stay **raw-tree** analyses via the
  `detect_codes_on_root` primitive — the numbers in this section are raw-tree
  baselines; the `macro-expansion-detection-gap` measure quantifies the live shift.
- **Sized the raw-vs-expanded divergence (2026-06-02, `macro-expansion-detection-gap`,
  5,113 macro-bearing tools compared).** Running the detectors on the raw tree vs the
  macro-expanded tree disagrees in two directions. *Over-flag* (raw fires, but a macro
  supplies the construct so Galaxy's post-expansion advisor would not): **984 tools
  (19.2%), entirely `16_04_exit_code`** — a `<stdio>`/error-handling block reached only
  through `<expand macro="stdio"/>`. Across these macro-bearing tools the raw tree
  fires that code 1,590 times (984 over-flag + 606 genuine post-expansion) — a **62%
  false-positive rate within the macro set**. *Under-report* (the macro
  supplies the trigger, unseen on the raw tree — the gap this bullet describes): **344
  tools (6.7%)**, led by `23_0_consider_optional_text` (262), then
  `20_09_consider_set_e` (38), `18_01` (30) and `24_2_fix_test_case_validation` (22).
  (The §28 `set_e` tightening raised its under-report 30 → 38: a macro that injects
  command *sequencing* now correctly flips a raw single-command to applicable
  post-expansion.) The expanded-view port (first bullet) **eliminates these 984
  over-flags and catches the 344 under-reports** in the live `upgrade` warning. It
  also makes a future
  `16_04_exit_code` auto-fix safe to *gate* on the detector — but the hard rule still
  stands at the codemod layer: never inject `<stdio>` off the **raw** tree (codemods
  operate on the raw tree; 984 tools already have it via a macro → double-inject). See
  `docs/upgrade_research/16_04_exit_code.md`.
- **Corpus noise reduction (2026-06-01, 8,608 considered; set_e refreshed 2026-06-02
  for §28).** Per-code crossing *events* drop from **103,330 → 27,367 (26.5%)** once
  detection is applied — ~73% of the old warning's lines were codes that didn't apply.
  Tool-level "warns at all" barely moves (94.2% → 92.3%): nearly every tool still
  trips a near-universal code (the always-on 16.04 note, `18_01` no-`use_shared_home`,
  `20_09` `set_e` on a multi-statement command, `24_2` has-tests). The win is
  *precision per code*, not on/off. Sanity-checked: no inverted predicate;
  `16_04_fix_output_format`→107 and `21_09_fix_from_work_dir_whitespace`→4 match the
  GTR015/GTR014 populations; `17_09`→0 and `24_0_consider_python_environment`→0 are
  genuinely rare conditions. (The §28 `set_e` tightening drops its applicable count
  to **4,674** — the −1,300 that moves the aggregate from 28,667 to 27,367.)

## 26. `NormalizeBooleanValues` (GTR017) — boolean case repair

**Date:** 2026-06-02. Reproduced-by: `uv run --package galaxy-tool-codemod
pytest galaxy-tool-codemod/tests/test_normalize_boolean_values.py` and `uv run
--package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_boolean_values.py`;
corpus recovery via `uv run python -m scripts.corpus_check codemod
galaxy_tool_codemod.codemods.normalize_boolean_values:NormalizeBooleanValues`.

- **The gap.** The Galaxy XSD types boolean attributes `xs:boolean`, which accepts
  only `true`/`false`/`1`/`0`. Tools that write Python-style `True`/`False` (or
  `Yes`/`No`/`On`/`Off`) validate at **no** profile even though Galaxy's runtime
  `string_as_bool` reads them case-insensitively. The corpus categorises **36**
  tools as failing solely for this reason (`invalid boolean ('True'/'False' …)`,
  `combined_corpus_data.json`).
- **`FixTypos` cannot reach it.** `corrections.py` is driven by the *lenient*
  generated model, whose permissive-boolean enum lists `"True"`/`"False"` as legal
  values — so `suggest_corrections` never flags them. A separate repair is needed.
- **What we chose.** A sibling validation-driven codemod, `NormalizeBooleanValues`,
  in the same family as `FixTypos`: it acts only on a globally-invalid tool, rewrites
  recognized boolean spellings to canonical `xs:boolean`, and (per profile,
  newest-first) keeps the change only if it restores validity, else reverts to a
  byte-identical snapshot. The rewrite mirrors `string_as_bool`, so it is
  **behaviour-preserving**. It is added to `CANONICAL_CODEMODS` (so `format` / the
  `iuc` preset repair it) and `AUTO_UPGRADE_CODEMODS` (repair-before-upgrade), and
  the shared snapshot/restore helper is factored to `codemods/_validation_repair.py`.
- **Schema-type-aware, never a blind replace.** Tier 1's
  `boolean_values.suggest_boolean_normalizations` descends the tree and the model
  classes in lockstep (the `corrections.py` technique), reporting only attributes
  the model types as boolean *at the element they appear on*. This is load-bearing:
  the corpus's offending values sit on literal-string attributes too — `value="True"`
  on `<option>` (18×) is a value the tool passes to the command, and lowercasing it
  would silently change behaviour. Per-element typing excludes it; per-profile typing
  handles `optional`, which is `xs:boolean` under some profiles and a free string
  under others.
- **Corpus recovery (2026-06-02).** Of **708** globally-invalid eligible tools,
  **21** are rewritten and reach full validity at the latest profile (26.1);
  **0 non-idempotent, 0 post-validate-failed, 0 crashed**. The recovered set is
  smaller than the 36 categorised because some carry the boolean value on an
  attribute the newer schema accepts permissively (so they fail elsewhere) or have
  additional blocking issues; `NormalizeBooleanValues` and `FixTypos` target
  disjoint failure modes, so the canonical pipeline now repairs both.

## 27. `FixInterpreter` (GTR016) — inline a deprecated `<command interpreter=…>`

**Date:** 2026-06-02. Reproduced-by: `uv run --package galaxy-tool-codemod
pytest galaxy-tool-codemod/tests/test_fix_interpreter.py
galaxy-tool-codemod/tests/test_interpreter.py`; corpus sizing `uv run python -m
scripts.measure interpreter-bucket-split`; idempotence + post-validity `uv run python
-m scripts.corpus_check codemod
galaxy_tool_codemod.codemods.fix_interpreter:FixInterpreter`.

- **The gap.** `16_04_fix_interpreter` is the single largest behaviour-block (1,726
  tools stuck at 16.04). Before 16.04 Galaxy ran `<command interpreter="python">script.py
  …</command>` as `python '<tool_dir>/script.py' …` (first substituted token, resolved
  under the tool dir, interpreter prepended; `evaluation.py:781-787`); from 16.04 the
  attribute is ignored, so an upgraded tool breaks unless rewritten.
- **What we chose — a conservative bucket-A runtime-gated fix.** `FixInterpreter`
  (`RuntimeGatedFix`, `introduced_profile="16.04"`) rewrites `<command interpreter="I">S
  …</command>` → `<command>I '$__tool_directory__/S' …</command>` and drops the attribute,
  for "bucket A": a single-token standard interpreter (`_STANDARD_INTERPRETERS`) whose
  body begins with a literal script filename (`_SCRIPT_TOKEN`). Bucket B (leading Cheetah
  / `$var` first token) and C (multi-token interpreter) cannot be reproduced statically
  and stay in the §23 warning. Wired into `RUNTIME_GATED_FIXES`; the crossing-gate (§24)
  applies it only when a tool crosses 16.04. **Not** in `CANONICAL_CODEMODS`.
- **Positional splice, not `str.replace` over the raw body** (adversarial-review finding).
  The rewrite is anchored at the offset `first_command_token_span` located (the first
  non-blank, non-`##` content line) — `body[:offset] + body[offset:].replace(S, …, 1)` —
  so a script name appearing inside a leading `##` comment is never mistargeted (the
  `redup.xml` mistarget the sweep is blind to, since the mangled output stays valid +
  idempotent). Pinned by a content-equality unit test
  (`test_script_name_in_leading_comment_is_not_mistargeted`).
- **CDATA-preserving.** First codemod to rewrite `<command>` text; `Cursor.set_text` gains
  a `cdata=True` flag (`etree.CDATA`) so shell operators (`&&`, `<`) stay literal. An
  originally-non-CDATA command gaining CDATA is an accepted side effect, aligned with
  the `<command>` CDATA practice (GTR018).
- **No file-exists gate in the codemod** (only in the measure's bucket-A refinement). The
  rewrite is faithful whether or not the script is co-located — Galaxy built the same
  `<tool_dir>/<token>` path regardless, failing identically if absent. Gating on the
  script's presence would make the result depend on whether the tool was loaded from a
  path or bytes, which the corpus sweep correctly flags as non-idempotent. So the codemod
  fixes bucket-A-by-shape (the measure's **A** 1,383 + **A-missing** 27).
- **The `'$__tool_directory__/S'` literal vs Galaxy's `shlex.quote`** — accepted boundary,
  documented in `docs/upgrade_research/16_04_fix_interpreter.md`: faithful for every path
  except a literal single quote in the resolved tool-dir abspath (an admin-controlled,
  out-of-scope install path; the token itself is quote/space-free via `_SCRIPT_TOKEN`).
- **Corpus impact.** The `corpus_check codemod` sweep rewrote **1,127** of its eligible
  tools (idempotent, 0 post-validate-failed, 0 crashed). That is fewer than the measure's
  1,410 bucket-A-by-shape population because the sweep's eligibility skips tools that
  already validate at the latest profile (an `interpreter=` is XSD-valid at every
  profile); those are still rewritten by the live `upgrade` when they cross 16.04. The
  `upgrade-behavior-blocks` `16_04_fix_interpreter` stuck count drops **1,726 → 316** (the
  residual is bucket B/C).
- **Mixed-content guard (2026-06-06; behavior-preservation GTR016).** `detect` builds the
  new body from `"".join(command.itertext())` but `set_text` overwrites only `.text`,
  leaving any child nodes (a comment / `<expand>`) and their tails — so a mixed-content
  `<command>`'s absorbed tail was emitted **twice** (e.g. `script.py <!-- n --> --x`
  → `python '…/script.py'  --x --x`), a silent behaviour change the validity oracle
  can't see. `detect` now skips a `<command>` with child nodes
  (`cursor.child_node_count() != 0`), matching `SingleQuoteCommandVars` /
  `WrapCommandCdata`. Clearing the children was rejected — an `<expand>` carries macro
  command content; skipping is the safe choice (the §23 warning still covers it). ~9
  corpus interpreter commands are mixed-content; the rewrite count drops accordingly.
  See `../docs/behavior_preservation.md`.

## 28. Per-tool detector **precision** audit — tightening the near-universal codes

**Date:** 2026-06-02. Reproduced-by: `uv run python -m scripts.measure
set-e-tightening` (the sizing) and `uv run python -m scripts.measure
upgrade-codes-applicability` (the per-code applicable baseline); the
single-statement predicate is unit-tested in
`galaxy-tool-xml/tests/test_measure.py`.

- **The gap.** §25's per-tool detection already narrows the `upgrade` warning to the
  codes whose detector fires, but tool-level "warns at all" barely moved (94.2% →
  92.4%) because a few detectors faithfully mirror Galaxy's **coarse** advisor and
  fire near-universally: `16_04_consider_implicit_extra_file_collection`
  (`lambda: True`), `20_09_consider_set_e` / `18_01_consider_home_directory` (any
  `<command>`), `24_2_fix_test_case_validation` (any `<test>`). They test "has a
  command / has tests", not whether the *changed construct* is genuinely present.
- **The governing rule (one-directional).** A detector may be tightened **only** when
  the absence of the governed construct is *provable from the static (macro-expanded)
  XML*; any ambiguity keeps the warning (never a false "safe"). This is *more precise
  than Galaxy's coarse check, never less* — consistent with §25's "port the **intent**,
  not the literal code" (we already fix Galaxy's transcription bugs). It stays inside
  the §22 boundary: we only ever **narrow** false positives, never claim a behavioural
  guarantee.
- **Per-code audit (all 17).**
  | Code | Today | Verdict |
  |---|---|---|
  | `20_09_consider_set_e` | `_detects_set_e` (no `strict=` **and** not a lone command) | **Tightened (shipped)** — a single simple command is provably unaffected by `set -e`; sized below. |
  | `23_0_consider_optional_text` | any `<param type="text">` w/o `optional` | **Deferred** — the sound suppressor is "a validator that rejects the empty string", but an exploratory scan over the 2,805 firing tools found only ~16% carry *any* text-param validator, and the *provably* empty-rejecting subset is smaller still (`empty_field` always; `regex`/`length` only for some patterns/mins — needs per-validator Galaxy-source grounding). Modest payoff for materially more work than `set_e`; left coarse. |
  | `16_04_consider_implicit_extra_file_collection` | `lambda: True` | **Keep coarse** — Galaxy emits it unconditionally; reliance on implicit working-dir discovery is not statically provable-absent. |
  | `18_01_consider_home_directory` | `_detects_no_shared_home` | **Keep coarse** — `$HOME` dependence can live inside an invoked binary; absence unprovable from XML. |
  | `24_2_fix_test_case_validation` | `_detects_has_test` | **Keep coarse** — a sound tightening needs a port of Galaxy's parameter-model test-case validator (large, separate effort). |
  | `16_04_exit_code` | `_detects_no_error_handling` | Already a real construct test. |
  | all other codes | narrow construct / `tool_type` tests | Already precise. |
- **`set_e` sizing (2026-06-02, `set-e-tightening`, combined corpus).** Of **9,311**
  command-bearing tools the current detector fires on (no `strict=`), **1,915 (20.6%)**
  are a *provably single simple command* — one non-comment statement line, no Cheetah
  control flow, no sequencing/pipeline/background metacharacter — so `set -e` cannot
  change their behaviour and the note is a false positive. The conservative heuristic
  (`_command_text_is_single_simple_statement`) never suppresses an ambiguous body, so
  it can only *remove* false positives.
- **The tightening, and its multi-measure regen (shipped 2026-06-02).**
  `_detects_set_e` replaces the old `_detects_no_strict` mirror: it still requires no
  `strict=`, and additionally suppresses a *provably single simple command*
  (`_command_text_is_single_simple_statement`, shared with the `set-e-tightening`
  measure so the sizing can't drift). `20_09_consider_set_e` is a `consider`-level
  **advisory note** — it never blocks an upgrade or mutates a tool — but the detector
  feeds three raw-tree corpus measures, all **regenerated from their standing
  commands** (never hand-edited — §5 of the pre-PR audit):
  - `upgrade-codes-applicability`: set_e applies **5,974 → 4,674**; aggregate crossing
    events **28,667 → 27,367 (27.7% → 26.5%)**; tool-level "warns at all" **92.4% →
    92.3%** (§25 updated).
  - `macro-expansion-detection-gap`: set_e under-report **30 → 38** (a macro injecting
    command *sequencing* now correctly flips a raw single-command to applicable
    post-expansion); total under-report **317 → 344** (§25 updated).
  - `upgrade_behavior_block_stats.md` (regenerated artifact): set_e as a
    must_fix+consider first-blocker **415 → 388**; the 27 freed tools re-block later
    (23.0 +7, 24.2 +17, reach-latest +3 — conservation holds).
  The change diverges *tighter* than Galaxy's advisor (more precise, never
  under-reporting), inside the §22 boundary. `23_0_consider_optional_text` remains a
  candidate pending its own sizing.

## 29. `WrapCommandCdata` (GTR018) / `WrapHelpCdata` (GTR019) — CDATA-wrap bodies

**Date:** 2026-06-03. Reproduced-by: `uv run --package galaxy-tool-codemod
pytest galaxy-tool-codemod/tests/test_wrap_command_cdata.py
galaxy-tool-codemod/tests/test_wrap_help_cdata.py
galaxy-tool-codemod/tests/test_cursor.py`; corpus sweeps via `uv run python -m
scripts.corpus_check codemod
galaxy_tool_codemod.codemods.wrap_command_cdata:WrapCommandCdata` and `…
wrap_help_cdata:WrapHelpCdata`. Sizing: `uv run python -m scripts.measure
help-formats` backs the `<help>` population; the wrappable counts below were a
one-off classification scan (mirrors the codemod's eligibility predicate).

- **The practice (IUC #34/#42).** Galaxy runs the `<command>` body through Cheetah
  then a shell, and renders `<help>` as reStructuredText; the IUC best practice
  wraps both in `<![CDATA[…]]>` so shell operators (`&&`, `<`, `|`) and markup stay
  literal without XML-escaping. This was Bucket 3 in `docs/iuc_best_practices.md`,
  originally **deferred** by the maintainer for content-change risk (fmt §D3 bars
  fmt from rewriting CDATA content).
- **Why the re-examination resolved the risk.** Wrapping is **behaviour-preserving
  by construction**: lxml already exposes the *entity-unescaped* body as `.text`
  (`&amp;&amp;` is `&&` in the tree), so `set_text(text, cdata=True)` (the §21
  primitive) only changes how that identical text is *serialised* — the value
  Galaxy runs/renders is unchanged. The earlier objection was content-change
  *safety*, which the static-validity oracle (§22) plus the pure-text scoping below
  settle.
- **Scope — the pure-text subset only.** The shared predicate
  (`codemods/_cdata.cdata_wrap_change`, used by both `detect_Command` and
  `detect_Help`) wraps a body iff it has non-whitespace text, **no child nodes**
  (`Cursor.child_node_count() == 0` — a mixed-content body can't be one CDATA
  section), is **not already wrapped** (`Cursor.is_cdata_wrapped()` — a serialise +
  `<![CDATA[` body check, the two read primitives added this pass), and contains no
  `]]>` terminator (which cannot live inside a section). The advisory checks are
  retained to cover the mixed-content residual these codemods skip — and were later
  made the partition `.2` sub-rules **GTR018.2 / GTR019.2**, restricted to exactly
  that residual via the shared tier-1 predicate (registry D10; check D9).
- **Canonical, not upgrade.** Both are safe, idempotent, `profile=`-preserving and
  so join `CANONICAL_CODEMODS` (the `format` / `iuc` pipeline) after the structural
  reorders — content-level tidying, independent of child order. This grows the `iuc`
  preset (GTR013/GTR017 set the precedent for non-whitespace canonical codemods).
- **Corpus soundness (2026-06-03, combined).** Of **8,607** eligible tools,
  `WrapCommandCdata` modifies **2,772** and `WrapHelpCdata` **3,247**; both report
  **0 non-idempotent, 0 post-validate-failed, 0 crashed** — idempotent and
  validity-preserving on every tool, zero retained regressions. The remaining bodies
  are already CDATA-wrapped (5,982 command / 5,007 help in the raw scan) or
  mixed-content (12 command / 9 help; 0 carry a `]]>` terminator).
- **Carriage-return guard (2026-06-06; behavior-preservation GTR018.1/GTR019.1).** The
  shared tier-1 predicate `galaxy_tool_xml.cdata.cdata_wrappable` was unsound for a
  body containing a carriage return: a CDATA section cannot carry `&#13;` (entity/char
  references are not recognised inside a section), and a raw CR is normalised to LF on
  the next parse — so wrapping a CR-bearing body silently rewrote it `\r`→`\n` and was
  non-idempotent. `cdata_wrappable` now rejects any body containing `\r`, so both `.1`
  rules leave it unwrapped (the CR survives as `&#13;`) and the `.2` advisories flag it
  in lockstep. **Zero corpus incidence** — no tool carries a CR in an otherwise-wrappable
  body, so the GTR018/019 counts above are unchanged; the guard is a soundness
  safety-net against the silent rewrite, not a corpus-driven change. Pinned by
  `test_cdata.py::test_cdata_wrappable_rejects_carriage_return`. See
  `../docs/behavior_preservation.md`.

## 30. `SingleQuoteCommandVars` (GTR020.1) — auto-quote the provable single-quote subset

**Date:** 2026-06-03. Reproduced-by: `uv run --package galaxy-tool-codemod
pytest galaxy-tool-codemod/tests/test_single_quote_command_vars.py`; the
classifier/lexer it shares are pinned in `galaxy-tool-xml/tests/test_command_vars.py`
and `…/test_command_text.py`. Sizing: `uv run python -m scripts.measure
iuc011-fixability`. Corpus sweep: `uv run python -m scripts.corpus_check codemod
galaxy_tool_codemod.codemods.single_quote_command_vars:SingleQuoteCommandVars`.

- **The practice (IUC #36).** Single-quote a Cheetah `$var` in `<command>` so it
  reaches the shell as one literal argument (no word-splitting / glob / injection).
  The advisory check (later the `.2` residual sub-rule `GTR020.2`;
  `galaxy-tool-lint/docs/decisions.md` D5/D9) reports the unquoted occurrences;
  D6 deferred an auto-fix as "partial, wrong shape, never
  auto-run under `format`". This codemod is the **revisit** (check D8): it ships the
  fix for the subset where quoting is *provably* behaviour-preserving.
- **Scope — the provable set only.** Quoting changes behaviour only when the value
  can contain whitespace. The tier-1 classifier (`galaxy_tool_xml.command_vars`,
  shared with the measure) resolves each occurrence against `<inputs>` and admits
  exactly `{safe, attr_safe, builtin_path}`: a bare `$param` of a single-token type
  (number / Galaxy-controlled path, or a `select` / `drill_down` whose option values
  are *provably* single tokens — see §32), a `$param.ext` /
  server-path attr (charset-restricted / deployment-fixed), and a `$__…__` Galaxy
  path built-in. Each is space-free for any tool that *currently works* (a path with
  a space already breaks unquoted), so the quote is a strict no-op there. Excluded
  as not-provable: `text` / `multiple=` params, `$on_string` and `.name` /
  `.element_identifier` label attrs (run-varying dataset labels), `structured`,
  `#set`/loop (`non_input`). The advisory `GTR020.2` keeps flagging that residual.
- **Wider than D6's floor, and *why* it's still provable.** D6 sketched a
  "safe-class-only" fix (46.7%). Sizing the two extra classes
  (`scripts.measure iuc011-fixability`) showed `builtin_path` (1,119 occ) +
  `attr_safe` (295 occ) lift coverage to **49.5%** of occurrences and add **+280**
  whole-tool-auto-fixable tools — and they fail in a *deployment*-fixed way, not a
  per-run way, so they meet the same "no-op for a working tool" bar as `safe`.
  `builtin_label` (`$on_string`) is excluded and is **0** in the corpus anyway.
- **Not the M5 mutation subsystem.** D6's objection was that quoting is a
  "Cheetah-rewriting mutation". It isn't here: the rewrite is a **positional splice**
  over the lexer's absolute `start`/`end` spans (`unquoted_cheetah_vars`), wrapping
  `'…'` around an existing run of bytes — no Cheetah evaluation, no reference
  resolution. Applied **right-to-left** so earlier offsets stay valid; the body is
  re-emitted preserving its CDATA-ness (`set_text(..., cdata=is_cdata_wrapped())`).
  Mixed-content `<command>` (child nodes) is skipped. **Idempotent by construction**
  — a wrapped occurrence reads as single-quoted on the next pass and is not
  re-flagged.
- **Canonical, and it *does* shift default-`format` bytes.** It joins
  `CANONICAL_CODEMODS` after `WrapCommandCdata` (so it sees the canonical CDATA body)
  — the first canonical codemod that changes output for tools never previously
  rewritten, a deliberate, data-backed reversal of D6's "never auto-run under
  `format`". Justified because every applied quote is behaviour-preserving. The
  workspace / cli / registry byte-identity notes were updated accordingly.
- **Corpus soundness (2026-06-03, combined).** Of **8,607** eligible tools, GTR020
  modifies **4,433** and reports **8,607 idempotent, 0 non-idempotent, 0
  post-validate-failed, 0 crashed** — quoting is idempotent and validity-preserving
  on every tool, zero retained regressions.

## 31. `SingleQuoteCommandVars` (GTR020.1) — shell boundary oracle (widening reverted as unsound)

**Date:** 2026-06-04. Phase-1 of the cheetah-lex + bashlex boundary-oracle work
(`../../docs/upgrade_research/cheetah_bashlex_boundary_oracle.md`).

GTR020.1 now decides each occurrence through the shared tier-1 policy
`galaxy_tool_xml.shell_oracle.quote_is_behavior_preserving` instead of the value-domain
`provably_quotable` alone. When the optional `galaxy-tool-xml[shell-oracle]` extra
(bashlex) is installed it composes the value-domain rule with a bashlex shell-context
classifier; without the extra it *is* `provably_quotable`, so the default `format` output
is unchanged and license-clean (§30 still describes that default).

### Decisions

- **No false-veto of glued/redirect-file safe vars (Phase-0 KU-4 correction).**
  Single-quoting a *space-free* value is behaviour-preserving even when the var is glued
  (`${ds}.bam`) or a redirect-file target (`> $ds`), so those must **not** be vetoed (that
  would break §30's own fixtures).
- **No widening (corrected 2026-06-04 — reverted).** A briefly-shipped "widen no-split
  contexts (assignment RHS `THREADS=$opts`) for any value" was **unsound** and reverted:
  Galaxy renders a Cheetah `$x` to its value as *literal text*, so `VAR=foo bar` splits
  (the bash no-split rule applies to shell *expansions*, not Cheetah literals) — quoting a
  space-bearing value there changes behaviour. So GTR020.1's set is the value-domain rule
  minus the dup narrowing; the oracle no longer promotes any GTR020.2 residual. Sound
  widening needs adversarial-shape render verification (deferred). See tier-1
  `docs/decisions.md` §17 + `../docs/upgrade_research/cheetah_bashlex_boundary_oracle.md` §KU-5.
- **One genuine narrowing: fd-dup.** `2>&$fd` quoted flips a descriptor dup into a file
  redirect, so `DUP_TARGET` is never quoted even when value-domain-safe.
- **The `EditCertifier` seam (`certify.py`).** The constructor takes
  `certifier: EditCertifier | None = None`; `None` (the canonical-pipeline path, which
  constructs codemods no-arg) uses the tier-1 static policy. The seam reserves the Phase-2
  CT3 render certifier (`--certify=render`) as a pure addition — no refactor of the static
  path. A certifier's `should_quote` is signature-compatible with the static policy.
- **Partition stays exact.** The GTR020.2 advisory check computes its residual from the
  *same* `quote_is_behavior_preserving`, so any occurrence the policy narrows (fd-dup)
  moves from fix to advisory in lockstep (check `docs/decisions.md` D10).

### Corpus sizing (combined, sha-deduped; needs the extra)

`scripts.measure shell-oracle-quoting` over 6,670 pure-text `<command>`s (48,789 unquoted
occurrences): after the revert the oracle **widens 0** and **narrows 0** vs the value-domain
rule. The pre-revert 66-occurrence / 22-tool widening was the unsound no-split case; the
fd-dup narrowing has no value-domain-safe occurrence corpus-wide (so GTR020.1 was never
unsafe in practice — the veto is defensive). Net: the oracle's current effect on GTR020.1 is
nil beyond `provably_quotable`; the infrastructure + sound dup veto remain for a future
render-verified widening.

### Reproduction

```sh
uv run --package galaxy-tool-codemod pytest \
  galaxy-tool-codemod/tests/test_single_quote_command_vars.py
uv run python -m scripts.measure shell-oracle-quoting   # needs galaxy-tool-xml[shell-oracle]
```

## 32. `SingleQuoteCommandVars` (GTR020.1) — `select`/`drill_down` scope-narrowing + faithful-lexer var extraction

**Date:** 2026-06-06. Closes a behavior-preservation audit finding (the adversarial
audit refuted §30's blanket "`select` is single-token" claim) and rewrites the var
extraction onto the faithful Cheetah lexer (tier-1 §16/§19). Reproduced-by: `uv run
--package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_single_quote_command_vars.py` (+ tier-1
`test_command_vars.py` / `test_command_text.py`). Sizing: `uv run python -m
scripts.measure select-quoting-safety`.

### The bug

§30 admitted `select`/`drill_down` to the `safe` class **by type alone**
(`SAFE_SINGLE_TYPES`), asserting an "author-fixed `select` value" is intrinsically a
single token. That is false: a `<param type="select">`'s value is an author-written
`<option value="…">` string with no charset constraint, and a **widespread, intentional
idiom** packs several argv words into one option value (`<option value="-b -h">`,
`"-labels -intervals"`) precisely so the unquoted `$param` word-splits. GTR020.1 wrapped
such a var in single quotes — fusing the intended N arguments into one literal token and
**changing the command Galaxy runs**. XSD validity and idempotence are both preserved, so
neither corpus oracle caught it; the corpus codemod sweep stayed green on a real
behaviour regression. Confirmed live on `iuc/bedtools/tagBed.xml` (`$field`, option
`"-labels -intervals"`).

### The fix — option-value inspection (provable subset retained)

`select` / `drill_down` are **removed from `SAFE_SINGLE_TYPES`** and resolved separately
(`command_vars._select_options_are_single_tokens`): `safe` **only** when the option set
is statically known — no `<options from_*>` runtime source — and every reachable
`<option value>` (including a `drill_down`'s nested options) is a single shell token (no
whitespace / glob / shell-active metacharacter). The unprovable residual — a value that
word-splits, a glob, a runtime-sourced option set, or a select with no statically-visible
options (e.g. macro-supplied, invisible to the pre-expansion codemod) — is demoted to
`text`, so the advisory `GTR020.2` flags it (partition stays exact: both consume the same
`input_param_info`). A **wholesale drop** of select/drill_down was rejected as
over-conservative by the sizing below.

### Faithful-lexer var extraction (tier-1 §16/§19)

`command_text.unquoted_cheetah_vars` filters its regex candidates against the faithful
CT3 span lexer (`cheetah_cdm.cheetah_spans`; CT3 is a base dependency — §19, promoted from
the optional `cheetah-cdm` extra 2026-06-06): a candidate survives only if its `$` starts a
genuine `PLACEHOLDER` span, dropping `$`-runs inside a `#raw` block, a `#* … *#` block
comment, an escaped `\$`, or a directive clause that the line-based regex cannot see. It
only **narrows**; only on the ~0.4% of bodies CT3 cannot compile is the raw regex result
used. The MIT license of CT3 (unlike GPL bashlex behind `shell-oracle`) made the hard
dependency clean.

This barely touches the GTR020.1 fix population (those false positives classify as
`non_input` and were never quoted) but it **materially sharpens the GTR020.2 advisory**:
the dominant dropped case is the ubiquitous escaped-shell-var idiom `\${GALAXY_SLOTS:-4}`
(and `#for`/`#set` directive vars), which the regex wrongly flagged as "please single-quote
this Cheetah variable". A 4,000-tool sample drops 5.2% of regex candidates, all confirmed
non-placeholders — corpus-wide GTR020.2 falls from 24,804 to 22,595 findings (the select
demotion adds ~705; the faithful filter removes the rest).

### Corpus sizing (`scripts.measure select-quoting-safety`, sha-deduped)

Of **15,047** non-multiple `select`/`drill_down` params, **85.5%** are provable (every
static option value a single token); the unsafe residual is 1.7% multi-flag (whitespace),
0.1% glob, 5.9% runtime-sourced, 6.9% no-static-options. In GTR020.1's actual scope —
bare references unquoted in `<command>` (**2,710** occurrences) — **85.0% (2,304) are
provable and stay auto-quoted**, while **406 occurrences across 269 tools were
unsound-before** (multi-flag/glob/dynamic) and a further 299 unprovable "no-options"
occurrences move to advisory. So the scope-narrowing keeps ~85% of the coverage and
removes the behaviour regression on 269 tools — wholesale removal would have sacrificed
all 2,304 provable quotes for no soundness gain.

### Corpus soundness

`scripts.corpus_check codemod …:SingleQuoteCommandVars` over the combined corpus: of
**8,607** eligible tools GTR020.1 now modifies **4,354** (down from §30's 4,433 — the 79
tools whose *only* rewrite was an unsound select quote), with **8,607 idempotent, 0
non-idempotent, 0 post-validate-failed, 0 crashed**. The fix removes a real behaviour
regression while leaving every other quote and the idempotence/validity invariants intact.

## 33. `TrimAttributeWhitespace` (GTR035) — first planemo-parity *fix* (whitespace trims)

**Date:** 2026-06-06. First rule from the planemo-linter reimplementation roadmap
(`../../docs/planemo_linter_parity.md`): a planemo linter that only *reports*,
reimplemented as a *fixer*. Reproduced-by: `uv run --package galaxy-tool-codemod
pytest galaxy-tool-codemod/tests/test_trim_attribute_whitespace.py`. Corpus sweep:
`uv run python -m scripts.corpus_check codemod
galaxy_tool_codemod.codemods.trim_attribute_whitespace:TrimAttributeWhitespace`.

- **The planemo linters.** `galaxy.tool_util.linters.general` warns on accidental
  leading/trailing whitespace in a tool's `version`/`name`/`id`
  (`ToolVersionWhitespace`/`ToolNameWhitespace`/`ToolIDWhitespace`) and a
  `<requirement>`'s `version` (`RequirementVersionWhitespace`) — *"this may cause
  errors"* — but never fixes them.
- **The soundness split (the homework the parity doc anticipated).** We trim only the
  **behaviour-preserving** subset:
  - `<tool name>` — display only; surrounding whitespace renders to nothing.
  - `<requirement version>` — a whitespace-bearing conda version cannot resolve (the
    solve fails), so a *working* tool never has one; trimming only ever repairs an
    already-broken requirement.
  - `<tool id>` and `<tool version>` are **excluded**: Galaxy reads both *raw* as the
    tool's identity / version key (`tool_util/parser/xml.py` `parse_id`/`parse_version`
    do not strip; `Tool.id` is the registration key, `Tool.version` the comparison key),
    so trimming would change a *working* tool's identity — not behaviour-preserving.
    They stay for an advisory check (planned), reported but not auto-fixed.
- **Tiering — codemod, not fmt.** Trimming an attribute *value* changes meaning (not
  layout trivia), so it is a tier-2 codemod, not a cosmetic fmt rule — even though the
  effect is runtime-neutral for the two attributes we fix. It joins `CANONICAL_CODEMODS`
  (safe, idempotent, `profile=`-preserving) after `NormalizeBooleanValues` (the other
  attribute-value normalizer). Detect-primitive: `detect_Tool` (name) + `detect_Requirement`
  (version) yield a `set_attribute(strip())` thunk. Idempotent by construction (post-trim
  the value equals its `strip()`).
- **Corpus.** 26 tools carry the issue (`docs/corpus_check_stats.md`); the codemod sweep
  modifies **20** of the eligible tools with **0 non-idempotent, 0 post-validate-failed,
  0 crashed** (`docs/corpus_rule_stats.md`); the canonical `format` pipeline stays
  idempotent (fmt sweep: 8,608 idempotent, 0 non-idempotent).

**Addendum (2026-06-10, the proofs-tightening pass):** GTR035 became a
**partition** — `GTR035.1` (this codemod, now `<requirement version>` only:
conda receives the spec verbatim, `conda_util.py:461-465`, so a
whitespace-bearing version never resolved — an unconditional repair proof) and
`GTR035.2` (a new check-tier advisory for `<tool name>` edge whitespace: its
preservation argument is a *display-contract* claim — `parse_name` reads the
attribute raw, `xml.py:220-221`, render-identical in HTML but byte-visible in
API JSON — below the construction bar fixable rules now hold to). The
`ToolNameWhitespace` planemo alias moved to `.2`; parity coverage is unchanged.
**Corpus:** all 26 detected whitespace instances are *name* cases — GTR035.2
now reports all 26, and GTR035.1 (version) is zero-corpus novel-tool insurance
(0 modified in the rules sweep). Behaviour-preservation ledger, "GTR035
advisory" proposal, applied at the maintainer's direction.

## 34. `ReplaceOutputElement` (GTR036) — deprecated `<output type="data">` → `<data>`

**Date:** 2026-06-06. Second planemo-parity *fix*
(`../../docs/planemo_linter_parity.md`): reimplement planemo's `OutputsOutput`
(*"Avoid the use of 'output' and replace by 'data' or 'collection'"*) as a fixer.
Reproduced-by: `uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_replace_output_element.py`. Corpus sweep:
`uv run python -m scripts.corpus_check codemod
galaxy_tool_codemod.codemods.replace_output_element:ReplaceOutputElement`.

- **Behaviour-preserving for `type="data"`.** Galaxy routes a `<outputs>` child by tag
  (`tool_util/parser/xml.py:548-563`): an `<output type="data">` goes through the *same*
  `_parse` as a `<data>`. So renaming the element to `<data>` and dropping the redundant
  `type="data"` is a no-op for Galaxy. Detect-primitive `detect_Output` →
  `rename_tag("data")` + `delete_attribute("type")`.
- **Scope homework — only `type="data"`.** Two siblings are left flagged (advisory), not
  rewritten:
  - `<output type="collection">` — Galaxy remaps `collection_type` → `type` /
    `collection_type_source` → `type_source` and fills `type_source` via
    `unicodify(None)` when the source attr is absent, so a literal rename is *not*
    provably equivalent. Deferred.
  - `<output>` with no `type` — an *expression* output (`_parse_expression`), a different
    output kind, not a data rename.
- **Guarded on the parent.** Acts only on `<output>` whose parent is `<outputs>`; an
  `<output>` under `<test>` is a test assertion, not an output definition. Joins
  `CANONICAL_CODEMODS` (safe, idempotent — no `<output>` remains after the rename,
  `profile=`-preserving).
- **Corpus.** 1 tool carries `<output type="data">` combined-corpus (`docs/corpus_check_stats.md`); the codemod sweep modifies **1**, with **0 non-idempotent, 0 post-validate-failed, 0 crashed** (`docs/corpus_rule_stats.md`); fmt pipeline stays idempotent. Low incidence, but correct for novel tool XML — not gated on corpus frequency.

**Addendum (2026-06-10, ledger item C3):** the `type="collection"` deferral is
reversed — Galaxy's deprecated-path remap is exact and mirrorable
(`parser/xml.py:548-563`: `attrib["type"] = unicodify(collection_type)`,
`attrib["type_source"] = unicodify(collection_type_source)`, then the same
`_parse_collection` as a `<collection>`), and the `unicodify(None)` corner is
settled by the typed overload (`util/__init__.py:1190-1196`: `None` in → `None`
out, which reads identically to an absent attribute). The codemod now rewrites
`<output type="collection">` **when `collection_type` is present** (tag rename
+ `collection_type`→`type` + `collection_type_source`→`type_source`); the
degenerate no-`collection_type` case (the deprecated path stores `type=None`)
and expression outputs stay advisory. ~0 corpus incidence — novel-tool
insurance, per `../../docs/deferred_fix_opportunities.md`.

## 35. `DropRedundantParamName` (GTR037) — drop a `<param>` name its `argument` implies

**Date:** 2026-06-06. Third planemo-parity *fix*
(`../../docs/planemo_linter_parity.md`): reimplement planemo's
`InputsNameRedundantArgument` as a fixer. Reproduced-by: `uv run --package
galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_drop_redundant_param_name.py`. Corpus sweep:
`uv run python -m scripts.corpus_check codemod
galaxy_tool_codemod.codemods.drop_redundant_param_name:DropRedundantParamName`.

- **The redundancy.** Galaxy derives a param name from `argument` when `name` is absent:
  `_parse_name(None, argument) = argument.lstrip("-").replace("-", "_")`
  (`tool_util/parser/util.py`). A `<param>` declaring **both**, where
  `name == argument.lstrip("-").replace("-", "_")`, repeats what Galaxy would compute
  anyway — exactly the linter's condition (`name == _parse_name(None, argument)`).
- **Behaviour-preserving.** After dropping `name`, Galaxy computes the identical name, so
  every Cheetah `$name` reference and by-name cross-reference keeps resolving. Only the
  redundant subset is dropped (`name != derived` is kept — it carries information).
- **Validity-safe for every profile (incl. novel XML).** `param/@name` is *optional* in
  **all 28** vendored XSDs that allow `argument` (verified: none require `name` while
  permitting `argument` — coupled in Galaxy's schema evolution), so dropping `name` never
  invalidates a tool that currently validates. This is a *static* guarantee, not a
  corpus observation — it holds for unseen tools too.
- **Scoped to definitions.** Acts only on a `<param>` under `<inputs>` (walks ancestors);
  a `<test><param>` is matched by name and is never touched. Joins `CANONICAL_CODEMODS`;
  idempotent (no `name` remains to match).
- **Corpus.** 343 tools carry a redundant name (1,846 findings, `docs/corpus_check_stats.md`); the codemod sweep modifies **332** eligible tools, **0 non-idempotent, 0 post-validate-failed, 0 crashed** (`docs/corpus_rule_stats.md`); fmt pipeline idempotent. The highest-impact planemo-parity fix so far.

## 36. `canonical_codemods()` — derive the canonical pipeline from ruleset membership

The hardcoded `CANONICAL_CODEMODS` tuple is removed. The canonical/`format` pipeline is now
**derived**: `canonical.canonical_codemods()` returns the codemods that declare the
`"default"` ruleset (`RuleMeta.rulesets`, tier-0.5 D4), sorted by `meta.order`. Each
canonical codemod carries an explicit `order=` (10, 20, … matching the historical tuple
sequence) so application order survives the tuple's removal; the registry's apply phase
sorts the codemod family by `meta.order` (registry D15). `AUTO_UPGRADE_CODEMODS` (the
separate, opt-in upgrade pipeline — not ruleset-driven) is unchanged. The front-to-back
order and the byte output are identical to before; `test_canonical.py` pins both the
derivation (`= "default"`-ruleset codemods, `meta.order`-sorted) and the ordering
constraints (repair-before-reorder, attributes-before-elements).

### Reproduction

```sh
uv run --package galaxy-tool-codemod pytest galaxy-tool-codemod/tests/test_canonical.py
```

## 37. `RepairHelpRst` (GTR089.1) — repair deterministically-fixable invalid `<help>` RST

**Date:** 2026-06-09. The **fixable `.1` half** of the GTR089 partition (the advisory
residual `GTR089.2` is the renamed check, check D31). The RST analogue of the Cheetah
mutators: it repairs invalid `<help>` reStructuredText behind a behaviour-preserving gate.
Joins `canonical_codemods()` (declares the `"default"` ruleset, `order=25`) — after the
repairs (`FixTypos` 10, `NormalizeBooleanValues` 20), before the reorders and, crucially,
before `WrapHelpCdata` (100) so the repaired text is re-canonicalised into CDATA.

### Decisions

- **Validation-driven, like `FixTypos`/`NormalizeBooleanValues`.** Overrides `apply`;
  `detect` is `coarse_detect`. A no-op unless the `<help>` body is invalid RST and the
  shared tier-1 `repair_help_rst` returns a repair — so on valid help (the vast majority)
  it costs one `rst_is_invalid` probe and changes nothing. Idempotent (a repaired tool is
  valid → next run no-ops).
- **The fix/advisory boundary is one tier-1 function.** Both this codemod and `GTR089.2`
  call `galaxy_tool_xml.rst` (`rst_is_invalid` / `repair_help_rst`); the gate and recipes
  live there (tier-1 §23), so the partition can't drift and the check tier stays
  codemod-independent.
- **Canonical-safe because the gate is strong.** RST repair is the first content-mutating
  canonical codemod over `<help>` prose; it ships in the default `format` only because the
  tier-1 gate keeps a fix solely when the rendered doctree is unchanged modulo the removed
  error (so `format` output can change on a tool with fixable broken help — the
  facade-vs-pipeline pin still holds). Macro-bearing / `format="markdown"` help is skipped;
  CDATA wrapping is preserved (`Cursor.set_text(..., cdata=is_cdata_wrapped(help))`).
- **Harness faithfulness fix (found by the sweep).** The retained-fixture round-trip in
  `scripts/corpus_check.py codemod` and `tests/test_regressions.py` used a bare
  `etree.tostring` (ASCII default), which escapes non-ASCII as numeric character references
  — and inside a CDATA body those are *not* interpreted, so an emoji/en-dash help table
  (`tools-iuc/fastqe`) round-tripped to corrupted literal `&#…;` text and read as spurious
  non-idempotence. Both now serialise as UTF-8 (the real pipeline's `to_bytes`), matching
  the fmt sweep; the codemod is idempotent under the real serialiser.

### Reproduction

```sh
uv run --package galaxy-tool-codemod pytest galaxy-tool-codemod/tests/test_repair_help_rst.py
uv run python -m scripts.corpus_check codemod galaxy_tool_codemod.codemods.repair_help_rst:RepairHelpRst
```

## 38. `ConvertHelpToMarkdown` (GTR092) — opt-in RST → Markdown `<help>` conversion

**Date:** 2026-06-10

The first **opt-in-command-only** codemod: `rulesets=∅` like the upgrade-only
codemods (so it is never selectable and never part of `format`), but applied by
the dedicated `convert-help` CLI command (cli D12) rather than `upgrade` — the
conversion is **behaviour-changing by construction** (it swaps Galaxy's rendering
engine from server-side docutils to client-side markdown-it; tier-1 xml §24), so
it can never ride a "safe" pipeline. Three gates make the opt-in sound:

- **Profile gate** — `<help format="…">` is XSD-valid only at **profile ≥ 24.2**
  (`_HELP_FORMAT_PROFILE`, pinned by a test that validates a converted tool at
  24.2 and confirms the same shape invalid at 24.1). A tool below the gate (or at
  the 16.01 default — 60.9 % of the corpus) is skipped with "run `upgrade`
  first"; 91.7 % of corpus tools reach the latest profile post-upgrade
  (`docs/upgrade_profile_shift_stats.md`).
- **Render-equivalence gate** — tier-1 `convert_help_rst`: whitelist conversion +
  semantic-skeleton equality, with invalid RST first passed through the GTR089.1
  surgical repair (both halves independently gated).
- **Dependency gate** — no `galaxy-tool-xml[markdown]` extra → no-op, never a
  blind conversion.

`conversion_skip_reason(module)` is the **single decision path**: `apply` runs it
and the `convert-help` surface reports it, so the user-facing skip note can never
disagree with the codemod. CDATA wrapping is preserved (`is_cdata_wrapped` →
`Cursor.set_text`); the `format="markdown"` attribute makes the codemod naturally
idempotent (a converted help is skipped as "already declares a format").

In `coded_codemods()` (the GTR catalog) but **not** `canonical_codemods()` and
**not** `AUTO_UPGRADE_CODEMODS`. The parity table renders its tier as `codemod`
with ruleset `—` (registry's `_OPT_IN_COMMAND_CODES` exception).

**Corpus** (`docs/corpus_rule_stats.md`): 8,607 eligible → **796 modified** (the
convertible ∩ already-at-profile-≥24.2 population — the rest skip on the profile
gate or the equivalence gate; 777 before the GFM table/line-block extension,
xml §24), **0 non-idempotent, 0 post-validation failures, 0 crashes** — every
conversion the gate admits is XSD-valid and stable.

### Reproduced by

```sh
uv run --package galaxy-tool-codemod pytest galaxy-tool-codemod/tests/test_convert_help_markdown.py
uv run python -m scripts.corpus_check rules   # GTR092 isolation row (needs the corpus)
```

## 39. GTR016 widened: any non-empty interpreter (the verbatim-composition proof)

**Date:** 2026-06-10. Item 1 of `../../docs/deferred_fix_opportunities.md` (the
corpus-incidence deferral ledger; maintainer-approved ranking). Reproduced-by:
`uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_interpreter.py
galaxy-tool-codemod/tests/test_fix_interpreter.py`; sizing
`uv run python -m scripts.measure interpreter-bucket-split`; validation
`uv run python -m scripts.corpus_check codemod
galaxy_tool_codemod.codemods.fix_interpreter:FixInterpreter`.

- **The conservatism removed.** §27's GTR016 required a *single-token standard*
  interpreter (`_STANDARD_INTERPRETERS`), leaving flag-bearing
  (`Rscript --no-save`), non-script (`java -jar`, `docker`), and compound
  (`export …; java -jar`) values to the §23 warning as "bucket C". That gate was
  never a soundness requirement — only nobody had proven it.
- **The proof (Galaxy source archaeology).** Galaxy interpolates the interpreter
  attribute **verbatim** in every composition form it ever shipped: the prepend
  form (`command_line = interpreter + " " + command_line` after an unquoted
  abspath replace) is byte-identical `release_16.04`
  (`evaluation.py:478-484`) through `release_20.01`; `release_20.09` switched to
  the token-splice form
  (`replace(executable, f"{interpreter} {shlex.quote(abs_executable)}", 1)`),
  alive in `dev:781-787` today (still honored for `legacy_defaults` tools). The
  forms are equivalent whenever the script is the rendered line's first content
  token — exactly the bucket-A literal-leading-token gate, which therefore
  becomes the **sole** static requirement. Every form gates on
  `if interpreter:`, so an empty `interpreter=""` was always ignored — the
  predicate bails on it (nothing to reproduce; the §23 warning still covers it).
- **The change.** `_interpreter.interpreter_rewrite` accepts any non-empty
  interpreter (`_STANDARD_INTERPRETERS` deleted); the rewrite body
  (`{interpreter} '$__tool_directory__/{token}'`) was already verbatim-faithful
  and is untouched. Bucket taxonomy: C dissolves — literal-leading-token tools
  join A, Cheetah-leading join B; `empty` is a new degenerate bucket (0 corpus
  tools). The measure + its fixture test + the stats page mirror the predicate,
  by construction as before.
- **Corpus.** Bucket A 1,383 → **1,407** (+ A-missing 27 → 28): the dissolved C
  (51) split 25 → A/A-missing, 26 → B (293). Codemod sweep: 8,607 eligible →
  **1,144 modified** (1,127 before; +17 crossing-gated), **0 non-idempotent, 0
  post-validate-failed, 0 crashed**. Behaviour-block walk: the
  `16_04_fix_interpreter` first-blocker residual drops **316 → 299**
  (`docs/upgrade_behavior_block_stats.md`) — each rescued tool's entire
  profile-upgrade chain unblocks.
- **Why this is the principle, not scope creep.** Per
  `docs/deferred_fix_opportunities.md`: corpus incidence sizes impact, never
  soundness. The widening is provable for *novel* tools regardless of the 25
  corpus instances; the proof, not the count, is the admission ticket.

## 40. GTR015 widened: the nested sole data input is addressable (qualified format_source)

**Date:** 2026-06-10. Item 2 of `../../docs/deferred_fix_opportunities.md`.
Reproduced-by: `uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_fix_output_format_input.py`; sizing
`uv run python -m scripts.measure output-format-input`; validation
`uv run python -m scripts.corpus_check codemod
galaxy_tool_codemod.codemods.fix_output_format_input:FixOutputFormatInput`.

- **The conservatism removed.** §24's GTR015 required the sole data input to be
  a *direct child* of `<inputs>` "so an unqualified `format_source` reference
  resolves" — leaving a sole *nested* input to the §23 warning on the belief
  that it wasn't addressable.
- **The proof (Galaxy source).** `determine_output_format` resolves
  `format_source` against `input_datasets`, which Galaxy keys by the **prefixed
  (qualified) name** (`actions/__init__.py` — `input_datasets[prefixed_name]`;
  prefixed keying present back to `release_16.04`'s `prefix + input.name`). The
  prefix grammar (`visit_input_values`): a `<conditional>` or `<section>`
  ancestor contributes `name|`, a `<when>` contributes nothing, a `<repeat>`
  contributes an **instance-indexed** `name_N|`. Qualified `format_source` is an
  upstream-*tested* feature: `test/functional/tools/format_source_in_conditional.xml`
  ships `format_source="cond|input1"` — and its second branch deliberately
  exercises the **absent-key fallthrough**, which is also behaviour-matched: with
  the input absent at runtime (unselected branch / empty optional), pre-16.04
  `format="input"` resolved to `"data"` (no datasets walked), and a missing
  `format_source` key falls through to the parsed output-format default — also
  `"data"` (`xml.py` `get("format", "data")`).
- **The change.** `_sole_top_level_data_input_name` →
  `_sole_data_input_qualified_name`: walk the sole `<param type="data">`'s
  ancestors to `<inputs>`, joining named `<conditional>`/`<section>` segments
  with `|` (a top-level input degenerates to its bare name). Bail on a
  `<repeat>` ancestor (instance-indexed prefix — no static address), an unnamed
  grouping, or anything unrecognised. The `output-format-input` measure now
  imports the resolver (agreement by construction, the GTR016 pattern) and
  splits the old "1 nested (needs qualified ref)" bucket into "1 nested,
  addressable (auto-fixable)" vs "1 under repeat / unnamed (needs author
  intent)".
- **What stays out, and why it is construction-not-corpus:** zero data inputs
  (nothing to inherit), two-or-more (pre-16.04 `format="input"` resolved to the
  *last* form input's ext under Galaxy's own `TODO`-marked nondeterminism — no
  deterministic behaviour exists to preserve), repeat-nested (no static
  address), and outputs already carrying `format_source` (§24's guard).
- **Corpus.** The widening rescues **0 corpus tools**: the corpus's single
  nested-single tool turns out to be **repeat-nested** (the
  `output-format-input` measure's "1 under repeat / unnamed" bucket; the
  "addressable" bucket is 0), so it is *correctly still bailed*, and the
  codemod sweep is unchanged at **79 modified, 0 non-idempotent, 0
  post-validate-failed, 0 crashed**. Pure novel-tool insurance in the GTR036
  spirit ("not gated on corpus frequency") — shipped for the proof, not the
  count.

## 41. `Upgrade21_09` (GTR093) — collection_type whitespace: the one-tool decline reversed

**Date:** 2026-06-10. Item 3 of `../../docs/deferred_fix_opportunities.md`
(reversing `PLAN.md`'s "Considered and declined — collection-type whitespace
normalization", which declined a provably-safe fix on **one-tool corpus
incidence**). Reproduced-by: `uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_upgrade_21_09.py`; sizing
`uv run python -m scripts.measure collection-type-normalization`.

- **The boundary.** 22.01's XSD types `collection_type` for the first time:
  `<param collection_type>` → `CollectionTypeList`
  (`(list|paired)([:,](list|paired))*`, whitespace-rejecting); the single-value
  sites (output `<collection type>`, `<output collection_type>`, test
  `<output_collection type>`) → `CollectionType`. 21.09 had free `xs:string`.
- **The proof (the part the decline never asked for).** Galaxy's runtime strips
  each comma token itself — `DataCollectionToolParameter.__init__`:
  `[t.strip() for t in collection_types.split(",")]`, unconditional — so
  comma-adjacent whitespace is runtime-insignificant and stripping it is a
  behaviour no-op that gains 22.01 validity. The same line proves two edges:
  `collection_type=""` is **dropped** (`if collection_types:` falsy — identical
  to absent), while a whitespace-only value is **left** (it strips to a
  matches-nothing restriction; lifting it would change behaviour).
- **What stays out, and why it is construction-not-corpus:** colon-inner
  whitespace (`type_description.py` splits `:` raw — runtime-significant), the
  single-value `CollectionType` sites (no runtime strip exists), and case
  (`List` — runtime comparisons exact). All left stuck + reported.
- **Corpus.** Exactly **1** tool (`qiime2_core__tools__import_fastq`,
  `"list, list:paired"`) — and even it is invisible to the codemod *sweep*
  (declares 22.05 but validates only to 21.09, so the sweep's
  `corpus_test_profile_for` anchor drops it; a harness-policy artifact, not a
  codemod gate — `UpgradeToLatest` itself reaches it fine via
  `UPGRADE_CODEMODS["21.09"]`). Shipped under the novel-tool soundness
  principle: the proof, not the count, is the admission ticket.

## 42. `Upgrade21_09` grows the proven 22.01 repairs: stdio (G1+G3+G5) + has_size Bytes (G2)

**Date:** 2026-06-10. The first two items of the approved G-series
(`../../docs/deferred_fix_opportunities.md`, "Profile-step gap audit").
Reproduced-by: `uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_upgrade_21_09.py`.

- **stdio (G1, with G3+G5 folded in by the source reads).** Galaxy's stdio
  parser (`lib/galaxy/tool_util/parser/xml.py`) proves three behaviour-no-op
  repairs for the 22.01 `use="required"` tightenings: `range` falls back to the
  `value` attribute (`:1248-1250` — runtime aliases ⇒ rename `value=`→`range=`;
  a `value` alongside `range` is never read ⇒ dropped); an `<exit_code>` with
  neither attribute, or whose range strips to empty (the parser does
  `re.sub(r"\s", "", …)` then hits the singular `int("")` path), is logged and
  skipped ⇒ the dead element is deleted; a `<regex>` without `match=`
  (`:1318-1324`) is likewise logged and skipped ⇒ deleted. `RangeType`'s only
  consumer is `ExitCode.range`, so the 22.01 pattern change reduces entirely to
  the empty form — G5 needed no work of its own.
- **has_size Bytes (G2, proof corrected during the read).** The runtime parser
  is `galaxy.util.bytesize.parse_bytesize` — *not* `size_to_bytes` — so the
  provable class is exactly: whitespace forms (`int()` tolerates them),
  wrong-case suffixes (`100MI` ≡ `100Mi` after `upper()`), and integral
  float/scientific forms (`129e6` ≡ `129000000`). Plain-`B`/word-suffix forms
  (`"2 TB"`, `"10 bytes"`) are **not** in the suffix table — they were never
  runtime-working, so they are left (nothing to preserve). Canonical form:
  the case/whitespace fix when it round-trips, else the exact integer byte
  count; non-integral parses are left. The suffix-grammar mirror lives in this
  codemod (`galaxy.util` stays confined to tier-1 `macros.py`), pinned by tests.
- **Corpus.** 0 tools for every one of these shapes (greps over 1,795
  `<exit_code>` elements and all `has_size` values) — like §40, shipped purely
  as novel-tool insurance under the ledger's principle.

## 43. `TokenizeVersion` (GTR094) — opt-in @TOOL_VERSION@ extraction, proof by execution

**Date:** 2026-06-10. Ledger item A2 (rank 5 of the approved G/ledger ranking,
`../../docs/deferred_fix_opportunities.md`); sized by `scripts.measure
version-tokenization` (75 clean candidates, PR #31). Reproduced-by: `uv run
--package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_tokenize_version.py`.

- **The transform.** `version="<base>+galaxy<suffix>"` (base == a package
  `<requirement>` version) → `@TOOL_VERSION@+galaxy@VERSION_SUFFIX@`; matching
  requirement versions → `@TOOL_VERSION@`; the two `<token>`s defined in the
  inline `<macros>` (created at the first child position when absent).
- **Proof by execution.** The mutation runs on a deep copy first and is kept
  only when `expand_from_tree` over the tokenized copy reproduces the original
  expansion **byte-for-byte** (both `<macros>` blocks dropped — Galaxy clears
  them after harvesting). The tokens substitute back to exactly the literals
  they replaced, so the post-expansion tool is unchanged by construction. A
  gate failure leaves the tree untouched and the surface reports it.
- **Fail-closed preconditions** (`tokenization_skip_reason`, the shared
  decision path): non-matching/already-tokenized versions; no requirement
  pinning the base; `@TOOL_VERSION@`/`@VERSION_SUFFIX@` already defined; macro
  `<import>`s on a bytes-parsed tool (the gate could not resolve them — the
  CLI passes paths so imports resolve in practice).
- **Classification.** The second **opt-in-command-only** codemod (the GTR092
  class): no ruleset, `OPT_IN_COMMAND_BY_CODE["GTR094"] = "tokenize-version"`,
  never `format`/`upgrade` (a multi-element style restructure). MCP tool =
  follow-up, per the GTR092 precedent (mcp D2 arrived one PR later).
- **Serializer-allowlist note.** The gate's internal `etree.tostring` compares
  two throwaway expansions (proof, not output) — allowlisted with that
  justification; output still flows through fmt via the facade.

## 44. `SingleQuoteCommandVars` (GTR020.1) — boolean scope narrowing (soundness fix)

**Date:** 2026-06-11. Reproduced-by: `uv run --package galaxy-tool-source pytest
galaxy-tool-source/tests/test_command_vars.py::test_boolean_is_safe_only_when_both_values_are_single_tokens`
and `uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_single_quote_command_vars.py::test_does_not_quote_flag_idiom_booleans`.
Sizing: `uv run python -m scripts.measure iuc011-fixability`.

- **The bug.** `command_vars.SAFE_SINGLE_TYPES` listed `boolean` alongside the
  intrinsically single-token types (`integer` / `float` / `data` …), so
  `input_param_info` classified **every** boolean `"safe"` *by type alone*, and
  GTR020.1 single-quoted any bare `$bool` in `<command>`. That is unsound: a
  boolean renders to its author-written `truevalue` / `falsevalue`, and the
  dominant Galaxy idiom `truevalue="--flag" falsevalue=""` (emit a flag when true,
  *nothing* when false) breaks under quoting — the false case `'$bool'` renders to
  `''`, a **stray empty argument** instead of nothing, and a space-bearing
  `truevalue=" -C"` becomes a literal leading-space token `' -C'` rather than
  word-splitting to `-C`. Either changes the command Galaxy runs.
- **How it surfaced.** Running `format` on `iuc/featurecounts` (an RNA-seq tool)
  during an experimental upstream-PR pass: six of its booleans
  (`ignore_dup` / `long_reads` / `by_read_group` / `largest_overlap` /
  `only_both_ends` / `exclude_chimerics`, all `falsevalue=""`) were being quoted.
  XSD validity + idempotence both held, so the corpus oracles missed it — the same
  blind spot as the multi-flag `select` case (§32).
- **The fix (mirrors §32).** Drop `boolean` from `SAFE_SINGLE_TYPES` and inspect its
  values: `_boolean_values_are_single_tokens` admits a boolean as `"safe"` only when
  **both** effective `truevalue` and `falsevalue` (Galaxy defaults `"true"` /
  `"false"`, verified in `galaxy.tool_util.parser.util.boolean_true_and_false_values`)
  are non-empty single shell tokens (the existing `_NOT_SINGLE_TOKEN` charset gate).
  The `falsevalue=""` flag idiom and any whitespace/metachar value fall to `"text"`
  (non-provable), where the advisory `GTR020.2` keeps flagging them; genuine
  single-token booleans (`true`/`false`, `yes`/`no`) stay auto-quoted.
- **Sizing impact.** The provable subset `{safe, attr_safe, builtin_path}` drops from
  ~49.5% (§30) to **44.6%** of occurrences (`safe` 41.5% + `attr_safe` 0.6% +
  `builtin_path` 2.4%) — the difference is the flag-idiom booleans correctly leaving
  the provable set. Corpus `check`/`rules` stat pages refresh on the next scheduled
  sweep (numbers, not coverage). The behaviour-preservation ledger records this as the
  second GTR020.1 over-quote class fixed (after the §32 multi-flag select).

## 45. The behavior gate: `upgrade` stops at the behaviour ceiling by default

**Date:** 2026-06-12. Reproduced-by: `uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_behavior_gate.py` (the gate primitives),
`galaxy-tool-codemod/tests/test_upgrades.py` (the capped walk), and the facade
gate tests in `galaxy-tool-refactor-registry/tests/test_facade.py`. Corpus:
`uv run python -m scripts.measure upgrade-behavior-blocks` (the stats page is
computed with the shipped gate functions) and
`uv run python -m scripts.corpus_check upgrade` (the per-tool contract sweep).

- **The flip.** §22 established that the walk is validity-gated and therefore
  structurally sound only; §23 added the per-tool warning. The default now
  *stops* instead of warning-and-proceeding: `behavior_gate.py` computes the
  applicable, non-auto-fixed `must_fix` codes over `(baseline, latest]`
  (`blocking_codes`) and the **ceiling**, the newest vendored profile strictly
  below the lowest blocker (`behavior_ceiling`). The walk, `UpdateProfile`,
  and tier-1 `newest_valid_profile` all accept a keyword-only `ceiling` and
  never declare past it. The maintainer's framing: stop when we can no longer
  guarantee the same behavior. The full soundness argument lives in
  `docs/proofs/behavior-gate.md` (guarded by `test_proof_documents.py`).
- **The gate is precomputable, so it lives outside the loop.** Every catalogue
  code is keyed to a fixed profile boundary and applicability is a property of
  the pre-upgrade tree, so the ceiling is decided once before the walk; no
  per-step re-evaluation. This is also exactly how the
  `upgrade-behavior-blocks` measure already modelled the policy, which is why
  the measure now consumes `blocking_codes` directly (one implementation, no
  drift).
- **"Auto-fixable" means proof by execution, never a static set.** A blocker is
  cleared only when its mapped `RuntimeGatedFix` (each declares the Galaxy
  `upgrade_code` it clears, pinned to the catalogue by test), applied to a
  throwaway copy, leaves the code's detector quiet on the macro-expanded view
  (`code_cleared_by_autofix`). Partial fix coverage (GTR015's sole-data-input
  subset, GTR016's bucket A) and macro-supplied constructs are thereby exact.
  The facade re-verifies on the live tree and credits `auto_fixed_codes` only
  when post-apply re-detection shows the code gone.
- **Policy: `must_fix` blocks; `consider` warns.** Galaxy emits
  `16_04_consider_implicit_extra_file_collection` unconditionally, so blocking
  on consider-level codes would freeze nearly every sub-16.04 tool at its
  baseline (see `docs/upgrade_behavior_block_stats.md`, which reports the
  counterfactual side by side). `blocking_codes(levels=...)` is the seam for a
  future stricter mode once the noisy consider detectors are tightened
  (follow-up); no `--block-on` knob is exposed today.
- **Fail-closed branches.** An unresolvable `@PROFILE@` baseline cannot range
  the crossings, so the profile does not move (`resolved_baseline` first tries
  the token's definitions, inline then imported, so most tokens place
  normally). No vendored profile below the lowest blocker (a 16.04 blocker on
  a legacy-default baseline; the oldest vendored XSD is 16.10) means no
  advance at all. The gate never lowers a declared profile.
- **§23 verdict change (the deferred credit).** `behavior_preserving` now
  credits auto-fixed codes: the warning and the verdict derive from one
  applicable set minus the credited fixes, so a tool whose only applicable
  must_fix crossing was provably fixed is reported behavior-preserving (and
  gets a "fixed automatically" note naming the GTR code) instead of a
  misleading must-fix warning. The un-credited §23 primitive
  `upgrade_is_behavior_preserving` had no remaining production consumer and
  was removed; `crossed_and_applicable_codes` stays the single source the
  facade derives both the warning and the verdict from.
- **Escape hatches, both explicit.** `allow_behavior_change` restores the
  historical walk-to-latest (blockers still reported as the user's review
  list); `target_profile` caps the walk at an explicit vendored profile
  (`UnknownProfile` otherwise) and composes with the gate (the lower wins).
  Stop reports name the blocking codes and point at
  `docs/profile_boundaries.md`, the generated per-boundary "what changed and
  what to do" reference (`scripts/gen_profile_boundaries.py`,
  freshness-tested).
- **`UpgradeToLatest`'s own default is unchanged** (walk to latest): tier 2
  stays consumable standalone and the structural corpus oracle
  (`corpus_check codemod galaxy_tool_codemod.upgrades:UpgradeToLatest`) keeps
  testing §22's contract; the default flip is facade policy. A stall at a
  requested ceiling is deliberate and is not a `missing_upgrade`.
- **The per-tool contract is swept.** `corpus_check upgrade` runs the gated
  default over every corpus tool and asserts: fail-closed honoured, the
  declaration never crosses the first blocker, no applicable `must_fix` code
  crossed un-fixed (recomputed independently of the facade), validity
  preserved, and a second run is a byte no-op, retaining every violation as a
  regression fixture (`docs/corpus_data/upgrade_gate_errors.json`).

## 46. The 24.2 truth measure: the dominant blocker is a 3x over-count

**Date:** 2026-06-12. Reproduced-by: `uv run python -m scripts.measure
test-case-validation-truth` (full numbers in
`docs/upgrade_research/24_2_fix_test_case_validation.md`); pinned by the
synthetic-fixture tests in `galaxy-tool-source/tests/test_measure.py`.

- **The question.** §45's gate stops 6,033 tools at 24.1 because
  `24_2_fix_test_case_validation`'s detector is a ships-a-`<test>` necessary
  condition (we do not vendor Galaxy's pydantic parameter models). How many of
  those tools' tests would *actually* fail Galaxy's strict 24.2 validation?
- **The oracle.** `galaxy-tool-util` joined the **dev** dependency group (the
  `markdown-it-py` precedent: measure-only, never a tier dependency; shipping
  it is PR 3's separate `[galaxy]`-extra decision). The measure calls
  `validate_test_cases_for_tool_source(tool_source, use_latest_profile=True)`,
  byte-for-byte the call `ProfileMigration24_2.advise` makes, so the numbers
  are Galaxy's own verdicts, not a reimplementation.
- **The answer.** Of 6,648 test-shipping tools: **4,517 (67.9%) validate
  cleanly** and would not block; **1,972 (29.7%) are true blockers**; 159
  (2.4%) crash Galaxy's own test parser/model (every one retained to
  `docs/corpus_data/test_case_validation_errors.json`, standing
  retain-failures rule). The error-kind histogram (type-or-value-mismatch
  2,380 cases; unknown-parameter 2,159; extra-input-forbidden 52; other 43)
  sizes PR 3's tightening payoff and PR 4's mechanical
  name-qualification candidate.
- **Consequence.** Tightening the 24.2 detector to the real validator (PR 3)
  would let roughly two thirds of the gate's currently-stopped tools advance
  past 24.2; construction soundness still governs (the fallback static checker
  must suppress only provably-clean tools, with this measure as its validation
  oracle, never its definition of correctness).

## 47. Our own 24.2 test-case checker tightens the detector (the Galaxy advantage)

**Date:** 2026-06-12. Reproduced-by: `uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_test_case_check.py` (rules + in-CI parity against
Galaxy's real validator) and `uv run python -m scripts.measure
test-case-validation-truth` (the corpus parity oracle). Background: §46 measured
the 24.2 blocker as a ~3x over-count; this is the shipped tightening that
recovers it.

- **The advantage (documented in `docs/galaxy_reimplementations.md` touchpoint
  3).** Galaxy's strict 24.2 validation re-parses the tool, builds a
  parameter-model tree, and **generates a pydantic class per tool** (~200ms).
  The decision needs only structural facts the toolchain already holds on its
  resident, macro-expanded lxml tree, so
  `test_case_check.all_test_cases_provably_clean` answers it as a direct
  query in milliseconds with no new dependency. `_detects_test_case_validation`
  now fires only when a tool ships a `<test>` **and** its tests are not provably
  clean, replacing the bare ships-a-`<test>` necessary condition.
- **One-directional by construction (the §28 rule).** The checker returns
  `True` (suppress the blocker, let the tool past 24.2) only when every test
  input is provably valid under rules justified from Galaxy's model code
  (per-type `py_type` + `requires_value` for the `test_case_xml`
  representation, `legacy_from_string` coercions at >= 24.2, the strict
  `Literal` membership for static selects, the `extra="forbid"` unknown-input
  rule, and the test parser's nothing-to-check `<output>` raise). Every
  construct it cannot model (repeats, collections, drill-downs, `<validator>`,
  un-expanded macros, novel types) returns `False` and stays blocked, so it is
  never wider than Galaxy.
- **Parity is a standing oracle, not a claim.** `scripts.measure
  test-case-validation-truth` now runs the checker beside Galaxy's real
  validator over every test-shipping corpus tool. The hard gate is
  `n_unsound == 0` where unsound = ours-clean AND Galaxy returns an invalid
  **verdict**. A Galaxy validator *raise* is not a verdict (its advisor has no
  try/except around the call, so a raise is Galaxy failing to advise, not
  flagging 24_2); those go to a separate `n_clean_galaxy_raised` bucket, and
  the tools behind them are handled upstream in the shipped pipeline (malformed
  XML never loads through tier-1; a tool whose macros do not expand validates
  at no profile, so the walk would not move it). The in-CI fixture parity test
  pins the same agreement without the corpus.
- **Payoff.** Of the 6,648 test-shipping corpus tools, the checker soundly
  suppresses the 24.2 blocker for the provably-clean subset (regenerated in
  `docs/upgrade_behavior_block_stats.md`); the residual `headroom` (tools
  Galaxy validates clean but the checker cannot yet prove) is reported by the
  measure as the target for any future widening, always behind the same
  zero-unsound gate.

## 48. GTR096 FixTestParamQualification: the first 24.2 auto-fix

**Date:** 2026-06-12. Reproduced-by: `uv run --package galaxy-tool-codemod pytest
galaxy-tool-codemod/tests/test_fix_test_param_qualification.py` (the codemod) and
`uv run python -m scripts.measure test-param-qualification` (the sizing + the
fix's corpus soundness proof). Follows §47 (the 24.2 detector tightening).

- **The opportunity.** §46's truth measure showed `unknown-parameter` is the
  largest 24.2 validation-error class (2,159 cases). Resolving each bad name
  against the input tree splits them: a flat test name whose leaf matches
  exactly one *nested* input parameter is the migration Galaxy prescribes
  (fully-qualify it `parent|...|child`); a name matching no input (a typo, a
  removed parameter, or a Galaxy built-in like `chromInfo`), a top-level input
  (already correct), or more than one (ambiguous) is not safely fixable.
- **The fix.** `FixTestParamQualification` (a runtime-gated fix, `upgrade_code`
  `24_2_fix_test_case_validation`, `introduced_profile` 24.2) rewrites only the
  unique-leaf nested case, via the shared
  `test_param_qualify.plan_test_param_qualifications`. It is the **first**
  auto-fix for the 24.2 code, so it slots into the gate's 1:1
  `auto_fixes_by_code()` mapping cleanly: the gate now probes 24.2 by applying
  it and re-detecting (`test_case_check`), crediting the code for the tools
  qualification clears.
- **Behaviour-preserving by construction.** It edits only `<tests>`, never a
  tool runtime element, and the unique-leaf precondition means the unqualified
  name already referred to exactly that one parameter. The crossing gate means
  a tool the fix does not fully clear is left blocked and its tests are not
  edited at all. Proof: `docs/proofs/GTR096.md`.
- **Sound at corpus scale, by execution.** `scripts.measure
  test-param-qualification` applies the fix to every checker-blocked tool and
  validates the **qualified** tree with Galaxy's real validator; the contract is
  zero unsound fixes (we unblock but Galaxy still rejects). It unblocks 159
  tools the 24.2 checker otherwise stops; the behavior gate's reaches-latest
  count rises accordingly (`docs/upgrade_behavior_block_stats.md`), and the
  gated `corpus_check upgrade` contract sweep stays at 0 violations.
