# Decisions — galaxy-tool-refactor-registry

Each entry records a decision once it lands: a date, the decision, and the
rationale. Mirrors the conventions of the sibling packages' `docs/decisions.md`.

## D1 (2026-05-30) — A tier-3.6 rule-registry facade with presets + per-rule selection

### Decision

A new package, `galaxy-tool-refactor-registry`, exposes a unified,
code-addressable view over the three rule families (codemod GTR, fmt GTR,
advisory), named presets (`cosmetic` / `iuc` / `strict`, default `iuc`),
per-rule `--select`/`--ignore`, and a **library-first** `run`/`upgrade`/`detect`
API. The `galaxy-tool-refactor` CLI is rewired to consume it; a future MCP server
(`galaxy-tool-refactor-mcp`) will too.

### Rationale

- **Where it sits.** It depends on tiers 0.5/1/2/3/3.5; the lower tiers do not
  depend on it (tier independence preserved, rules-0.5 stays dependency-free). It
  is the single orchestration layer below the app — the CLI and the MCP server
  are thin, equivalent consumers, so they cannot drift.
- **Library-first, not in the app.** An MCP server importing a `click` CLI app is
  the wrong shape. Keeping the orchestration in a non-CLI library (structured
  in/out, no `sys.exit`, writes only on request, introspectable) lets both
  front-ends wrap one core. See `../../galaxy-tool-refactor-mcp/docs/vision.md`.
- **fmt stays the only serializer.** All XML bytes come from
  `format_tool_document_subset` / fmt's `to_bytes`; the facade never serialises
  XML, so the long-standing "only fmt writes XML" invariant holds.

## D2 (2026-05-30) — `RuleHandle`: one uniform adapter over three rule shapes

### Decision

A frozen `RuleHandle` (`handle.py`) carries `meta`, `family`
(`codemod`/`fmt`/`check`), `fixable`, `detect(document) -> list[Violation]`, and
`apply(document) -> None | None`. Family adapters (`adapters.py`) wrap each
native shape: a codemod's `detect`/`apply` run via a `Module` (its coarse
`detect` for validation-driven codemods needs no special-casing); an fmt rule
uses the per-rule subset seams (`format_tool_document_subset` /
`detect_tool_document_subset`, fmt D15); an advisory check yields `Violation`s
and has `apply=None`.

### Rationale

The three families have genuinely different mechanics (Change/thunk vs.
Edit-on-tree vs. report-only). A single thin handle lets the registry, presets,
and facade treat every rule the same and address it by `RuleMeta.code` — which is
also the unit a future MCP tool or a plugin loader enumerates. The GTR code
namespace is collision-free (fmt 001/003/004; canonical codemods
002/005/006/013/017/018/019; upgrade codemods 007–012; runtime-gated fixes 014–016;
checks GTR021–GTR033); `registry._index` asserts it so a
future code clash fails loudly rather than silently shadowing.

## D3 (2026-05-30) — Presets, default `iuc`, and selectable vs. upgrade-only

### Decision

Three presets, derived from the family registries (single source of truth, no
hardcoded code lists that can drift):

- `cosmetic` = fmt cosmetic rules (GTR001/003/004).
- `iuc` = `CANONICAL_CODEMODS` (GTR006/017/002/005/013) + cosmetic — **the
  default**. Byte-identical to the previous `format` pipeline on already-valid
  tools (pinned by a regression test); GTR017 (`NormalizeBooleanValues`), like
  GTR006 (`FixTypos`), is a no-op unless the tool validates nowhere.
- `strict` = `iuc` + every advisory check (report-only).

