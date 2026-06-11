# galaxy-tool-refactor

A uv workspace housing eight independently-installable Python packages for
parsing, validating, formatting, linting, and refactoring Galaxy tool
definition XML.

## Packages

| Package | PyPI status | Role |
|---|---|---|
| [`galaxy-tool-refactor-rules`](galaxy-tool-refactor-rules/README.md) | [published](https://pypi.org/project/galaxy-tool-refactor-rules/), `pip install galaxy-tool-refactor-rules` | Shared `RuleMeta` descriptor + `Violation` diagnostic + glossary renderer. Dependency-free; underpins the GTR rule registry across the tiers. |
| [`galaxy-tool-source`](galaxy-tool-source/README.md) | [published](https://pypi.org/project/galaxy-tool-source/), `pip install galaxy-tool-source` | Parse, validate, and inspect Galaxy tool XML. Foundation for the other tiers. |
| [`galaxy-tool-codemod`](galaxy-tool-codemod/README.md) | [published](https://pypi.org/project/galaxy-tool-codemod/), `pip install galaxy-tool-codemod` | Detect-primitive `CodemodCommand` framework + bundled structural codemods (`canonical_codemods()`, `AUTO_UPGRADE_CODEMODS`); each rule has a detect (lint) and a fix phase. |
| [`galaxy-tool-fmt`](galaxy-tool-fmt/README.md) | [published](https://pypi.org/project/galaxy-tool-fmt/), `pip install galaxy-tool-fmt` | Opinionated `black`-like cosmetic formatter (with a non-mutating `detect`). The only tier that serialises canonical output XML. |
| [`galaxy-tool-lint`](galaxy-tool-lint/README.md) | [published](https://pypi.org/project/galaxy-tool-lint/), `pip install galaxy-tool-lint` | Advisory, detect-only IUC best-practice checks (`GTR` codes); read-only, reports but never mutates. Depends only on tiers 1 + 0.5. |
| [`galaxy-tool-refactor-registry`](galaxy-tool-refactor-registry/README.md) | [published](https://pypi.org/project/galaxy-tool-refactor-registry/), `pip install galaxy-tool-refactor-registry` | Unified, code-addressable rule registry over all three families + named rulesets (`cosmetic`/`default`/`iuc`/`strict`) + a library-first `run`/`upgrade`/`detect` API. The orchestration core the CLI and the MCP server sit on. |
| [`galaxy-tool-refactor-cli`](galaxy-tool-refactor-cli/README.md) | [published](https://pypi.org/project/galaxy-tool-refactor-cli/), `pip install galaxy-tool-refactor-cli` | The `galaxy-tool-refactor` app CLI: `format`, `upgrade`, report-only `check`, read-only `find-references`, mutating `rename-param`, `rulesets` / `rules`, and the opt-in `normalize-macros`, with `--ruleset` / `--select` / `--ignore` rule selection. |
| [`galaxy-tool-refactor-mcp`](galaxy-tool-refactor-mcp/README.md) | [published](https://pypi.org/project/galaxy-tool-refactor-mcp/), `pip install galaxy-tool-refactor-mcp` | An agent-facing **MCP server** over the registry facade (CLI sibling): a thin FastMCP binding over a protocol-agnostic adapter, exposing `format_tool`/`upgrade_tool`/`check_tool`/`list_rulesets`/`list_rules`. |
| [`galaxy-tool-refactor`](galaxy-tool-refactor-meta/README.md) | [published](https://pypi.org/project/galaxy-tool-refactor/), `pip install galaxy-tool-refactor` | Front-door **metapackage**: `pip install galaxy-tool-refactor` installs the CLI; the `[mcp]` extra adds the MCP server. No code of its own. |

## Quick start

Install the CLI from PyPI:

```bash
pip install galaxy-tool-refactor          # the `galaxy-tool-refactor` command
pip install "galaxy-tool-refactor[mcp]"   # also installs the agent-facing MCP server
```

Then run it on a tool (or a directory of tools):

```bash
galaxy-tool-refactor check tool.xml       # report IUC / style deviations (read-only)
galaxy-tool-refactor format tool.xml      # apply the safe, behaviour-preserving fixes
```

To work on the toolkit itself, clone the workspace and use `uv` instead:

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
                  galaxy-tool-source ← parse, validate, typed views (lxml tree = source of truth)
              ↑        ↑        ↑
 galaxy-tool-xml-   galaxy-tool-   galaxy-tool-lint
 codemod (tier 2)   xml-fmt (3)    (advisory checks, tier 3.5)
 structural         cosmetic       read-only; reports, never writes
              ↑        ↑        ↑
              galaxy-tool-refactor-registry  ← unified rule registry + rulesets (tier 3.6)
              (library-first facade: run / upgrade / detect, introspectable)
                          ↑                       ↑
   galaxy-tool-refactor-cli (tier 4)     galaxy-tool-refactor-mcp (tier 4)
   the `galaxy-tool-refactor` app CLI    agent-facing MCP server (FastMCP)
```

Every rule has a non-mutating **detect (lint)** phase alongside its **fix**
phase (the `ruff check` / `ruff format` model). The lower tiers stay
independent: `galaxy-tool-fmt` — both its library and its CLI — is
**cosmetic-only** and does **not** depend on `galaxy-tool-codemod`;
`galaxy-tool-lint` depends only on tiers 1 + 0.5. Cross-tier orchestration
lives in the **registry facade** (`galaxy-tool-refactor-registry`, tier 3.6),
which the app CLI consumes:

- `galaxy-tool-refactor format` — apply a ruleset's fixable rules then cosmetic
  formatting. The default ruleset = `canonical_codemods()` (typo repair +
  attribute / element order + CDATA wraps + GTR020 command-var single-quoting) +
  cosmetic — behaviour-preserving (no longer byte-identical to the pre-GTR020
  historical output; codemod `docs/decisions.md` §30). Safe, idempotent; never
  changes `profile=`.
- `galaxy-tool-refactor upgrade` — repair, then iterative profile upgrade, then
  cosmetic formatting. Opt-in, semantic. No `--ruleset`; `--select`/`--ignore`
  adjust its fixable rule set.
- `galaxy-tool-refactor check` — report-only linter: prints
  `file:line  CODE  message` for the selected rules. The default ruleset reports
  only *fixable* GTR findings; `--ruleset strict` adds the *advisory* checks
  (marked `(advisory)`). Exits non-zero on any fixable finding; advisory findings
  are informational unless `--strict`.
- `galaxy-tool-refactor find-references NAME PATHS` — read-only query (not a rule):
  print every Cheetah `$NAME` reference site across a tool's templated sections
  (`galaxy_tool_source.cheetah_refs`).
- `galaxy-tool-refactor rename-param OLD NEW PATHS` — the mutating sibling of
  `find-references`: rename a parameter across every Cheetah section, by-name
  cross-ref attribute and `<tests>` mirror, plus the definition; atomic per file
  (`--check` previews). The first Cheetah mutator (`galaxy_tool_source.cheetah_rename`).
- `galaxy-tool-refactor rulesets` / `rules` — list the baked-in rulesets and rules.
- `galaxy-tool-refactor normalize-macros` — opt-in, repo-scoped: lowercase literal
  `format`/`ftype` in `<macros>`-root files (the macro-library fix the per-tool
  `upgrade` can't reach). A separate command — it writes files other than the one
  named, so it's never folded into `format`/`upgrade`.

Rule selection (`--ruleset NAME`, `--select CODE…`, `--ignore CODE…`) is shared by
`format`/`upgrade`/`check`, ruff-style (`--ignore` ▸ `--select` ▸ `--ruleset`).
Rulesets and rules are developer-defined — there are no user-defined rules.

For the full rationale, see `galaxy-tool-source/docs/decisions.md` §9 (three-tier
vision), `galaxy-tool-refactor-cli/docs/decisions.md` §D1–D4 (the app tier, the
`format`/`upgrade`/`check` commands, and the move onto the registry facade),
`galaxy-tool-refactor-registry/docs/decisions.md` D1–D4 (the facade, rulesets, and
selection), `galaxy-tool-fmt/docs/decisions.md` §D12 (fmt CLI back to
cosmetic-only) + §D14/§D15 (cosmetic detect + per-rule subset seams),
`galaxy-tool-lint/docs/decisions.md` D1 (the advisory check tier), and
`galaxy-tool-refactor-mcp/docs/decisions.md` D1 (the MCP server) +
`docs/vision.md` (the agent-authored-rules direction, still future).

## Running tests

```bash
uv run --package galaxy-tool-refactor-rules pytest galaxy-tool-refactor-rules/tests/
uv run --package galaxy-tool-source            pytest galaxy-tool-source/tests/
uv run --package galaxy-tool-codemod    pytest galaxy-tool-codemod/tests/
uv run --package galaxy-tool-fmt        pytest galaxy-tool-fmt/tests/
uv run --package galaxy-tool-lint      pytest galaxy-tool-lint/tests/
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

# Per-rule isolation QA (every GTR rule alone); writes docs/corpus_rule_stats.md
uv run python -m scripts.corpus_check rules

# Unified-detect violation counts (what `check` reports, incl. advisory);
# writes docs/corpus_check_stats.md
uv run python -m scripts.corpus_check check

# Download/update Galaxy release XSDs
uv run python -m scripts.fetch_schemas

# Clone/update Toolshed repos
uv run python -m scripts.fetch_toolshed
```

## Contributing

Contributions are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup
(`uv sync`, the pre-push gate), the coding standards, and the PR workflow. New
here? [`ARCHITECTURE.md`](ARCHITECTURE.md) maps the seven tiers.

## Security

To report a vulnerability, see [`SECURITY.md`](SECURITY.md) (please use GitHub's
private vulnerability reporting, not a public issue).

