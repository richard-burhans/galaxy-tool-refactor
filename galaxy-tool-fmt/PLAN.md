# Plan: galaxy-tool-fmt

## Status

**M0–M4 are done; the CLI has shipped (M2).** Three cosmetic rules
remain in this package (GTR001 indent, GTR003 blank line,
GTR004 empty-element shorthand); the former structural rules GTR002
(`<param>` attribute order) and GTR005 (`<tool>` attribute order) have
moved to `galaxy-tool-codemod` as `ReorderParamAttributes` and
`ReorderToolAttributes`. This package — library **and** CLI — is now
cosmetic-only; the former `[canonical]` extra was removed and all
cross-tier orchestration moved to the tier-4 app
(`galaxy-tool-refactor`). See `docs/decisions.md` §D12 (which
supersedes the §D10 optional-extra split).

The corpus sweep now covers the combined corpus (github + toolshed,
sha256-deduplicated), gated on validity under any vendored profile (fmt
`docs/decisions.md` §D13): 9,358 unique `<tool>` documents, of which 8,608
validate under at least one profile and were format-checked — 100% idempotent,
0 crashes. The per-rule isolation sweep finds every GTR rule (fmt + codemod)
clean over the same corpus. See `../docs/corpus_format_stats.md` and
`../docs/corpus_rule_stats.md`.

## Design intent

A `black`-like formatter for Galaxy tool XML: one canonical formatting
per input, no user-tunable style. The opinion lives here so tiers 1
and 2 can ignore trivia. After every format pass, repeated formatting
of the output must be a no-op (idempotence).

## What we *preserve*

- Element structure, attribute names and order (where Galaxy XML
  doesn't impose semantic order, the formatter's canonical order
  applies)
- CDATA sections (the contents of `<command>`, `<configfile>`, etc.)
- XML comments — including whitespace-only ones (see `docs/decisions.md`
  D5's 2026-05-28 refinement)
- Element text content verbatim
- The XML encoding declaration

## What we *rewrite*

Cosmetic rules in this package:

- Indentation (canonical: 4 spaces, no tabs — GTR001)
- Attribute quoting (canonical: double quotes — locked by lxml + tests, D7)
- Empty-element shorthand (canonical: `<foo/>` over `<foo></foo>` when
  the content model permits — GTR004)
- Trailing / inner whitespace on dense leaves
- Blank-line policy (canonical: one blank between top-level sections —
  GTR003)
- One-line layout for all attributes regardless of source layout
  (locked by lxml + tests, D8)

Structural transforms are not applied by this package's CLI (cosmetic-only
since §D12). They live in tier 2 and are run by the tier-4 app
(`galaxy-tool-refactor`): `galaxy_tool_codemod.canonical.CANONICAL_CODEMODS`
= `FixTypos`, `ReorderParamAttributes`, `ReorderToolAttributes` (the app's
`format` command); profile upgrade is the separate `AUTO_UPGRADE_CODEMODS` =
`FixTypos`, `UpgradeToLatest` (the app's `upgrade` command). The two this
package originally owned:

- `<param>` attribute order (canonical: IUC order — `ReorderParamAttributes`,
  was GTR002 in this package)
- `<tool>` attribute order (canonical: id, name, version, profile,
  alphabetical — `ReorderToolAttributes`, was GTR005)

See `galaxy-tool-codemod/docs/decisions.md` §11–14 for the others.

## Milestone status

### M0 — scaffold ✅

`pyproject.toml`, `src/galaxy_tool_fmt/`, `tests/`,
`galaxy-tool-source` declared as a dependency, ruff / mypy / pytest
configured.

### M1 — format(document) returning bytes ✅

`format_tool_document(document) -> bytes` in
`galaxy_tool_fmt.format` runs every registered rule via
`apply_edits` and serialises through lxml.

### M2 — CLI ✅

`galaxy-tool-fmt FILE...` writes cosmetic formatting back to each
file in place. Mirrors `black`'s ergonomics: `--check`, `--diff`,
`--quiet`, recursive directory discovery. The CLI is **cosmetic-only**;
structural canonicalisation and profile upgrades are the tier-4 app's
job (`galaxy-tool-refactor format` / `upgrade`). See `docs/decisions.md`
§D12 (which superseded the §D10 optional-extra design).

### M3 — Attribute / element ordering rules → moved to codemod tier

Originally landed here as GTR002 (`<param>`) and GTR005 (`<tool>`);
2026-05-28 they were relocated to `galaxy-tool-codemod` as
`ReorderParamAttributes` and `ReorderToolAttributes`. Open questions
about which other elements deserve canonicalisation (`<output>`,
`<test>`, `<requirement>`?) now belong on the codemod side of the
fence.

### M4 — Corpus idempotence sweep ✅

`scripts/corpus_check.py` walks `corpus_sources.json`, gates on profile
26.1 validation, and asserts `format(format(x)) == format(x)`. Failing
tools are retained under `tests/data/regressions/` and replayed by
`tests/test_regressions.py` on every `pytest` run. Per-rule trigger
stats and the latest sweep numbers live in `docs/corpus_format_stats.md`.

## Open questions

- **Tool-XML-specific rules beyond GTR001–005.** Galaxy idioms a
  generic formatter wouldn't know about — Cheetah blocks inside
  `<command>`, formatting around `<expand>` / `<macro>`. Each
  deserves a dedicated rule; track in `docs/decisions.md` as
  evidence accumulates.
- **Integration with tier 2.** Tier 2 will call this internally for
  diff display in its test harness; the `format_tool_document` API is
  already stable for that path.

## v0.1 acceptance *(met; the package is published on PyPI at 0.2.0)*

1. `uv sync`, `uv run pytest`, `uv run ruff check .`, `uv run ruff
   format --check .`, `uv run mypy src` all clean.
2. `uv run python -m scripts.corpus_check fmt` reports 0 non-idempotent
   and 0 crashed on the current `corpus_sources.json` snapshot.
3. M2 ships: `galaxy-tool-fmt FILE...` works end-to-end with
   `--check` and `--diff`.
