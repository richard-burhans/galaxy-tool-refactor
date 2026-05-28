# Plan: galaxy-tool-xml-fmt

## Status

**M0–M4 are done. M2 (CLI) is the remaining v0.1 work.** Five rules
ship (GTX001–005), the format pipeline is wired, the regression
fixture-replay test is green on every retained corpus failure, and the
2026-05-28 sweep over 21 public repos found 100% idempotence on the
4,014 tools that validate under profile 26.1.

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

- Indentation (canonical: 4 spaces, no tabs — GTX001)
- Attribute quoting (canonical: double quotes — locked by lxml + tests, D7)
- Empty-element shorthand (canonical: `<foo/>` over `<foo></foo>` when
  the content model permits — GTX004)
- Trailing / inner whitespace on dense leaves
- Blank-line policy (canonical: one blank between top-level sections —
  GTX003)
- `<param>` attribute order (canonical: IUC order — GTX002)
- `<tool>` attribute order (canonical: id, name, version, profile,
  alphabetical — GTX005)
- One-line layout for all attributes regardless of source layout
  (locked by lxml + tests, D8)

## Milestone status

### M0 — scaffold ✅

`pyproject.toml`, `src/galaxy_tool_xml_fmt/`, `tests/`,
`galaxy-tool-xml` declared as a dependency, ruff / mypy / pytest
configured.

### M1 — format(document) returning bytes ✅

`format_tool_document(document) -> bytes` in
`galaxy_tool_xml_fmt.format` runs every registered rule via
`apply_edits` and serialises through lxml.

### M2 — CLI ⏳ *(remaining v0.1 work)*

`galaxy-tool-xml-fmt FILE...` writes canonical formatting back to each
file in place. Mirror `black`'s ergonomics: `--check`, `--diff`,
`--quiet`, recursive directory discovery,
`pyproject.toml`-based config later if it earns its keep.

The entry point in `pyproject.toml` (`galaxy_tool_xml_fmt.cli:main`)
is wired but the module doesn't exist yet — pip-installing today and
running the binary errors with `ModuleNotFoundError`.

### M3 — Attribute / element ordering rules ✅ (so far)

GTX002 (`<param>`) and GTX005 (`<tool>`) ship. The shared
`attribute_ordering` helper makes adding a new per-element-kind rule
a priority-map + one-line registration. Open: which other elements
the community will want canonicalised (`<output>`, `<test>`,
`<requirement>`?). Deferred until a real ask lands.

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
