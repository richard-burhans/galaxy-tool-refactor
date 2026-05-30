# Plan — detect/fix rule split (in progress)

Working plan for the detect/fix rule-split effort. **Status: PR1–PR4 landed.
PR5 not yet started.** This doc is the resume point — read it top to bottom to
pick the work back up cold. It is being superseded by per-tier
`docs/decisions.md` entries as the work lands (PR1 → `galaxy-tool-xml-codemod`
§19, `galaxy-tool-refactor-rules` D2; PR2 → `galaxy-tool-xml-fmt` D14; PR3 →
`galaxy-tool-refactor-cli` D2; PR4 → `galaxy-tool-xml-check` D1 +
`galaxy-tool-refactor-cli` D3 + `galaxy-tool-refactor-rules` D-detect_only),
then removed.

**PR1 done (2026-05-30):** tier-0.5 `Violation`; tier-2 `Change` /
`apply_changes`; `CodemodCommand` is detect-primitive (`detect_<Tag>` walk,
`apply` derived); `Cursor` gained `sourceline` / `xpath` and
`would_reorder_attributes` / `would_reorder_children`; GTX002/005/013 converted
to detect+apply; validation-driven codemods got coarse `detect`
(`codemods/_coarse_detect.py`); `corpus_check codemod` enforces the
detect⇔modified parity invariant. Reorderer modified counts unchanged
(GTX002 6,075 · GTX005 1,020 · GTX013 4,640), 0 parity mismatches across 8,607
eligible tools.

**PR2 done (2026-05-30):** fmt `detect_tool_document` (`galaxy-tool-xml-fmt/
detect.py`) — non-mutating, per-occurrence `Violation`s via **net-diff + owner
attribution** (format a copy, record the last rule to touch each node, diff vs
original; net-zero churn is silent so canonical docs report nothing). Naive
per-edit mapping over-reports because GTX001/GTX003 overlap on tails. Includes
Comment/PI tails. `corpus_check fmt` enforces detect⇔format-changes parity:
8,608 tools, 8,608 idempotent, 0 parity mismatches. See `galaxy-tool-xml-fmt`
D14.

**PR3 done (2026-05-30):** report-only `galaxy-tool-refactor check` subcommand
(`galaxy-tool-refactor-cli/cli.py`). `_detect_violations` composes the canonical
codemods' `detect` (`Change.to_violation()`) + fmt `detect_tool_document`; prints
`file:line  CODE  message` sorted by line, exit 1 on findings/errors. Reuses
`cli_support.iter_targets`/`is_tool_root`/`load_tool` (own loop, NOT
`_process_file`). Scope = the `format` rule set (not `upgrade` — too noisy).
See `galaxy-tool-refactor-cli` D2.

**PR4 done (2026-05-30):** new tier-3.5 package `galaxy-tool-xml-check`
(`CheckRule` ABC + `IUC001`–`IUC012` + `all_checks`/`detect_violations`); depends
only on tiers 1 + 0.5. Added `RuleMeta.detect_only` (tier 0.5). 10 real checks
(tests/command-CDATA/id-charset/version/requirements/error-handling/EDAM-xrefs/
help/description/help-CDATA), 2 reserved placeholders (IUC011 Cheetah, IUC012
`&&`-vs-`&` — no-op stubs, deferred per maintainer). `check` runs them as
**advisory**: findings shown + marked `(advisory)`, exit stays 0 unless `--strict`
(fixable GTX findings still exit 1). Corpus sanity (2,000 tools): hit rates
0.7%–91%, none at 0/100% except placeholders. See `galaxy-tool-xml-check` D1,
cli D3.

Branch: `detect-fix-rule-split` (off `main` @ the GTX013 merge, `db66c7c`).

## Goal (committed design — 4 decisions, decided 2026-05-29)

Restructure the rule system so every rule has two phases, the `ruff check` /
`ruff format` model:

- a **detect (lint)** phase that reports whether/where the tool XML violates the
  rule (non-mutating);
- a **fix** phase (the current paradigm) that mutates.

Why: (1) a real lint capability, (2) richer corpus stats (per-rule *violation*
counts, not just "touched"), and (3) a home for the ~40 non-auto-fixable IUC
best-practices (`docs/iuc_best_practices.md` bucket 4) as **detect-only rules**
in the same shared GTX/IUC registry.

