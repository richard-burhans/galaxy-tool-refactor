# galaxy-tool-refactor

A uv workspace housing five independently-installable Python packages for
parsing, validating, formatting, and refactoring Galaxy tool definition XML.

## Packages

| Package | PyPI status | Role |
|---|---|---|
| [`galaxy-tool-refactor-rules`](galaxy-tool-refactor-rules/README.md) | pre-alpha | Shared `RuleMeta` descriptor + glossary renderer. Dependency-free; underpins the GTX rule registry across tiers 2 & 3. |
| [`galaxy-tool-xml`](galaxy-tool-xml/README.md) | pre-release | Parse, validate, and inspect Galaxy tool XML. Foundation for the other tiers. |
| [`galaxy-tool-xml-codemod`](galaxy-tool-xml-codemod/README.md) | pre-alpha | Visitor-based framework + bundled structural codemods (`CANONICAL_CODEMODS`, `AUTO_UPGRADE_CODEMODS`). |
| [`galaxy-tool-xml-fmt`](galaxy-tool-xml-fmt/README.md) | pre-release | Opinionated `black`-like cosmetic formatter. The only tier that writes XML. |
| [`galaxy-tool-refactor-cli`](galaxy-tool-refactor-cli/README.md) | pre-alpha | The `galaxy-tool-refactor` app CLI — composes the tiers into `format` and `upgrade` commands. |

## Quick start

```bash
git clone <this-repo>
cd galaxy-tool-refactor
uv sync
```

## Architecture

Tiers 1–3 build on tier 1 and are **independent siblings** (none depends on
another); tier 0.5 is a shared metadata primitive; tier 4 is the app that
composes them into the user-facing workflow:

```
   galaxy-tool-refactor-rules     ← shared RuleMeta (dependency-free, tier 0.5)
                  ↑          ↑
                  galaxy-tool-xml ← parse, validate, typed views (lxml tree = source of truth)
                   ↑              ↑
   galaxy-tool-xml-codemod   galaxy-tool-xml-fmt
   (structural refactors)    (cosmetic formatter; the only tier that writes XML)
                   ↑              ↑
              galaxy-tool-refactor-cli  ← the `galaxy-tool-refactor` app CLI (tier 4)
              (composes codemods + fmt: `format`, `upgrade`)
```

The lower tiers stay independent: `galaxy-tool-xml-fmt` — both its library and
its `galaxy-tool-xml-fmt` CLI — is **cosmetic-only** and does **not** depend on
`galaxy-tool-xml-codemod`. All cross-tier orchestration lives in the app
(`galaxy-tool-refactor-cli`):

- `galaxy-tool-refactor format` — `CANONICAL_CODEMODS` (typo repair + attribute
  order) then cosmetic formatting. Safe, idempotent; never changes `profile=`.
- `galaxy-tool-refactor upgrade` — `AUTO_UPGRADE_CODEMODS` (repair, then
  iterative profile upgrade) then cosmetic formatting. Opt-in, semantic.

For the full rationale, see `galaxy-tool-xml/docs/decisions.md` §9 (three-tier
vision), `galaxy-tool-refactor-cli/docs/decisions.md` §D1 (the app tier and the
upgrade/format split), and `galaxy-tool-xml-fmt/docs/decisions.md` §D12 (fmt CLI
back to cosmetic-only).

## Running tests

```bash
uv run --package galaxy-tool-refactor-rules pytest galaxy-tool-refactor-rules/tests/
uv run --package galaxy-tool-xml            pytest galaxy-tool-xml/tests/
uv run --package galaxy-tool-xml-codemod    pytest galaxy-tool-xml-codemod/tests/
uv run --package galaxy-tool-xml-fmt        pytest galaxy-tool-xml-fmt/tests/
uv run --package galaxy-tool-refactor-cli   pytest galaxy-tool-refactor-cli/tests/
```

## Corpus scripts

Shared maintainer scripts live in `scripts/`. The corpus (cloned Galaxy tool
repositories) is stored in `corpus/` (gitignored) and seeded from
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

# Download/update Galaxy release XSDs
uv run python -m scripts.fetch_schemas

# Clone/update Toolshed repos
uv run python -m scripts.fetch_toolshed
```
