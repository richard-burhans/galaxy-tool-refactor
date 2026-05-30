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
  (so the GTX rule registry spans both tiers) is that second consumer.
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
§D2. The cross-tier GTX registry at the time spanned GTX001–GTX012 (3 fmt rules,
9 codemods); it later grew GTX013 (codemod §17) and the IUC advisory codes
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