The four locked decisions:

1. **Timing** — separate effort/branch *after* GTX013 landed. (Done: GTX013 is
   merged via PR #14.)
2. **Codemod detect mechanism** — refactor codemods to **yield a non-mutating
   change-list** (like fmt's `Edit` list), *not* a coarse dry-run+diff. Every
   `CodemodCommand.apply` (in-place mutation today) must be reworked to produce
   changes first. fmt is already half-way (`Rule.apply(tree) -> Iterable[Edit]`
   computes edits before the engine applies them, so the edit list IS fmt's
   detection result — no drift risk).
3. **Granularity** — per-occurrence: each violation carries a location
   (line/xpath) + message + rule code.
4. **CLI** — a new report-only `galaxy-tool-refactor check` command covering all
   rules including detect-only, alongside `format` / `upgrade`.

## Architecture findings (from this session's exploration)

### Tier 0.5 — `galaxy-tool-refactor-rules`
- `meta.py`: `RuleMeta` frozen dataclass — `code, summary, since, until, cite,
  order`. No detect/fix capability flag yet. Dependency-free (must stay so).
- `reference.py`: `render_rule_reference_table` — pure markdown glossary renderer.

### Tier 3 — `galaxy-tool-xml-fmt` (already detect/fix-shaped)
- `rules.py`: `Rule` ABC, `apply(tree) -> Iterable[Edit]`.
- `edits.py`: `Edit` is a frozen-dataclass discriminated union
  (`NoOp | SetText | SetTail | ClearText`); `apply_edits` dispatches via
  `match/case` — the single mutation site, honours the CDATA whitespace guard.
- `format.py`: `format_tool_document` runs `all_rules()` and applies edits
  immediately. **The edit list is the detection result already** — but `Edit`s
  carry no rule code / message; the *rule* carries `meta.code`. To surface as
  violations, map each edit (or the rule's edit batch) to `(code, location,
  message)`.
- `cli_support.py`: shared engine — `iter_targets`, `is_tool_root`,
  `run(transform=...)` built around **rewrite + drift detection** (`--check` /
  `--diff` / `--quiet`). A `check` report path should reuse `iter_targets` /
  `is_tool_root` but NOT `_process_file` (that path writes / diffs bytes).

### Tier 2 — `galaxy-tool-xml-codemod` (the big lift)
- `codemod.py`: `CodemodCommand.apply(module)` walks the tree (`_dispatch`) and
  calls `visit_<TagPascalCase>(cursor)`; mutations happen **immediately** via the
  `Cursor`. Hooks: `corpus_eligible`, `corpus_validation_profile`,
  `upgrade_steps_applied`.
- `cursor.py`: mutation primitives — `set_attribute`, `delete_attribute`,
  `rename_attribute`, `rename_tag`, `remove`, `add_child`, `reorder_attributes`,
  `reorder_children`. (These are the mutation kinds a declarative change union
  would need to cover.)
- Two codemod shapes:
  - **(a) visit-walkers** — `ReorderParamAttributes` (GTX002),
    `ReorderToolAttributes` (GTX005), `ReorderToolChildren` (GTX013). Pure
    structural, call one Cursor mutator per matched element. *Easy to split into
    detect + apply.*
  - **(b) validation-driven `apply` overrides** — `FixTypos` (GTX006),
    `UpdateProfile` (GTX007), `UpgradeToLatest` (GTX012) + per-step
    `Upgrade19_01/24_0/24_1/25_1` (GTX008–011). Iterative, re-validate between
    steps, depend on profile. *Cannot statically pre-compute a change-list.*
- `canonical.py`: `CANONICAL_CODEMODS` (FixTypos → ReorderParamAttributes →
  ReorderToolAttributes → ReorderToolChildren) and `AUTO_UPGRADE_CODEMODS`
  (FixTypos → UpgradeToLatest).
- `catalog.py`: `coded_codemods()` — every GTX-coded codemod, for the registry.

### Tier 4 — `galaxy-tool-refactor-cli`
- `cli.py`: `format` / `upgrade`, each a `cli_support.run(transform=…)` call.
  New `check` command goes here as a report-only third subcommand.

### `scripts/corpus_check.py`
- `codemod` sweep classifies via `_codemod_exercise`: measures "modified" by
  **byte-diff** (pass-1 vs before) and checks idempotence by re-parse + re-apply.
  With `detect()`, per-rule *violation counts* come straight from the change-list
  (no byte-diff needed), and detect/apply parity (detect-found ⇔ apply-changed)
  becomes a new sweep invariant.
- `rules` sweep does per-rule isolation; `_sweep_codemod_isolated` /
  `_sweep_fmt_rule`. Detect-only rules need coverage here too.

## Proposed design (to confirm in plan-mode next session)

Core mechanism (decision #2). Introduce a codemod-tier **`Change`** describing
one structural mutation, carrying `(code, location[sourceline + xpath/tag],
message)`. `CodemodCommand` gains `detect(module) -> Iterable[Change]`; `apply`
becomes "apply the detected changes" for the visit-walkers.

**OPEN sub-decision — `Change` representation:**
- *Declarative union* (mirror fmt's `Edit`): `ReorderAttributes / RenameTag /
  RemoveElement / SetAttribute / AddChild / …` + `apply_changes` dispatcher. Pure
  data, inspectable, exact parity with fmt. Larger enumeration up front.
- *Thunk-carrying* `Change`: `(code, location, message)` + a closure that
  performs the mutation via the existing `Cursor` primitives. Minimal disruption
  (current mutation code becomes the closure body), still non-mutating until
  applied, detect list still IS the report. Less "pure data".
- Leaning thunk-carrying for the walkers (reuses Cursor, one mutation site);
  revisit if a declarative union proves cleaner. **Ask the user.**

**Validation-driven codemods (shape b):** can't pre-compute a static
change-list. Proposal: `detect()` reports a single coarse "would change"
occurrence (or run-on-copy + diff), `apply` stays bespoke. Acceptable because
lint value concentrates in the structural + detect-only rules. **Confirm.**

**Detect-only rules (bucket 4, ~12 mechanically-detectable):** new IUC-coded
rules, `detect()` only / no fix, in the shared registry. **OPEN:** where they
live (new small check library vs. existing tier) and where the cross-tier
`Violation`/diagnostic type lives (tier 0.5 candidate — but it must stay
lxml-free; a location is just `int` line + `str` xpath, so that may be fine).

**`RuleMeta`:** likely grows a capability flag (e.g. `fixable: bool` /
`detect_only`) so the registry, `check`, and docs know which rules mutate.

## Incremental roadmap (one PR per step; TDD; corpus sweep gates each)

1. **Framework** — `Change` + `detect()` / `apply_changes` in codemod tier;
   refactor the 3 visit-walker reorderers to detect+apply; validation-driven
   codemods keep bespoke `apply` with coarse `detect`. Sweep parity: detect
   counts vs byte-diff `modified`.
2. **fmt violations** — surface the `Edit` list as `(code, location, message)`
   violations; settle the shared `Violation`/diagnostic shape.
3. **CLI `check`** — report-only subcommand over codemod + fmt rules;
   per-occurrence `file:line  CODE  message`; non-zero exit on findings.
4. **Detect-only IUC rules** — implement the detectable bucket-4 subset; wire
   into `check`, the registry, and `docs/iuc_best_practices.md`.
5. **corpus_check** — per-rule violation counts; cover detect-only rules;
   regenerate stat pages.

Constraints throughout: dignified-python governs; keyword-only after first arg;
absolute imports, no re-exports/`__all__`; `pathlib` + explicit UTF-8; LBYL;
TDD (failing test first); record decisions in the owning tier's
`docs/decisions.md`; back empirical claims with corpus sweeps.

## Open questions to resolve before implementing
1. `Change` representation: declarative union vs. thunk-carrying closure.
2. Validation-driven codemods: coarse `detect` (single "would change") vs.
   run-on-copy + structural diff.
3. Home for detect-only rules + the `Violation` type (new package vs. existing
   tier; can the location type stay in dependency-free tier 0.5?).
4. First-PR scope (framework + reorderers only, or include a `check` skeleton).
