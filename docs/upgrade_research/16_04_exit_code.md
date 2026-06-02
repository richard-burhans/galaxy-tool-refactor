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

**A mechanical fix exists**: inject the legacy stderr-fatal `<stdio>` block quoted
in the message — Galaxy's own verbatim recommended snippet. It is *faithful to
Galaxy's advice* but **not byte-for-byte equivalent to the true legacy default**.
The pre-16.04 default (`output_checker.py:194`, `if stderr:`) fails a job only when
stderr is a **non-empty** string and ignores the exit code, whereas the injected
`<regex match=".*" source="stderr" level="fatal">` is evaluated via
`re.search(".*", stderr, re.IGNORECASE)` (`output_checker.py:77`), and `.*` matches
the **empty** string — so a clean successful run with empty stderr is OK under the
legacy default but **fatal** under the injected block. That is the common success
path, not a rare edge: a known fidelity gap to disclose if/when this becomes an
opt-in `RuntimeGatedFix`.

The caveat is *desirability*: doing so **pins the legacy (stderr-based) behaviour**,
which is generally worse than exit-code detection — the modern recommendation is to
adopt exit codes, not restore stderr scanning. So a strictly behaviour-preserving
upgrade *can* auto-insert it, but a quality-oriented upgrade would rather leave it for
human review (adopt the better default). This is the classic "we can preserve it, but
should we?" case.

## Macro-expansion hazard (sizing)

`_detects_no_error_handling` runs on the **raw** tree, but a tool's `<stdio>` is very
often supplied by an imported macro (`<expand macro="stdio"/>`), invisible until
expansion. The `macro-expansion-detection-gap` measure (2026-06-02, 5,113 macro-bearing
tools compared) found **984 tools (19.2%) where this code fires on the raw tree but
not after expansion** — i.e. they already have error handling via a macro. For this
code raw reports 1,590 hits but only 606 are genuine post-expansion: a **62%
false-positive rate**, the single largest raw-vs-expanded divergence in the corpus
(reproduce: `uv run python -m scripts.measure macro-expansion-detection-gap`).

**Hard rule for any future fix:** a `<stdio>`-injecting auto-fix must run off the
**macro-expanded** view (or otherwise prove no macro supplies `<stdio>`). Injecting on
the raw tree would **double-inject** error handling into those 984 tools. As a
report-only detector this divergence is only cosmetic over-reporting; it becomes a
correctness bug the moment a fix acts on it.

## Status / recommendation

No auto-fix today. A `RuntimeGatedFix` that injects the legacy `<stdio>` block is
**feasible** if/when we want a maximally behaviour-preserving upgrade — but it should
be opt-in and clearly framed as "pin legacy error detection," not a best-practice fix,
and (per the hazard above) must be **expansion-aware** to avoid double-injection.
Default to detect/report.
