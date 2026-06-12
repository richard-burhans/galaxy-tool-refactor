# `16_04_consider_implicit_extra_file_collection` — research note

| | |
|---|---|
| **Code** | `16_04_consider_implicit_extra_file_collection` |
| **Profile** | 16.04 |
| **Level** | `consider` (niche) |
| **Auto-fix today** | **none** |
| **Detector** | fires **unconditionally** |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/1688 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

Pre-16.04, Galaxy would *implicitly* discover tool outputs by looking in the job
working directory for files keyed on an output's ID. From 16.04 this stops: outputs
must be **explicitly declared**, and dynamic outputs must be specified via a
`galaxy.json` file or a `<discover_datasets>` block. Galaxy's message:

> "Starting with profile 16.04 tools, Galaxy no longer attempts to just find tool
> outputs keyed on the output ID in the working directory. Tool outputs need to be
> explicitly declared and dynamic outputs need to be specified in a 'galaxy.json'
> file or with a 'discover_datasets' block."

## Detection

Galaxy emits this **unconditionally** within the 16.04 migration
(`lib/galaxy/tool_util/upgrade/__init__.py:124`:
`advice_collection.add("16_04_consider_implicit_extra_file_collection")` with no
guard). Our detector mirrors that: `_DETECTORS["16_04_consider_implicit_extra_file_collection"] = lambda _root: True`.

Because it is unconditional, **every** sub-16.04 tool trips it. This is exactly why
the `must_fix`+`consider` policy in `../upgrade_behavior_block_stats.md` shows 5,386
tools stalling here (re-measured 2026-06-12 with the shipped gate: token-resolved
baselines + macro-expanded detection) (it is the catalogue-first applicable code at 16.04, so it
shadows the others as the "first blocker").

## Mechanical-fix feasibility

**Not mechanically fixable.** The advice is "make sure you aren't relying on implicit
discovery." Whether a given tool actually depended on the old implicit behaviour
cannot be decided from the XML — it depends on what the tool's command writes to the
working directory. There is nothing to rewrite.

## Status / recommendation

Detect/report-only by nature. Its unconditional firing is the main reason a strict
(every-`consider`) behaviour-preserving upgrade is effectively impossible for
sub-16.04 tools — a finding, not a fixable defect.
