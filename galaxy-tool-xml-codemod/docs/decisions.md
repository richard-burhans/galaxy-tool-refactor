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
  latest. First full combined sweep (8 648 eligible): 8 575 reached latest,
  `Upgrade24_1` advanced 94; residual sticking points 24.1 (56), 19.01 (9),
  25.1 (5), 21.05/21.09/24.0 (1 each); 0 non-idempotent / crashed.
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
  galaxy_tool_xml_codemod.upgrades:UpgradeToLatest --limit 300` → 297 reached
  latest, 3 stuck at 25.1 (next codemod to write); 0 non-idempotent /
  post-validate-failed / crashed.
