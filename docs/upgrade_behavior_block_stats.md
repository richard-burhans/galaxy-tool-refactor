# Upgrade behavior-block statistics

A hypothetical **behavior-preserving** auto-upgrade: walk each tool's
profile from its declared (no-profile defaulted to Galaxy's `16.01`)
baseline toward the latest, but **stop at the first Galaxy profile-behaviour
change that both applies to the tool and the toolchain cannot auto-fix**.
This is stricter than `galaxy-tool-refactor upgrade`, which bumps `profile=`
to the newest structurally-valid version and only *warns* about crossed
behaviour changes (codemod `docs/decisions.md` §22). A code *applies* when
its per-tool detector fires (`upgrade_codes_applicable`); auto-fixability is
judged exactly by applying the mapped codemod and re-detecting.

Only two behaviour codes are auto-fixable: `21_09_fix_from_work_dir_whitespace`
(GTX014, full) and `16_04_fix_output_format` (GTX015, only a sole-top-level
data-input tool). The structural `upgrade_vN` codemods fix *validity*, not
behaviour, so they never clear a blocker here.

Two policies are reported: blocking on `must_fix` codes only (the sharper,
more actionable view) and on `must_fix` + `consider` (every behaviour change).
The latter is dominated by `16_04_consider_implicit_extra_file_collection`,
which Galaxy emits **unconditionally** — so essentially every sub-16.04 tool
stalls at 16.04 immediately.

`24_2_fix_test_case_validation` counts are an **upper bound** (ships `<test>`;
not validated): its detector fires on tools that merely *ship* a `<test>` —
we don't vendor Galaxy's parameter-model validator — not on tools whose tests
actually fail, so the true blocker count is a smaller subset (see
`upgrade_research/24_2_fix_test_case_validation.md`).

Regenerate with (needs the corpus, so not run in CI):

```sh
uv run python -m scripts.measure upgrade-behavior-blocks
```

Unique `<tool>` files (sha256-deduped) with a placeable baseline: **7,872**. Excluded (macro-token / unparseable `profile=`): **1,486**. Latest vendored profile: `26.1`. `Reaches latest` includes tools already at/above every applicable code.

## Blocking on `must_fix` only

Reaches latest behavior-preservingly: **1,630**; stuck: **6,242**.

| Profile | Level | Behavior code (first blocker) | Tools stuck |
|---|---|---|--:|
| 16.04 | must_fix | `16_04_fix_interpreter` | 1,726 |
| 16.04 | must_fix | `16_04_fix_output_format` | 18 |
| 24.2 | must_fix | `24_2_fix_test_case_validation` | 4,498 |

## Blocking on `must_fix` + `consider`

Reaches latest behavior-preservingly: **239**; stuck: **7,633**.

| Profile | Level | Behavior code (first blocker) | Tools stuck |
|---|---|---|--:|
| 16.04 | must_fix | `16_04_fix_interpreter` | 1,726 |
| 16.04 | consider | `16_04_consider_implicit_extra_file_collection` | 3,971 |
| 18.01 | consider | `18_01_consider_structured_like` | 1 |
| 18.01 | consider | `18_01_consider_home_directory` | 296 |
| 20.09 | consider | `20_09_consider_output_collection_order` | 64 |
| 20.09 | consider | `20_09_consider_set_e` | 415 |
| 21.09 | consider | `21_09_consider_python_environment` | 4 |
| 23.0 | consider | `23_0_consider_optional_text` | 311 |
| 24.2 | must_fix | `24_2_fix_test_case_validation` | 845 |
