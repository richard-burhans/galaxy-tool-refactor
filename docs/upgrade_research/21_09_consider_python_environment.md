# `21_09_consider_python_environment` — research note

| | |
|---|---|
| **Code** | `21_09_consider_python_environment` |
| **Profile** | 21.09 |
| **Level** | `consider` |
| **Auto-fix today** | **none** |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/12515 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

From 21.09, **data source tools** no longer include Galaxy's virtual environment in
their runtime; tools that need it should add the `galaxy-util` package to their
requirements. Galaxy's message:

> "Starting with 21.09 data source tools, Galaxy's virtual environment is no longer
> included in the tool's runtime environment. Tools that require it, should include
> the galaxy-util package in their requirements."

## Detection

Galaxy adds the code when `tool_type == "data_source"`
(`lib/galaxy/tool_util/upgrade/__init__.py:224-226`). Our detector is
`_tool_type_is("data_source")`. Rare (~4 first-blocker tools in
`../upgrade_behavior_block_stats.md`).

## Mechanical-fix feasibility

**Not mechanically fixable.** Whether the tool actually needs `galaxy-util` depends on
what its runtime code imports — not in the XML. Auto-adding a requirement would be
guesswork. (One of three near-identical "python_environment" advisories; see
`18_09_consider_python_environment` and `24_0_consider_python_environment`.)

## Status / recommendation

Detect/report-only. Applies only to `data_source` tools (rare). No codemod.
