# `18_09_consider_python_environment` — research note

| | |
|---|---|
| **Code** | `18_09_consider_python_environment` |
| **Profile** | 18.09 |
| **Level** | `consider` |
| **Auto-fix today** | **none** |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/6466 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

From 18.09, **data managers** run without Galaxy's own virtual environment, so a data
manager that implicitly used a Python package shipped in Galaxy's venv must now
declare it. Galaxy's message:

> "Starting with profile 18.09 tools, data managers run without Galaxy's virtual
> environment. Be sure your requirements reflect all the data manager's dependencies."

## Detection

Galaxy adds the code when the tool's `tool_type == "manage_data"`
(`lib/galaxy/tool_util/upgrade/__init__.py:170-172`). Our detector is
`_tool_type_is("manage_data")`.

## Mechanical-fix feasibility

**Not mechanically fixable.** "Make sure your `<requirements>` cover all deps" needs
knowledge of what the data manager's code imports — not present in the tool XML. There
is no deterministic edit. (This is one of three near-identical "python_environment"
advisories; see also `21_09_consider_python_environment` and
`24_0_consider_python_environment`.)

## Status / recommendation

Detect/report-only. Applies only to `manage_data` tools (rare). No codemod.
