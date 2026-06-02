# `20_05_consider_inputs_as_json_changes` — research note

| | |
|---|---|
| **Code** | `20_05_consider_inputs_as_json_changes` |
| **Profile** | 20.05 |
| **Level** | `consider` |
| **Auto-fix today** | **none** |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/9776 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

From 20.05, the **format of data in `inputs` config files** changed slightly:
unselected optional `select`/`data_column` parameters become JSON `null` instead of
the string `"None"`, and multiple `select`/`data_column` parameters become JSON lists
instead of comma-separated strings. Galaxy's message:

> "Starting with 20.05, the format of data in 'inputs' config files changed slightly.
> Unselected optional `select` and `data_column` parameters get json null values
> instead of the string 'None' and multiple `select` and `data_column` parameters are
> lists (instead of comma separated strings)."

## Detection

Galaxy adds the code when the tool has a `<configfiles><inputs>` element
(`lib/galaxy/tool_util/upgrade/__init__.py:183`: `.//configfiles/inputs`). Our
`_detects_inputs_config` mirrors it (`root.find(".//configfiles/inputs") is not None`).

## Mechanical-fix feasibility

**Not XML-mechanical.** The behaviour change is in the *consuming code* — the script
or command that reads the generated `inputs` JSON must handle `null`/lists instead of
`"None"`/comma-strings. That logic lives outside the tool XML (in the wrapped script),
so a codemod over the XML cannot fix it.

## Status / recommendation

Detect/report-only. The fix belongs in the tool's script, not the XML. No codemod.
