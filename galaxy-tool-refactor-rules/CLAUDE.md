# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-refactor-rules` is the **rule-metadata** tier (tier 0.5) of the
Galaxy tool refactoring framework. It is a tiny, dependency-free package that
both tier 2 (`galaxy-tool-xml-codemod`) and tier 3 (`galaxy-tool-xml-fmt`)
depend on:

| Tier | Layer | Package |
|---|---|---|
| 0.5 | **rule metadata** | `galaxy-tool-refactor-rules` *(this repo)* |
| 1 | parsing & validation | `galaxy-tool-xml` |
| 2 | structure | `galaxy-tool-xml-codemod` |
| 3 | formatting | `galaxy-tool-xml-fmt` |

It owns exactly two things:

- `meta.py` — the `RuleMeta` frozen dataclass (the GTX rule descriptor).
- `reference.py` — `render_rule_reference_table`, a pure markdown renderer for
  a rule glossary.

**Invariant: stay dependency-free.** Do not import lxml, tier 1/2/3, or any
runtime dependency here. The whole point of this package is to be a shared
primitive that does not drag the tiers into each other — adding a dependency
would defeat that and risk re-coupling fmt to codemod (see
`galaxy-tool-xml-fmt/docs/decisions.md` §D10). The behavioral rule/codemod base
classes belong in their own tiers, not here.

## Coding standards

Hand-written code follows **dignified-python**, vendored at the workspace root
`.claude/skills/dignified-python/`:

- Absolute imports, no re-exports, no `__all__`.
- Keyword-only arguments after the first.
- No import-time side effects.
- Type hints throughout; mypy strict.

`optimized-python` (`.claude/skills/optimized-python/`) is a secondary
reference; **dignified-python governs on conflict**.

## Commands

Run these from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync` — install dependencies
- `uv run --package galaxy-tool-refactor-rules pytest galaxy-tool-refactor-rules/tests/` — run tests
- `uv run ruff check galaxy-tool-refactor-rules/src galaxy-tool-refactor-rules/tests` — lint
- `uv run mypy --config-file galaxy-tool-refactor-rules/pyproject.toml galaxy-tool-refactor-rules/src` — type-check (strict)

## Useful workspace references

- `galaxy-tool-xml-fmt/src/galaxy_tool_xml_fmt/rules.py` — the tier-3 `Rule` ABC
  that carries `meta: ClassVar[RuleMeta]`.
- `galaxy-tool-xml-codemod/src/galaxy_tool_xml_codemod/catalog.py` — the tier-2
  catalog of GTX-coded codemods.
- `scripts/corpus_check.py` — the stat-page generator that renders the
  cross-tier rule reference table via `render_rule_reference_table`.
