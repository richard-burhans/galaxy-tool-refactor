# `18_01_consider_structured_like` — research note

| | |
|---|---|
| **Code** | `18_01_consider_structured_like` |
| **Profile** | 18.01 |
| **Level** | `consider` |
| **Auto-fix today** | **none** |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/6162 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

From 18.01, the `structured_like` attribute (on an output `<collection>`) must
reference inputs in a **fully-qualified** manner — using `|` to name parent
conditionals/sections. Galaxy's message:

> "Starting with 18.01 tools, the 'structured_like` attribute must reference inputs
> in a fully qualified manner - using '|' to describe parent conditionals for
> instance."

## Detection

Galaxy adds the code when an output collection declares `structured_like`
(`lib/galaxy/tool_util/upgrade/__init__.py:159`:
`.//outputs/collection[@structured_like]`). Our `_detects_structured_like` mirrors it
(`root.find(".//outputs/collection[@structured_like]") is not None`).

## Mechanical-fix feasibility

**Partial / hard.** Fully-qualifying a name requires walking the input tree to find
the referenced input and computing its `parent|…|name` path — doable in principle
with the parsed model, but only when the reference is unambiguous (a single input of
that name). Galaxy's own source notes this is a candidate for "more specific advice"
but doesn't auto-fix (`upgrade/__init__.py:10`). Rare in the corpus (it is the first
blocker for ~1 tool in `../upgrade_behavior_block_stats.md`).

## Status / recommendation

Detect/report-only. Low frequency and ambiguous; not a high-value codemod.
