# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-refactor-cli` is the **app tier** (tier 4) of the Galaxy tool
refactoring framework: the only package that composes the lower tiers into a
user-facing workflow.

| Tier | Layer | Package |
|---|---|---|
| 0.5 | rule metadata | `galaxy-tool-refactor-rules` |
| 1 | parsing & validation | `galaxy-tool-xml` |
| 2 | structure | `galaxy-tool-xml-codemod` |
| 3 | formatting | `galaxy-tool-xml-fmt` |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` *(this repo)* |

It depends on codemod (tier 2) and fmt (tier 3) and exposes the
`galaxy-tool-refactor` CLI with two subcommands:

- `format` — apply `CANONICAL_CODEMODS` (repair + attribute order) then fmt's
  cosmetic rules. Safe, idempotent, never changes `profile=`.
- `upgrade` — apply `AUTO_UPGRADE_CODEMODS` (repair, then iterative profile
  upgrade) then cosmetic formatting. Opt-in and semantic.

Both reuse fmt's `cli_support` engine (file walking, `--check`/`--diff`/`--quiet`,
drift detection, summary); the subcommands differ only in which codemod pipeline
they apply. Both serialize through fmt — which is *why* this tier sits above
fmt (a writer inside codemod would invert the tiers, since fmt already depends
on codemod's contracts conceptually). See `docs/decisions.md` §D1 and
`galaxy-tool-xml-fmt/docs/decisions.md` §D12.

## Coding standards

Hand-written code follows **dignified-python** (vendored at the workspace root
`.claude/skills/dignified-python/`): LBYL over try/except; exceptions only at
the CLI error boundary; `pathlib.Path` with explicit `encoding="utf-8"`;
keyword-only args after the first; absolute imports, no re-exports, no
`__all__`; no import-time side effects. `optimized-python` is a secondary
reference; **dignified-python governs on conflict**.

## Commands

Run from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync` — install dependencies
- `uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/` — run tests
- `uv run ruff check galaxy-tool-refactor-cli/src galaxy-tool-refactor-cli/tests` — lint
- `uv run mypy --config-file galaxy-tool-refactor-cli/pyproject.toml galaxy-tool-refactor-cli/src` — type-check (strict)
- `uv run galaxy-tool-refactor format <file>` / `uv run galaxy-tool-refactor upgrade <file>` — run the CLI

## Useful workspace references

- `galaxy-tool-xml-codemod/src/galaxy_tool_xml_codemod/canonical.py` — the
  `CANONICAL_CODEMODS` / `AUTO_UPGRADE_CODEMODS` pipeline contracts this CLI runs.
- `galaxy-tool-xml-fmt/src/galaxy_tool_xml_fmt/cli_support.py` — the shared
  file-processing engine.
- `galaxy-tool-xml-fmt/src/galaxy_tool_xml_fmt/format.py` — `format_tool_document`,
  the serializer this CLI writes through.
