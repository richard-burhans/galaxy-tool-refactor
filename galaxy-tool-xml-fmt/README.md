# galaxy-tool-xml-fmt

A `black`-like opinionated cosmetic formatter for Galaxy tool XML.
The **formatting** tier of the Galaxy refactoring architecture:

| Tier | Layer | Package | Role |
|---|---|---|---|
| 0.5 | **rule metadata** | `galaxy-tool-refactor-rules` | shared `RuleMeta` descriptor |
| 1 | **parsing & validation** | `galaxy-tool-xml` | parse · profile-aware validate · typed view |
| 2 | **structure** | `galaxy-tool-xml-codemod` | structural refactors |
| 3 | **formatting** | **`galaxy-tool-xml-fmt`** *(this repo)* | cosmetic formatter |
| 3.5 | **advisory checks** | `galaxy-tool-xml-check` | detect-only IUC checks |
| 3.6 | **rule registry / presets** | `galaxy-tool-refactor-registry` | unified rules + presets (facade) |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` | composes the tiers via the facade (`format` / `upgrade` / `check`) |

## Status

The format pipeline and three cosmetic rules ship; the cosmetic-only
`galaxy-tool-xml-fmt` CLI is working. Structural canonicalisation
(attribute reordering on `<tool>` and `<param>`) and profile upgrades
live in tier 2 and are run by the tier-4 app
(`galaxy-tool-refactor`), not by this package's CLI.

The most recent cosmetic-pipeline sweep ran over the combined corpus
(github + toolshed, sha256-deduplicated): 9,358 unique `<tool>` documents,
of which 8,608 validate under at least one vendored profile and were
format-checked — 100% idempotent, 0 crashes, 0 regression fixtures
retained. Full numbers in `docs/corpus_format_stats.md`.

## Role in the architecture

`galaxy-tool-xml-fmt` is the **only** component that writes Galaxy
tool XML to disk. The lower tiers hand off mutable lxml trees with
preserved trivia (CDATA, comments, attribute order, encoding); this
tier owns the trivia-loss boundary: a format pass on a touched file
will rewrite indentation / quote style / empty-element shorthand to
the project's opinion, even when the structural change was a no-op.

The design rationale lives in `galaxy-tool-xml/docs/decisions.md`
§3 (lxml-as-source-of-truth) and §9 (three-tier vision); the
cosmetic-only CLI split is `docs/decisions.md` §D12.

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
`ReorderToolAttributes`. They're applied by the tier-4 app's
`galaxy-tool-refactor format` command, not by this package's CLI.

## Library API

`format_tool_document(document: ToolDocument) -> bytes` (imported
from `galaxy_tool_xml_fmt.format`). The function mutates the
document's lxml tree in place with the cosmetic rules above and
returns the canonical-form bytes. **No structural mutations** — to
apply the canonical structural pipeline programmatically, run
`galaxy_tool_xml_codemod.canonical.CANONICAL_CODEMODS` against the
document yourself before calling `format_tool_document`, or use the
tier-4 `galaxy-tool-refactor format` command, which does exactly that.

## CLI

```sh
galaxy-tool-xml-fmt path/to/tool.xml
```

The CLI mirrors `black`'s ergonomics: positional FILE/DIR args
(directories expand to `*.xml` recursively), `--check`, `--diff`,
`--quiet`. It is **cosmetic-only**: it applies fmt's cosmetic rules
and never runs codemods. For structural canonicalisation or profile
upgrades, use the tier-4 app (`galaxy-tool-refactor format` /
`galaxy-tool-refactor upgrade`).

The shared file-walking / drift-detection engine lives in
`galaxy_tool_xml_fmt.cli_support` (public); both this CLI and the
app's `format`/`upgrade` commands use it.

## Setup

From the workspace root:

```sh
uv sync                    # workspace dev install (all seven packages)
uv run pytest
```

End-user install:

```sh
pip install galaxy-tool-xml-fmt
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
