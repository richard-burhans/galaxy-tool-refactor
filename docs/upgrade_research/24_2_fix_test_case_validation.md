# `24_2_fix_test_case_validation` — research note

| | |
|---|---|
| **Code** | `24_2_fix_test_case_validation` |
| **Profile** | 24.2 |
| **Level** | `must_fix` |
| **Auto-fix today** | **none** |
| **Stuck tools** (must_fix-only) | **4,498** — the largest blocker (see `../upgrade_behavior_block_stats.md`) |
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
- **`select` must be a value, not a label**: `SelectParameterModel.py_type_if_required`
  builds a `Literal` type from option **values** only — a test using the option
  label fails.
- **`data_column` must be an integer index**: `case.py:123-149` only coerces a
  column-name string (e.g. `"c1: Transaction_date"`) for profile < 24.2; at ≥ 24.2 it
  leaves it a string, and the model expects `StrictInt` → fails.
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
given tool's tests *actually* fail. Consequence: our **4,498 over-counts** — it is
"tools that ship tests and are below 24.2," an upper bound. The true number is some
(likely large) subset whose tests violate one of the four rules.

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

## Status / recommendation

The largest behaviour-block by our heuristic, but the headline count is inflated by
the detector approximation. Highest-value next step is **measurement, not a fix**:
quantify how many tools' tests *truly* fail (e.g. by running Galaxy's validator over
the corpus, or porting a narrow check), which would right-size this blocker. Treat as
**detect/report-only** for now; a mechanical fix is low-confidence and only partial.
