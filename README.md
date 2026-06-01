# galaxy-tool-refactor

A uv workspace housing seven independently-installable Python packages for
parsing, validating, formatting, linting, and refactoring Galaxy tool
definition XML.

## Packages

| Package | PyPI status | Role |
|---|---|---|
| [`galaxy-tool-refactor-rules`](galaxy-tool-refactor-rules/README.md) | pre-alpha | Shared `RuleMeta` descriptor + `Violation` diagnostic + glossary renderer. Dependency-free; underpins the GTX/IUC rule registry across the tiers. |
| [`galaxy-tool-xml`](galaxy-tool-xml/README.md) | pre-release | Parse, validate, and inspect Galaxy tool XML. Foundation for the other tiers. |
| [`galaxy-tool-xml-codemod`](galaxy-tool-xml-codemod/README.md) | pre-alpha | Detect-primitive `CodemodCommand` framework + bundled structural codemods (`CANONICAL_CODEMODS`, `AUTO_UPGRADE_CODEMODS`); each rule has a detect (lint) and a fix phase. |
| [`galaxy-tool-xml-fmt`](galaxy-tool-xml-fmt/README.md) | pre-release | Opinionated `black`-like cosmetic formatter (with a non-mutating `detect`). The only tier that serialises canonical output XML. |
| [`galaxy-tool-xml-check`](galaxy-tool-xml-check/README.md) | pre-alpha | Advisory, detect-only IUC best-practice checks (`IUC` codes); read-only, reports but never mutates. Depends only on tiers 1 + 0.5. |
| [`galaxy-tool-refactor-registry`](galaxy-tool-refactor-registry/README.md) | pre-alpha | Unified, code-addressable rule registry over all three families + named presets (`cosmetic`/`iuc`/`strict`) + a library-first `run`/`upgrade`/`detect` API. The orchestration core the CLI (and a future MCP server) sit on. |
| [`galaxy-tool-refactor-cli`](galaxy-tool-refactor-cli/README.md) | pre-alpha | The `galaxy-tool-refactor` app CLI — `format`, `upgrade`, report-only `check`, plus `presets` / `rules`, with `--preset` / `--select` / `--ignore` rule selection. |

## Quick start

```bash
git clone <this-repo>
cd galaxy-tool-refactor
uv sync
```

## Architecture

Tiers 1–3.5 build on tier 1 and are **independent siblings** (none depends on
another); tier 0.5 is a shared metadata primitive; tier 4 is the app that
composes them into the user-facing workflow:

```
   galaxy-tool-refactor-rules     ← shared RuleMeta + Violation (dependency-free, tier 0.5)
                  ↑          ↑
                  galaxy-tool-xml ← parse, validate, typed views (lxml tree = source of truth)
              ↑        ↑        ↑
 galaxy-tool-xml-   galaxy-tool-   galaxy-tool-xml-check
 codemod (tier 2)   xml-fmt (3)    (advisory IUC checks, tier 3.5)
 structural         cosmetic       read-only; reports, never writes
              ↑        ↑        ↑
              galaxy-tool-refactor-registry  ← unified rule registry + presets (tier 3.6)
              (library-first facade: run / upgrade / detect, introspectable)
                          ↑                       ↑
   galaxy-tool-refactor-cli (tier 4)     galaxy-tool-refactor-mcp (tier 4, future)
   the `galaxy-tool-refactor` app CLI    agent-facing MCP server (placeholder)
```

Every rule has a non-mutating **detect (lint)** phase alongside its **fix**
phase (the `ruff check` / `ruff format` model). The lower tiers stay
independent: `galaxy-tool-xml-fmt` — both its library and its CLI — is
**cosmetic-only** and does **not** depend on `galaxy-tool-xml-codemod`;
`galaxy-tool-xml-check` depends only on tiers 1 + 0.5. Cross-tier orchestration
lives in the **registry facade** (`galaxy-tool-refactor-registry`, tier 3.6),
which the app CLI consumes:

