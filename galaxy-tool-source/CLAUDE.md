# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Project

`galaxy-tool-xml` is a foundation library and CLI for parsing, profile-aware
validation, and typed inspection of Galaxy tool definition XML. It is the
foundation for a separate, `black`-like Galaxy tool linter/formatter — it has
**no serializer**: it exposes the mutable lxml tree and callers serialize it
themselves.

## Commands

Run these from the **workspace root** (`galaxy-tool-refactor/`):

- `uv sync` — install dependencies; the build hook generates the per-version models.
- `uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/` — run this package's tests.
- `uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_binding.py::test_load_tool_returns_document` — run a single test.
- `uv run --package galaxy-tool-xml pytest -m slow galaxy-tool-xml/tests/` — run the xsdata codegen sweep over every vendored XSD.
- `uv run ruff check galaxy-tool-xml/src` — lint.
- `uv run mypy --config-file galaxy-tool-xml/pyproject.toml galaxy-tool-xml/src` — type-check (strict).
- `uv run python -m scripts.fetch_schemas` — download release XSDs (`--force` re-downloads all).
- `uv run python -m scripts.regenerate` — regenerate the per-version typed models from every vendored XSD.
- `uv run python -m scripts.corpus_check validate` — sweep public Galaxy tool repositories for crashes (maintainer QA).
- `uv run galaxy-tool-xml validate <file>` / `suggest <file>` / `profiles` — the CLI.
- `uv build --package galaxy-tool-xml` — build the wheel (the build hook generates the per-version models).

## Naming

The repo directory, the distribution, and the CLI command are all
`galaxy-tool-xml`; the import package is `galaxy_tool_xml`.

## Architecture

