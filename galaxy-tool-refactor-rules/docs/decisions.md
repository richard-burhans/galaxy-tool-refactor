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

`RuleMeta` fields are unchanged from the fmt original (`code`, `summary`,
`since`, `until`, `cite`, `order`). The cross-tier GTX registry after this change
spans GTX001–GTX012 (3 fmt rules, 9 codemods); codes are globally unique across
the two tiers (asserted by a test in `galaxy-tool-xml-fmt`'s corpus-check suite,
which can import both tiers).
