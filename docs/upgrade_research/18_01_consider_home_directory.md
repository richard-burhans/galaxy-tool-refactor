# `18_01_consider_home_directory` — research note

| | |
|---|---|
| **Code** | `18_01_consider_home_directory` |
| **Profile** | 18.01 |
| **Level** | `consider` (niche) |
| **Auto-fix today** | **none** |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/5193 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

From 18.01, each job gets its **own home directory**. A tool that depended on global
state in a shared home must opt back in with `use_shared_home="true"` on its
`<command>`. Galaxy's message:

> "Starting with profile 18.01 tools, each job is given its own home directory. Most
> tools should not depend on global state in a home directory, if this is required
> though set 'use_shared_home=\"true\"' on the command tag of the tool."

## Detection

Galaxy adds the code when `<command>` has **no** `use_shared_home` attribute
(`lib/galaxy/tool_util/upgrade/__init__.py:155-157`). Our `_detects_no_shared_home`
mirrors it (`command is not None and command.get("use_shared_home") is None`).

## Mechanical-fix feasibility

**Not mechanically decidable.** Whether the tool relies on a shared home depends on
what its command/scripts read from `$HOME` — invisible in the XML. Auto-adding
`use_shared_home="true"` everywhere would wrongly pin the legacy behaviour for the
vast majority that don't need it (Galaxy itself notes "most tools should not depend
on global state"). Galaxy lists this among the "could be more precise" items it
deliberately leaves as advice (`upgrade/__init__.py:9`).

## Status / recommendation

Detect/report-only. Niche; no codemod.
