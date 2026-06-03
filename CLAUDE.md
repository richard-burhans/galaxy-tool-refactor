# CLAUDE.md — galaxy-tool-refactor workspace

> New here? Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first — a map of the major
> abstractions across the seven tiers and the cross-tier contracts between them.

## Layout

```
galaxy-tool-refactor/
├── galaxy-tool-refactor-rules/ Tier 0.5 (shared RuleMeta + glossary renderer)
├── galaxy-tool-xml/          Tier 1 (parsing & validation)
├── galaxy-tool-xml-codemod/  Tier 2 (structure)
├── galaxy-tool-xml-fmt/      Tier 3 (formatting)
├── galaxy-tool-xml-check/    Tier 3.5 (advisory detect-only IUC checks)
├── galaxy-tool-refactor-registry/ Tier 3.6 (unified rule registry + presets; library-first facade)
├── galaxy-tool-refactor-cli/ Tier 4 (app CLI: format + upgrade + check + presets/rules + normalize-macros)
├── galaxy-tool-refactor-mcp/ Tier 4 (MCP server over the registry facade; thin FastMCP adapter)
├── scripts/                  Shared maintainer scripts (not installed)
│   ├── corpus_check.py         validate | fmt | codemod | rules | check subcommands
│   ├── fetch_schemas.py        download release XSDs
│   ├── fetch_toolshed.py       clone Toolshed repos
│   ├── measure.py              ad-hoc corpus queries
│   └── regenerate.py           regenerate per-version xsdata models
├── docs/
│   └── corpus_data/            per-tool JSON/TSV from corpus sweeps
├── corpus_sources.json       list of GitHub repos to clone (committed seed list)
└── .local/                   machine-local scratch, gitignored (NOT committed)
    ├── corpus/                 cloned Galaxy tool repos (seeded from corpus_sources.json)
    └── galaxy-src/             clone of galaxyproject/galaxy for source inspection
```

## Install

```bash
uv sync          # installs all eight packages + dev deps into .venv
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
uv run --package galaxy-tool-refactor-mcp   pytest galaxy-tool-refactor-mcp/tests/
```

## Lint / type-check

```bash
uv run ruff check galaxy-tool-refactor-rules/src galaxy-tool-xml/src galaxy-tool-xml-codemod/src galaxy-tool-xml-fmt/src galaxy-tool-xml-check/src galaxy-tool-refactor-registry/src galaxy-tool-refactor-cli/src galaxy-tool-refactor-mcp/src
uv run mypy --config-file galaxy-tool-refactor-rules/pyproject.toml galaxy-tool-refactor-rules/src
uv run mypy --config-file galaxy-tool-xml/pyproject.toml         galaxy-tool-xml/src
uv run mypy --config-file galaxy-tool-xml-codemod/pyproject.toml galaxy-tool-xml-codemod/src
uv run mypy --config-file galaxy-tool-xml-fmt/pyproject.toml     galaxy-tool-xml-fmt/src
uv run mypy --config-file galaxy-tool-xml-check/pyproject.toml   galaxy-tool-xml-check/src
uv run mypy --config-file galaxy-tool-refactor-registry/pyproject.toml galaxy-tool-refactor-registry/src
uv run mypy --config-file galaxy-tool-refactor-cli/pyproject.toml galaxy-tool-refactor-cli/src
uv run mypy --config-file galaxy-tool-refactor-mcp/pyproject.toml galaxy-tool-refactor-mcp/src
```

## Pre-push QA gate

`scripts/qa_gate.sh` runs the deterministic quality slice — ruff, mypy (strict,
per package), and pytest for all eight packages — and exits non-zero (naming the
failing step) if anything fails. A `git push` **PreToolUse hook**
(`.claude/settings.json`) calls it and **blocks the push** on failure, so code
never leaves the machine with a red gate. Run it manually any time:

```bash
bash scripts/qa_gate.sh
```

This is a mechanical backstop only — it does **not** replace the full pre-PR
code + documentation audit (standards, doc/code agreement, stale-doc and
stat-consistency review). That audit is the **`/pre-pr-audit` skill**
(`.claude/skills/pre-pr-audit/`) — invoke it before opening any PR; it owns the
six-step checklist and calls `qa_gate.sh` as its final step. For deeper,
design-level reviews of the abstractions there is the **`/architecture-audit`
skill**. New contributors approve the project hook on first use; in a session that
predates the hook, open `/hooks` once (or restart) to load it.

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
uv run python -m scripts.measure               # ad-hoc corpus queries (--list)

