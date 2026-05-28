# CLAUDE.md — galaxy-tool-refactor workspace

## Layout

```
galaxy-tool-refactor/
├── galaxy-tool-xml/          Tier 1 — parse, validate, typed views
├── galaxy-tool-xml-fmt/      Tier 3 — black-like formatter
├── galaxy-tool-xml-codemod/  Tier 2 — structural-refactor framework
├── scripts/                  Shared maintainer scripts (not installed)
│   ├── corpus_check.py         validate | fmt subcommands
│   ├── fetch_schemas.py        download release XSDs
│   ├── fetch_toolshed.py       clone Toolshed repos
│   ├── measure.py              ad-hoc corpus queries
│   └── regenerate.py           regenerate per-version xsdata models
├── docs/
│   └── corpus_data/            per-tool JSON/TSV from corpus sweeps
├── corpus/                   cloned Galaxy tool repos (gitignored)
└── corpus_sources.json       list of GitHub repos to clone
```

## Install

```bash
uv sync          # installs all three packages + dev deps into .venv
```

## Test

```bash
uv run --package galaxy-tool-xml     pytest galaxy-tool-xml/tests/
uv run --package galaxy-tool-xml-fmt pytest galaxy-tool-xml-fmt/tests/
uv run --package galaxy-tool-xml-codemod pytest galaxy-tool-xml-codemod/tests/
```

## Lint / type-check

```bash
uv run ruff check galaxy-tool-xml/src
uv run ruff check galaxy-tool-xml-fmt/src
uv run mypy --config-file galaxy-tool-xml/pyproject.toml     galaxy-tool-xml/src
uv run mypy --config-file galaxy-tool-xml-fmt/pyproject.toml galaxy-tool-xml-fmt/src
```

## Corpus scripts

```bash
uv run python scripts/corpus_check.py validate [--source github|toolshed|combined] [--limit N]
uv run python scripts/corpus_check.py fmt      [--repo NAME] [--limit N]
uv run python scripts/fetch_schemas.py         # download release XSDs
uv run python scripts/fetch_toolshed.py        # clone Toolshed repos
uv run python scripts/regenerate.py            # regenerate per-version models
uv run python scripts/measure.py               # ad-hoc corpus queries
```

## Coding standards

All hand-written code follows **dignified-python** (governs), with
**optimized-python** as a secondary reference. Both skills are vendored at
`.claude/skills/dignified-python/` and `.claude/skills/optimized-python/`.

Key rules:
- LBYL over `try/except`; exceptions only at CLI error boundary (chained `from e`)
  and at third-party API boundaries where no LBYL alternative exists.
- `pathlib.Path` with explicit `encoding="utf-8"` on all text I/O.
- Keyword-only arguments after the first.
- Absolute imports, no re-exports, no `__all__`.
- No import-time side effects (`@cache` for module state).

## Architecture

Three tiers, each independently installable:

| Package | Role |
|---|---|
| `galaxy-tool-xml` | Parse (`load_tool`), validate, typed xsdata views. **No serializer.** |
| `galaxy-tool-xml-fmt` | Black-like formatter; the only tier that writes XML to disk. |
| `galaxy-tool-xml-codemod` | Visitor/transformer framework for structural refactors (pre-alpha). |

See `galaxy-tool-xml/docs/decisions.md` §9 for the three-tier rationale.
See `galaxy-tool-xml/docs/codemod-architecture.md` for the Tier 2 design.
See `galaxy-tool-xml-codemod/PLAN.md` for Tier 2 milestone planning.
