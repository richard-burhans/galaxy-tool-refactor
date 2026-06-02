# `24_0_request_cleaning` — research note

| | |
|---|---|
| **Code** | `24_0_request_cleaning` |
| **Profile** | 24.0 |
| **Level** | `consider` |
| **Auto-fix today** | **none** |
| **Galaxy PR** | (none recorded in the catalogue) |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

From 24.0, **data source tools** require explicit `request_param_translation` for each
parameter sent to the tool; a tool relying on unspecified parameters needs new XML
elements added for them. Galaxy's message:

> "Starting with 24.0 data source tools, Galaxy requires explicit
> `request_param_translation` for each parameter sent to the tool. If this tools
> depends on unspecified parameters - new xml elements will need to be added for these
> parameters."

## Detection

Galaxy adds the code when `tool_type` is `data_source_async` **or** `data_source`
(`lib/galaxy/tool_util/upgrade/__init__.py:252-253`). Our detector is
`_tool_type_is("data_source_async", "data_source")`.

## Mechanical-fix feasibility

**Not mechanically fixable.** Knowing *which* request parameters the tool depends on
(and thus what `request_param_translation` elements to add) requires understanding the
external data-source request contract — not present in the tool XML. There is no
deterministic edit.

## Status / recommendation

Detect/report-only. Applies only to data-source tools (rare). No codemod.