- `galaxy-tool-refactor format` — apply a preset's fixable rules then cosmetic
  formatting. Default preset `iuc` = `CANONICAL_CODEMODS` (typo repair +
  attribute / element order) + cosmetic — byte-identical to the historical
  behaviour. Safe, idempotent; never changes `profile=`.
- `galaxy-tool-refactor upgrade` — repair, then iterative profile upgrade, then
  cosmetic formatting. Opt-in, semantic. No `--preset`; `--select`/`--ignore`
  adjust its fixable rule set.
- `galaxy-tool-refactor check` — report-only linter: prints
  `file:line  CODE  message` for the selected rules. The default (`iuc`) reports
  only *fixable* GTX findings; `--preset strict` adds the *advisory* IUC checks
  (marked `(advisory)`). Exits non-zero on any fixable finding; advisory findings
  are informational unless `--strict`.
- `galaxy-tool-refactor presets` / `rules` — list the baked-in presets and rules.

Rule selection (`--preset NAME`, `--select CODE…`, `--ignore CODE…`) is shared by
`format`/`upgrade`/`check`, ruff-style (`--ignore` ▸ `--select` ▸ `--preset`).
Presets and rules are developer-defined — there are no user-defined rules.

For the full rationale, see `galaxy-tool-xml/docs/decisions.md` §9 (three-tier
vision), `galaxy-tool-refactor-cli/docs/decisions.md` §D1–D4 (the app tier, the
`format`/`upgrade`/`check` commands, and the move onto the registry facade),
`galaxy-tool-refactor-registry/docs/decisions.md` D1–D4 (the facade, presets, and
selection), `galaxy-tool-xml-fmt/docs/decisions.md` §D12 (fmt CLI back to
cosmetic-only) + §D14/§D15 (cosmetic detect + per-rule subset seams),
`galaxy-tool-xml-check/docs/decisions.md` D1 (the advisory check tier), and
`galaxy-tool-refactor-mcp/docs/vision.md` (the future MCP / agent direction).

## Running tests

```bash
uv run --package galaxy-tool-refactor-rules pytest galaxy-tool-refactor-rules/tests/
uv run --package galaxy-tool-xml            pytest galaxy-tool-xml/tests/
uv run --package galaxy-tool-xml-codemod    pytest galaxy-tool-xml-codemod/tests/
uv run --package galaxy-tool-xml-fmt        pytest galaxy-tool-xml-fmt/tests/
uv run --package galaxy-tool-xml-check      pytest galaxy-tool-xml-check/tests/
uv run --package galaxy-tool-refactor-registry pytest galaxy-tool-refactor-registry/tests/
uv run --package galaxy-tool-refactor-cli   pytest galaxy-tool-refactor-cli/tests/
```

## Corpus scripts

Shared maintainer scripts live in `scripts/`. The corpus (cloned Galaxy tool
repositories) is stored in `.local/corpus/` (gitignored) and seeded from
`corpus_sources.json`.

Invoke the scripts as modules (`python -m scripts.X`), not as files — they
import from `scripts._shared`, which requires the workspace root on `sys.path`.

```bash
# Validate tier-1 API invariants against the corpus
uv run python -m scripts.corpus_check validate

# Check formatter (tier-3) cosmetic-pipeline idempotence against the corpus
uv run python -m scripts.corpus_check fmt

# Sweep one structural (tier-2) codemod for idempotence + post-codemod validity
uv run python -m scripts.corpus_check codemod <dotted.module>:<ClassName>

# Per-rule isolation QA (every GTX rule alone); writes docs/corpus_rule_stats.md
uv run python -m scripts.corpus_check rules

# Unified-detect violation counts (what `check` reports, incl. advisory IUC);
# writes docs/corpus_check_stats.md
uv run python -m scripts.corpus_check check

# Download/update Galaxy release XSDs
uv run python -m scripts.fetch_schemas

# Clone/update Toolshed repos
uv run python -m scripts.fetch_toolshed
```
