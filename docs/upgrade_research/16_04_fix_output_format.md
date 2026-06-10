# `16_04_fix_output_format` — research note

| | |
|---|---|
| **Code** | `16_04_fix_output_format` |
| **Profile** | 16.04 |
| **Level** | `must_fix` |
| **Auto-fix today** | **GTR015** `FixOutputFormatInput` (partial) |
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
but **unambiguous when the tool has exactly one data input**. Since the 2026-06-10
widening (codemod `docs/decisions.md` §40) that includes a sole *nested* input:
Galaxy keys the `format_source` lookup map by the **prefixed (qualified) name**
(`actions/__init__.py`; conditional/section ancestors contribute `name|`, `<when>`
nothing), an upstream-tested feature
(`test/functional/tools/format_source_in_conditional.xml`,
`format_source="cond|input1"`). A **repeat**-nested input has no static address
(instance-indexed prefix) and stays out.

## What GTR015 already does

`codemods/fix_output_format_input.py` (`FixOutputFormatInput`, `RuntimeGatedFix`,
`introduced_profile="16.04"`) auto-fixes exactly the unambiguous case:
`_sole_data_input_qualified_name(root)` returns the lone data input's qualified
name (bare for top-level, `cond|name` / `sect|name` for an addressable nested
one), and every `<data format="input">` output is rewritten to
`format_source="<that name>"`. Tools with zero, two-or-more, or a
repeat-nested/unnamed-grouping single data input are left for the warning to
report (size it via `scripts/measure.py output-format-input`).

## Mechanical-fix feasibility

- **Already covered** for the sole-data-input case (GTR015) — including, since
  the 2026-06-10 widening (§40), a sole conditional/section-nested input via its
  qualified name (the old "unqualified name wouldn't resolve" justification was
  true but incomplete; the *qualified* name does resolve, verified against
  Galaxy source and Galaxy's own conditional format_source test tool). The
  widening rescues **0 corpus tools** — the corpus's single nested-single tool
  is **repeat**-nested (instance-indexed prefix, no static address), so it is
  correctly still bailed — making this pure novel-tool insurance.
- GTR015 leaves **41** tools unfixed — the genuinely undecidable cases (per
  `scripts/measure.py output-format-input`): 38 with multiple data inputs
  (pre-16.04 `format="input"` resolved to the *last* form input's ext under
  Galaxy's own `TODO`-marked nondeterminism — no deterministic behaviour to
  preserve), 2 with zero data inputs (nothing to inherit from), and the 1
  repeat-nested single. These need author intent and stay detect/report-only.
  (The **33** in the header is a different metric — the count of tools where
  this code is the *first* must_fix blocker in the sequential profile walk;
  most ambiguous tools stall earlier at 16.04 on `16_04_fix_interpreter`, so 33
  is a subset.)

## Status / recommendation

Largely solved. The residual is small and inherently ambiguous — leave as
detect/warn. No further codemod work is high-value here.
