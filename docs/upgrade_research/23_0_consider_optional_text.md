# `23_0_consider_optional_text` — research note

| | |
|---|---|
| **Code** | `23_0_consider_optional_text` |
| **Profile** | 23.0 |
| **Level** | `consider` |
| **Auto-fix today** | **none** |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/15491 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

From 23.0, a text parameter that is *inferred* optional (its `optional` attribute is
not set, but it accepts an empty string) templates as `None` in Cheetah, where it
previously templated as the empty string `""`. Galaxy's message:

> "Text parameters that are inferred to be optional (i.e the `optional` tag is not
> set, but the tool parameter accepts an empty string) are set to `None` for
> templating in Cheetah. Previous to this version tools would receive the empty
> string \"\" as the templated value."

## Detection (with an upstream bug)

Galaxy's advisor scans text params lacking `optional`
(`lib/galaxy/tool_util/upgrade/__init__.py:236-239`), but does so via `_find_all`,
which (line 318-319) **ignores its xpath argument and always returns
`.//data[@from_work_dir]`** — so the upstream predicate is broken (documented in our
`profile_semantics.py` module docstring). It also scans `.//input[@type='text']`,
whereas tool params are `<param>`. Our `_detects_non_optional_text` fixes both: it
scans `.//param[@type='text']` for a missing `optional` attribute. Frequent first
blocker (489 tools in `../upgrade_behavior_block_stats.md`, re-measured 2026-06-12 with the shipped gate: token-resolved baselines + macro-expanded detection).

## Mechanical-fix feasibility

**Not safely mechanical.** The behaviour difference (`None` vs `""`) is observed by
the tool's *command/Cheetah template* — e.g. `#if $text_param` or
`$text_param.strip()` behaves differently for `None`. A faithful fix would have to
edit command logic (or set `optional`/a default) in a way that depends on what the
template does with the value. Setting `optional="false"` would change validation
semantics, not preserve templating. No deterministic XML edit preserves behaviour.

## Status / recommendation

Detect/report-only. The behaviour lives in the command template; no codemod.
