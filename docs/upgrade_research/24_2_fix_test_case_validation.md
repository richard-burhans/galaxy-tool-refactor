# `24_2_fix_test_case_validation` — research note

| | |
|---|---|
| **Code** | `24_2_fix_test_case_validation` |
| **Profile** | 24.2 |
| **Level** | `must_fix` |
| **Auto-fix today** | **none** |
| **Stuck tools** (must_fix-only) | **3,483**, still the largest blocker (see `../upgrade_behavior_block_stats.md`; down from 6,033 via the provably-clean detector (§47) and the GTR096 qualification auto-fix (§48)) |
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

## Detection: Galaxy vs ours

Galaxy's advisor **actually runs the validator** and reports any failure
(`lib/galaxy/tool_util/upgrade/__init__.py:256-266`, `ProfileMigration24_2.advise`
calls `validate_test_cases_for_tool_source(..., use_latest_profile=True)` and adds
the code per `result.validation_error`).

**History:** the first detector was a bare approximation, `_detects_has_test`,
which fired on any tool shipping a `tests/test` (a necessary condition; no
`<test>` means the code can't trip). That over-counted: it flagged **6,033**
tools as first-blockers when the truth measure showed only ~1,972 actually
fail. As of 2026-06-12 the detector is tightened to the provably-clean checker
(below), and the GTR096 qualification auto-fix (§48) clears another slice, so
the gate now stops **3,483**, recovering most of the gap soundly. The residual
still exceeds the 1,972 true blockers because the checker is conservative,
leaving the tools it cannot prove clean (the `headroom`) blocked. Two of
Galaxy's rules have escape hatches the checker honors: the
select rule applies only to *static*-option selects (dynamic-options selects
accept any string), and the `data_column` rule fails only on column-*name*
strings (integer-as-string values coerce at any profile).

## The faithful fix (per violation)

- Unknown/misspelled param → remove or correct the name.
- `select` label → replace with the option's `value`.
- `data_column` name → replace with the integer index.
- Nested param → prefix with the `parent|…|child` qualified path.

The qualified-name and unknown-name fixes are largely derivable from the tool XML
structure. The **select label→value** and **column name→index** fixes need the
parameter model (option value mapping, column semantics) and sometimes author intent.

## Mechanical-fix feasibility

- **Detection** is solved without the heavy dependency: the toolchain's own
  structural checker (`test_case_check`, the shipped tightening below) answers
  Galaxy's strict-validation decision as a direct query over the resident
  macro-expanded tree, one-directional and parity-gated against Galaxy's real
  validator. We can now say "provably clean," not just "has tests."
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
original ships-a-`<test>` detector counted as first blockers** in
`../upgrade_behavior_block_stats.md`; the tightened detector (§47) plus the
GTR096 qualification auto-fix (§48) bring the gate's 24.2 stop down to 3,483,
recovering most of that gap soundly while conservatively keeping the
not-yet-provable tools blocked. Per-case validation-error kinds across
the 1,972: `type-or-value-mismatch` 2,380 cases (strict pydantic coercion),
`unknown-parameter` 2,159 ("Invalid parameter name found", the
name-qualification / typo class and the PR 4 mechanical-fix candidate),
`extra-input-forbidden` 52, `other` 43. The 159 validator-error tools (Galaxy
rejects the test block before validation, e.g. an output with nothing to
check) are listed in `../corpus_data/test_case_validation_errors.json`.

## The shipped tightening (2026-06-12, PR 3)

Rather than ship Galaxy's validator (it re-parses the tool and generates a
pydantic class per tool, ~200ms; `docs/galaxy_reimplementations.md` touchpoint
3), the toolchain ships its **own** structural checker,
`galaxy_tool_codemod.test_case_check.all_test_cases_provably_clean`, which
answers the same decision as a direct query over the resident macro-expanded
tree in milliseconds with no new dependency. `_detects_test_case_validation`
now fires only when a tool ships a `<test>` **and** its tests are not provably
clean (codemod decisions §47). The checker is one-directional: it suppresses
the 24.2 blocker only for the provably-clean subset and leaves everything it
cannot model (repeats, collections, drill-downs, any `<validator>`,
un-expanded macros, novel types) blocked, so it is never wider than Galaxy.

`scripts.measure test-case-validation-truth` is the standing parity oracle: it
runs Galaxy's real validator beside the checker over every test-shipping
corpus tool, gated on **zero unsound suppressions** (ours-clean but Galaxy
returns an invalid verdict). A Galaxy validator *raise* is a separate
non-blocking bucket (Galaxy's advisor cannot decide either; the underlying
tools, malformed XML and unexpandable macros, are handled upstream in the
shipped pipeline). The 2026-06-12 sweep: of 2,590 tools the checker proves
clean, **2,587 agree with a clean Galaxy verdict, 0 are unsound, and 3 sit in
the Galaxy-raised bucket**; 1,930 tools Galaxy validates clean are not yet
provable by the checker (the `headroom`, the target for any future widening).
Closing the last 2 unsound cases drove a principled narrowing: a
leading-underscore parameter/conditional name breaks Galaxy's pydantic model
builder, so the checker bails such tools to unclean.

## Status / recommendation

The 24.2 detector is now tightened to the provably-clean checker, recovering
the bulk of the ~3x over-count soundly. Remaining: the `unknown-parameter`
subset (2,159 cases) is the candidate for a mechanical name-qualification fix
(PR 4), and the measure's `headroom` figure (tools Galaxy validates clean but
the checker cannot yet prove) is the target for any future widening, always
behind the same zero-unsound gate.
