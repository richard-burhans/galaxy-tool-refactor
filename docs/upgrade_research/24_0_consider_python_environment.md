# `24_0_consider_python_environment` — research note

| | |
|---|---|
| **Code** | `24_0_consider_python_environment` |
| **Profile** | 24.0 |
| **Level** | `consider` |
| **Auto-fix today** | **none** |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/17422 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

From 24.0, **async data source tools** no longer include Galaxy's virtual environment
in their runtime; tools that need it should add `galaxy-util` to their requirements.
Galaxy's message:

> "Starting with 24.0 async data source tools, Galaxy's virtual environment is no
> longer included in the tool's runtime environment. Tools that require it, should
> include the galaxy-util package in their requirements."

## Detection

Galaxy adds the code when `tool_type == "data_source_async"`
(`lib/galaxy/tool_util/upgrade/__init__.py:249-251`). Our detector is
`_tool_type_is("data_source_async")`.

## Mechanical-fix feasibility

**Not mechanically fixable** — identical reasoning to the other two
"python_environment" advisories (`18_09_consider_python_environment`,
`21_09_consider_python_environment`): the dependency need is invisible in the XML.

## Status / recommendation

Detect/report-only. Applies only to `data_source_async` tools (very rare). No codemod.
