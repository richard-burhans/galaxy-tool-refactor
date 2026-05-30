# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-xml-check` is the **advisory check** tier (tier 3.5) of the Galaxy
tool refactoring framework: read-only IUC best-practice checks that report but
never mutate.

| Tier | Layer | Package |
|---|---|---|
| 0.5 | rule metadata | `galaxy-tool-refactor-rules` |
| 1 | parsing & validation | `galaxy-tool-xml` |
| 2 | structure | `galaxy-tool-xml-codemod` |
| 3 | formatting | `galaxy-tool-xml-fmt` |
| 3.5 | **advisory checks** | `galaxy-tool-xml-check` *(this repo)* |
| 4 | app / CLI | `galaxy-tool-refactor-cli` |

It owns the IUC-coded **detect-only** rules (`RuleMeta.detect_only=True`): a
`CheckRule` ABC (`rules.py`), the concrete checks (`checks.py`), and the registry
+ runner (`detect.py` — `all_checks()` / `detect_violations()`). Each check is an
LBYL tree query over a tier-1 `ToolDocument` that yields the shared tier-0.5
`Violation`.

**Tier independence.** Depends ONLY on tier 1 + tier 0.5 — never on the mutating
tiers (codemod/fmt) or the app. The advisory tier is a sibling the app composes,
not a consumer of the fixers. Findings are advisory: the app's `check` command
reports them but does not fail on them by default.

**Scope.** Covers the ~10 mechanically-detectable IUC practices (presence /
attribute / structure queries). The two `<command>`-CDATA-text heuristics
(single-quoted Cheetah, `&&`-vs-`&`) are reserved placeholders (`IUC011`/`IUC012`)
— registered but `detect()` is a stub — deferred until tuned. See
`../docs/iuc_best_practices.md` for the coverage map.

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
- `uv run --package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/` — run tests
- `uv run ruff check galaxy-tool-xml-check/src galaxy-tool-xml-check/tests` — lint
- `uv run mypy --config-file galaxy-tool-xml-check/pyproject.toml galaxy-tool-xml-check/src` — type-check (strict)

## Useful workspace references

- `galaxy-tool-refactor-rules/src/galaxy_tool_refactor_rules/violation.py` — the
  shared `Violation` these checks yield; `meta.py` — `RuleMeta` (the
  `detect_only` flag this tier sets).
- `galaxy-tool-xml/README.md` — tier-1 public API (`ToolDocument`,
  `newest_valid_profile`, the typed model) the checks query.
- `galaxy-tool-refactor-cli/src/galaxy_tool_refactor_cli/cli.py` — the app
  `check` command that runs these alongside the codemod + fmt detect phases.
- `../docs/iuc_best_practices.md` — the cross-tier IUC coverage map.
