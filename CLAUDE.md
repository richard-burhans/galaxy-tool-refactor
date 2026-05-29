# CLAUDE.md — galaxy-tool-refactor workspace

## Layout

```
galaxy-tool-refactor/
├── galaxy-tool-refactor-rules/ Tier 0.5 (shared RuleMeta + glossary renderer)
├── galaxy-tool-xml/          Tier 1 (parsing & validation)
├── galaxy-tool-xml-codemod/  Tier 2 (structure)
├── galaxy-tool-xml-fmt/      Tier 3 (formatting)
├── galaxy-tool-refactor-cli/ Tier 4 (app CLI: format + upgrade)
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
uv sync          # installs all five packages + dev deps into .venv
```

## Test

```bash
uv run --package galaxy-tool-refactor-rules pytest galaxy-tool-refactor-rules/tests/
uv run --package galaxy-tool-xml            pytest galaxy-tool-xml/tests/
uv run --package galaxy-tool-xml-codemod    pytest galaxy-tool-xml-codemod/tests/
uv run --package galaxy-tool-xml-fmt        pytest galaxy-tool-xml-fmt/tests/
uv run --package galaxy-tool-refactor-cli   pytest galaxy-tool-refactor-cli/tests/
```

## Lint / type-check

```bash
uv run ruff check galaxy-tool-refactor-rules/src galaxy-tool-xml/src galaxy-tool-xml-codemod/src galaxy-tool-xml-fmt/src galaxy-tool-refactor-cli/src
uv run mypy --config-file galaxy-tool-refactor-rules/pyproject.toml galaxy-tool-refactor-rules/src
uv run mypy --config-file galaxy-tool-xml/pyproject.toml         galaxy-tool-xml/src
uv run mypy --config-file galaxy-tool-xml-codemod/pyproject.toml galaxy-tool-xml-codemod/src
uv run mypy --config-file galaxy-tool-xml-fmt/pyproject.toml     galaxy-tool-xml-fmt/src
uv run mypy --config-file galaxy-tool-refactor-cli/pyproject.toml galaxy-tool-refactor-cli/src
```

## Corpus scripts

```bash
# Tier-1 invariants (parsing/validation): sweep validity vectors, retain crashes.
uv run python -m scripts.corpus_check validate [--source github|toolshed|combined] [--limit N]

# Tier-3 invariants (cosmetic formatting): sweep format()→format() idempotence.
uv run python -m scripts.corpus_check fmt [--source github|toolshed|combined] [--repo NAME] [--limit N]

# Tier-2 invariants (one structural codemod at a time): sweep idempotence + post-codemod validity.
uv run python -m scripts.corpus_check codemod <dotted.module>:<ClassName> [--repo NAME] [--limit N]

# Per-rule isolation QA (every GTX rule alone, fmt + codemod): idempotence (+ post-validity
# for codemods), retain failures, write docs/corpus_rule_stats.md.
uv run python -m scripts.corpus_check rules [--source github|toolshed|combined] [--repo NAME] [--limit N]

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

Tiers, each independently installable:

| Tier | Layer | Package | Owns |
|---|---|---|---|
| 0.5 | **rule metadata** | `galaxy-tool-refactor-rules` | `RuleMeta` descriptor + `render_rule_reference_table`. Dependency-free; shared by tiers 2 & 3 so the GTX registry spans both. |
| 1 | **parsing & validation** | `galaxy-tool-xml` | `load_tool` / `parse_tool` / `validate_tool`, typed xsdata views. **No serializer.** |
| 2 | **structure** | `galaxy-tool-xml-codemod` | `CodemodCommand` visitor framework + bundled structural codemods (each carries a `RuleMeta` GTX code; see `catalog.coded_codemods()`) + `CANONICAL_CODEMODS` contract. |
| 3 | **formatting** | `galaxy-tool-xml-fmt` | Cosmetic rules (indent / blank line / empty-element shorthand) + the shared `cli_support` CLI engine. The only tier that writes XML to disk. |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` | The user-facing `galaxy-tool-refactor` CLI. Composes tiers 2 + 3 into `format` (canonicalise + cosmetic) and `upgrade` (repair + profile upgrade). |

**Orchestration lives in the app tier.** Each lower tier is consumable
standalone; none runs the end-to-end workflow. The app
(`galaxy-tool-refactor-cli`) hard-depends on codemod (tier 2) and fmt
(tier 3) and owns both commands:

- `galaxy-tool-refactor format` — `CANONICAL_CODEMODS` (repair +
  attribute order) then fmt's cosmetic rules. Safe, idempotent; never
  changes `profile=`.
- `galaxy-tool-refactor upgrade` — `AUTO_UPGRADE_CODEMODS` (repair, then
  iterative profile upgrade) then cosmetic formatting. Opt-in, semantic.

`galaxy-tool-xml-fmt`'s own CLI is **cosmetic-only** and has no codemod
dependency (the former `[canonical]` extra is gone). The library
(`format_tool_document`) is likewise cosmetic-only.

See `galaxy-tool-xml/docs/decisions.md` §9 for the three-tier
rationale; `galaxy-tool-refactor-cli/docs/decisions.md` §D1,
`galaxy-tool-xml-fmt/docs/decisions.md` §D12, and
`galaxy-tool-xml-codemod/docs/decisions.md` §16 for the app tier, the
fmt-CLI-cosmetic-only reversal, and the `CANONICAL_CODEMODS` /
`AUTO_UPGRADE_CODEMODS` split; and
`galaxy-tool-refactor-rules/docs/decisions.md` §D1 (+ codemod §15,
fmt §D11) for the shared `RuleMeta` extraction and the cross-tier
GTX registry.
