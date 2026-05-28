# galaxy-tool-refactor

A uv workspace housing three independently-installable Python libraries for
parsing, validating, formatting, and refactoring Galaxy tool definition XML.

## Packages

| Package | PyPI status | Role |
|---|---|---|
| [`galaxy-tool-xml`](galaxy-tool-xml/README.md) | pre-release | Parse, validate, and inspect Galaxy tool XML. Foundation for the other tiers. |
| [`galaxy-tool-xml-fmt`](galaxy-tool-xml-fmt/README.md) | pre-release | Opinionated `black`-like formatter. The only tier that writes XML. |
| [`galaxy-tool-xml-codemod`](galaxy-tool-xml-codemod/README.md) | pre-alpha | Visitor/transformer framework for structural refactors. |

## Quick start

```bash
git clone <this-repo>
cd galaxy-tool-refactor
uv sync
```

## Architecture

The three tiers are designed to compose:

```
galaxy-tool-xml        ← parse, validate, typed views (lxml tree as source of truth)
     ↑
galaxy-tool-xml-fmt    ← formatter (reads tier 1 tree, writes canonical XML)
     ↑
galaxy-tool-xml-codemod ← structural refactors (visitor/transformer on tier 1 model)
```

For the full rationale, see `galaxy-tool-xml/docs/decisions.md` §9.

## Running tests

```bash
uv run --package galaxy-tool-xml     pytest galaxy-tool-xml/tests/
uv run --package galaxy-tool-xml-fmt pytest galaxy-tool-xml-fmt/tests/
uv run --package galaxy-tool-xml-codemod pytest galaxy-tool-xml-codemod/tests/
```

## Corpus scripts

Shared maintainer scripts live in `scripts/`. The corpus (cloned Galaxy tool
repositories) is stored in `corpus/` (gitignored) and seeded from
`corpus_sources.json`.

```bash
# Validate tier-1 API invariants against the corpus
uv run python scripts/corpus_check.py validate

# Check formatter idempotence against the corpus
uv run python scripts/corpus_check.py fmt

# Download/update Galaxy release XSDs
uv run python scripts/fetch_schemas.py

# Clone/update Toolshed repos
uv run python scripts/fetch_toolshed.py
```
