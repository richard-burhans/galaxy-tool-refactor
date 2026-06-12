# `24_2_fix_test_case_validation` — research note

| | |
|---|---|
| **Code** | `24_2_fix_test_case_validation` |
| **Profile** | 24.2 |
| **Level** | `must_fix` |
| **Auto-fix today** | **none** |
| **Stuck tools** (must_fix-only) | **6,033**, the largest blocker (see `../upgrade_behavior_block_stats.md`; re-measured 2026-06-12 with the shipped gate, which resolves `@PROFILE@` baselines and detects on the macro-expanded view, so ~1,500 previously-excluded tools now count) |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/18679 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed at 24.2

From profile 24.2, a tool's `<test>` cases must validate against a **stricter,
Pydantic-model-based schema** derived from the tool's parameters. The migration
turns ill-specified test cases (that Galaxy previously tolerated) into hard errors.
Galaxy's message:

> "Starting with 24.2 tools, test cases must validate against a more stringent
> schema. Unknown parameters are disallowed (prevents misspellings), select
> parameters must be specified by value (to prevent ambiguity and match the API),
> column parameters must be specified as integers, and parameters must be full
> qualified ('|' separation to include parent repeat, cond, and sections)."

## How Galaxy validates (verified)

The validator builds a Pydantic model of the tool's parameters and validates each
parsed test case against it:

- Entry point: `lib/galaxy/tool_util/parameters/case.py:363-378`
  (`validate_test_cases_for_tool_source`) → builds the model via
  `input_models_for_tool_source(...)`, then validates each `<test>` with
  `test_case_state()` / `TestCaseToolState.validate()`.
- The model is **strict**: `create_model_strict` sets
  `ConfigDict(extra="forbid", …)` (`lib/galaxy/tool_util_models/parameters.py`), so
  **unknown/misspelled parameter names** are rejected.
- **`select` must be a value, not a label** — *for static-option selects only*:
  `SelectParameterModel.py_type_if_required` builds a `Literal` type from option
  **values**, so a test using the option label fails. This applies **only** to
  static-option selects; a dynamic-options select (`options is None`,
  `parameters.py:1808-1809`) validates as `StrictStr` (`parameters.py:1725`) and
  accepts any string, so it never trips this rule.
- **`data_column` must be an integer index** — *for the column-name case only*: an
  integer-as-string value (e.g. `"1"`) is coerced to `int` **unconditionally at any
  profile** (`case.py:133-139`); only the column-**name** pattern `"c1: …"`
  (`COLUMN_NAME_STR_PATTERN`) is profile-gated — coerced for profile < 24.2, left a
  string at ≥ 24.2 where the model expects `StrictInt` → fails (`case.py:140-148`).
- **Fully-qualified names**: nested params must use `parent|child` paths
  (`visitor.py:130-136` `flat_state_path`, paths built in `case.py`).

The profile gate lives inside the coercion (`case.py:140`:
`elif Version(profile) < Version("24.2"):` allows the old leniency).

## Detection — Galaxy vs ours (important caveat)

Galaxy's advisor **actually runs the validator** and reports any failure
(`lib/galaxy/tool_util/upgrade/__init__.py:256-266`, `ProfileMigration24_2.advise`
calls `validate_test_cases_for_tool_source(..., use_latest_profile=True)` and adds
the code per `result.validation_error`).

**Our detector is only an approximation**: `_detects_has_test` fires when the tool
ships any `tests/test` (a necessary condition — no `<test>` ⇒ the code can't trip).
We do **not** vendor Galaxy's parameter-model validator, so we cannot tell whether a
given tool's tests *actually* fail. Consequence: our **6,033 over-counts**; it is
"tools that ship tests and are below 24.2," an upper bound. The true number is some
subset whose tests violate one of the four rules — and **smaller than the four-rule
list suggests**, because two of the rules have escape hatches that exempt most cases:
the select rule applies only to *static*-option selects (dynamic-options selects
accept any string), and the `data_column` rule fails only on column-*name* strings
(integer-as-string values coerce at any profile). So the true-failure subset is
materially below 6,033.

## The faithful fix (per violation)

- Unknown/misspelled param → remove or correct the name.
- `select` label → replace with the option's `value`.
- `data_column` name → replace with the integer index.
- Nested param → prefix with the `parent|…|child` qualified path.

The qualified-name and unknown-name fixes are largely derivable from the tool XML
structure. The **select label→value** and **column name→index** fixes need the
parameter model (option value mapping, column semantics) and sometimes author intent.

## Mechanical-fix feasibility

- **Detection** beyond our `<test>`-presence heuristic would require porting (or
  importing) Galaxy's `galaxy.tool_util.parameters` validator — a heavy dependency
  we currently don't carry. Without it we can only say "has tests," not "tests fail."
- **Fixing** is mixed: name-qualification could be mechanical given the parsed model,
  but select/column corrections are ambiguous. A reliable codemod is **not**
  straightforward.

**Why the select label→value fix is not mechanically safe** (recorded so it isn't
revisited as "easy"): (1) dynamic-options selects (`from_dataset` / `from_data_table`
/ `dynamic_options=` code) carry no value table — Galaxy validates them as `StrictStr`
(`parameters.py:1724-1725`; `options` stays `None`), so a blind rewrite has nothing to
map against and would corrupt currently-valid values; (2) for a static select the test
value alone cannot be classified as a label-needing-rewrite vs an already-correct value
vs a label that coincidentally equals another option's value (the `Literal` is built
from values only, `parameters.py:1720`). If a fix is ever scoped, restrict it to
static-options selects with the parsed option set, and guard idempotence for values
that already validate.

## The measured truth (2026-06-12)

Reproduced by: `uv run python -m scripts.measure test-case-validation-truth`
(runs Galaxy's REAL validator, the exact `ProfileMigration24_2.advise` call,
over every test-shipping corpus tool; needs the `galaxy-tool-util` dev
dependency and the corpus).

Of the **6,648** unique tools shipping at least one `<test>` (the detector's
upper-bound population):

| Outcome | Tools | Share |
|---|--:|--:|
| Every test case validates at 24.2 (would NOT block) | **4,517** | 67.9% |
| At least one invalid test case (**true blockers**) | **1,972** | 29.7% |
| Galaxy's own test parser/model raises (retained) | 159 | 2.4% |

So the true blocker population is **1,972, roughly one third of the 6,033 the
ships-a-`<test>` detector counts as first blockers** in
`../upgrade_behavior_block_stats.md`; the other two thirds of test-shipping
tools could advance past 24.2 today if the detector could tell them apart
(PR 3 of the behavior-gate arc). Per-case validation-error kinds across the
1,972: `type-or-value-mismatch` 2,380 cases (strict pydantic coercion),
`unknown-parameter` 2,159 ("Invalid parameter name found", the
name-qualification / typo class and the PR 4 mechanical-fix candidate),
`extra-input-forbidden` 52, `other` 43. The 159 validator-error tools (Galaxy
rejects the test block before validation, e.g. an output with nothing to
check) are listed in `../corpus_data/test_case_validation_errors.json`.

## Status / recommendation

The largest behaviour-block by our heuristic, and the truth measure above
shows the headline count is inflated roughly 3x by the detector
approximation. Next steps, in order: ship the real validator behind a tier-2
`[galaxy]` extra with the static checker as the no-extra fallback (PR 3),
then revisit the `unknown-parameter` subset for a mechanical
name-qualification fix (PR 4). Treat as **detect/report-only** until then; a
mechanical fix beyond that subset is low-confidence and only partial.
