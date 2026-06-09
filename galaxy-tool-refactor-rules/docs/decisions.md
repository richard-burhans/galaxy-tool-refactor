# Decisions — galaxy-tool-refactor-rules

Each entry records a decision once it lands: a date, the decision, and the
rationale. Mirrors the conventions of the sibling packages' `docs/decisions.md`.

## D1 (2026-05-29) — Extract the shared `RuleMeta` into its own tier-0.5 package

### Decision

The `RuleMeta` descriptor (previously private to `galaxy-tool-xml-fmt`) and a
pure markdown rule-glossary renderer now live in a new, dependency-free package
`galaxy-tool-refactor-rules`. Both tier 3 (`galaxy-tool-xml-fmt`) and tier 2
(`galaxy-tool-xml-codemod`) depend on it; neither depends on the other.

Only the *metadata* moved. The behavioral bases stayed in their tiers:
`galaxy_tool_xml_fmt.rules.Rule` (yields lxml `Edit`s) and
`galaxy_tool_xml_codemod.codemod.CodemodCommand` (cursor-walk visitor) have
different execution contracts and are not unified.

### Rationale

- **A documented trigger, now met.** `galaxy-tool-xml-fmt/docs/decisions.md` §D1
  §Layout said a shared rule package would be extracted "only when a second
  consumer materialises." Giving the codemod tier the same metadata vocabulary
  (so the GTR rule registry spans both tiers) is that second consumer.