# Macro organisation across the corpus (inline vs imported macro files,
# shared-macro importer distribution, the inverse imports-per-tool bundle-size
# histogram with a transitive/direct split, token names, <yield>, stale
# macro-token profiles). Writes docs/macro_corpus_stats.md (manually-regenerated
# artifact; needs the corpus, so it is not run in CI):
uv run python -m scripts.measure macro-topology
uv run python -m scripts.measure macro-profile-tokens

# Phase-3b decision input: where profile tokens are defined (inline / directly
# imported / deeper), sole-owned vs shared defining files, whether shared files'
# importers agree on the target profile (the fork-vs-edit-in-place question),
# and <import> scan-soundness (`..`/absolute). Writes
# docs/macro_profile_ownership_stats.md (manually-regenerated; needs the corpus):
uv run python -m scripts.measure macro-profile-ownership

# Decision-augmenting sizing sweeps (print-only; numbers folded into the
# decisions docs they back). command-iuc-heuristics sizes the IUC011/IUC012
# placeholders (check §D1); command-lone-amp classifies every lone `&` by class
# (redirect/quoted/pipe/background/joining) to settle the IUC012 deferral with
# data — the genuine `cmd1 & cmd2` anti-pattern is ~1 tool (check §D3);
# command-unquoted-var sizes IUC011 honestly — excluding Cheetah directive lines +
# tracking shell quotes, a genuinely-unquoted `$var` still fires on 73.2% of tools,
# so IUC011 (unlike IUC012) has real signal (check §D4); iuc011-fixability then
# resolves each unquoted `$var` against <inputs> to ask whether AUTO-quoting is
# safe — 46.7% are provably-single-valued params, but 33.6% are #set-assembled/loop
# vars a static fixer can't reach, so IUC011 stays advisory (check §D6);
# macro-fmt-idempotence backs fmt §D16:
uv run python -m scripts.measure command-iuc-heuristics
uv run python -m scripts.measure command-lone-amp
uv run python -m scripts.measure command-unquoted-var
uv run python -m scripts.measure iuc011-fixability
uv run python -m scripts.measure macro-fmt-idempotence

# Phase-3c sizing: clean @TOOL_VERSION@/@VERSION_SUFFIX@ extraction candidates
# (literal version="<base>+galaxy<suffix>" whose base == a package requirement
# version), split by whether a <macros> block exists or would need creating:
uv run python -m scripts.measure version-tokenization

# Per-Galaxy-upgrade-code blast radius: how many tools `upgrade`-to-latest would
# cross each profile-behaviour code (backs codemod decisions §23 + the §22
# soundness boundary; data = the vendored PROFILE_UPGRADE_CODES):
uv run python -m scripts.measure semantic-upgrade-boundaries

# How much per-tool detection narrows that warning: per code, range-crossed vs
# actually-applicable counts across the corpus (backs codemod decisions §25;
# needs the corpus, so not run in CI):
uv run python -m scripts.measure upgrade-codes-applicability

# Detector-precision sizing: how many tools the always-firing 20_09_consider_set_e
# detector (any <command> w/o strict=) would SOUNDLY stop flagging if tightened to
# "provably single simple command" — set -e cannot change a lone command (backs
# codemod decisions §28; needs the corpus, so not run in CI):
uv run python -m scripts.measure set-e-tightening

# Raw-tree vs post-macro-expansion detector divergence: per consider/must_fix code,
# over-flag (raw fires, a macro supplies the construct -> Galaxy would not) vs
# under-report (macro supplies the trigger -> the §25 gap) vs agree. Sizes the
# detection gap behind the macro-expansion detector port (backs codemod decisions
# §25; needs the corpus, so not run in CI):
uv run python -m scripts.measure macro-expansion-detection-gap

# Declared/defaulted profile vs the profile reached after `upgrade` (runs
# UpgradeToLatest per tool): before/after distributions + shift summary. Writes
# docs/upgrade_profile_shift_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure upgrade-profile-shift

# Where a *behavior-preserving* auto-upgrade would stall: walk each tool's
# profile toward latest, stopping at the first applicable Galaxy behaviour code
# (PROFILE_UPGRADE_CODES) the toolchain cannot auto-fix. Distribution of stuck
# tools by blocking profile/code, under must_fix-only and must_fix+consider
# policies. Writes docs/upgrade_behavior_block_stats.md (needs the corpus, so
# not run in CI):
uv run python -m scripts.measure upgrade-behavior-blocks

# Sizing for the format="input" runtime-gated fix (GTX015, codemod decisions §24):
# output <data format="input"> tools split by data-input cardinality (the single
# top-level data input subset is auto-fixable), plus the format_source-guard and
# crossing-gate skip counts (§24):
uv run python -m scripts.measure output-format-input

