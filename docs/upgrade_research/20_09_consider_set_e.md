# `20_09_consider_set_e` — research note

| | |
|---|---|
| **Code** | `20_09_consider_set_e` |
| **Profile** | 20.09 |
| **Level** | `consider` |
| **Auto-fix today** | **none** (mechanically possible — see below) |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/9962 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

From 20.09, tool scripts run with **`set -e`** — the shell exits immediately on the
first command with a non-zero exit status. A tool whose command chains sub-commands
and *relied* on continuing past a non-zero exit must opt out with `strict="false"` on
its `<command>`. Galaxy's message:

> "Starting with profile 20.09 tools, tool scripts are executed with the 'set -e'
> instruction. … If your command uses multiple sub-commands and you'd like to allow
> them to execute with non-zero exit codes add 'strict=\"false\"' to the command tag
> to restore the tool's legacy behavior."

## Detection

Galaxy adds the code when `<command>` has **no** `strict` attribute
(`lib/galaxy/tool_util/upgrade/__init__.py:205-209`). Our `_detects_no_strict`
mirrors it (`command is not None and command.get("strict") is None`). It is a frequent
first blocker (~415 tools in `../upgrade_behavior_block_stats.md`).

## Mechanical-fix feasibility

**Behaviour-preserving fix is mechanical**: add `strict="false"` to `<command>` to
restore the pre-20.09 (no `set -e`) behaviour. Like `16_04_exit_code`, the catch is
*desirability* — `set -e` is the safer modern default, and blindly adding
`strict="false"` would pin the laxer legacy behaviour for every tool, including the
many that are perfectly fine under `set -e`. A faithful behaviour-preserving upgrade
*could* inject it; a quality-oriented upgrade would not.

## Status / recommendation

No auto-fix today. Mechanically trivial to "pin legacy," but that is usually the wrong
move — default to detect/report. If a maximally behaviour-preserving mode is ever
built, this + `16_04_exit_code` are the two "inject the legacy-restore attribute"
candidates, and both should be opt-in and clearly labelled.
