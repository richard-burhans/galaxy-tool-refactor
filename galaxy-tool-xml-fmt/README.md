# galaxy-tool-xml-fmt

A `black`-like opinionated cosmetic formatter for Galaxy tool XML.
The **formatting** tier of a three-layer Galaxy refactoring
architecture:

| Tier | Layer | Package | Role |
|---|---|---|---|
| 1 | **parsing & validation** | `galaxy-tool-xml` | parse · profile-aware validate · typed view |
| 2 | **structure** | `galaxy-tool-xml-codemod` | structural refactors |
| 3 | **formatting** | **`galaxy-tool-xml-fmt`** *(this repo)* | cosmetic formatter |

## Status

The format pipeline and three cosmetic rules ship; the CLI is
working. Structural canonicalisation (attribute reordering on
`<tool>` and `<param>`) lives in tier 2 and is consumed via the
optional `[canonical]` extra.

The most recent corpus sweep checked 4,052 tools across 21 public
Galaxy tool repositories with both cosmetic and structural pipelines:
100% idempotent, 0 crashes. Full numbers in
`docs/corpus_format_stats.md`.

## Role in the three-tier architecture

`galaxy-tool-xml-fmt` is the **only** component that writes Galaxy
tool XML to disk. Tiers 1 and 2 hand off mutable lxml trees with
preserved trivia (CDATA, comments, attribute order, encoding); this
tier owns the trivia-loss boundary: a format pass on a touched file
will rewrite indentation / quote style / empty-element shorthand to
the project's opinion, even when the structural change was a no-op.

The design rationale lives in `galaxy-tool-xml/docs/decisions.md`
§3 (lxml-as-source-of-truth) and §9 (three-tier vision).

## Cosmetic rules shipping (library)

| Code | Summary | Source |
|---|---|---|
| GTX001 | Canonical 4-space indentation | IUC tool-XML style |
| GTX003 | One blank line between top-level `<tool>` children | editorial |
| GTX004 | Collapse whitespace-only leaves to `<foo/>` form | editorial |

D7 and D8 in `docs/decisions.md` cover two policies — always-double-
quote attributes and one-line-per-element layout — that lxml's
serializer enforces by default; both are locked in by tests but
ship no GTX rule.

The earlier GTX002 (`<param>` attribute order) and GTX005 (`<tool>`
attribute order) were structural, not cosmetic, and have **moved**
to `galaxy-tool-xml-codemod` as `ReorderParamAttributes` and
`ReorderToolAttributes`. They're applied by the CLI when the
`[canonical]` extra is installed (see "CLI modes" below).

## Library API

`format_tool_document(document: ToolDocument) -> bytes` (imported
from `galaxy_tool_xml_fmt.format`). The function mutates the
document's lxml tree in place with the cosmetic rules above and
returns the canonical-form bytes. **No structural mutations** — to
apply the canonical structural pipeline programmatically, run
`galaxy_tool_xml_codemod.canonical.CANONICAL_CODEMODS` against the
document yourself before calling `format_tool_document`.

## CLI modes

```sh
galaxy-tool-xml-fmt path/to/tool.xml
```

The CLI mirrors `black`'s ergonomics: positional FILE/DIR args
(directories expand to `*.xml` recursively), `--check`, `--diff`,
`--quiet`.

Two modes, decided at runtime by whether the codemod package is
installed:

- **canonical** (with `[canonical]` extra) — runs
  `CANONICAL_CODEMODS` from tier 2 first, then the cosmetic rules.
  Default for the project's preferred workflow.
- **cosmetic-only** (without the extra) — runs only fmt's cosmetic
  rules; emits a one-line hint to stderr at startup.

## Setup

From the workspace root:

```sh
uv sync                    # workspace dev install (all three packages)
uv run pytest
```

End-user install (cosmetic only):

```sh
pip install galaxy-tool-xml-fmt
```

End-user install (canonical pipeline):

```sh
pip install galaxy-tool-xml-fmt[canonical]
```

## Corpus QA

Two relevant subcommands of `scripts/corpus_check.py`:

- `corpus_check.py fmt` — sweeps fmt's cosmetic-pipeline idempotence.
- `corpus_check.py codemod <dotted:Class>` — sweeps a structural
  codemod (tier 2) and retains failures as fixtures under
  `galaxy-tool-xml-codemod/tests/data/regressions/`.

Run `uv run python -m scripts.corpus_check --help` for the flags.

## Coding standards

Hand-written code follows **dignified-python** (vendored at
`.claude/skills/dignified-python/`). See `CLAUDE.md`.
