# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-xml-codemod` is tier 2 of the Galaxy tool refactoring
framework. Tier 1 (`galaxy-tool-xml`) provides parsing, profile-aware
validation, and per-release typed views. Tier 3 (`galaxy-tool-xml-fmt`) owns all XML serialization.

This package supplies the **structural-refactor framework**:
visitor / transformer base classes on top of `galaxy-tool-xml`'s typed
model, plus typed cursor mutation primitives shaped after LibCST (but
**not** a LibCST drop-in — see `docs/architecture.md` §Risks).

The architecture rationale lives in `docs/architecture.md` (a working
copy forked from `galaxy-tool-xml/docs/codemod-architecture.md`). Open
questions and the milestone plan are in `PLAN.md`.

## Coding standards

Hand-written code follows **dignified-python**, vendored at the workspace root
`.claude/skills/dignified-python/`:

- LBYL over `try/except`. Exceptions only at the CLI error boundary
  (chained `from e`) and at third-party API boundaries with no LBYL form.
- `pathlib.Path` with explicit `encoding="utf-8"` on text I/O.
- Keyword-only arguments after the first.
- Absolute imports, no re-exports, no `__all__`.
- No import-time side effects (`@cache` for module state).

`optimized-python` (`.claude/skills/optimized-python/`) is a secondary
reference; **dignified-python governs on conflict**.

## Workflow

- **Plan-driven**: major changes get a written plan (either under
  `~/.claude/plans/` for agent state, or in `PLAN.md` for repo-scoped
  plans) before implementation.
- **Empirical claims must be backed by data.** Use the workspace corpus
  artifacts (`../docs/corpus_data/`) and `../scripts/measure.py` when
  answering questions about real-world tool XML.
- **Decisions are recorded** in `docs/decisions.md` once they land
  (mirror the parent's `docs/decisions.md` conventions: §10 for
  testing-derived measurements, each entry citing the date and the
  exact reproduction command).
- See `galaxy-tool-xml/docs/decisions.md` §9 for the three-tier
  rationale.

## Commands

Run these from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync` — install dependencies
- `uv run --package galaxy-tool-xml-codemod pytest galaxy-tool-xml-codemod/tests/` — run tests
- `uv run ruff check galaxy-tool-xml-codemod/src` — lint
- `uv run mypy --config-file galaxy-tool-xml-codemod/pyproject.toml galaxy-tool-xml-codemod/src` — type-check (strict)

## Useful workspace references

- `galaxy-tool-xml/README.md` — tier-1 public API
- `galaxy-tool-xml/docs/decisions.md` §3 (trivia contract), §6 (corpus
  stats), §9 (three-tier vision)
- `galaxy-tool-xml/docs/codemod-architecture.md` — full tier-2 design
- `../docs/corpus_data/combined_corpus_data.json` — every swept Galaxy
  tool, indexed for ad-hoc analysis
- `../scripts/measure.py` — master script for empirical corpus queries