# <help> markup-format distribution: per-tool implicit-RST vs explicit
# format="markdown"/other (backs docs/galaxy_processing_model.md — RST renders
# server-side, markdown renders client-side; both supported):
uv run python -m scripts.measure help-formats

# Cheetah complexity of <command> + inline <configfile> (directive/variable-shape/
# hazard distribution; heuristic regex, not a Cheetah parse). Backs
# docs/upgrade_research/cheetah_variable_rewriting.md. Writes
# docs/cheetah_command_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure cheetah-command-complexity

# Auto-fixable population for a 16_04_fix_interpreter codemod (GTX016): tools with a
# deprecated <command interpreter=…> split into bucket A (rewritable) / A-missing / B
# (leading-Cheetah) / C (non-standard interpreter), reusing the codemod's own
# eligibility predicate. Backs docs/upgrade_research/16_04_fix_interpreter.md. Writes
# docs/interpreter_bucket_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure interpreter-bucket-split

# Macro-file format/ftype residual (macro epic Phase 2a): tools stuck below latest
# that reach a newer profile once the literal format/ftype in their imported macro
# files are lowercased (the value Upgrade24_1 can't reach) — sound (temp-copy +
# re-validate, strict increase), split shared vs sole-owned defining file. Backs
# galaxy-tool-xml-codemod/docs/macro-aware-normalization.md. Writes
# docs/macro_format_residual_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure macro-format-residual

# Phase-2b sizing: of the tools still stuck after 2a, how many reach a newer profile
# when token-supplied datatype values (format="@FMT@" whose <token> value is coercible)
# are also normalized — split inline vs imported token. 0 across the corpus => the
# heavyweight expansion-provenance layer is unjustified for datatypes (2a is complete).
# Writes docs/macro_token_residual_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure macro-token-datatype-residual
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
| 3 | **formatting** | `galaxy-tool-xml-fmt` | Cosmetic rules (indent / blank line / empty-element shorthand) + the shared `cli_support` CLI engine. The only tier that serialises canonical output XML. |
| 3.5 | **advisory checks** | `galaxy-tool-xml-check` | Detect-only IUC best-practice checks (`IUC` codes, `RuleMeta.detect_only`); read-only LBYL queries over tier 1 yielding `Violation`. Depends only on tiers 1 + 0.5. |
| 3.6 | **rule registry / presets** | `galaxy-tool-refactor-registry` | Unified, code-addressable `RuleHandle` over all three families + named presets (`cosmetic`/`iuc`/`strict`) + `run`/`upgrade`/`detect`. **Library-first** (no click/exit; structured I/O; introspectable). Depends on 0.5/1/2/3/3.5; lower tiers don't depend on it. |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` | The user-facing `galaxy-tool-refactor` CLI. Consumes the registry facade (tier 3.6); owns `format`, `upgrade`, `check`, `presets`, `rules`, `normalize-macros`. |
| 4 | **MCP server** | `galaxy-tool-refactor-mcp` | An agent-facing MCP server over the registry facade (a sibling of the CLI). A thin FastMCP binding (`server.py`) over a protocol-agnostic adapter (`service.py`, facade → JSON). Tools: `format_tool`/`upgrade_tool`/`check_tool`/`list_presets`/`list_rules`. Goal 1 of `docs/vision.md`; agent-authored rules (Goal 2) remain future. |

**Orchestration lives in the registry facade (tier 3.6); the CLI is a thin
front-end.** Each lower tier is consumable standalone; the facade composes them
into one code-addressable rule set with presets and a library-first
`run`/`upgrade`/`detect` API. The CLI (`galaxy-tool-refactor-cli`) depends on the
facade (plus fmt's `cli_support` engine and tier-1 parsing) and owns six
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
- `galaxy-tool-refactor normalize-macros` — opt-in, repo-scoped: lowercase literal
  `format`/`ftype` in `<macros>`-root files (the macro-library analog of 24.2
  normalization the per-tool `upgrade` can't reach). Writes files other than the one
  named, so it is never folded into `format`/`upgrade` (cli `docs/decisions.md` §D7).

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
For the per-profile upgrade map (what each profile bump requires, the
structural-vs-semantic split, and the validity-as-oracle soundness boundary)
see `docs/profile_upgrades.md` (+ codemod `docs/decisions.md` §22).
`galaxy-tool-refactor-mcp` is the agent-facing MCP server over the facade (Goal 1
of its `docs/vision.md`, shipped — see `galaxy-tool-refactor-mcp/docs/decisions.md`
D1); the agent-authored-rules direction (Goal 2) is still future.
