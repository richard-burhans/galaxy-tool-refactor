# Using the library instead of the CLI

Most people will reach for the command line. But every command is a thin shell over a
**library-first** core (the registry facade), so the same work is available in-process
with no subprocess and no parsing of console output: useful for a CI bot, an IDE
integration, or an agent. This page shows a couple of worked calls; for the full API
surface see [Using it as a Python library](../usage/library.md).

The facade takes a path (or bytes, or a parsed `ToolDocument`) plus a resolved set of
rule codes, and returns a structured result. It never prints and never calls
`sys.exit`.

## Report what deviates (no mutation)

```python
from pathlib import Path
from galaxy_tool_refactor_registry import facade, resolve

tool = Path("seqfilter.xml")
det = facade.detect(tool, codes=resolve.resolve_codes(rulesets=["default"]))

for v in det.violations:
    print(v.code, f"line {v.sourceline}", "advisory" if det.is_advisory(v) else "fixable", v.message)
```

Run on the tool from [the CLI walkthrough](complete-pass.md), this prints:

```text
GTR020.1 line 5 fixable single-quoted 1 behaviour-preserving Cheetah variable(s) in <command>
GTR019.1 line 16 fixable <help> body is not wrapped in CDATA
```

> **Note on codes.** The library returns the precise rule code, `GTR020.1`, while the
> CLI's `check` prints the partition **parent**, `GTR020`, for readability. They refer
> to the same rule; selecting the parent (`--select GTR020`, or
> `resolve.resolve_codes(select=["GTR020"])`) expands to include its sub-rules.

## Upgrade in-process and inspect the result

```python
up = facade.upgrade(
    tool,
    codes=resolve.resolve_upgrade_codes(),
    modernize=True,
)

print(up.baseline_profile, "->", up.reached_profile)   # 18.01 -> 25.1
print("behavior preserving:", up.behavior_preserving)  # True
upgraded_xml: bytes = up.formatted                     # the serialised result
```

`UpgradeResult` carries the whole story as data, not prose: `baseline_profile`,
`reached_profile`, `behavior_preserving` (`True` / `False` / `None`), `stopped_at`,
`blocking_codes`, and `auto_fixed_codes`. A caller decides what to do with it (open a
PR, fail a build, surface a suggestion) instead of scraping a message.

> **One gotcha.** Pass a `Path` (or a `ToolDocument` loaded from one), not raw `bytes`,
> whenever the tool `<import>`s a macro file: raw bytes have no source directory, so the
> imports cannot resolve. Self-contained tools are fine as bytes.
