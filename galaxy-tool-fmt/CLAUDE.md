# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-fmt` is the **formatting** tier of the Galaxy tool
refactoring framework — one of seven tiers (this package depends only on tier 1
and the shared tier-0.5 rules metadata):

| Tier | Layer | Package | Owns |
|---|---|---|---|
| 0.5 | **rule metadata** | `galaxy-tool-refactor-rules` | shared `RuleMeta` + `Violation` |
| 1 | **parsing & validation** | `galaxy-tool-source` | parse · XSD validate · typed views |
| 2 | **structure** | `galaxy-tool-codemod` | structural mutations |
| 3 | **formatting** | `galaxy-tool-fmt` *(this repo)* | cosmetic formatting (+ non-mutating `detect`); the only tier that serialises canonical output XML |
| 3.5 | **advisory checks** | `galaxy-tool-lint` | detect-only IUC best-practice checks |
| 3.6 | **rule registry / rulesets** | `galaxy-tool-refactor-registry` | unified rule registry + rulesets; library-first facade |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` | composes the tiers via the facade (`format`/`upgrade`/`check`) |

The fmt tool is opinionated like `black`: a single canonical
formatting per input, no user-tunable style. The opinionated choice
goes here so the lower tiers can ignore trivia (indentation, quote
style, attribute spacing, empty-element shorthand) entirely.

It formats both **tool** files (`<tool>` root) and **macro-library** files
(`<macros>` root). Each rule declares the document kinds it applies to via
`RuleMeta.applies_to` (`format.rules_for_kind`): the generic XML rules (GTR001
indent, GTR004 shorthand) run on both; the tool-only blank-line rule (GTR003)
runs on tools only. `format_macro_document` is the `<macros>` counterpart to
`format_tool_document`; the CLI opts into macro files via `cli_support.run`'s
`macro_transform` (see `docs/decisions.md` §D16, rules §D3).

**Tier independence.** This package — both the library
(`format_tool_document`) and the `galaxy-tool-fmt` CLI — is
**cosmetic-only** and does **not** depend on `galaxy-tool-codemod`.
It works with just `galaxy-tool-source + galaxy-tool-fmt` installed.

For the fully-canonical and profile-upgrade workflows, use the
`galaxy-tool-refactor` app CLI (`galaxy-tool-refactor-cli`, tier 4),
which composes the codemod and fmt tiers. Orchestration lives there,
not here — fmt's CLI no longer runs codemods (the former `[canonical]`
extra was removed; see `docs/decisions.md` §D12). This package does
own the shared CLI engine `cli_support.py` (file walking,
`--check`/`--diff`/`--quiet`, drift detection), which both fmt's CLI
and the app's CLI consume.

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
- See `galaxy-tool-source/docs/decisions.md` §3 (representation /
  trivia contract) and §9 (three-tier vision) for the rationale this
  tool inherits.

## Commands

Run these from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync` — install dependencies
- `uv run --package galaxy-tool-fmt pytest galaxy-tool-fmt/tests/` — run tests
- `uv run ruff check galaxy-tool-fmt/src` — lint
- `uv run mypy --config-file galaxy-tool-fmt/pyproject.toml galaxy-tool-fmt/src` — type-check (strict)
- `uv run python -m scripts.corpus_check fmt` — sweep corpus for cosmetic-pipeline idempotence
- `uv run python -m scripts.corpus_check codemod <dotted.module>:<ClassName>` — sweep a structural codemod (tier 2 subcommand)

## Useful workspace references

- `galaxy-tool-source/README.md` — tier-1 public API and the trivia
  contract this formatter respects
- `galaxy-tool-source/docs/decisions.md` §3 (representation), §9
  (three-tier vision)
- `galaxy-tool-codemod/src/galaxy_tool_codemod/canonical.py` —
  the `canonical_codemods()` / `AUTO_UPGRADE_CODEMODS` contracts the tier-3.6
  registry facade runs (this package's CLI does not)
- `galaxy-tool-refactor-registry/` — the tier-3.6 facade that composes
  codemod + fmt into `run` / `upgrade` / `detect` (it calls this package's
  `format_tool_document_subset` / `detect_tool_document_subset`, fmt §D15)
- `src/galaxy_tool_fmt/cli.py` — the cosmetic-only CLI (thin wrapper
  over `cli_support`); `src/galaxy_tool_fmt/cli_support.py` — the
  shared file-walking / drift-detection engine the app CLI also uses
- `galaxy-tool-refactor-cli/` — the tier-4 app CLI (over the registry facade)
- `../docs/corpus_data/combined_corpus_data.json` — the real-world
  distribution of tool XML idioms the formatter must preserve idempotently
