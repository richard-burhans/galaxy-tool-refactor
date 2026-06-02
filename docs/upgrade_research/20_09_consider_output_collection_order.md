# `20_09_consider_output_collection_order` — research note

| | |
|---|---|
| **Code** | `20_09_consider_output_collection_order` |
| **Profile** | 20.09 |
| **Level** | `consider` |
| **Auto-fix today** | **none** |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/10434 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

From 20.09, the **order of elements defined in tool tests** became relevant for
verifying that collections are properly sorted. Tests may start failing after the
upgrade and need their `<element>` order rearranged. Galaxy's message:

> "Starting in profile 20.09 tools, the order elements defined in tool test became
> relevant in order to verify collections are properly sorted. This may cause tool
> tests to fail after the upgrade, rearrange the elements defined in output
> collections if this occurs."

## Detection

Galaxy parses the tests and adds the code when any test `output_collection` has
`element_tests` (`lib/galaxy/tool_util/upgrade/__init__.py:195-203`). Our
`_detects_output_collection_order` approximates this on the raw tree: any
`<output_collection>` (a test-only construct) with an `<element>` descendant.

## Mechanical-fix feasibility

**Not mechanically fixable.** The correct element order is the *actual* sorted order
the tool produces at runtime — unknowable from the XML. Rearranging blindly could make
a passing test wrong. Only a human (or a test run) can determine the right order.

## Status / recommendation

Detect/report-only. A test-semantics issue, surfaced for review. No codemod.
