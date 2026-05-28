# galaxy-tool-xml-fmt

A `black`-like opinionated formatter for Galaxy tool XML. The third
tier of a three-tier Galaxy refactoring architecture:

| Tier | Package | Role |
|---|---|---|
| 1 | `galaxy-tool-xml` | parse · profile-aware validate · typed view |
| 2 | `galaxy-tool-xml-codemod` | structural refactors |
| 3 | **`galaxy-tool-xml-fmt`** *(this repo)* | opinionated formatter |

## Status

**Pre-v0.1.** The format pipeline and five rules (GTX001–005) are
implemented; the CLI is not yet built. See `PLAN.md` for what's done
and what remains.

The 2026-05-28 corpus sweep over 21 public Galaxy tool repositories
checked 4,014 tools that validate under profile 26.1: 100% idempotent,
0 crashes after the GTX004 comment-handling fix. Full numbers in
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

## Rules currently shipping

| Code | Summary | Source |
|---|---|---|
| GTX001 | Canonical 4-space indentation | IUC tool-XML style |
| GTX002 | Canonical `<param>` attribute order | IUC + galaxy-language-server |
| GTX003 | One blank line between top-level `<tool>` children | editorial |
| GTX004 | Collapse whitespace-only leaves to `<foo/>` form | editorial |
| GTX005 | Canonical `<tool>` attribute order | Galaxy schema docs |

D7 and D8 in `docs/decisions.md` cover two policies — always-double-
quote attributes and one-line-per-element layout — that lxml's
serializer enforces by default; both are locked in by tests but
ship no GTX rule.

## API

`format_tool_document(document: ToolDocument) -> bytes` (imported
from `galaxy_tool_xml_fmt.format`). The function mutates the document's
lxml tree in place and returns the canonical-form bytes.

A `galaxy-tool-xml-fmt` CLI (mirroring `black`'s ergonomics — `--check`,
`--diff`, recursive discovery) is in the plan but not yet shipped.

## Setup

```sh
uv sync
uv run pytest
```

The tier-1 dependency `galaxy-tool-xml` is pulled from GitHub by
`pyproject.toml`. Once tier 1 is published to PyPI the source override
in `[tool.uv.sources]` will be dropped.

## Corpus QA

`scripts/corpus_check.py` shallow-clones the repositories listed in
`corpus_sources.json` (gitignored under `corpus/`) and sweeps every
tool that validates under profile 26.1 through the formatter,
checking idempotence. Any failing tool is retained as a permanent
regression fixture under `tests/data/regressions/`; the fast test
suite replays those fixtures on every `pytest` run. Run
`uv run python scripts/corpus_check.py --help` for the flags.

## Coding standards

Hand-written code follows **dignified-python** (vendored at
`.claude/skills/dignified-python/`). See `CLAUDE.md`.
