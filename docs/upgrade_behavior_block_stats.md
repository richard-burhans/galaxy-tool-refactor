# Upgrade behavior-block statistics

Where the **shipped default** `galaxy-tool-refactor upgrade` stops: the walk
caps at the behaviour ceiling: the newest vendored profile reachable from
the tool's baseline (no-profile defaults to Galaxy's `16.01`; a `@PROFILE@`
token is resolved through its definitions) without crossing a Galaxy
`must_fix` behaviour change that applies to the tool and that no bundled fix
provably clears (`galaxy_tool_codemod.behavior_gate`; codemod
`docs/decisions.md`). A code *applies* when its per-tool detector fires on
the macro-expanded view; auto-fixability is proven by execution, by the mapped
fix is applied to a copy and the detector re-run. This page is computed with
the same `behavior_gate` functions the live command uses, so the published
numbers and the shipped behaviour cannot drift.

The auto-fixes are the runtime-gated codemods (GTR014 from_work_dir
whitespace, GTR015 output format=input for a sole-data-input tool, GTR016
interpreter inlining for a literal-script command). The structural
`upgrade_vN` codemods fix *validity*, not behaviour, so they never clear a
blocker here.

Two policies are reported: blocking on `must_fix` codes only, **the shipped
default** (applicable `consider` codes are warned about, never blocking),
and the counterfactual `must_fix` + `consider` (every behaviour change).
The latter is dominated by `16_04_consider_implicit_extra_file_collection`,
which Galaxy emits **unconditionally** — so essentially every sub-16.04 tool
would stall at 16.04 immediately, which is why it is not the default
(`--allow-behavior-change` lifts the gate entirely instead).

`24_2_fix_test_case_validation` is now tightened past the bare ships-a-`<test>`
necessary condition: its detector fires only when a tool ships a `<test>` AND
the tests are not provably clean under the toolchain's own structural 24.2
checker (`galaxy_tool_codemod.test_case_check`, codemod decisions §47), which
answers Galaxy's strict-validation decision as a direct query over the
macro-expanded tree (no per-tool pydantic model). The checker is
one-directional and parity-gated against Galaxy's real validator with zero
unsound suppressions (`scripts.measure test-case-validation-truth`;
`docs/galaxy_reimplementations.md`). The residual count below is the true
blocker subset plus the tools the checker cannot yet prove clean (see
`upgrade_research/24_2_fix_test_case_validation.md`).

Regenerate with (needs the corpus, so not run in CI):

```sh
uv run python -m scripts.measure upgrade-behavior-blocks
```

Unique `<tool>` files (sha256-deduped) with a placeable baseline: **9,371**. Excluded (unresolvable macro-token / unparseable `profile=`; the live gate fails closed on these): **2**. Latest vendored profile: `26.1`. `Reaches latest` includes tools already at/above every applicable code.

## Blocking on `must_fix` only (the shipped default)

Reaches latest behavior-preservingly: **5,553**; stuck: **3,818**.

| Profile | Level | Behavior code (first blocker) | Tools stuck |
|---|---|---|--:|
| 16.04 | must_fix | `16_04_fix_interpreter` | 302 |
| 16.04 | must_fix | `16_04_fix_output_format` | 33 |
| 24.2 | must_fix | `24_2_fix_test_case_validation` | 3,483 |

## Blocking on `must_fix` + `consider`

Reaches latest behavior-preservingly: **1,345**; stuck: **8,026**.

| Profile | Level | Behavior code (first blocker) | Tools stuck |
|---|---|---|--:|
| 16.04 | must_fix | `16_04_fix_interpreter` | 302 |
| 16.04 | consider | `16_04_consider_implicit_extra_file_collection` | 5,386 |
| 18.01 | consider | `18_01_consider_structured_like` | 1 |
| 18.01 | consider | `18_01_consider_home_directory` | 296 |
| 20.05 | consider | `20_05_consider_inputs_as_json_changes` | 9 |
| 20.09 | consider | `20_09_consider_output_collection_order` | 105 |
| 20.09 | consider | `20_09_consider_set_e` | 596 |
| 21.09 | consider | `21_09_consider_python_environment` | 4 |
| 23.0 | consider | `23_0_consider_optional_text` | 489 |
| 24.2 | must_fix | `24_2_fix_test_case_validation` | 838 |
