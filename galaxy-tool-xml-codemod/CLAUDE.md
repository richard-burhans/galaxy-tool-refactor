# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`galaxy-tool-xml-codemod` is the **structure** tier of the Galaxy tool
refactoring framework — one of seven tiers (this package depends only on tier 1
and the shared tier-0.5 rules metadata):

| Tier | Layer | Package | What it owns |
|---|---|---|---|
| 0.5 | **rule metadata** | `galaxy-tool-refactor-rules` | shared `RuleMeta` + `Violation` |
| 1 | **parsing & validation** | `galaxy-tool-xml` | parsing, profile-aware XSD validation, typed views |
| 2 | **structure** | `galaxy-tool-xml-codemod` *(this repo)* | structural mutations (attribute order, element shape) |
| 3 | **formatting** | `galaxy-tool-xml-fmt` | whitespace / indentation / shorthand; the only tier that writes XML to disk |
| 3.5 | **advisory checks** | `galaxy-tool-xml-check` | detect-only IUC best-practice checks |
| 3.6 | **rule registry / presets** | `galaxy-tool-refactor-registry` | unified rule registry + presets; library-first facade |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` | composes the tiers via the facade (`format`/`upgrade`/`check`) |

This package supplies the **structural-refactor framework**: a
``CodemodCommand`` **detect-primitive** base with tag-PascalCase dispatch
(``detect_Param``, ``detect_Tool``, …) whose ``apply`` is derived from
``detect`` (each rule has a non-mutating detect phase + a fix phase), an
``lxml``-backed ``Cursor``
with typed mutation primitives (``set_attribute``, ``delete_attribute``,
``rename_attribute``, ``rename_tag``, ``reorder_attributes``,
``reorder_children``, ``remove``, ``add_child``, ``attribute_names``,
``set_text`` — the token-aware ``@PROFILE@`` rewrite, §21), a
``Module`` wrapper, a ``parse_module`` entry
point (plus ``MacroModule`` / ``parse_macro_module`` — the macro-file
counterparts wrapping a tier-1 ``MacroDocument``; ``Cursor`` is generic, so its
mutators work on a ``<macros>`` tree unchanged. The ``CodemodCommand`` base
stays tool-only until a macro-subject codemod needs it — see ``docs/decisions.md``
§20), and the bundled codemods exposed via two ordered pipeline
contracts in ``canonical.py``:

- ``CANONICAL_CODEMODS`` = ``FixTypos`` → ``ReorderParamAttributes`` →
  ``ReorderToolAttributes`` → ``ReorderToolChildren`` (the safe
  canonical/format pipeline; ``ReorderToolChildren`` = GTX013, IUC #52
  element order, validity-safe because ``<tool>`` is ``xs:all``).
- ``AUTO_UPGRADE_CODEMODS`` = ``FixTypos`` → ``UpgradeToLatest`` (the
  opt-in profile-upgrade pipeline).

``FixTypos`` and ``UpgradeToLatest`` (which loops ``UpdateProfile`` +
single-step ``upgrade_vN`` codemods from ``upgrades.py``) are
validation-driven and override ``apply``. The upgrade registry is grown
empirically from ``corpus_check codemod`` discovery sweeps; see
``docs/decisions.md`` §11–14, §16 for the canonical/upgrade split, and
§17–18 for the element-order codemod (GTX013) + the `codemod` sweep's
`--source combined` default.

**Tier independence:** this package does not depend on fmt. The
orchestration — running these pipelines and writing output through fmt's
serializer — lives in the tier-3.6 registry facade
(``galaxy-tool-refactor-registry``), which consumes ``CANONICAL_CODEMODS``
(its ``run`` / the app's ``format``) and ``AUTO_UPGRADE_CODEMODS`` (its
``upgrade``); the tier-4 app CLI (``galaxy-tool-refactor-cli``) is a thin
front-end over that facade. fmt's own CLI is cosmetic-only and does not
consume these contracts (see ``galaxy-tool-xml-fmt/docs/decisions.md``
§D12).

The architecture rationale lives in `docs/architecture.md` (a working
copy forked from `galaxy-tool-xml/docs/codemod-architecture.md` —
predates the M1-M3.5 implementation; the current shape is recorded in
`docs/decisions.md`). Milestone status and remaining work are in
`PLAN.md`.

## Coding standards

Hand-written code follows **dignified-python**, vendored at the workspace root
`.claude/skills/dignified-python/`:

- LBYL over `try/except`. Exceptions only at the CLI error boundary
  (chained `from e`) and at third-party API boundaries with no LBYL form.
- `pathlib.Path` with explicit `encoding="utf-8"` on text I/O.
- Keyword-only arguments after the first.
- Absolute imports, no re-exports, no `__all__`.
- No import-time side effects (`@cache` for module state).

`optimized-python` (`.claude/skills/optimized-python/`) is a secondary
reference; **dignified-python governs on conflict**.

## Workflow

- **Test-driven development.** New code lands tests-first (failing test,
  then minimum code to pass). One test module per source module under
  `tests/`.
- **Plan-driven**: major changes get a written plan (either under
  `~/.claude/plans/` for agent state, or in `PLAN.md` for repo-scoped
  plans) before implementation.
- **Empirical claims must be backed by data.** Use the workspace corpus
  artifacts (`../docs/corpus_data/`), `../scripts/measure.py`, and the
  `corpus_check.py codemod` subcommand when answering questions about
  real-world tool XML.
- **Decisions are recorded** in `docs/decisions.md` once they land
  (mirror the parent's `docs/decisions.md` conventions: §-numbered,
  each entry citing date and a reproduction command when relevant).
- See `galaxy-tool-xml/docs/decisions.md` §9 for the three-tier
  rationale.

## Commands

Run these from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync` — install dependencies
- `uv run --package galaxy-tool-xml-codemod pytest galaxy-tool-xml-codemod/tests/` — run tests
- `uv run ruff check galaxy-tool-xml-codemod/src galaxy-tool-xml-codemod/tests` — lint
- `uv run mypy --config-file galaxy-tool-xml-codemod/pyproject.toml galaxy-tool-xml-codemod/src` — type-check (strict)
- `uv run python -m scripts.corpus_check codemod <dotted.module>:<ClassName>` — sweep a codemod across the corpus, retain failures as fixtures
  - e.g. `uv run python -m scripts.corpus_check codemod galaxy_tool_xml_codemod.codemods.reorder_param_attributes:ReorderParamAttributes`

## Useful workspace references

- `galaxy-tool-xml/README.md` — tier-1 public API
- `galaxy-tool-xml/docs/decisions.md` §3 (trivia contract), §6 (corpus
  stats), §9 (three-tier vision)
- `galaxy-tool-xml/docs/codemod-architecture.md` — the original tier-2 design
- `galaxy-tool-refactor-registry/src/galaxy_tool_refactor_registry/apply.py` —
  the tier-3.6 facade that runs ``CANONICAL_CODEMODS`` order (consumed by
  ``run`` / the app's ``format``); `presets.py` derives the `iuc` preset from it
- `canonical.py` — the public ``CANONICAL_CODEMODS`` and
  ``AUTO_UPGRADE_CODEMODS`` pipeline contracts the registry facade consumes
- `codemods/` — bundled codemod implementations (verb-noun module names)
- `eligibility.py` — corpus-sweep profile-selection policy
- `../docs/corpus_data/combined_corpus_data.json` — every swept Galaxy
  tool, indexed for ad-hoc analysis
- `../scripts/measure.py` — master script for empirical corpus queries
