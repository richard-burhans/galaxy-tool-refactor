# Decisions — galaxy-tool-refactor-cli

Each entry records a decision once it lands: a date, the decision, and the
rationale. Mirrors the conventions of the sibling packages' `docs/decisions.md`.

## D1 (2026-05-29) — A top-level app tier that separates `upgrade` from `format`

### Decision

A new tier-4 package owns the user-facing `galaxy-tool-refactor` CLI and all
cross-tier orchestration. It depends on the codemod tier (tier 2) and the fmt
tier (tier 3) and exposes two commands (a third, report-only `check`, was added
in §D2 over the check tier):

- `format` — apply `CANONICAL_CODEMODS` (typo + boolean-case repair + attribute
  order) then fmt's cosmetic rules. Safe, idempotent; never changes `profile=`.
- `upgrade` — apply `AUTO_UPGRADE_CODEMODS` (typo repair, then iterative profile
  upgrade) then cosmetic formatting. Opt-in and semantic; reports the profile
  steps applied and warns on stalls.

Profile upgrade was previously folded into the default canonical pipeline that
fmt's CLI ran (`UpgradeToLatest` was in `CANONICAL_CODEMODS`). It has been
pulled out into the opt-in `upgrade` command here.

### Rationale

- **Upgrade is semantic, fallible, and reports outcomes** — it changes
  `profile=`, applies lossy structural migrations, and can stall below the
  latest profile. Folding that into a silent, idempotent "format my tool" pass
  conflated two very different operations. Separate, explicit commands let users
  opt into modernization deliberately (mirrors how formatters gate semantic
  rewrites behind an explicit flag).
