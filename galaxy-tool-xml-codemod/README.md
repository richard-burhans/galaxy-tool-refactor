# galaxy-tool-xml-codemod

A LibCST-shaped framework for structural refactors of Galaxy tool XML.
The second tier of a planned three-tier Galaxy refactoring architecture:

| Tier | Package | Role |
|---|---|---|
| 1 | `galaxy-tool-xml` | parse · profile-aware validate · typed view |
| 2 | **`galaxy-tool-xml-codemod`** *(this repo)* | structural refactors |
| 3 | `galaxy-tool-xml-fmt` *(planned)* | `black`-like opinionated formatter |

## Status

**Pre-alpha — scope and contracts being firmed up.** The detailed design
lives in `docs/architecture.md` (working copy mirrored from
`galaxy-tool-xml/docs/codemod-architecture.md`). Open work items are
tracked in `PLAN.md`.

## Public API

To be defined. Entry point will be `parse_module(source) -> Module`
(the name mirrors LibCST's `parse_module`; the return type is our own
and is **not** a LibCST drop-in).

## Setup

```sh
# install tier 1 in editable mode if developing both in parallel
uv pip install -e ../galaxy-tool-xml
uv sync
uv run pytest
```

## Coding standards

Hand-written code follows **dignified-python** (vendored at
`.claude/skills/dignified-python/`). See `CLAUDE.md`.
