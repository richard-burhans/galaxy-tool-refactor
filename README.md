# galaxy-tool-refactor

A uv workspace housing three independently-installable Python libraries for
parsing, validating, formatting, and refactoring Galaxy tool definition XML.

## Packages

| Package | PyPI status | Role |
|---|---|---|
| [`galaxy-tool-xml`](galaxy-tool-xml/README.md) | pre-release | Parse, validate, and inspect Galaxy tool XML. Foundation for the other tiers. |
| [`galaxy-tool-xml-fmt`](galaxy-tool-xml-fmt/README.md) | pre-release | Opinionated `black`-like formatter. The only tier that writes XML. |
| [`galaxy-tool-xml-codemod`](galaxy-tool-xml-codemod/README.md) | pre-alpha | Visitor-based framework + bundled structural codemods (`CANONICAL_CODEMODS`). |

## Quick start

```bash
git clone <this-repo>
cd galaxy-tool-refactor
uv sync
```

## Architecture

All three tiers build on tier 1; they are **independent siblings**, not a
linear chain:

```
                  galaxy-tool-xml         ← parse, validate, typed views (lxml tree = source of truth)
                   ↑              ↑
   galaxy-tool-xml-codemod   galaxy-tool-xml-fmt
   (structural refactors)    (cosmetic formatter; the only tier that writes XML)
                   ╰ ─ optional ─ ╯
                  [canonical] extra
```

`galaxy-tool-xml-fmt`'s library is cosmetic-only and does **not** depend on
`galaxy-tool-xml-codemod`. fmt's CLI declares codemod as an optional
`[canonical]` extra; when installed, the CLI runs the codemod package's
`CANONICAL_CODEMODS` (structural canonicalisation) before fmt's cosmetic
rules. The preferred "format my tool" workflow uses all three tiers; a
minimal `xml + fmt` install gets cosmetic-only output.

For the full rationale, see `galaxy-tool-xml/docs/decisions.md` §9 and
`galaxy-tool-xml-fmt/docs/decisions.md` §D10.

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