- **Output goes through fmt's serializer**, so the orchestrator must sit *above*
  fmt. It could not live in the codemod tier without inverting the tier order
  (fmt already consumes codemod's pipeline contracts). A dedicated app tier is
  the clean home; it also let fmt's CLI shed its codemod orchestration and
  return to cosmetic-only (see `galaxy-tool-fmt/docs/decisions.md` §D12).
- **`FixTypos` runs in both pipelines.** It stays in the default `format`
  pipeline (repairing near-miss typos is safe and useful) *and* runs first in
  `upgrade` as a precondition — `UpgradeToLatest` no-ops on a tool that
  validates nowhere, so a broken-and-outdated tool must be repaired before it
  can upgrade. `FixTypos` is idempotent, so appearing in both is harmless.

### Shape

- One `click` group, `galaxy-tool-refactor`, with `format` and `upgrade`
  subcommands; both reuse fmt's `cli_support` engine for file walking,
  `--check` / `--diff` / `--quiet`, drift detection, and the summary.
- Both serialize via `format_tool_document`, so output is canonical-form XML in
  either case; the commands differ only in which codemod pipeline runs. The
  typical modernization flow is `upgrade` then `format` (the second is
  idempotent on already-formatted output).

### Reproduction

```sh
uv sync
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/
```

## D2 (2026-05-30) — Report-only `check` subcommand (PR3)

### Decision

A third subcommand, `galaxy-tool-refactor check`, reports where tools deviate
from canonical form without changing anything: one `file:line  CODE  message`
line per finding, non-zero exit if any findings (or errors). It composes the
detect phases the lower tiers gained in PR1/PR2 — the canonical codemods'
`detect` (each `Change` projected via `Change.to_violation()`) plus fmt's
`detect_tool_document` — over the same rules `format` would apply. PR3 of the
detect/fix rule-split effort (PR1–5, merged in #15).

### Rationale

- **Scope = the `format` rule set, report-only.** `check` mirrors the safe
  `format` pipeline (`CANONICAL_CODEMODS` + cosmetic fmt), not `upgrade` — the
  upgrade codemods are opt-in/semantic and would flag most tools as "would
  upgrade," drowning the signal. A future `--upgrade` flag can extend coverage;
  the detect-only rules (PR4) will also feed this command.
- **A separate, smaller engine — not fmt's `cli_support.run`.** That engine is
  built around rewrite + drift detection (`_process_file` reads, transforms,
  compares bytes, writes/diffs). `check` reuses only the report-safe public
  pieces — `iter_targets`, `is_tool_root`, `load_tool` — and runs its own loop
  that collects `Violation`s and prints them. No bytes are written or compared.
- **Detect phases are non-mutating and independent**, so the canonical codemods'
  detect and fmt's detect run against the one parsed document without
  interfering; findings are sorted by source line. Orchestration of the two
  lower tiers belongs in this app tier, consistent with `format`/`upgrade`.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/
# round trip: check reports, format fixes, check is then clean
uv run galaxy-tool-refactor check tool.xml   # exit 1 + findings
uv run galaxy-tool-refactor format tool.xml
uv run galaxy-tool-refactor check tool.xml   # exit 0, "clean"
```

## D3 (2026-05-30) — `check` gains advisory findings (PR4)

### Decision

`check` now also runs the tier-3.5 advisory checks
(`galaxy-tool-lint.detect_violations`) alongside the fixable GTR detect
phases. The two finding classes are distinguished by `RuleMeta.detect_only`:
fixable (what `format` would change) versus advisory (the IUC best-practice checks).
Per-finding output marks advisory lines `(advisory)`; the summary splits the
counts ("N fixable, M advisory in K file(s)"). `check` exits non-zero on any
*fixable* finding or error; a new `--strict` flag also fails on advisory
findings.

### Rationale

A GTR finding is definitive ("a codemod / `format` would change this"); an IUC
finding is a judgment call ("consider adding tests"). Failing CI on the latter
by default would make advisory opinions hard gates — a canonical tool that
merely lacks EDAM xrefs should stay green. Keeping both in one report (the user
sees everything) while gating only on fixable findings — with `--strict` to opt
into stricter gating — gives the linter the right ergonomics. The app composes
all three detect tiers (codemod + fmt + check); orchestration stays here.

## D4 (2026-05-30) — CLI consumes the registry facade; `--preset` / `--select` / `--ignore`

> **Renamed since (PR #146, registry D15):** presets became **rulesets** —
> `--preset` → `--ruleset`, the `presets` subcommand → `rulesets`,
> `list_presets()` → `list_rulesets()`, and the default named set is now
> `default`. This entry (and later "preset" mentions in this log) keep the
> original vocabulary as a historical record.

### Decision

Rule orchestration moved out of the CLI into the tier-3.6 registry facade
(`galaxy-tool-refactor-registry`). The CLI now depends on the facade (plus fmt's
`cli_support` engine and tier-1 parsing) and **not** on the codemod / check tiers
directly. `format`, `upgrade`, and `check` gain shared selection options
`--preset NAME`, `--select CODE…`, `--ignore CODE…` (ruff-style precedence:
`--ignore` ▸ `--select` ▸ `--preset`, where `--select` *replaces* the preset's
set). Two introspection subcommands were added — `presets` and `rules` — mirroring
the facade's `list_presets()` / `list_rules()`. `format`/`upgrade` transforms call
`facade.run` / `facade.upgrade`; `check` calls `facade.detect`. Unknown
preset/code is mapped to `click.BadParameter` at the boundary.

### What changed for users

- **Default `check` no longer reports advisory findings.** The default preset
  is `iuc` (fixable rules only — what `format` changes); advisory checks are now
  **opt-in** via `--preset strict`. Under `strict`, advisory findings are shown
  and informational (exit 0) unless `--strict` is also given. This supersedes the
  §D3 behaviour where `check` always ran advisory checks: advisory is now a
  selectable concern like every other rule, consistent with the preset model.
- **`format --preset strict`** surfaces advisory findings as per-file notes
  (via `TransformOutcome.notes`, fmt D15) but never mutates for them — only
  fixable rules change a file.
- **`upgrade` does not accept `--preset`** (presets are a format/check concept);
  it rejects it with a clean message. `--select`/`--ignore` still adjust its
  fixable rule set (e.g. `--ignore GTR006` to skip typo repair); the profile
  upgrade itself always runs.

### Rationale

The orchestration had to sit *below* the CLI so a future MCP server
(`galaxy-tool-refactor-mcp`) can reuse it without importing a `click` app; a
library-first facade is the shared core (see the registry package's
`docs/decisions.md` D1). Making advisory a preset concern (rather than an
always-on `check` phase) keeps one consistent selection model across all three
commands — the price is that bare `check` is now fixable-only; `--preset strict`
restores "show me everything." The default `format`/`check`/`upgrade` behaviour is
otherwise unchanged (the registry refactor itself was byte-identical to the old
inline `format` pipeline; registry D3). A *later* deliberate change does shift
default-`format` bytes: GTR020 (`SingleQuoteCommandVars`) joined
`CANONICAL_CODEMODS`, single-quoting the provably-single-valued `<command>` vars
(codemod `docs/decisions.md` §30) — behaviour-preserving, but not byte-identical to
the pre-GTR020 output.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/
uv run galaxy-tool-refactor presets
uv run galaxy-tool-refactor check --preset strict tool.xml   # advisory shown, exit 0
uv run galaxy-tool-refactor format --select GTR001 tool.xml  # indent only
```

## D5 (2026-05-30) — `format` / `check` also handle macro-library files

### Decision

The app `format` and `check` commands now process macro-library files
(`<macros>` root), not just tools. `format` cosmetically formats them
(`format_macro_document` via `cli_support.run`'s `macro_transform`); `check`
reports their cosmetic drift (`detect_macro_document`, all fixable). `upgrade`
passes no `macro_transform`, so it runs no *separate* cosmetic pass over macro
files the way `format` does; its **semantic** macro edit — the token-aware
imported-`@PROFILE@` bump — landed in §D6 below, not as a `macro_transform`.
Note that bump path nonetheless reserialises the file it edits through
`format_macro_document` (`macro_profile.py`), so a *bumped* macro file is
cosmetically normalised as a side effect (registry §D5); only un-bumped macro
files are left untouched by `upgrade`.

Macro files get **cosmetic rules only** (codemods are tool-only,
`RuleMeta.applies_to={"tool"}`), so the macro transform bypasses the registry
facade (which runs codemods + fmt) and calls `format_macro_document` directly.
Rule **selection (`--preset`/`--select`/`--ignore`) governs the tool pipeline**;
macro files always get the standard kind-applicable cosmetic rules (GTR001 /
GTR004). A `--select GTR002` run, say, still cosmetically cleans macro files —
documented, accepted for v1.

### Rationale

- **Cosmetic formatting of a macro file is safe regardless of sharing** —
  whitespace-only, idempotent, and stripped during Galaxy macro expansion — so
  there is no blast-radius reason to gate it. The import-graph **bundle +
  shared-skip** is deliberately *not* built here; it is content-edit
  infrastructure whose real consumer is the Phase-3 token-aware `@PROFILE@`
  upgrade (and the macro-library normaliser), and it will be built with that
  consumer so the shared-skip protects the edits it is designed for. Building it
  now, applied to safe cosmetic formatting, would be infrastructure ahead of its
  consumer — the pattern this project defers.
- **Reuses the kind-aware fmt machinery** (`format_macro_document` /
  `detect_macro_document`, `RuleMeta.applies_to`; fmt §D16, rules §D3) and
  `cli_support`'s `is_macros_root` / `macro_transform` (fmt §D16) — no new
  orchestration.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/
uv run galaxy-tool-refactor format path/to/macros.xml   # cosmetically formatted
uv run galaxy-tool-refactor check  path/to/macros.xml   # reports GTR001/GTR004 drift
```

## D6 (2026-05-30) — `upgrade` bumps imported `@PROFILE@` tokens (Phase 3b-2)

**Date:** 2026-05-30. Phase 3b-2 (the imported-token arm of the profile upgrade).
Reproduced-by: `uv run --package galaxy-tool-refactor-cli pytest
galaxy-tool-refactor-cli/tests/test_cli.py -k imported`.

`upgrade` now upgrades a `profile="@PROFILE@"` whose token is defined in an
*imported* macro file by bumping that token in place — the ~1,382-tool bulk the
inline GTR007 path (§3a) does not reach.

- **A whole-run phase, not a per-file transform.** The decision is run-relative
  (a shared macro file is edited once; the target must be unanimous across *all*
  its importers in the run), and it edits *macro* files, not the tool file under
  the cursor — so it cannot ride `cli_support.run`'s per-file `transform`. A new
  `_upgrade_macro_profile_tokens` phase runs first: it walks the run's tool files
  (`iter_targets` + `is_tool_root`, loading from the path so imports resolve),
  collects each one's `profile_token_site`, and feeds the lot to the registry
  (`plan_from_sites` → `apply_profile_token_plans`). The per-file tool
  `run(...)` (repair + structural upgrade + format) then proceeds unchanged; the
  two phases touch disjoint files.
- **Agreement, not a fork.** A shared macro file's token is bumped in place only
  when every profile-using importer agrees on the target; otherwise it is
  reported and skipped. This is the data-driven resolution of the deferred
  shared-macro policy (registry §D5): the `macro-profile-ownership` sweep found 0
  of 46 shared files diverge, so the copy-on-write fork the §D5-era note
  anticipated as this consumer's companion was **not** built — agreement covers
  every real case, and fork stays deferred until divergence appears.
- **`--check` / `--diff` preview, no write; folds into the exit code.** Under
  `--check` (or `--diff`) the phase reports `would upgrade …` and writes nothing;
  a pending macro bump makes `--check` exit non-zero alongside the tool run.
  Bump-up-only and idempotent (a token already at the target is a silent no-op).
- **Why the split CLI/registry.** The editing + agreement logic is library-first
  in the registry (`apply_profile_token_plans`, exception-free, `write` flag);
  the CLI owns only the path walk, parse-error tolerance, and reporting — so a
  future MCP server reuses the same orchestration.

## D7 (2026-06-03) — `normalize-macros`: opt-in macro-library `format`/`ftype` fix

A sixth subcommand, `normalize-macros PATHS… [--check]`, lowercases literal
`format`/`ftype` in `<macros>`-root files — the macro-library analog of the 24.2
normalization the per-tool `upgrade` cannot reach (a value defined in an *imported*
macro file; `galaxy-tool-codemod/docs/macro-aware-normalization.md`, registry
`docs/decisions.md` D8). 15 corpus tools were stuck solely on this
(`docs/macro_format_residual_stats.md`).

- **Why a separate command, not part of `format`/`upgrade`.** It rewrites files
  *other than the one named* — a shared macro file (`gdal_macros.xml`) changes the
  expansion of every importer. Folding cross-file writes into the per-tool pipeline
  would make formatting one tool silently edit a shared dependency. Keeping it an
  explicit, repo-scoped invocation makes the blast radius intentional (the option-D
  shape from `macro-aware-normalization.md`).
- **No selection, no preset.** Presets / `--select` / `--ignore` are tool-rule
  concepts; this is a single fixed canonicalization over macro files, so it takes
  only paths and `--check`.
- **Thin over the registry.** The CLI resolves PATHS (directories walked for
  `<macros>`-root files via `is_macros_root`) and calls
  `macro_datatype.normalize_macro_files` (`write=not --check`); the library does the
  edit + reserialise through `format_macro_document` and reports `unparseable` files
  the CLI surfaces on stderr.
- **Validity-safe, gate-free** (unlike the `@PROFILE@` consensus of D6): lowercasing a
  literal datatype token only satisfies the 24.2 pattern, never regresses an importer
  (registry `docs/decisions.md` D8).

## D8 (2026-06-04) — `find-references`: read-only Cheetah `$var` reference query

### Decision

A seventh subcommand, `find-references NAME PATHS…`, prints every Cheetah `$NAME`
reference site (`file:line  [section]  $ref`) across each tool's templated sections
(`<command>`, inline `<configfile>`, env vars, output labels, dynamic options). It is a
**read-only query**, not a rule: no `--preset`/`--select`, no GTR code, mutates nothing,
exits non-zero only on read/parse errors. It wraps the new facade `find_references` over
the tier-1 reference model `galaxy_tool_xml.cheetah_refs` (`tool_cheetah_references`).

It is the first read-only consumer of the M5 Cheetah-section-editing work
(`../../docs/upgrade_research/cheetah_section_editing.md`): read-only first, highest
coverage, zero mutation risk — validating the reference substrate before any mutator.
The extractor is **faithful** via the CT3 span lexer (a base dependency; tier-1
`cheetah_refs` §18, updated 2026-06-06): a `$var` in a `##`/`#raw`/escaped-`\$` context
is correctly *not* reported, so the query agrees with the faithful `rename-param`
mutator; it falls back to the conservative `_CHEETAH_VAR` regex only on the ~0.4% of
sections CT3 cannot compile. A query (not a rule) needs no preset, registry handle, or
`docs/*_stats.md` regeneration.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/test_cli.py -k find_references
uv run galaxy-tool-refactor find-references input path/to/tool.xml
```

## D9 (2026-06-05) — `rename-param`: the mutating sibling of `find-references`

### Decision

An eighth subcommand, `rename-param OLD NEW PATHS…`, renames a parameter across each
tool, wrapping the facade `rename_param` over the tier-1 `cheetah_rename` primitive (the
first Cheetah **mutator**, M5.3; `galaxy-tool-xml/docs/decisions.md` §20). Like
`find-references` it is **not a rule** (no `--preset`/`--select`, no GTR code) — a rename
is a user-parameterised refactoring operation, not a baked-in fix that `format`/`upgrade`
applies. It rewrites every live `$OLD` reference (command/configfile via the faithful CDM
lexer, attribute-Cheetah, by-name cross-reference attributes, `<tests>` mirrors) plus the
definition, **atomically per file**: a tool changes only if every occurrence is provably
safe, else it is skipped with the bail reason (`shadowed` / `mixed-content` /
`lexer-bail` / `filter-bare-ref` / `cross-ref-residual`). `--check` previews and exits
non-zero if any file would change (matching `format --check`); `--quiet` suppresses
per-file lines. OLD/NEW are validated as identifiers at the CLI boundary.

It runs its own file loop (like `find-references` / `check`) rather than fmt's
`cli_support.run`: rename's per-file bail-with-reason outcome does not map onto that
engine's format-drift model. Corpus coverage (the `rename-coverage` measure): 96.3% of
input definitions rename cleanly; see `galaxy-tool-xml/docs/decisions.md` §20, §22.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/test_cli.py -k rename
uv run galaxy-tool-refactor rename-param old_name new_name path/to/tool.xml
```

## D10 (2026-06-05) — `rename-param` / `find-references` go cross-file; `--backup`

### Decision

`rename-param` and `find-references` now operate over a tool **and its imported macro
files** (the bundle — `galaxy-tool-xml/docs/decisions.md` §21, registry D12), fixing a
silent bug: a param referenced only in an imported macro was previously renamed in the
tool while the macro reference was left dangling.

- **`find-references`** scans the tool plus every imported macro
  (`find_references_in_bundle`), printing `file:line [section] $ref` against the member's
  own file; occurrences are de-duplicated so a macro shared by several scanned tools is
  reported once. Read-only, no new flags.
- **`rename-param --repo-root DIR`.** A rename whose edits all land in the tool needs no
  repo context and applies as before. When the rename must edit an imported macro, the
  CLI builds the transitive importer map over `--repo-root` and the registry gate applies
  only if the macro is **sole-owned**; a **shared** macro is reported (with its other
  importers) and the rename is skipped. A macro edit with **no** `--repo-root` is skipped
  with a message telling the user to supply one — never guessed. **Behaviour change:** a
  rename that today "succeeds" while spilling into a macro now either applies (sole-owned +
  `--repo-root`) or skips — it never silently breaks a macro.
- The registry does the writing (multiple members: tool + sole-owned macros), so the CLI
  no longer writes rename output itself (the cli.py serialiser-allowlist entry was retired).
- **`--backup`** (on `format` / `upgrade` / `rename-param` / `normalize-macros`) copies
  each file to `<file>.bak` before overwriting it (fmt's `cli_support.make_backup`), gated
  by `write` so `--check` never makes backups. A belt-and-suspenders net beside `--check` /
  `--diff` / git, more useful now that one `rename-param` run can write several files.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/test_cli.py -k "rename or find_references or backup"
uv run galaxy-tool-refactor rename-param old new path/to/tool.xml --repo-root path/to/repo --backup
```

## D11 (2026-06-05) — `rename-param --across-importers` (consensus rename)

### Decision

`rename-param` gains `--across-importers` (requires `--repo-root`): when a rename reaches
a macro shared by other tools, instead of skipping it (the D10 default), rename the
parameter across **every** importer of that shared macro in lockstep, editing the shared
macro once. Wraps the registry `rename_param_consensus` (registry D14).

- The run de-duplicates: once a tool is rewritten as part of a consensus group, it is not
  reprocessed when `iter_targets` reaches it again.
- A group where any importer cannot rename the parameter safely is reported (`cannot
  rename … across importers`, naming each dissenter and its reason) and **nothing** is
  written — not even the tools that agreed (atomic across the group).
- Without `--across-importers`, a shared macro is still skipped-and-reported (D10); the
  flag is the explicit opt-in to the wider, multi-tool edit.

### Reproduction

```sh
uv run --package galaxy-tool-refactor-cli pytest \
  galaxy-tool-refactor-cli/tests/test_cli.py -k across_importers
uv run galaxy-tool-refactor rename-param old new tools/ --repo-root . --across-importers
```

## D12 (2026-06-10) — `convert-help`: the opt-in RST → Markdown command

The ninth subcommand, following the `normalize-macros` precedent (D7): a
behaviour-changing operation gets a **deliberate, separate command**, never a
flag on `format`/`upgrade`. `convert-help PATHS [--check] [--backup]` walks tool
files (`iter_targets`/`is_tool_root`), calls the facade's `convert_help`
(registry D18), writes in place on success, and prints the codemod's own skip
reason otherwise — including the actionable "profile below 24.2 — run `upgrade`
first" gate (`<help format=…>` is not XSD-valid earlier; codemod §38). Skips are
informational (exit 0); read/parse errors exit non-zero. Requires the
`galaxy-tool-xml[markdown]` extra; without it every tool is skipped with an
install hint, and nothing is ever converted ungated.

## D13 (2026-06-10) — `tokenize-version`: the tenth command

The CLI surface for GTR094 (registry D19; codemod §43) — the `convert-help`
pattern verbatim (`--check`/`--backup`, per-file tokenized/skipped-with-reason
reporting, non-zero only on I/O or parse errors), with one deliberate
difference: **files are passed to the facade by path, not bytes**, so the
expansion-equality gate can resolve `<import>`ed macro files against the tool's
own directory (a bytes-parsed tool with imports fails closed by design).

## D14 (2026-06-11): `tokenize-version --macros-file` shared-macros mode

`--macros-file NAME` puts the two version tokens in a macros file the tool
`<import>`s instead of an inline `<macros>` block (registry D20). The command
**bifurcates** on the flag: without it, the per-file inline loop (D13) is unchanged;
with it, targets are **grouped by directory** and each directory's set is planned by
`facade.tokenize_version_shared` (create the file, merge into an existing one when
proven inert for its other importers, or tokenize a same-version group together).
The created-vs-merged distinction drives backup (a merged existing file is backed up
under `--backup`, a newly created one is not). The name must be a plain filename
(rejected otherwise, so the import resolves beside the tool and we never write outside
the directory). Per the construction-soundness-over-corpus principle the mode ships
for novel tool suites even though the corpus payoff is tiny
(`scripts.measure version-token-sharing`).

## D15 (2026-06-11): `tokenize-version --adopt-suffix` (identity-changing authoring)

`--adopt-suffix` is the opt-in, **identity-changing** sibling of `tokenize-version`:
for a tool whose *bare* version (no `+galaxy`) equals a package `<requirement>`, it
*adds* `+galaxy0` and tokenizes, so `version="1.20"` becomes
`@TOOL_VERSION@+galaxy@VERSION_SUFFIX@` expanding to `1.20+galaxy0`. The published
version changes, so unlike plain `tokenize-version` it is **not** behaviour-preserving
and cannot use the expansion-equality gate. It is gated instead on the tier-1
**controlled-change gate** (`adopt_suffix_equality_holds`): the macro expansion must
differ *solely* in the root `version` attribute (`base` → `base+galaxy0`), proving the
only effect is the intended version-identity bump and nothing leaked elsewhere.

It is a flag on `tokenize-version` (not a separate command) sharing the tokenization
machinery, but the CLI **bifurcates** to its own loop (`_run_adopt_suffix` via
`facade.adopt_version_suffix`), reports each applied tool loudly ("published version
changed"), and is **mutually exclusive with `--macros-file`** (inline only; rejected
with an error if both are given). Never in `format`/`upgrade`; not exposed over MCP
(agents should not silently bump a tool's published version). The bare-version
population is sized by `scripts.measure version-tokenization`
(`n_version_equals_req_no_suffix`, ~284 tools). Tier-1 `version_tokens`
(`adopt_suffix_skip_reason` + `adopt_suffix_equality_holds`); facade
`adopt_version_suffix`.

## D16 (2026-06-12): `upgrade` flags for the behavior-preserving default

> **Superseded as the default (2026-06-12, D17):** the gated walk these flags
> control is now the opt-in `--modernize` mode; the bare `upgrade` bumps
> minimally. The flags' mechanics below are current.

Reproduced-by: `uv run --package galaxy-tool-refactor-cli pytest
galaxy-tool-refactor-cli/tests/test_cli.py -k "behavior or target_profile"`.

- `upgrade` gains `--allow-behavior-change` (named for the consequence the
  user accepts; lifts the registry facade's default gate, registry D21) and
  `--target-profile PROFILE` (an explicit vendored cap; validated **up front**
  against `available_profiles()` so a typo fails before any file or the
  whole-run macro phase is touched, reusing the typed `UnknownProfile`
  message). Exit codes are unchanged: a gate stop is a successful partial
  upgrade, and `--check`/`--diff` semantics are untouched.
- Both flags thread into the whole-run imported `@PROFILE@` bump
  (`_upgrade_macro_profile_tokens` -> `profile_token_site`), so the
  shared-token targets honor the same gate as the per-tool transform; without
  this the macro path could over-declare a profile the gated per-tool walk
  would refuse (the D6 phase ordering makes the macro edit happen first, so
  the gap would be real).
- The command docstring now leads with the behavior-preserving contract and
  the stop report; the historical "structural, not behaviour-preserving"
  paragraph is replaced by the gate description (the structural caveat
  remains true of `--allow-behavior-change`).

## D17 (2026-06-12): `--modernize` opts into the walk; the default bumps minimally

Reproduced-by: `uv run --package galaxy-tool-refactor-cli pytest
galaxy-tool-refactor-cli/tests/test_cli.py -k "modernize or minimal or
upgrade"`. Policy: registry D22, codemod decisions §50.

- `upgrade` gains `--modernize`: the facade's previously-default
  behavior-gated walk to the behaviour ceiling. The bare command now bumps
  `profile=` only when strictly needed for validity (kept when the repaired
  tool validates at its baseline, undeclared stays undeclared, minimum valid
  profile otherwise), per the IUC maintainer feedback cited in codemod §50.
  `--target-profile` continues to cap an explicit walk and so implies the
  walk mode without requiring `--modernize`.
- `--allow-behavior-change` without `--modernize`/`--target-profile` is
  rejected **up front** as a `click.BadParameter` carrying the typed
  `UpgradeFlagError` message, before any file or the whole-run macro phase is
  touched (the D16 up-front-validation pattern). No silent imply: the flag
  only means lifting the walk's gate.
- The mode threads into the whole-run imported `@PROFILE@` phase
  (`_upgrade_macro_profile_tokens` -> `profile_token_site(modernize=...)`),
  so a shared token whose importers validate at its current value is left
  alone by default, exactly like an inline declaration (the same
  no-disagreement argument as D16's gate threading).
- Help text leads with the minimal-bump contract; the behavior-gate
  paragraph now describes `--modernize`. Exit codes are unchanged, and
  `--check`/`--diff` semantics are untouched.

## D18 (2026-06-12): the deployment ceiling on `--modernize`; `--target-profile` exceeds it

Reproduced-by: `uv run --package galaxy-tool-refactor-cli pytest
galaxy-tool-refactor-cli/tests/test_cli.py -k "deployment or modernize"`.
Policy: registry D23.

No new flags. The `--modernize` walk now lands on the deployment ceiling
(the newest profile every major public Galaxy server runs) when nothing
lower stops it first, and the report says so with the snapshot date and the
escape. `--allow-behavior-change` keeps its single meaning (lift the
behaviour gate); the only way past the deployment ceiling is an explicit
`--target-profile`, which prints an informational note when the requested
target exceeds it. The help text names both ceilings so the flag surface
stays self-describing.

## D19 (2026-06-13): `lint-skip` — prune provable `.lint_skip` suppressions

Reproduced-by: `uv run --package galaxy-tool-refactor-cli pytest
galaxy-tool-refactor-cli/tests/test_cli.py -k lint_skip`. The provable-removal
gate and the facade are registry D24.

- **The command.** `galaxy-tool-refactor lint-skip PATHS [--check] [--backup]`:
  for each tool directory under PATHS that carries a `.lint_skip`, load **every**
  `<tool>` in the directory (the sidecar governs them all; a malformed tool bails
  the whole directory — we cannot prove dir-wide safety), call
  `facade.reconcile_lint_skip`, then write the repaired tools (only those a fix
  changed) and the rewritten `.lint_skip` (deleted when nothing but blanks
  remains), backing up originals under `--backup`. `--check` previews and exits
  non-zero when anything would change (a CI gate, matching `format --check`).
- **The tenth-plus command, deliberately separate.** Like `normalize-macros` and
  `convert-help` it rewrites files other than the one named (the tool XML *and*
  its sidecar), so it is never folded into `format`/`upgrade`. It is a
  convenience: it reports only the lines it removes; suppressions it cannot fix,
  prove, or cover are left untouched and unmentioned (registry D24). `check`
  remains the command for "tell me everything", so `lint-skip` does not duplicate
  that surface.
- **All-tools-in-dir, write-only-what-changed.** Discovery finds directories via
  the tools under PATHS but then globs *all* `<tool>` files in each, so running
  `lint-skip tools/vg/view.xml` still reconciles against `convert.xml` /
  `deconstruct.xml` too (a line is removable only when clear for the whole
  directory). The facade returns per-document bytes; the command writes only the
  documents a fix actually changed.

## D20 (2026-06-15): `gate-suggest` — the forward gate's suggest mode, a hidden CI command

Reproduced-by: `uv run --package galaxy-tool-refactor-cli pytest
galaxy-tool-refactor-cli/tests/test_gate_suggest.py`. Forward-gate background is
`docs/forward_gate.md`; the gate-eligible rule subset is registry D26
(`gate_eligibility`).

- **What it is.** `galaxy-tool-refactor gate-suggest --changed-against REF
  [--repo OWNER/REPO --pr N] [--root DIR] [--dry-run]`: for each tool a PR changed
  that is not in canonical form, compute the behaviour-preserving fix (the
  gate-eligible codes — the same subset block mode's `check` enforces) and post it
  as GitHub one-click `suggestion` review comments, with the local `format`
  command and the IUC doc link. A change outside the PR's diff cannot be inlined
  (GitHub only comments on diff lines), so it is summarized in the review body.
  Non-blocking. `--dry-run` prints the review payload without posting (no token).
- **Why it ships in the package (not as bundled CI shell).** The published
  forward-gate Action's `mode: suggest` previously ran a bundled
  `scripts/gate_suggest.py`. Hardening it: the logic now lives in the installed
  release (`galaxy_tool_refactor_cli.gate_suggest`), so the Action's suggest step
  is one `galaxy-tool-refactor gate-suggest` call against the pinned version — the
  same provenance guarantee block mode already had (the rule set derives from the
  installed release's classification, never drifting from the bulk normalizer).
  Needs `galaxy-tool-refactor >= 0.3.2`.
- **Hidden, not author-facing.** It is CI plumbing, not a command a tool author
  runs on a file, so it is `hidden=True` (absent from `--help` and the
  twelve-command count). The pure suggestion-computation core
  (`build_suggestions` / `review_payload` / `_comment`) is unit-tested; the
  git/`gh` I/O (`collect` / `post_review`) is exercised live (validated end-to-end
  on a real PR). `make gate-suggest` is the maintainer on-ramp.

## D21 (2026-06-21): `bump-version-suffix` — bump the Galaxy revision suffix (opt-in, identity-changing)

Reproduced-by: `uv run --package galaxy-tool-refactor-cli pytest
galaxy-tool-refactor-cli/tests/test_cli.py -k bump_version_suffix`. The tier-1
primitives are `galaxy-tool-source/docs/decisions.md` §32; the suite-scoped shared
bump is registry D27.

- **The command.** `galaxy-tool-refactor bump-version-suffix PATHS [--scope
  per-tool|suite] [--check] [--backup]`: increment a tool's integer Galaxy revision
  suffix, `version="…+galaxy7"` → `…+galaxy8`. The twelfth author-facing command. It
  wraps `facade.bump_version_suffix`, writes the changed tool (and, in the shared case,
  the imported macros file), and backs up originals under `--backup`; `--check` previews
  and exits non-zero when anything would change.
- **Author-invoked, not content-detected.** The command bumps when run. It does **not**
  inspect whether the tool's content changed (there is no `ShedVersion` / content-diff
  machinery): the author runs it precisely when they have changed a published tool and
  need to publish a new revision. This is the deliberate division of labour the IUC
  conference question §1 settles — the toolchain can canonicalize a published tool, but
  bumping its revision is a "publish a new revision" decision the author (and the
  IUC policy) owns, not a behaviour-preserving auto-fix.
- **Opt-in command only, no GTR code, never `format`/`upgrade`/MCP.** Incrementing the
  suffix *changes the published version*, so — exactly like `tokenize-version
  --adopt-suffix` (§D15) — it is identity-changing by construction. It therefore carries
  no GTR code, is in no ruleset, and is never folded into `format`/`upgrade` or exposed
  over MCP (the MCP surface is the single-document, behaviour-preserving facade ops).
  It is a deliberate, separate author action.
- **`--scope` and the three suffix sites.** The suffix lives at exactly one of three
  sites, resolved by tier-1 `current_suffix` (§32): a literal `+galaxy<N>` in the tool's
  own `version=`, an inline `@VERSION_SUFFIX@` token in the tool's own `<macros>`, or a
  `@VERSION_SUFFIX@` token in an **imported** macros file. The two *tool-local* sites
  (literal / inline token) bump the tool itself, so `--scope` is irrelevant for them. An
  *imported* shared token is identity-shared across every importer of that file, so the
  scope choice matters: under `--scope per-tool` (the conservative reading) the bump is
  **declined with a reason** (rerun with `--scope suite`); under `--scope suite` (the
  default) the shared file's token is bumped **once**, moving every importer in lockstep,
  behind the registry's proof-by-execution gate (D27). The provisional default is
  suite-wide, the IUC §1 question now just confirms or flips it.
- **Skip reasons.** `bump_suffix_skip_reason` (§32) declines, with a reason, a tool with
  no `version=`, a `version=` with no `+galaxy` suffix (the user is pointed at
  `tokenize-version --adopt-suffix`, which adds `+galaxy0` first), or a non-integer
  suffix (we only increment integer revisions).

## D22 (2026-07-02): `--block-consider` — the strict-gate flag on `upgrade`

The CLI face of registry D28: `upgrade --modernize --block-consider` (or with
`--target-profile`) stops the walk at applicable `consider`-level Galaxy
changes too, not only `must_fix`. Reproduced-by: `uv run --package
galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/test_cli.py -k
block_consider`.

- **Same boundary discipline as `--allow-behavior-change` (D16).** Requires a
  walk mode (`click.BadParameter` wrapping the typed `UpgradeFlagError`
  otherwise), and the contradictory pair `--block-consider
  --allow-behavior-change` is rejected up front (`UpgradeFlagConflict`) — the
  LBYL check lives in the command so the user gets a parameter-anchored
  message, mirroring the existing flag checks.
- **Threads through both phases.** The per-file transform passes it to
  `facade.upgrade`, and the whole-run imported-`@PROFILE@` phase passes it to
  `profile_token_site`, so a shared token bump is computed under the same gate
  as each importer's own walk (the D6 consistency rule).
- **Help text warns about the freeze.** Galaxy emits one consider change
  unconditionally at 16.04, so the flag's help says most low-baseline tools
  stop immediately — an informed opt-in, not a surprise.
