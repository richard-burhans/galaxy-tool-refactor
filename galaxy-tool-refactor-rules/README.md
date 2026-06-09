# galaxy-tool-refactor-rules

Shared **rule-metadata vocabulary** for the Galaxy tool refactoring framework —
a small, dependency-free "tier 0.5" package consumed by both higher tiers:

| Tier | Layer | Package |
|---|---|---|
| 0.5 | **rule metadata** | `galaxy-tool-refactor-rules` *(this package)* |
| 1 | parsing & validation | `galaxy-tool-xml` |
| 2 | structure | `galaxy-tool-xml-codemod` |
| 3 | formatting | `galaxy-tool-xml-fmt` |
| 3.5 | advisory checks | `galaxy-tool-xml-check` |
| 3.6 | rule registry / rulesets | `galaxy-tool-refactor-registry` |
| 4 | app / CLI | `galaxy-tool-refactor-cli` |

It provides:

- **`galaxy_tool_refactor_rules.meta.RuleMeta`** — a frozen dataclass describing
  one GTR rule (`code`, `summary`, `since`, `until`, `cite`, `order`,
  `detect_only`, `applies_to`). A tier-3 formatter `Rule`, a tier-2
  `CodemodCommand`, and a tier-3.5 `CheckRule` each carry a
  `meta: ClassVar[RuleMeta]`, so the tiers share one registry vocabulary.
- **`galaxy_tool_refactor_rules.violation.Violation`** — a frozen dataclass for a
  detect-phase finding (`code`, `sourceline`, `xpath`, `message`); the pure,
  lxml-free, read-only counterpart to the mutating tier-2 `Change` / tier-3 `Edit`.
- **`galaxy_tool_refactor_rules.reference.render_rule_reference_table`** — a pure
  helper that renders `(RuleMeta, tier)` pairs as a GitHub-flavored markdown
  glossary table.

## Why a separate package

The descriptor is the only thing the two tiers genuinely share — their
*behavioral* bases differ (fmt yields lxml edits; codemod walks a cursor), so
those stay in their own packages. Keeping `RuleMeta` here, with **zero runtime
dependencies**, lets both fmt and codemod depend on it without depending on each
other — preserving the tier independence documented in
`galaxy-tool-xml-fmt/docs/decisions.md` §D10. The extraction was anticipated in
that package's §D1 ("a shared rule-engine package will be extracted only when a
second consumer materialises"); the codemod tier is that consumer.

## Install / test

```bash
uv sync   # from the workspace root
uv run --package galaxy-tool-refactor-rules pytest galaxy-tool-refactor-rules/tests/
```
