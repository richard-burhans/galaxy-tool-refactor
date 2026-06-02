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

**A behaviour-preserving restore is mechanical and well-defined**: inject
`use_shared_home="true"` on `<command>` — a single attribute Galaxy's parser honours
(`command_el.get('use_shared_home')` flips `job_home` vs `shared_home`, `xml.py:301-307`),
which faithfully pins the pre-18.01 shared-home default. This is the same shape as the
`16_04_exit_code` (`<stdio>`) and `20_09_consider_set_e` (`strict="false"`)
legacy-restore opt-ins.

The catch is *desirability*, identical to `set_e`'s "set -e is the safer modern
default" caveat: most tools don't need shared home (Galaxy notes "most tools should
not depend on global state"), so pinning it over-applies. Galaxy lists this among the
"could be more precise" items it deliberately leaves as advice (`upgrade/__init__.py:9`).

## Status / recommendation

Detect/report-only — a legacy-restore opt-in (`use_shared_home="true"`), not applied
by default because it pins worse behaviour. Niche; no codemod today.