The selectable set (`registry()`, what `--select`/`--ignore` accept) is exactly
canonical codemods + cosmetic fmt + advisory checks. The upgrade-only codemods —
GTR007–GTR012 (internal to `UpgradeToLatest`'s loop) and the runtime-gated
GTR014–GTR016 (applied by `upgrade`) — are **not** selectable; they surface only
via `list_rules(include_upgrade=True)`.

### Rationale

`strict` includes the *whole* advisory family rather than freezing at GTR021–GTR030,
so when the reserved GTR031/GTR032 stubs gain real logic they are automatically
covered; today they fire nothing, so this is observationally identical. *(Since
superseded exactly as anticipated: GTR031 retired into the GTR020 partition —
check D8 — and GTR032 gained its real detector in check D34; `strict` covered
both automatically, vindicating this rationale.)* Default
`iuc` keeps bare `format` unchanged for existing users. Excluding the upgrade-only
codes from selection avoids exposing internal pipeline steps as if they were
standalone, user-toggleable rules.

## D4 (2026-05-30) — Selection precedence, apply ordering, advisory-as-notes, upgrade

### Decision

- **Precedence (ruff-style): `--ignore` ▸ `--select` ▸ `--preset`.** An explicit
  `--select` *replaces* the preset's set (resets the base), then `--ignore`
  subtracts. Unknown preset/code raise typed `UnknownPreset`/`UnknownRuleCode`
  (the CLI maps them to `click.BadParameter`).
- **Apply ordering reproduces `format`:** selected codemods in
  `CANONICAL_CODEMODS` order, then selected cosmetic fmt rules in `meta.order`;
  serialise once through fmt. Advisory rules never apply.
- **Advisory under an applying command reports, never mutates.** `run` detects the
  advisory rules in the selection on the pre-format tree and returns them as
  `FormatResult.advisory` + rendered `notes`; the formatted bytes are unaffected
  (so `strict` and `iuc` format identically — pinned by a test).
- **`upgrade` has no preset.** Presets (`cosmetic`/`iuc`/`strict`) are
  format/check concepts; the CLI rejects `--preset` on `upgrade`. `upgrade` runs
  `UpgradeToLatest` unconditionally (its purpose) plus the fixable rules from
  `resolve_upgrade_codes` (base = `FixTypos` + cosmetic fmt; `FixTypos` runs
  first as the repair precondition). `--select`/`--ignore` adjust that base — e.g.
  `--ignore GTR006` upgrades without typo repair.

### Rationale

ruff's mental model is familiar and unambiguous, and replace-then-subtract avoids
"is select additive?" guesswork. The apply order is the one `format` already used,
so the default path is a no-op behaviour change. Reporting (not erroring on, not
silently dropping) advisory rules under `format` lets a `strict` preset mean
"format me and tell me everything," without making advisory opinions a hard gate
or a surprise. Keeping `upgrade`'s pipeline fixed (preset-free) avoids pretending
`cosmetic`/`strict` mean something for a profile-migration command.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-registry pytest galaxy-tool-refactor-registry/tests/
# the regression guard: the iuc preset == the old format pipeline, byte for byte
# (tests/test_facade.py::test_iuc_preset_is_byte_identical_to_today_format)
```

## D5 (2026-05-30) — Imported `@PROFILE@` consensus analysis (Phase 3b-1)

**Date:** 2026-05-30. First step of Phase 3b (imported profile-token upgrade).
Reproduced-by: `uv run --package galaxy-tool-refactor-registry pytest
galaxy-tool-refactor-registry/tests/test_macro_profile.py`.

- **What we chose.** `macro_profile.py` — the pure decision core for upgrading a
  `profile="@TOKEN@"` whose token is defined in an *imported* macro file (the
  ~1,382-tool bulk; the inline case is `UpdateProfile`/GTR007). Two pieces kept
  separate so the policy is testable without I/O: `profile_token_site(document)`
  reads one tool and returns the defining macro file + token name + the tool's
  `newest_valid_profile` target (or `None` for a literal/inline/unresolved
  profile); `plan_from_sites(sites)` groups sites by the file they would edit and
  decides, per file, whether the profile-using importers **agree** on one target
  (every importer has a target and they are identical).
- **The locked policy (data-driven).** Edit the imported token in place **only
  when the importers agree**; otherwise report-and-skip. We do **not** build a
  copy-on-write fork: the `macro-profile-ownership` sweep (PR #28) found 0 of 46
  shared profile-macro files whose importers diverge, so an in-place bump always
  satisfied every importer and fork machinery would never resolve a real
  conflict — deferred until divergence has a consumer (defer-until-consumer).
- **No direct-vs-deeper split.** We always edit the file that *defines* the
  token (`TokenDefinition.source`), which is correct whether the token is in a
  directly-imported file or deeper in the chain; the corpus has no deeper cases
  anyway. Shared-file safety is carried entirely by the agreement check.
- **Why the registry.** The analysis spans a *set* of tools (run-relative), which
  is orchestration — it belongs in the facade tier, above the per-tool lower
  tiers and below the CLI. It is library-first and exception-free (per-document,
  no scanning/error-handling): the CLI does the path walk + parse-error handling
  and feeds it `ProfileTokenSite`s.
- **The edit landed alongside (3b-2).** `apply_profile_token_plans(plans, *,
  write)` (same module) consumes the plans: for an agreeing, stale plan it
  rewrites the defining file's `<token>` text and — when `write` — reserialises
  through `format_macro_document` and writes it back (bump-up-only, idempotent);
  a non-agreeing plan is recorded as a skip and never touched. The CLI `upgrade`
  command drives it as a whole-run phase (cli §D6).

## D6 (2026-06-03) — Stat-artifact freshness guard (derived-doc coverage + summary)

**Reproduced by:** `uv run --package galaxy-tool-refactor-registry pytest
galaxy-tool-refactor-registry/tests/test_stat_artifact_coverage.py`.

- **The gap.** The repo regenerates several `docs/*_stats.md` pages from corpus
  sweeps, each owned by a *different* `scripts/corpus_check.py` subcommand
  (`corpus_check_stats.md`←`check`, `corpus_rule_stats.md`←`rules`,
  `corpus_format_stats.md`←`fmt`). Nothing *forced* the regen, so pages drifted:
  GTR014–GTR017 silently lagged out of the rule + format pages for **four PRs**
  (both stuck at the GTR013 sweep) until the GTR018/GTR019 PR caught them up.
- **What we chose (Phase 1).** A coverage guard mirroring
  `test_serializer_allowlist.py`: a test-local `STAT_ARTIFACTS` manifest maps each
  page → its regen command → the code-set it must list, with the code-set derived
  **live from the same rule registries the generator iterates**
  (`all_rules()`/`coded_codemods()`/`CANONICAL_CODEMODS`/`all_checks()`) so the
  expectation can't drift from the generator. The test reads each committed page
  and fails — naming the page and the exact regen command — if a covered code is
  absent. It is **corpus-free + deterministic**, so it runs in CI / `qa_gate.sh`
  and trips at the PR that adds the rule, not four PRs later.
- **Coverage, not numbers.** It guards that no rule is *silently absent*; it does
  **not** verify the corpus-measured counts (those need the corpus, unavailable in
  CI). The per-page code-sets match the generators exactly: check =
  fmt ∪ canonical-codemod ∪ advisory-IUC; rule/format = fmt ∪ *all* coded codemods
  (incl. the upgrade-only GTR007–GTR012 the glossary lists).
- **Home — registry/tests, not `scripts/`.** The guard needs every rule family's
  registry; the registry tier already imports all of them. It cannot live in a
  `scripts/`-importing test because the registry package has its own
  `[tool.pytest.ini_options]`, so the root `pythonpath = ["."]` (which makes
  `scripts` importable elsewhere) does not apply to its test run.
- **Phase 2 (shipped) — summary currency.** The manifest now carries each covered
  rule's `(code, summary)`, and `test_every_covered_summary_is_current` asserts the
  rule's *current* summary appears in the page — so **rewording** a rule's summary
  (not just adding a code) forces a regen. The page renders summaries through one
  backtick transform (`<token>` → `` `<token>` ``, `reference._backtick_xml_tokens`,
  duplicated as the check tier's `_check_md_summary` — verified identical for all 32
  rules); the guard mirrors that one-line regex locally so it stays a pure
  test-tier addition (no sweep/library change — the user picked the lean
  render-and-check over a header fingerprint). Still corpus-free + CI-run.
- **Phase 3 (deferred).** A watched-input *fingerprint* (rule set + **measure
  source** + **corpus snapshot**) embedded in each page header, so a changed
  *measure* or corpus — not just rule metadata — forces a whole-page recompute.
  Deferred because CI has no corpus (so the corpus dimension is only locally
  checkable) and per-function source hashing is fragile / over-invalidating; the
  in-tree dimension that CI *can* enforce is now covered by Phases 1–2.

## D7 (2026-06-03) — Research-note citation guard (the prose-side companion)

**Reproduced by:** `uv run --package galaxy-tool-refactor-registry pytest
galaxy-tool-refactor-registry/tests/test_research_note_citations.py`.

- **The gap D6 left open.** D6 guards the *generated* `docs/*_stats.md` pages, but
  the hand-written per-code notes under `docs/upgrade_research/` *quote* numbers
  **from** those pages (first-blocker / stuck counts from
  `upgrade_behavior_block_stats.md`; A / A+A-missing bucket counts from
  `interpreter_bucket_stats.md`). When an artifact was re-walked (post-GTR016 + the
  `20_09_consider_set_e` tightening) the counts shifted and **five notes silently
  kept the old numbers** (`16_04_fix_output_format` 18→33,
  `16_04_consider_implicit_extra_file_collection` ~3,971→5,381,
  `23_0_consider_optional_text` ~311→318, `24_2_fix_test_case_validation`
  4,498→4,956, `16_04_fix_interpreter` header citing the artifact for 1,726 while it
  read 316) — caught only by a manual accuracy pass (PR #79).
- **What we chose.** A sibling guard in the same arch-test shape: a `NOTE_CITATIONS`
  manifest maps each note → `(source page, lookup key)`; the expected count is read
  **live** from the parsed artifact (`parse_behavior_blocks` keys by
  `(policy, code)`; `parse_interpreter_buckets` adds the synthetic `A+A-missing`
  total), so it can't drift from the source. The guard fails — naming the note, the
  current number, and the regen command — when a note no longer contains the live
  count (`cited_number_present` matches the thousands-formatted token exactly, so
  `316` ≠ `3,164`). Corpus-free + deterministic → runs in CI / `qa_gate.sh`.
- **Scope: artifact-sourced numbers only.** *Derived* figures (the interpreter
  note's `1,726` = `316` + `1,410` without-codemod baseline) and *sweep-only*
  figures (the `1,127` rewritten count, which lives in no committed artifact) are
  intentionally **not** guarded — there is no committed source of truth to derive
  them from. The companion of D6: D6 keeps generated pages honest about *which rules*
  they list; D7 keeps prose notes honest about *which numbers* they quote.
## D8 (2026-06-03) — Imported-macro `format`/`ftype` normalization (macro epic, Phase 2a)

**Reproduced by:** `uv run --package galaxy-tool-refactor-registry pytest
galaxy-tool-refactor-registry/tests/test_macro_datatype.py`; corpus sizing
`uv run python -m scripts.measure macro-format-residual`
(`docs/macro_format_residual_stats.md`).

- **The gap.** `Upgrade24_1` (GTR010) lowercases `format`/`ftype` to satisfy the 24.2
  pattern facet, but only on the tool's **own** tree. A coercible value defined in an
  *imported* macro file (e.g. `<data format="GTiff">` in `gdal_macros.xml`) is
  unreachable from the per-tool pipeline, so **15** corpus tools stay stuck below 24.2
  solely because of it (6 via a shared defining file, 9 sole-owned;
  `galaxy-tool-codemod/docs/macro-aware-normalization.md`). This is the first
  consumer of the macro write-back epic (`docs/macro_handling_architecture.md` §6c).
- **What we chose (Phase 2a, the scoped slice).** `macro_datatype.normalize_macro_files`
  — the macro-library analog of `Upgrade24_1`: load each `<macros>`-root file as a
  `MacroDocument`, lowercase every **literal** `format`/`ftype` (the shared tier-2
  `datatype_format` helper, `skip_tokens=True` to leave `@TOKEN@` placeholders), and
  reserialise through `format_macro_document` (fmt stays the only serializer). It lives
  here (parallel to `macro_profile.py`) because it needs tier-1 + tier-2 + fmt. The
  CLI exposes it as the opt-in `normalize-macros` command — **never** folded into
  `format`/`upgrade`, because it writes files other than the one named.
- **Why no per-importer validity gate (unlike `macro_profile`'s consensus).** The edit
  is exactly the canonicalization `Upgrade24_1` already applies tool-tree-wide as
  semantics-preserving: lowercase is the canonical Galaxy datatype extension at every
  profile, and it only *satisfies* the 24.2 pattern facet, never breaks it. An importer
  blocked by the uppercase value can only improve; one already valid stays valid. So a
  shared macro file is as safe to edit as the tool's own tree — the shared-file blast
  radius is *surfaced* (the measure splits shared vs sole-owned), not gated. Contrast
  `@PROFILE@` (D5), where importers can disagree on a target and consensus is required.
- **Robustness.** A macro file that fails to load (unsupported version / malformed) is
  skipped and recorded in `MacroDatatypeResult.unparseable`, never aborting the batch —
  parsing is the one boundary with no LBYL form.
- **Scope.** Phase 2a only — literal values. Token-supplied (`format="@FORMAT@"`) and
  arbitrary expanded-node edits need the general expansion-provenance layer (Phase 2b),
  still deferred (`docs/macro_handling_architecture.md` §6, §7).

## D9 (2026-06-03) — Unified `GTR` rule namespace (retire the GTX/IUC split)

### Decision

Every rule across all three families now carries a single `GTR###` ("Galaxy Tool
Refactor") code. The historical two-prefix scheme — `GTX` for fixable (fmt +
codemod) rules, `IUC` for advisory checks — is retired. **Fixability is a rule
property** (`RuleHandle.fixable` / `RuleMeta.detect_only`), never encoded in the
code prefix. This is PR A of the sub-rule/partition work (Flavor 1); PR B adds the
dotted `GTR###.1`/`.2` partition sub-rules.

### Rationale

- The `GTX`/`IUC` split was incidental (it grew out of the order rules were added),
  and it conflated *identity* with *fixability*. The sub-rule partition work makes
  that conflation untenable: a single best-practice can have both a fixable part and
  an advisory part, so its code cannot live in a fixable-or-advisory prefix.
- One namespace is less to explain and impossible to mis-bucket. The collision
  guard (`registry._index`) now polices one space. The advisory checks
  (`GTR021`–`GTR033`) still *enforce* the external **IUC best-practices** standard —
  that name refers to the standard, not to our code prefix.

### Mapping (old → new), number-preserving

`GTX0NN → GTR0NN` (prefix swap, number kept); `IUC0NN → GTR0(NN+20)`. So
`GTX001…GTX020 → GTR001…GTR020`, and `IUC001…IUC013 → GTR021…GTR033`. Every prose
range stayed consecutive (`GTX007–012 → GTR007–012`, `IUC001–010 → GTR021–030`).

| New | Old | Rule | Family / fixable |
|---|---|---|---|
| GTR001 | GTX001 | indent | fmt / fixable |
| GTR002 | GTX002 | reorder `<param>` attrs | codemod / fixable |
| GTR003 | GTX003 | blank line between `<tool>` children | fmt / fixable |
| GTR004 | GTX004 | empty-element shorthand | fmt / fixable |
| GTR005 | GTX005 | reorder `<tool>` attrs | codemod / fixable |
| GTR006 | GTX006 | FixTypos | codemod / fixable |
| GTR007 | GTX007 | UpdateProfile | codemod / upgrade-only |
| GTR008 | GTX008 | Upgrade19_01 | codemod / upgrade-only |
| GTR009 | GTX009 | Upgrade24_0 | codemod / upgrade-only |
| GTR010 | GTX010 | Upgrade24_1 | codemod / upgrade-only |
| GTR011 | GTX011 | Upgrade25_1 | codemod / upgrade-only |
| GTR012 | GTX012 | UpgradeToLatest | codemod / upgrade-only |
| GTR013 | GTX013 | reorder `<tool>` children | codemod / fixable |
| GTR014 | GTX014 | FixFromWorkDirWhitespace | codemod / runtime-gated |
| GTR015 | GTX015 | FixOutputFormatInput | codemod / runtime-gated |
| GTR016 | GTX016 | FixInterpreter | codemod / runtime-gated |
| GTR017 | GTX017 | NormalizeBooleanValues | codemod / fixable |
| GTR018 | GTX018 | WrapCommandCdata | codemod / fixable |
| GTR019 | GTX019 | WrapHelpCdata | codemod / fixable |
| GTR020 | GTX020 | SingleQuoteCommandVars | codemod / fixable |
| GTR021 | IUC001 | tests present | check / advisory |
| GTR022 | IUC002 | `<command>` CDATA | check / advisory |
| GTR023 | IUC003 | id charset | check / advisory |
| GTR024 | IUC004 | version format | check / advisory |
| GTR025 | IUC005 | requirements present | check / advisory |
| GTR026 | IUC006 | error handling | check / advisory |
| GTR027 | IUC007 | EDAM/xrefs | check / advisory |
| GTR028 | IUC008 | help present | check / advisory |
| GTR029 | IUC009 | description present | check / advisory |
| GTR030 | IUC010 | `<help>` CDATA | check / advisory |
| GTR031 | IUC011 | single-quote `$var` | check / advisory |
| GTR032 | IUC012 | `&&`-vs-lone-`&` (no-op stub) | check / advisory |
| GTR033 | IUC013 | requirement version pinned | check / advisory |

### Note for PR B

The three command/help/quoting practices each have a fixable rule **and** an
advisory residual (GTR018/GTR022, GTR019/GTR030, GTR020/GTR031). PR B collapses each
pair into a partition parent + `.1` (fix) / `.2` (advisory-residual) sub-rule and
restricts the advisory to the non-provable complement. Until then they remain
distinct flat codes (overlapping, as before the rename).

### Reproduction

```sh
bash scripts/qa_gate.sh
uv run galaxy-tool-refactor rules           # every code now GTR###
```

## D10 (2026-06-04) — Partition sub-rules: a practice splits into a fixable `.1` + advisory `.2`

### Decision

A best-practice that splits into a **provably-fixable** part and an **advisory
residual** is modelled as one **partition parent** code (e.g. `GTR020`) with two
dotted sub-rules: `GTR020.1` (the fixable codemod) and `GTR020.2` (the advisory
check). Three practices use this (PR B of the sub-rule work, building on the D9
unified namespace):

| Parent | `.1` fix (tier 2, in `iuc`) | `.2` advisory (tier 3.5, in `strict`) |
|---|---|---|
| GTR018 | `WrapCommandCdata` (pure-text `<command>`) | command-CDATA residual (mixed-content) |
| GTR019 | `WrapHelpCdata` (pure-text `<help>`) | help-CDATA residual (mixed-content) |
| GTR020 | `SingleQuoteCommandVars` (provable vars) | single-quote residual (non-provable vars) |

### How it works

- **`RuleMeta.parent`** (tier 0.5) carries the parent code on each sub-rule; the
  parent is a *registry-level grouping*, not itself a rule handle.
- **Grouping + selection-tree** (`registry.py`): `partition_groups()` derives
  `parent → (children)` from `meta.parent`; `parent_codes()` joins `known_codes()`
  (so a parent is selectable); `expand_codes()` maps a parent → its children.
  `resolve.resolve_codes` expands the user's `--select` / `--ignore`, so
  `--select GTR020` pulls the whole practice while `--ignore GTR020.2` drops only the
  advisory. Presets need no special-casing — they derive from `meta.code`, so `iuc`
  (canonical codemods) gets the `.1` children and `strict` (advisory checks) the `.2`.
- **Build-time guard** (`_validate_partitions`, called from `_index()`): asserts the
  scheme so a future partition added wrong fails fast — every sub-rule's code is
  `<parent>.<suffix>`, the parent code does not collide with a real rule (a parent is
  a group key, not a rule), and each parent groups at least one fixable **and** one
  advisory child (the fix/advisory split). Pinned by `tests/test_registry.py`.
- **Display** (`display_code`): a finding renders under the **parent** code (both
  halves read as one practice, "GTR020"), with the existing `(advisory)` suffix
  distinguishing the residual. The structured `Violation.code` keeps the precise
  child code.
- **The real behaviour change — a *clean* partition.** Before, the advisory and the
  fix *overlapped* (the advisory flagged everything, including what the fix handles).
  Now each `.2` advisory's `detect` is **restricted to the complement** of its `.1`
  fix, reusing the *same* shared tier-1 predicate
  (`galaxy_tool_xml.cdata.cdata_wrappable` for CDATA, `command_vars.provably_quotable`
  for quoting) so the two halves are disjoint + exhaustive by construction — no
  drift. Net effect: `check` no longer double-reports the auto-fixable occurrences.
  A soundness guard (`tests/test_partition.py`) pins it.

### Why parent-as-grouping, not a parent rule

A parent with its own `detect` would double-count (parent = union, children =
partition). Making it a pure grouping keeps the children the single source of
findings and lets the dotted code carry the only new identity.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-registry pytest \
  galaxy-tool-refactor-registry/tests/test_partition.py
uv run galaxy-tool-refactor check --preset strict tool.xml   # GTR020 fixable + advisory
uv run galaxy-tool-refactor format --select GTR020 tool.xml  # whole practice's fix
```

## D11 (2026-06-05) — `rename_param`: a mutating facade op (not a rule)

### Decision

The facade gains `rename_param(source, *, old, new, write_path=None) -> RenameParamResult`
— the mutating sibling of `find_references`, the user-facing operation behind the CLI
`rename-param` (cli `docs/decisions.md` §D9). It wraps the tier-1 `cheetah_rename`
primitive (the first Cheetah mutator; `galaxy-tool-xml/docs/decisions.md` §20).

Like `find_references` it is an **operation, not a rule**: a parameter rename is
user-parameterised, so it carries no GTR code, no preset membership, and no
`--select`/`--ignore` path — it never enters the `run`/`detect` rule pipeline.

Two invariants it upholds:

- **The facade owns the transaction.** It deep-copies the document's tree, runs the
  tier-1 rename on the copy, and serialises (through fmt — the only serializer — with no
  cosmetic rules, so only the renamed tokens differ) **only on success**. A bail returns
  `changed=False` + a reason and never touches `source`. This is why the tier-1 primitive
  may mutate-then-bail freely: the caller's tree is a throwaway copy.
- **Atomic.** Either every live reference + the definition is rewritten, or nothing is
  (see §20 for the bail taxonomy). `RenameParamResult` carries `changed` / `renamed`
  (site count) / `reason` / `formatted`.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-registry pytest \
  galaxy-tool-refactor-registry/tests/test_facade.py -k rename
```

## D12 (2026-06-05) — Cross-file rename: the sole-owned shared-macro gate

### Decision

`bundle_rename.py` adds the repo-aware tier above the tier-1 bundle rename
(`galaxy-tool-xml/docs/decisions.md` §21): it decides whether a macro a rename would
edit is *safe* to write, and is the home for the cross-tool orchestration (exactly
where `macro_profile.py` puts the `@PROFILE@` consensus — tier 1 has no concept of
"the other tools in the repo").

- **`build_importer_map(repo_root) -> {macro: frozenset[tool]}`** walks the repo for
  `<tool>` roots and inverts each one's **transitive** `imported_macro_paths`. Keyed on
  transitive (not direct) imports, so a macro shared only through a deeper chain is not
  mis-counted as sole-owned.
- **Sole-owned gate (v1).** `rename_param_bundle` loads the bundle, renames across it,
  then classifies each macro the rename touched: sole-owned (importers `== {tool}`) →
  written; **shared** (any other importer) → the whole rename is *skipped and reported*
  (`reason="shared-macro"` + the blast radius), and the tool is **not** written either,
  so it is never left half-renamed referencing a name the shared macro still emits as
  `$old`. Renaming all importers in lockstep (consensus, à la `macro_profile`) is the
  opt-in `rename_param_consensus` path (D14); this default refuses rather than guess.
- **`--repo-root` is the soundness keystone.** A rename that must edit a macro but was
  given **no importer map** bails `macro-edit-needs-repo-root` rather than guess — an
  under-counted importer set would silently authorise a shared write that breaks a tool
  outside the scanned set (the highest-severity risk in the design). A *pure tool-internal*
  rename (no macro touched) needs no map. Ownership is framed as "sole-owned within the
  repo root the map was built over."
- **An unparseable imported macro bails the rename** (`unparseable-macro`): a macro we
  cannot read might reference `old`, so renaming the tool would risk a dangling reference.
- **Read-only `find_references_in_bundle`** scans the tool **and** each imported macro
  (no gate — it never writes), attributing each occurrence to its own file.

`--backup` (a `make_backup` copy to `<file>.bak` before each overwrite, in fmt's
`cli_support`) threads through the registry write sites (`rename_param_bundle`,
`normalize_macro_files`, `apply_profile_token_plans`), gated by `write`.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-registry pytest \
  galaxy-tool-refactor-registry/tests/test_bundle_rename.py
uv run python -m scripts.measure rename-macro-spread
```

## D13 (2026-06-05) — Cross-file rename gate fails **closed** on an uncovered macro

### Decision

Follow-up hardening to D12. The sole-owned gate classified an edited macro by
`importers.get(macro, frozenset({tool}))` — so a macro **absent** from the importer map
defaulted to "sole-owned by this tool" and the rename **applied** (fail-open). That is
only reachable by misuse — `--repo-root` pointed somewhere that does not contain the
tool — but it is exactly the under-counted-importer-set hazard D12's `--repo-root`
requirement exists to prevent: an unseen tool elsewhere could import the same macro and
break.

`_gate_macros` now classifies each edited macro three ways: sole-owned (in the map,
`== {tool}`) → apply; shared (in the map, other importers) → `shared-macro` skip;
**absent from the map** → `macro-ownership-unprovable` skip (fail **closed**). In correct
usage the tool is under the repo root, so it imports the macro and the macro is in the
map with at least `{tool}`; absence means the root does not cover the tool, so ownership
cannot be proven and the edit is refused. `BundleRenameResult` gains `unprovable:
tuple[Path, ...]`; the CLI prints a message pointing at the likely cause (the tool is not
under the given `--repo-root`).

### Reproduction

```sh
uv run --package galaxy-tool-refactor-registry pytest \
  galaxy-tool-refactor-registry/tests/test_bundle_rename.py -k unprovable
```

## D14 (2026-06-05) — Consensus rename across shared-macro importers

### Decision

The fast-follow promised in D12: `rename_param_consensus` renames a parameter across a
macro shared by several tools by editing **all** of its importers in lockstep, rather
than skipping the shared macro. Opt-in (CLI `--across-importers`); the default stays the
conservative sole-owned gate.

- **Group = fixed-point closure.** Starting from the seed tool, the group grows by "edits
  a macro that other tools import": each tool's bundle rename is computed, and every
  importer of every macro it edits is pulled in, transitively. So a chain of shared
  macros is fully covered — no tool that would be affected is left out.
- **Consensus = unanimity.** The rename applies only if **every** group tool either
  renames cleanly or simply does not use the parameter (`not-found` — e.g. it imports the
  shared macro but expands a different fragment). A single importer that references the
  parameter but cannot rewrite it safely makes the whole group `no-consensus`
  (the dissenters are reported); nothing is written. This mirrors `macro_profile`'s
  "agree iff all importers agree" exactly, one tier up.
- **Each file written once.** The shared macro is edited identically by every importer's
  bundle rename; the deduped result writes it (and each tool whose own tree changed) a
  single time. A co-importer that only references the parameter through the shared macro
  contributes that macro, not its own (unchanged) file.
- **Same soundness rails as D12/D13.** An edited macro absent from the importer map →
  `macro-ownership-unprovable` (the repo root does not cover it); `--repo-root` is
  required (the CLI rejects `--across-importers` without it).

### Reproduction

```sh
uv run --package galaxy-tool-refactor-registry pytest \
  galaxy-tool-refactor-registry/tests/test_bundle_rename.py -k consensus
```

## D15 (2026-06-09) — Presets → declarative rulesets (per-rule membership)

### Decision

Replace the centralized preset system with **declarative rule-sets** whose membership is
declared on each rule, and remove the hardcoded `CANONICAL_CODEMODS` tuple. A maintainer
marks which sets a rule belongs to right on the rule; the registry derives `name → codes`.

- **Membership lives on the rule.** `RuleMeta` (tier 0.5) gains
  `rulesets: frozenset[str]`; each fmt rule / canonical codemod / advisory check declares
  its set(s). The tier-0.5 `rulesets.py` catalog owns the *names + descriptions* (the one
  property of a set, not of any member) and `DEFAULT_RULESET = "default"`.
- **Derivation, not a second list.** `rulesets.ruleset_codes()` groups the registry by
  `handle.meta.rulesets` — it can't drift from the rules that exist. The old `presets.py`
  (which enumerated families + the `CANONICAL_CODEMODS` tuple) is gone.
- **`CANONICAL_CODEMODS` retired.** Membership *and order* moved onto the rules:
  `canonical.canonical_codemods()` is now derived (codemods declaring `"default"`, sorted
  by `meta.order`), and `apply.py` orders the codemod phase by `meta.order` instead of a
  tuple index. `selectable_codemods()` = codemods with a non-empty `rulesets`;
  `upgrade_only_codemods()` = those with none. *(Renamed `non_selectable_codemods()`
  in the 2026-06-10 audit: GTR092 — opt-in-command-only, not upgrade — joined the
  no-ruleset set, so "upgrade-only" stopped being accurate.)*
- **Union selection.** `resolve_codes(*, rulesets, select, ignore)` takes the **union** of
  the named sets as its base (default `{"default"}`); `--select` replaces, `--ignore`
  subtracts (precedence unchanged). `UnknownPreset` → `UnknownRuleset`;
  `PresetInfo`/`list_presets` → `RulesetInfo`/`list_rulesets`. The CLI flag is
  `--ruleset` (repeatable / comma-separated), the introspection command is `rulesets`.
- **Behaviour preserved.** Seeded membership reproduces the old preset sets exactly:
  `cosmetic` = fmt rules; `default` = canonical codemods + cosmetic (the old `iuc`, still
  the no-arg `format` set — the byte-identity regression test holds); `iuc` mirrors
  `default` for now (a placeholder to be reshaped per-rule later); `strict` = `default` +
  every advisory check. The default selection name changed `iuc` → `default`; the bytes
  did not.
- **Guarded.** `test_ruleset_membership.py` pins: every declared name is in the catalog,
  every selectable rule declares ≥1 ruleset, upgrade-only codemods declare none, and no
  catalog ruleset is empty. Rule/rules decisions: tier-0.5 D4, codemod §36.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-registry pytest \
  galaxy-tool-refactor-registry/tests/test_rulesets_resolve.py \
  galaxy-tool-refactor-registry/tests/test_ruleset_membership.py
uv run galaxy-tool-refactor rulesets
```

## D16 (2026-06-09) — Planemo aliases: name-based selection + generated parity table

### Decision

Build a **planemo-linter alias** over the per-rule `RuleMeta.planemo_linters` (rules
D5) so a planemo user can address a rule by its planemo name, without splitting our
rules to match planemo's decomposition (a survey found only 4 of 25 bundles are
genuine split-candidates; splitting the other 21 would manufacture mutually-exclusive
rules). Deferred the 4 splits.

- **`planemo.py` — `planemo_index()`** derives `planemo name (lower-cased) → frozenset[GTR
  codes]` from `all_handles()`. Case-insensitive; a bundled rule is reached by any of
  its names.
- **Selection by name.** `resolve._expand_selection` expands each `--select`/`--ignore`
  token: a GTR code (case-insensitive; canonical upper), a partition parent (expands),
  or a planemo name (→ covering codes); else `UnknownRuleCode`. A bundled name selects
  the whole covering GTR (lossy exactly for the 4 split-candidates — documented). The
  CLI no longer upper-cases tokens (so an error echoes what the user typed).
- **Reporting.** `RuleInfo` gains `planemo_linters`; `list_rules` populates it; the CLI
  `rules` command shows a `planemo:` field; MCP `list_rules` includes it.
- **Generated parity table.** `parity.render_parity_table()` renders the GTR coverage
  table of `docs/planemo_linter_parity.md` from metadata (planemo coverage, detect/fix,
  tier, narrowest ruleset, `meta.summary`); `scripts/gen_planemo_parity.py` writes it
  between BEGIN/END markers; `test_planemo_parity_table.py` pins the committed block.
  Only the prose preamble + the HAVE/SKIP/n-a accounting stay hand-written. The one
  hand-known exception is GTR032's `detect = —` (the reserved no-op stub, check D3).

### Reproduction

```sh
uv run --package galaxy-tool-refactor-registry pytest \
  galaxy-tool-refactor-registry/tests/test_planemo_aliases.py \
  galaxy-tool-refactor-registry/tests/test_planemo_parity_table.py
uv run galaxy-tool-refactor rules | grep planemo
uv run python -m scripts.gen_planemo_parity
```

## D17 (2026-06-10) — Alias reconciliation: the parity HAVE count is metadata-derived

### Decision

Close the 2026-06-09b audit's **M3** finding (`docs/architecture_audit.md`): the parity
Summary's hand-maintained **HAVE** figure and `RuleMeta.planemo_linters` disagreed
(110 vs 103) because eight aliases were **under-declared** — the rules' docstrings and
check `decisions.md` already claimed the coverage, but the metadata (and therefore
`--select`, `planemo_index()`, and the generated table) lagged. Verified each claim
against both our detect source and the planemo source, then:

- **Added the 8 missing aliases**: `ToolIDWhitespace` → GTR023 (whitespace fails the
  charset), `StdIOAbsenceLegacy` → GTR026 (same no-stdio condition), `CitationsNoValid`
  → GTR038 (empty `<citations>` covered), `ValidatorDatasetMetadataEqualValueOrJson` →
  GTR068 (the `value_json` branch), and the four data-param `<options>` linters
  (`InputsDataOptionsAttrib`/`…FilterAttribFiltersType`/`…FiltersType`/`…FiltersRef`) →
  GTR074. Strictly additive: each name now resolves in `--select`/`--ignore`.
- **`BioToolsValid` re-marked HAVE\*** (was n/a) — it was already aliased on GTR027 and
  is the same presence-check approximation as the HAVE\*-marked `EDAMTermsValid`; the
  two were treated inconsistently. **`ValidDatatypes` stays DETECT** but keeps its
  GTR010 alias (the case-normalizer is the closest rule; the roadmap row says so).
- **Pinned the accounting** (`test_planemo_aliases.py`): HAVE = aliased canonical
  linters − `{ValidDatatypes}` + `{XSD}` (tier-1 `validate_tool` coverage, deliberately
  alias-free), checked against the Summary row; Total checked against the vendored
  canonical list. Folds in the audit's **L2**: every alias must name a real planemo
  `Linter` class from the vendored `tests/data/planemo_linters_c6e0ee3.txt` (146 names,
  AST-extracted at the roadmap's pinned galaxy commit), so a typo'd alias now fails CI
  instead of silently never matching.

Summary moved HAVE 110 → **111** / n-a 12 → **11** (the `BioToolsValid` re-mark).

### Reproduction

```sh
uv run --package galaxy-tool-refactor-registry pytest \
  galaxy-tool-refactor-registry/tests/test_planemo_aliases.py
uv run python -m scripts.gen_planemo_parity
```

## D18 (2026-06-10) — `convert_help`: the opt-in conversion entry point

### Decision

Expose GTR092 (`ConvertHelpToMarkdown`, codemod §38) through a dedicated facade
function — `convert_help(source, write_path=None) -> ConvertHelpResult` — and
**nowhere else**: the conversion swaps Galaxy's rendering engine, so it joins no
ruleset, `run`, or `upgrade`. The facade asks the codemod's own
`conversion_skip_reason` first and surfaces it verbatim (`ConvertHelpResult.
skip_reason`), so the library/CLI note and the codemod's behaviour share one
decision path. Serialisation goes through `apply_selection(codes=frozenset())` —
fmt stays the only serializer; nothing but the `<help>` element changes.
`write_path` is written only when the conversion actually applied.

Registry classification: GTR092 lands in `upgrade_only_codemods()` (no ruleset →
not selectable; introspection via `list_rules(include_upgrade=True)`), but the
parity table's tier column keeps its real family via the `_OPT_IN_COMMAND_CODES`
exception — it is applied by `convert-help`, not `upgrade`. *(Both renamed in the
2026-06-10 audit: `non_selectable_codemods()` / `adapters.OPT_IN_COMMAND_BY_CODE`;
`--select GTR092` now hints at the dedicated command instead of a bare "unknown".)*

### Reproduction

```sh
uv run --package galaxy-tool-refactor-registry pytest \
  galaxy-tool-refactor-registry/tests/test_facade.py -k convert_help
```

## D19 (2026-06-10) — `tokenize_version`: the second opt-in conversion entry point

The GTR094 sibling of D18's `convert_help`: `tokenize_version(source, *,
write_path=None) -> TokenizeVersionResult(formatted, tokenized, skip_reason)`.
The facade re-derives the outcome from the tree after `apply` (the codemod's
expansion-equality gate may decline beyond the shared preconditions), so the
reported skip reason can never disagree with what happened. Serialisation goes
through `apply_selection(codes=frozenset())` — fmt stays the only output
serializer. `OPT_IN_COMMAND_BY_CODE` gains the second entry; the partition
tripwire and `list_rules(include_upgrade=True)` cover it as before.

## D20 (2026-06-11): `tokenize-version --macros-file` shared-macros tokenization

`version_token_share.plan_shared_tokenization` plans the `--macros-file` mode of
`tokenize-version` (cli §D13): putting the IUC version tokens in a macros file the
tool `<import>`s instead of an inline `<macros>` block. One module unifies three
shapes:

- **create**: the named file does not exist: create it with the two `<token>`s and
  add the `<import>` to the tool.
- **merge**: the file exists and the tool imports it: add the tokens to it, retarget
  the tool (no second import).
- **consensus**: several target tools in one directory share the file at the *same*
  `version="<base>+galaxy<suffix>"`: tokenize all of them and define the shared tokens
  once. A divergent version among the eligible targets, or a conflicting existing
  token value, is declined with a reason.

**Soundness is proof by execution**, the project-wide discipline. Each retargeted
tool is gated by the tier-1 inline `expansion_equality_holds` (importing a file that
defines the tokens is equivalent to inline by Galaxy macro semantics, so the inline
proof covers the separate-file rendering). A **merge into an existing file is also
proven *inert*** for every *other* importer in the directory: the module copies the
directory into a temp dir, overrides the macros file with the merged version, and
requires each other importer's macro expansion to be byte-identical before and after.
An importer whose expansion would change (it references the token names, or a
duplicate definition would shadow) declines the merge. So a shared file is edited only
when provably harmless to its other tools, so no coarse sole-owned gate is needed
(the `rename-param` D12 approach): the behaviour is checked directly.

**Built for the construction, not the corpus.** A novel tool suite sharing one
`macros.xml` at a common version is the target; the corpus payoff today is tiny (1
shared file / 2 tools, per `scripts.measure version-token-sharing`), but the
construction-soundness-over-corpus principle governs: soundness holds by
construction, so the feature ships regardless of frequency. The facade
(`tokenize_version` for one tool, `tokenize_version_shared` for a group) and the CLI
(grouping targets by directory) sit on top; fmt stays the only serializer (the
module's `etree.tostring` / temp-dir `write_bytes` are the throwaway gate, allowlisted).
Reproduced by `uv run python -m scripts.measure version-token-sharing` (which also
retains any planner crash as a regression corpus, the standing retain-failures order).
