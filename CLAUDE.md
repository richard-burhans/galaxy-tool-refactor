# CLAUDE.md — galaxy-tool-refactor workspace

## Layout

```
galaxy-tool-refactor/
├── galaxy-tool-refactor-rules/ Tier 0.5 (shared RuleMeta + glossary renderer)
├── galaxy-tool-xml/          Tier 1 (parsing & validation)
├── galaxy-tool-xml-codemod/  Tier 2 (structure)
├── galaxy-tool-xml-fmt/      Tier 3 (formatting)
├── galaxy-tool-xml-check/    Tier 3.5 (advisory detect-only IUC checks)
├── galaxy-tool-refactor-registry/ Tier 3.6 (unified rule registry + presets; library-first facade)
├── galaxy-tool-refactor-cli/ Tier 4 (app CLI: format + upgrade + check + presets/rules)
├── galaxy-tool-refactor-mcp/ Tier 4 (future MCP server — placeholder, NOT a workspace member yet)
├── scripts/                  Shared maintainer scripts (not installed)
│   ├── corpus_check.py         validate | fmt | codemod | rules | check subcommands
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
uv sync          # installs all seven packages + dev deps into .venv
```

## Test

```bash
uv run --package galaxy-tool-refactor-rules pytest galaxy-tool-refactor-rules/tests/
uv run --package galaxy-tool-xml            pytest galaxy-tool-xml/tests/
uv run --package galaxy-tool-xml-codemod    pytest galaxy-tool-xml-codemod/tests/
uv run --package galaxy-tool-xml-fmt        pytest galaxy-tool-xml-fmt/tests/
uv run --package galaxy-tool-xml-check      pytest galaxy-tool-xml-check/tests/
uv run --package galaxy-tool-refactor-registry pytest galaxy-tool-refactor-registry/tests/
uv run --package galaxy-tool-refactor-cli   pytest galaxy-tool-refactor-cli/tests/
```

## Lint / type-check

```bash
uv run ruff check galaxy-tool-refactor-rules/src galaxy-tool-xml/src galaxy-tool-xml-codemod/src galaxy-tool-xml-fmt/src galaxy-tool-xml-check/src galaxy-tool-refactor-registry/src galaxy-tool-refactor-cli/src
uv run mypy --config-file galaxy-tool-refactor-rules/pyproject.toml galaxy-tool-refactor-rules/src
uv run mypy --config-file galaxy-tool-xml/pyproject.toml         galaxy-tool-xml/src
uv run mypy --config-file galaxy-tool-xml-codemod/pyproject.toml galaxy-tool-xml-codemod/src
uv run mypy --config-file galaxy-tool-xml-fmt/pyproject.toml     galaxy-tool-xml-fmt/src
uv run mypy --config-file galaxy-tool-xml-check/pyproject.toml   galaxy-tool-xml-check/src
uv run mypy --config-file galaxy-tool-refactor-registry/pyproject.toml galaxy-tool-refactor-registry/src
uv run mypy --config-file galaxy-tool-refactor-cli/pyproject.toml galaxy-tool-refactor-cli/src
```

## Pre-push QA gate

`scripts/qa_gate.sh` runs the deterministic quality slice — ruff, mypy (strict,
per package), and pytest for all seven packages — and exits non-zero (naming the
failing step) if anything fails. A `git push` **PreToolUse hook**
(`.claude/settings.json`) calls it and **blocks the push** on failure, so code
never leaves the machine with a red gate. Run it manually any time:

```bash
bash scripts/qa_gate.sh
```

This is a mechanical backstop only — it does **not** replace the full pre-PR
code + documentation audit (standards, doc/code agreement, stale-doc and
stat-consistency review). New contributors approve the project hook on first use;
in a session that predates the hook, open `/hooks` once (or restart) to load it.

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

# Unified-detect violation counts (what `check` reports: canonical codemods + fmt + advisory
# IUC): per-rule tools-flagged + total findings, write docs/corpus_check_stats.md.
uv run python -m scripts.corpus_check check [--source github|toolshed|combined] [--repo NAME] [--limit N]

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
| 3.5 | **advisory checks** | `galaxy-tool-xml-check` | Detect-only IUC best-practice checks (`IUC` codes, `RuleMeta.detect_only`); read-only LBYL queries over tier 1 yielding `Violation`. Depends only on tiers 1 + 0.5. |
| 3.6 | **rule registry / presets** | `galaxy-tool-refactor-registry` | Unified, code-addressable `RuleHandle` over all three families + named presets (`cosmetic`/`iuc`/`strict`) + `run`/`upgrade`/`detect`. **Library-first** (no click/exit; structured I/O; introspectable). Depends on 0.5/1/2/3/3.5; lower tiers don't depend on it. |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` | The user-facing `galaxy-tool-refactor` CLI. Consumes the registry facade (tier 3.6); owns `format`, `upgrade`, `check`, `presets`, `rules`. |
| 4 | **MCP server** *(future)* | `galaxy-tool-refactor-mcp` | Placeholder for an agent-facing MCP server over the registry facade. **Not implemented / not a workspace member yet** — see its `docs/vision.md`. |

**Orchestration lives in the registry facade (tier 3.6); the CLI is a thin
front-end.** Each lower tier is consumable standalone; the facade composes them
into one code-addressable rule set with presets and a library-first
`run`/`upgrade`/`detect` API. The CLI (`galaxy-tool-refactor-cli`) depends on the
facade (plus fmt's `cli_support` engine and tier-1 parsing) and owns five
commands:

- `galaxy-tool-refactor format` — apply a preset's fixable rules (default `iuc` =
  `CANONICAL_CODEMODS` + cosmetic, byte-identical to the historical behaviour)
  then serialise. Safe, idempotent; never changes `profile=`. Advisory rules in a
  selection (`--preset strict`) are reported as notes, never applied.
- `galaxy-tool-refactor upgrade` — repair, then iterative profile upgrade, then
  format. Opt-in, semantic. No `--preset` (presets are a format/check concept);
  `--select`/`--ignore` adjust its fixable rule set.
- `galaxy-tool-refactor check` — report-only over the selected rules' detect
  phases. Fixable GTX findings exit non-zero; advisory IUC findings appear only
  under `--preset strict` and are informational unless `--strict`.
- `galaxy-tool-refactor presets` / `rules` — introspection of the baked-in
  presets and rules.

Selection is shared across `format`/`upgrade`/`check`: `--preset NAME`,
`--select CODE…`, `--ignore CODE…` (ruff-style precedence `--ignore` ▸ `--select`
▸ `--preset`; `--select` replaces the preset's set). Rules and presets are
developer-defined — no user-defined rules.

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
GTX registry; and `docs/iuc_best_practices.md` (+ codemod §17) for the
IUC best-practices coverage map and the `<tool>` element-order codemod
(GTX013); and `galaxy-tool-refactor-registry/docs/decisions.md` D1–D4
(+ cli `docs/decisions.md` D4, fmt §D15) for the rule-registry facade,
presets, per-rule selection, and the move of orchestration below the CLI.
`galaxy-tool-refactor-mcp/docs/vision.md` records the (unbuilt) MCP /
agent-extensibility direction the facade is shaped for.
