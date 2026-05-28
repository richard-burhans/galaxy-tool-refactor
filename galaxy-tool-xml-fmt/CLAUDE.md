# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-xml-fmt` is the **formatting** tier of the Galaxy tool
refactoring framework — one of three layers:

| Tier | Layer | Package | Owns |
|---|---|---|---|
| 1 | **parsing & validation** | `galaxy-tool-xml` | parse · XSD validate · typed views |
| 2 | **structure** | `galaxy-tool-xml-codemod` | structural mutations |
| 3 | **formatting** | `galaxy-tool-xml-fmt` *(this repo)* | cosmetic formatting; the only tier that writes XML to disk |

The fmt tool is opinionated like `black`: a single canonical
formatting per input, no user-tunable style. The opinionated choice
goes here so the lower tiers can ignore trivia (indentation, quote
style, attribute spacing, empty-element shorthand) entirely.

**Tier independence.** This package's library
(`format_tool_document`) does **not** depend on
`galaxy-tool-xml-codemod`. Cosmetic-only formatting is fully
functional with just `galaxy-tool-xml + galaxy-tool-xml-fmt` installed.

For the project's preferred (fully-canonical) workflow — structural
canonicalisation **then** cosmetic formatting — install the
`[canonical]` extra (`pip install galaxy-tool-xml-fmt[canonical]`) and
use the `galaxy-tool-xml-fmt` CLI. When the extra is present, the CLI
runs `galaxy_tool_xml_codemod.canonical.CANONICAL_CODEMODS` before
fmt's cosmetic rules. Without the extra, the CLI prints a one-line
hint at startup and proceeds with cosmetic rules only.

## Coding standards

Hand-written code follows **dignified-python**, vendored at the workspace root
`.claude/skills/dignified-python/`:

- LBYL over `try/except`. Exceptions only at the CLI error boundary
  (chained `from e`) and at third-party API boundaries with no LBYL form.
- `pathlib.Path` with explicit `encoding="utf-8"` on text I/O.
- Keyword-only arguments after the first.
- Absolute imports, no re-exports, no `__all__`.
- No import-time side effects (`@cache` for module state).

`optimized-python` (`.claude/skills/optimized-python/`) is a secondary reference;
**dignified-python governs on conflict**.

## Workflow

- **Plan-driven**: major changes get a written plan (either under
  `~/.claude/plans/` for agent state, or in `PLAN.md` for repo-scoped
  plans) before implementation.
- **Empirical claims must be backed by data.** Use the workspace corpus
  artifacts (`../docs/corpus_data/`) and `../scripts/measure.py` when
  answering questions about real-world tool XML.
- **Decisions are recorded** in `docs/decisions.md` once they land
  (mirror the parent's conventions: each entry cites a date and a
  reproducible measurement command).
- See `galaxy-tool-xml/docs/decisions.md` §3 (representation /
  trivia contract) and §9 (three-tier vision) for the rationale this
  tool inherits.

## Commands

Run these from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync` — install dependencies
- `uv run --package galaxy-tool-xml-fmt pytest galaxy-tool-xml-fmt/tests/` — run tests
- `uv run ruff check galaxy-tool-xml-fmt/src` — lint
- `uv run mypy --config-file galaxy-tool-xml-fmt/pyproject.toml galaxy-tool-xml-fmt/src` — type-check (strict)
- `uv run python -m scripts.corpus_check fmt` — sweep corpus for cosmetic-pipeline idempotence
- `uv run python -m scripts.corpus_check codemod <dotted.module>:<ClassName>` — sweep a structural codemod (tier 2 subcommand)

## Useful workspace references

- `galaxy-tool-xml/README.md` — tier-1 public API and the trivia
  contract this formatter respects
- `galaxy-tool-xml/docs/decisions.md` §3 (representation), §9
  (three-tier vision)
- `galaxy-tool-xml-codemod/src/galaxy_tool_xml_codemod/canonical.py` —
  the `CANONICAL_CODEMODS` contract the CLI runs as a prelude
- `src/galaxy_tool_xml_fmt/cli.py` — the orchestrator with the
  optional-codemod try-import
- `../docs/corpus_data/combined_corpus_data.json` — the real-world
  distribution of tool XML idioms the formatter must preserve idempotently
