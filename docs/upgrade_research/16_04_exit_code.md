# `16_04_exit_code` — research note

| | |
|---|---|
| **Code** | `16_04_exit_code` |
| **Profile** | 16.04 |
| **Level** | `consider` |
| **Auto-fix today** | **none** (mechanically possible — see below) |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/1688 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

Pre-16.04, Galaxy detected tool errors by checking whether **anything was written to
stderr**. From 16.04, the command's **exit code** is used by default. A tool that
relied on the old stderr-based detection (and exits 0 even on failure, or writes
harmless text to stderr) changes behaviour on upgrade. Galaxy's message:

> "Starting with 16.04 tools the exit code of the command executed will be used to
> detect errors by default. … Add `<stdio><regex match=".*" source="stderr"
> level="fatal" description="Unknown error encountered" /></stdio>` to your tool to
> restore the legacy behavior or restructure your command block to rely on the exit
> code."

## Detection

Galaxy adds the code when the tool has **no `<stdio>` and no `<command detect_errors>`**
(`lib/galaxy/tool_util/upgrade/__init__.py:129-132`). Our `_detects_no_error_handling`
mirrors it exactly:

```python
return (root.find(".//stdio") is None
        and root.find(".//command[@detect_errors]") is None)
```

## Mechanical-fix feasibility

**Behaviour-preserving fix is mechanical and well-defined**: inject the legacy
stderr-fatal `<stdio>` block quoted in the message. That reproduces the pre-16.04
error semantics exactly for any tool lacking error handling.

The caveat is *desirability*: doing so **pins the legacy (stderr-based) behaviour**,
which is generally worse than exit-code detection — the modern recommendation is to
adopt exit codes, not restore stderr scanning. So a strictly behaviour-preserving
upgrade *can* auto-insert it, but a quality-oriented upgrade would rather leave it for
human review (adopt the better default). This is the classic "we can preserve it, but
should we?" case.

## Status / recommendation

No auto-fix today. A `RuntimeGatedFix` that injects the legacy `<stdio>` block is
**feasible** if/when we want a maximally behaviour-preserving upgrade — but it should
be opt-in and clearly framed as "pin legacy error detection," not a best-practice fix.
Default to detect/report.
