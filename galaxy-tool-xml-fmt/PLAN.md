# Plan: galaxy-tool-xml-fmt

## Status

**M0–M4 are done; the CLI has shipped (M2).** Three cosmetic rules
remain in this package (GTX001 indent, GTX003 blank line,
GTX004 empty-element shorthand); the former structural rules GTX002
(`<param>` attribute order) and GTX005 (`<tool>` attribute order) have
moved to `galaxy-tool-xml-codemod` as `ReorderParamAttributes` and
`ReorderToolAttributes`. The codemod package is an optional
`[canonical]` extra of this package; fmt's CLI orchestrates both
layers when the extra is installed. See `docs/decisions.md` §D10 for
the architecture split.

The 2026-05-28 corpus sweep checked 4,052 tools across 21 public
repos: 100% idempotent under both the cosmetic pipeline (this package)
and the structural pipeline (each canonical codemod).

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

- Indentation (canonical: 4 spaces, no tabs — GTX001)
- Attribute quoting (canonical: double quotes — locked by lxml + tests, D7)
- Empty-element shorthand (canonical: `<foo/>` over `<foo></foo>` when
  the content model permits — GTX004)
- Trailing / inner whitespace on dense leaves
- Blank-line policy (canonical: one blank between top-level sections —
  GTX003)
- One-line layout for all attributes regardless of source layout
  (locked by lxml + tests, D8)

Structural transforms applied by the CLI via the `[canonical]` extra
(implemented in `galaxy-tool-xml-codemod`):

- `<param>` attribute order (canonical: IUC order — `ReorderParamAttributes`,
  was GTX002 in this package)
- `<tool>` attribute order (canonical: id, name, version, profile,
  alphabetical — `ReorderToolAttributes`, was GTX005)

## Milestone status

### M0 — scaffold ✅

`pyproject.toml`, `src/galaxy_tool_xml_fmt/`, `tests/`,
`galaxy-tool-xml` declared as a dependency, ruff / mypy / pytest
configured.

### M1 — format(document) returning bytes ✅

`format_tool_document(document) -> bytes` in
`galaxy_tool_xml_fmt.format` runs every registered rule via
`apply_edits` and serialises through lxml.

### M2 — CLI ✅

`galaxy-tool-xml-fmt FILE...` writes canonical formatting back to each
file in place. Mirrors `black`'s ergonomics: `--check`, `--diff`,
`--quiet`, recursive directory discovery. The CLI also performs
optional structural canonicalisation via `[canonical]` extra (see
`docs/decisions.md` §D10).

### M3 — Attribute / element ordering rules → moved to codemod tier

Originally landed here as GTX002 (`<param>`) and GTX005 (`<tool>`);
2026-05-28 they were relocated to `galaxy-tool-xml-codemod` as
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

- **Tool-XML-specific rules beyond GTX001–005.** Galaxy idioms a
  generic formatter wouldn't know about — Cheetah blocks inside
  `<command>`, formatting around `<expand>` / `<macro>`. Each
  deserves a dedicated rule; track in `docs/decisions.md` as
  evidence accumulates.
- **Integration with tier 2.** Tier 2 will call this internally for
  diff display in its test harness; the `format_tool_document` API is
  already stable for that path.

## v0.1 acceptance

1. `uv sync`, `uv run pytest`, `uv run ruff check .`, `uv run ruff
   format --check .`, `uv run mypy src` all clean.
2. `uv run python scripts/corpus_check.py` reports 0 non-idempotent
   and 0 crashed on the current `corpus_sources.json` snapshot.
3. M2 ships: `galaxy-tool-xml-fmt FILE...` works end-to-end with
   `--check` and `--diff`.