- **Tier independence is preserved, not weakened.** The standing constraint
  (fmt's library must not depend on codemod — §D10 there) is about not dragging
  the *structural framework* into cosmetic-only installs. A metadata-only
  package with **zero runtime dependencies** is a shared primitive like tier 1,
  not the structural framework; both tiers can depend on it safely.
- **Dependency-free by design.** Keeping lxml / edits / cursor out of this
  package is what makes it a safe shared dependency. The package ships a
  `py.typed` marker and is type-checked under mypy strict.

### Scope

`RuleMeta` fields at the time of this extraction were the fmt original (`code`,
`summary`, `since`, `until`, `cite`, `order`); `detect_only` was added later in
§D2. The cross-tier GTR registry at the time spanned GTR001–GTR012 (3 fmt rules,
9 codemods); it later grew GTR013 (codemod §17) and the advisory codes
(tier 3.5, `galaxy-tool-xml-check`). Codes are globally unique across the tiers
(asserted by a test in `galaxy-tool-xml-fmt`'s corpus-check suite, which can
import both tiers).

## D2 (2026-05-30) — Add the shared `Violation` diagnostic type

### Decision

A `Violation` frozen dataclass joins `RuleMeta` in this tier-0.5 package
(`violation.py`). It is the per-occurrence result of a rule's **detect (lint)**
phase: `code` (matching `RuleMeta.code`), `sourceline` (1-based `int`, `0` when
the element has no source position), `xpath` (`str`), and `message`. It is the
read-only counterpart to the mutating tier-2 `Change` and tier-3 `Edit`.

This lands as part of the detect/fix rule-split effort (see
`galaxy-tool-xml-codemod/docs/decisions.md` §19; the effort, PR1–5, merged in
#15). Tier-2 `Change` projects onto a `Violation` via `Change.to_violation()`.

### Rationale

- **One shared diagnostic vocabulary.** Both the codemod (tier 2) and formatter
  (tier 3) detect phases, the future report-only `check` CLI (tier 4), and the
  planned advisory check library all surface findings; a single `Violation`
  type lets them do so without depending on one another — the same role
  `RuleMeta` plays for the rule registry.
- **Dependency-free is preserved.** The location is a plain `int` line plus a
  `str` xpath, never an lxml handle, so this package stays free of lxml / tier
  1/2/3 imports (the invariant from D1 and `galaxy-tool-xml-fmt` §D10). Putting
  `Violation` in tier 2 instead would have forced fmt to import codemod once fmt
  surfaces its edits as violations — exactly the re-coupling the tier split
  exists to prevent.

### Scope

`Violation` is pure data with no methods beyond the dataclass. A capability flag
on `RuleMeta` (e.g. `detect_only`) is deferred until detect-only rules arrive
(roadmap PR4), so the flag has a first non-default user when added.

## D3 (2026-05-30) — `RuleMeta.applies_to` (document-kind applicability)

### Decision

`RuleMeta` gains `applies_to: frozenset[str]` (default `frozenset({"tool"})`) —
the document kinds a rule operates on, a subset of `{"tool", "macro"}`. A generic
XML rule (canonical indentation GTR001, empty-element shorthand GTR004) declares
`{"tool", "macro"}`; a tool-structural rule (blank line between `<tool>` sections
GTR003, attribute / element order, profile upgrades) keeps the default `{"tool"}`;
a future macro-library rule declares `{"macro"}`. Consumers run a rule against a
document only when the document's kind is in this set (fmt's `rules_for_kind`,
and later the registry/codemod tiers).

### Rationale

- **One field drives fmt *and* codemods.** Phase 2 of the macro-aware effort
  needs to run rules on macro-library files (`<macros>` root); rather than a
  bespoke "is this rule macro-safe?" check per tier, applicability becomes rule
  metadata, read uniformly wherever a document of a given kind is formatted or
  codemodded.
- **Default `{"tool"}` is conservative and churn-free.** Every existing rule is
  tool-structural by history, so the default leaves them unchanged; only the two
  generic whitespace rules are explicitly widened. A rule runs on a macro file
  only when it opts in.
- **A set, not a single `scope` enum.** "Applies to any XML" is just "both
  kinds", so a `frozenset` avoids a special `"any"` value and extends cleanly if
  another document kind ever appears. See `galaxy-tool-xml-fmt/docs/decisions.md`
  §D16 for the fmt-side consumption (`format_macro_document` / `rules_for_kind`).


## D4 (2026-06-09) — `RuleMeta.rulesets` + the `Ruleset` catalog

### Decision

Add `rulesets: frozenset[str] = frozenset()` to `RuleMeta` and a dependency-free
`rulesets.py` (a `Ruleset(name, description)` catalog + `DEFAULT_RULESET`). This is the
maintainer-facing "mark which rules belong to which set" mechanism: a rule declares its
set membership on its own meta, and the registry tier (3.6) derives `name → codes` by
grouping rules by these names (registry D15). The catalog holds the names + descriptions
because that is a property of the *set*, not of any member; names are plain strings so a
rule in any tier can declare membership without a heavier import. `order` is now used by
**both** the fmt and codemod families (each ordered independently) — its docstring was
corrected accordingly, since the canonical pipeline's order moved off the old hardcoded
`CANONICAL_CODEMODS` tuple onto `meta.order`. Staying dependency-free is preserved (only
`dataclasses`). The default empty `rulesets` means "never independently selectable" (e.g.
an upgrade-only codemod driven by `UpgradeToLatest`).

### Reproduction

```sh
uv run --package galaxy-tool-refactor-rules pytest \
  galaxy-tool-refactor-rules/tests/test_rulesets.py galaxy-tool-refactor-rules/tests/test_meta.py
```

## D5 (2026-06-09) — `RuleMeta.planemo_linters` (the planemo-name alias)

### Decision

Add `planemo_linters: frozenset[str] = frozenset()` to `RuleMeta`: the planemo
(`galaxy.tool_util.lint`) linter class names a rule covers (e.g. GTR028 →
`{"HelpMissing", "HelpEmpty"}`). One GTR rule may cover several planemo linters —
planemo splits some single practices across linter classes, and our rule is the
natural unit (a survey found 21 of 25 such bundles are one practice). Formalizing
the mapping (previously only in docstrings + the hand-maintained parity table) on
the rule makes it the single source of truth: the registry (D16) derives a
`planemo name → GTR code` index for name-based selection and **generates** the
parity table from it. Empty for our own rules with no planemo equivalent (the
cosmetic fmt rules, the XSD-restoring repairs). Dependency-free (just strings).

### Reproduction

```sh
uv run --package galaxy-tool-refactor-rules pytest galaxy-tool-refactor-rules/tests/test_meta.py
```
