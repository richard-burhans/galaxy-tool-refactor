# `16_04_fix_output_format` — research note

| | |
|---|---|
| **Code** | `16_04_fix_output_format` |
| **Profile** | 16.04 |
| **Level** | `must_fix` |
| **Auto-fix today** | **GTX015** `FixOutputFormatInput` (partial) |
| **Stuck tools** (must_fix-only) | **33** — tools where this code is the *first* must_fix blocker in the sequential profile walk (a subset of the 41 ambiguous; the rest stall earlier at 16.04 on `16_04_fix_interpreter`). See `../upgrade_behavior_block_stats.md` |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/1688 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What the feature was

An output could declare `<data format="input" .../>`, meaning *"this output's
datatype should be inherited from an input."* It was a shorthand for format
inheritance without naming which input.

## What it did / why it was disabled

`format="input"` was a sentinel handled specially throughout the output code
(e.g. `lib/galaxy/tool_util/parser/output_objects.py:161` treats `format != "input"`
as the "real format" case). The problem: with multiple inputs it was **undefined
which input** the format came from. Galaxy's upgrade message states it plainly:

> "Starting with 16.04 tools, having format='input' on a tool output is disabled.
> The behavior was not well defined for these outputs. Please add
> format_source=\"a_specific_input_name\" for a specific input to inherit the
> format from."

The modern, explicit replacement is `format_source="<input name>"`
(`parser/xml.py:589`: `output.format_source = data_elem.get("format_source", …)`),
which names exactly one input to inherit from.

## Detection (ours mirrors Galaxy's)

Galaxy's advisor (`lib/galaxy/tool_util/upgrade/__init__.py:126-127`):

```python
if _has_matching_xpath(tool_source, ".//data[@format = 'input']"):
    advice_collection.add("16_04_fix_output_format")
```

Our `_detects_output_format_input` uses the identical xpath
(`root.find(".//data[@format='input']")`) — a faithful mirror.

## The faithful fix

Replace `format="input"` with `format_source="<input name>"` on the output `<data>`.
This requires **choosing which input** to inherit from — author intent in general,
but **unambiguous when the tool has exactly one data input addressable by an
unqualified name** (a single top-level `<param type="data">`).

## What GTX015 already does

`codemods/fix_output_format_input.py` (`FixOutputFormatInput`, `RuntimeGatedFix`,
`introduced_profile="16.04"`) auto-fixes exactly the unambiguous case:
`_sole_top_level_data_input_name(root)` returns the lone top-level data input's
name, and every `<data format="input">` output is rewritten to
`format_source="<that name>"`. Tools with zero, two-or-more, or a *nested* single
data input are left for the warning to report. Per the codemod docstring this
covers ~109 of ~150 corpus tools with a `format="input"` output (size it via
`scripts/measure.py output-format-input`).

## Mechanical-fix feasibility

- **Already covered** for the sole-data-input case (GTX015).
- GTX015 leaves **41** tools unfixed — the genuinely ambiguous cases (per
  `scripts/measure.py output-format-input`): 38 with multiple data inputs (which
  one?), 2 with zero data inputs (nothing to inherit from), and 1 with a nested
  single data input (the unqualified name wouldn't resolve). These need author
  intent and should stay detect/report-only. (The **33** in the header is a
  different metric — the count of tools where this code is the *first* must_fix
  blocker in the sequential profile walk; most ambiguous tools stall earlier at
  16.04 on `16_04_fix_interpreter`, so 33 is a subset of the 41.)

## Status / recommendation

Largely solved. The residual is small and inherently ambiguous — leave as
detect/warn. No further codemod work is high-value here.
