# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-lint` is the **advisory check** tier (tier 3.5) of the Galaxy
tool refactoring framework: read-only IUC best-practice checks that report but
never mutate.

| Tier | Layer | Package |
|---|---|---|
| 0.5 | rule metadata | `galaxy-tool-refactor-rules` |
| 1 | parsing & validation | `galaxy-tool-source` |
| 2 | structure | `galaxy-tool-codemod` |
| 3 | formatting | `galaxy-tool-fmt` |
| 3.5 | **advisory checks** | `galaxy-tool-lint` *(this repo)* |
| 3.6 | rule registry / rulesets | `galaxy-tool-refactor-registry` |
| 4 | app / CLI | `galaxy-tool-refactor-cli` |

It owns the GTR-coded **detect-only** rules (`RuleMeta.detect_only=True`): a
`CheckRule` ABC (`rules.py`), the concrete checks (the `checks/` sub-package,
split by element/source area into `tool` / `partition` / `outputs` / `inputs` /
`validators` / `tests` / `help` submodules + cross-module `_shared` helpers), and
the registry + runner (`detect.py` — `all_checks()` is an explicit list, mirroring
the codemod tier's `coded_codemods()` and fmt's `all_rules()`; `detect_violations()`).
Each check is an LBYL tree query over a tier-1 `ToolDocument` that yields the shared
tier-0.5 `Violation`.

**Tier independence.** Depends ONLY on tier 1 + tier 0.5 — never on the mutating
tiers (codemod/fmt) or the app. The advisory tier is a sibling the app composes,
not a consumer of the fixers. Findings are advisory: the app's `check` command
reports them but does not fail on them by default.

**Scope.** Covers the mechanically-detectable IUC practices (presence /
attribute / structure queries). The **flat** IUC advisories are `GTR021`,
`GTR023`–`GTR029`, `GTR033` (package `<requirement>`s pin a version, D7) plus the
`GTR032` (`&&`-vs-lone-`&`) — a real detector since D34 (the
D3 no-op era ended): the `lone_amp.py` classifier flags only the genuine
*joining* class.
(unused `<param>`, D11). **Four are the advisory `.2` half of a partition
practice** (D9/D31; registry D10): `GTR018.2` / `GTR019.2` (the `<command>` / `<help>`
CDATA mixed-content residual), `GTR020.2` (the non-provable unquoted-`$var`
residual, via the **read-only `command_text` lexer** in **tier 1**
`galaxy_tool_source.command_text`), and `GTR089.2` (`HelpRstResidual` — the invalid
`<help>` RST the repair can't safely fix, via the tier-1 `galaxy_tool_source.rst`
predicate). Each `.2` reuses the same tier-1 predicate its fixable sibling
(`GTR018.1` / `GTR019.1` / `GTR020.1` / `GTR089.1`, codemod tier) uses, so the
partition is sound and the check never depends on the codemod tier.

On top of those, the tier hosts the **planemo-parity wave `GTR038`–`GTR091`** (54
rules) — a reimplementation of every mechanically-reimplementable
`galaxy.tool_util.lint` linter, grouped by source area (citations/TODO, outputs,
embedded expressions, the full `inputs.py` correctness surface, `tests.py`, and
`<help>` RST validity via the tier-1 `galaxy_tool_source.rst` predicate — `GTR089`, now
split into the `GTR089.1` repair + `GTR089.2` residual partition, so docutils is a
tier-1 dep, not declared here — plus output reference integrity and data-param
format, `GTR090`–`GTR091`; the `GTR035.2` name-whitespace residual, D33; and the
`GTR095` id/name/version missing-or-empty trio — the half tier-1 `validate` can't
see, D35). The tier is now **70 checks total**. Each
wave check that a `<macro>` could spoof skips that tool via the tier-1 `has_macros`
raw-tree guard (`detect()` reads the un-expanded tree). The authoritative
planemo→GTR map is `../docs/planemo_linter_parity.md`; per-group rationale + corpus
counts are in `docs/decisions.md` **D12–D32**. See `../docs/iuc_best_practices.md`
for the IUC coverage map and D3–D11 for the command-text + requirement-pinning +
partition-residual + unused-param decisions.

## Coding standards

Hand-written code follows **dignified-python** (vendored at the workspace root
`.claude/skills/dignified-python/`): LBYL over try/except; `pathlib` with
explicit `encoding`; keyword-only args after the first; absolute imports, no
re-exports, no `__all__`; no import-time side effects (`@cache` for module
state). `optimized-python` is a secondary reference; **dignified-python governs
on conflict**. New checks land tests-first.

## Commands

Run from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync` — install dependencies
- `uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/` — run tests
- `uv run ruff check galaxy-tool-lint/src galaxy-tool-lint/tests` — lint
- `uv run mypy --config-file galaxy-tool-lint/pyproject.toml galaxy-tool-lint/src` — type-check (strict)

## Useful workspace references

- `galaxy-tool-refactor-rules/src/galaxy_tool_refactor_rules/violation.py` — the
  shared `Violation` these checks yield; `meta.py` — `RuleMeta` (the
  `detect_only` flag this tier sets).
- `galaxy-tool-source/README.md` — tier-1 public API (`ToolDocument`,
  `newest_valid_profile`, the typed model) the checks query.
- `galaxy-tool-refactor-cli/src/galaxy_tool_refactor_cli/cli.py` — the app
  `check` command that runs these alongside the codemod + fmt detect phases.
- `../docs/iuc_best_practices.md` — the cross-tier IUC coverage map.