`ToolDocument` (`document.py`) wraps a mutable lxml tree — the **source of
truth**, faithfully preserving CDATA, comments, and attribute order.
`binding.py` parses (`load_tool`, `parse_tool`; `load_macros` for a `<macros>`
file → `MacroDocument`), validates (`validate_tool`), and finds a tool's newest
valid profile (`newest_valid_profile`). `MacroDocument` (`document.py`) is the
macro-file counterpart to `ToolDocument` — a mutable tree with no profile/model
and no standalone XSD validation. `profiles.py`
resolves a tool's `profile` to one of the ~28 vendored per-release XSDs.
`macros.py` handles Galaxy macros and is the sole `galaxy-util` adapter; it also
exposes read-only macro-file resolution (`imported_macro_paths`) and
token-definition lookup (`token_definitions` / `TokenDefinition`) over a tool and
its imported macro files. `bundle.py` builds a `ToolBundle` (a tool + its
transitively-imported macro documents) via `load_bundle` and renames a parameter
across the whole bundle (`rename_param_in_bundle`) — the cross-file extension of
`cheetah_rename` (decisions §21).
`corrections.py` suggests near-miss typo fixes. `schema_content.py` derives
the text-bearing element-tag set from the vendored XSDs (the fmt tier's
payload-guard source of truth). `rst.py` / `rst_markdown.py` own
the `<help>` reStructuredText subsystem: validity + surgical repair (the GTR089
partition seam, decisions §23) and the render-equivalence-gated RST → Markdown
conversion (GTR092's engine, §24; markdown-it-py rides the `[markdown]` extra). `models/` holds an
xsdata-generated read-only typed model per vendored schema version, generated at
build time by `_codegen.py` and reached via `ToolDocument.model()`;
`models/registry.py` resolves a version to its model.

The public API is the prose-declared list in `README.md`; everything else is
private and may change. For the rationale behind each architectural choice
(profile-aware validation, the lxml-as-source-of-truth contract, the macro
expansion adapter, etc.) plus assumptions about the Galaxy ecosystem and
testing-derived data, see `docs/decisions.md`.

## Coding standards

Hand-written code follows **dignified-python**, vendored at the workspace root
`.claude/skills/dignified-python/`: LBYL over `try/except`; exceptions only at
the click error boundary (chained `from e`); `pathlib` with explicit
`encoding` for text I/O; no import-time side effects (`@cache` for module
state); absolute imports, no re-exports, no `__all__`; keyword-only arguments
after the first. `optimized-python` (`.claude/skills/optimized-python/`) is
installed as a reference; **dignified-python governs on any conflict**. The
generated per-version model packages (`models/v*/`, `models/any_tool.py`) are
exempt — they are not hand-written; `models/__init__.py` and `models/registry.py`
are hand-written and are not exempt.

## Non-obvious conventions

- The lxml tree is the source of truth; the typed model is a derived read-only
  view, bound to the tool's own profile. The library does not emit XML.
- Parsing uses `strip_cdata=False`: CDATA, comments, and attribute order are
  preserved. XML is parsed from `bytes`, never a decoded `str`, so the
  document's own encoding declaration is honoured.
- The Galaxy XSD is a **post-macro-expansion** schema; `validate_tool`
  transforms the tool per `macro_handling` (default `expand`) into a throwaway
  copy and validates that — the `ToolDocument` tree is never mutated.
- `galaxy.util` is Galaxy's *internal* API; all use of it is confined to
  `macros.py`, and `galaxy-util` is pinned to a version range.
- The per-version model packages (`models/v*/`, `models/any_tool.py`) are
  generated — never hand-edit; they are gitignored, regenerated by the build
  hook and by `scripts/regenerate.py`, and excluded from ruff and mypy. Each
  generated `v*/__init__.py` re-exports its module — the one sanctioned
  exception to the no-re-exports rule.
- `schema/` holds vendored XSDs downloaded once by `scripts/fetch_schemas.py`;
  re-running is additive, `--force` re-downloads. `manifest.json` and
  `PROVENANCE.md` are committed alongside the XSDs.
- `../docs/corpus_data/` (workspace root) holds the fine-grained per-tool data
  (JSON + TSV) emitted alongside the aggregate `../docs/*_corpus_stats.md`
  artifacts; both regenerate together on a full `corpus_check.py validate` sweep.
  Toolshed row
  versions come from `.local/corpus/galaxy-toolshed/manifest.json`, which
  `fetch_toolshed.py` populates by capturing each clone's tip changeset
  before `.hg/` is removed. The combined stats markdown also carries two
  failure-reason tables (macro-expansion failures, no-valid-profile
  reasons) categorising every tool whose validity vector is empty —
  these answer the "are these our bugs?" question at a glance.
- Both validation and binding are profile-aware: `validate_tool` uses the
  per-release XSD, and `ToolDocument.model()` binds against the model for the
  tool's resolved profile (overridable via `model(version=...)`).
- Binding uses a lenient xsdata config: unknown elements/attributes are ignored,
  and schema-required fields the tree omits (an element a macro would supply)
  default to `None`, so binding an un-expanded tool never raises.
- `corrections.py` is suggest-only and independent of `validate_tool`; its
  vocabulary comes from introspecting the generated model for the tool's own
  profile, with a macro skip-set so an un-expanded tool's macro constructs are
  never flagged.
- No-profile tools validate against `16.10` (our oldest vendored XSD), matching
  Galaxy's `16.01` legacy default for a missing `profile` (`resolve_profile(None)`
  → nearest vendored = 16.10). See `docs/decisions.md` §1.5.
- Failure modes: syntax errors (`load_tool` raises, the others collect them),
  macro-expansion errors, and XSD validation errors. The XSD has no
  `targetNamespace`, so Galaxy tool XML is namespace-free.

## Implementation workarounds

Two deviations from a naive implementation, both forced by upstream bugs:

- **xsdata codegen** (`_codegen.py`): xsdata 26.2's circular-reference detector
  raises `KeyError` on the Galaxy 24.2+ schema when inner classes are nested, so
  codegen sets `output.unnest_classes = True`. Each version is generated in its
  own subprocess — xsdata caches its resolved output path process-wide.
- **Schema compilation** (`profiles.py`): Galaxy releases 19.05 through 23.0
  shipped an XSD whose `Output` type has a non-deterministic content model that
  libxml2 refuses to compile. `compiled_schema` retries after applying Galaxy's
  own release-23.1 fix (drop the redundant `Output` group) in memory — the
  vendored XSD files on disk remain verbatim.
