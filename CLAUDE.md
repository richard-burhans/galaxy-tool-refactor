# CLAUDE.md — galaxy-tool-refactor workspace

## Layout

```
galaxy-tool-refactor/
├── galaxy-tool-xml/          Tier 1 (parsing & validation)
├── galaxy-tool-xml-codemod/  Tier 2 (structure)
├── galaxy-tool-xml-fmt/      Tier 3 (formatting)
├── scripts/                  Shared maintainer scripts (not installed)
│   ├── corpus_check.py         validate | fmt | codemod subcommands
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
uv run --package galaxy-tool-xml         pytest galaxy-tool-xml/tests/
uv run --package galaxy-tool-xml-codemod pytest galaxy-tool-xml-codemod/tests/
uv run --package galaxy-tool-xml-fmt     pytest galaxy-tool-xml-fmt/tests/
```

## Lint / type-check

```bash
uv run ruff check galaxy-tool-xml/src galaxy-tool-xml-codemod/src galaxy-tool-xml-fmt/src
uv run mypy --config-file galaxy-tool-xml/pyproject.toml         galaxy-tool-xml/src
uv run mypy --config-file galaxy-tool-xml-codemod/pyproject.toml galaxy-tool-xml-codemod/src
uv run mypy --config-file galaxy-tool-xml-fmt/pyproject.toml     galaxy-tool-xml-fmt/src
```

## Corpus scripts

```bash
# Tier-1 invariants (parsing/validation): sweep validity vectors, retain crashes.
uv run python -m scripts.corpus_check validate [--source github|toolshed|combined] [--limit N]

# Tier-3 invariants (cosmetic formatting): sweep format()→format() idempotence.
uv run python -m scripts.corpus_check fmt [--repo NAME] [--limit N]

# Tier-2 invariants (one structural codemod at a time): sweep idempotence + post-codemod validity.
uv run python -m scripts.corpus_check codemod <dotted.module>:<ClassName> [--repo NAME] [--limit N]

uv run python -m scripts.fetch_schemas         # download release XSDs
uv run python -m scripts.fetch_toolshed        # clone Toolshed repos
uv run python -m scripts.regenerate            # regenerate per-version models
uv run python -m scripts.measure               # ad-hoc corpus queries
```

**Note:** invoke as `python -m scripts.X`, not `python scripts/X.py` — the
scripts import from `scripts._shared`, which requires `scripts` to be
importable as a package (i.e. the workspace root on `sys.path`).

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
- TDD for codemod-tier work — failing test first, then minimum code to pass.

## Architecture

Three tiers, each independently installable:

| Tier | Layer | Package | Owns |
|---|---|---|---|
| 1 | **parsing & validation** | `galaxy-tool-xml` | `load_tool` / `parse_tool` / `validate_tool`, typed xsdata views. **No serializer.** |
| 2 | **structure** | `galaxy-tool-xml-codemod` | `CodemodCommand` visitor framework + bundled structural codemods + `CANONICAL_CODEMODS` contract. |
| 3 | **formatting** | `galaxy-tool-xml-fmt` | Cosmetic rules (indent / blank line / empty-element shorthand). The only tier that writes XML to disk. |

**Tier 3 → tier 2 dependency is optional.** `galaxy-tool-xml-fmt`'s
library is cosmetic-only and has no codemod dependency. fmt's CLI
declares `galaxy-tool-xml-codemod` as an optional `[canonical]` extra
and runs `CANONICAL_CODEMODS` as a prelude when the extra is
installed. The project's preferred "format my tool" workflow uses all
three tiers; minimal installs (xml + fmt) get cosmetic-only output.

See `galaxy-tool-xml/docs/decisions.md` §9 for the three-tier
rationale; `galaxy-tool-xml-codemod/docs/decisions.md` §9 + §10 and
`galaxy-tool-xml-fmt/docs/decisions.md` §D10 for the
optional-extra split and the `CANONICAL_CODEMODS` rename.
