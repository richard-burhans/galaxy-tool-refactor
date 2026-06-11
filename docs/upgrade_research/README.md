# Profile-upgrade code research notes

One research note per Galaxy **profile-upgrade code** — the runtime-behaviour changes
a tool opts into when its `profile=` is bumped. These back the question *"can a
behaviour-preserving auto-upgrade fix this, or only report it?"* (see
[`../upgrade_behavior_block_stats.md`](../upgrade_behavior_block_stats.md), which
measures where a behaviour-preserving upgrade stalls).

The codes mirror Galaxy's own catalogue,
`lib/galaxy/tool_util/upgrade/upgrade_codes.json`, vendored in
`galaxy-tool-codemod/src/galaxy_tool_codemod/profile_semantics.py` as
`PROFILE_UPGRADE_CODES`. Detection mirrors Galaxy's advisor
(`lib/galaxy/tool_util/upgrade/__init__.py`). Galaxy-source citations in each note are
from the local clone `.local/galaxy-src/` @ `c6e0ee3` (2026-06-01).

Each note follows the same shape: what the construct was · what changed at the
profile · why a bump matters · the faithful fix · detection (Galaxy + our mirror) ·
mechanical-fix feasibility · status.

> **`must_fix`** = bumping past this profile *breaks* the tool unless changed.
> **`consider`** = a runtime-behaviour change to review (the tool still runs). Our
> toolchain auto-fixes three codes today via runtime-gated fixes the `upgrade` path
> applies (GTR014/GTR015/GTR016); see the per-code notes.

## `must_fix` codes

| Code | Profile | Auto-fix today | Mechanical feasibility | Note |
|---|---|---|---|---|
| `16_04_fix_interpreter` | 16.04 | **GTR016** `FixInterpreter` — bucket-A rewrite to `$__tool_directory__` (runtime-gated) | [note](16_04_fix_interpreter.md) |
| `16_04_fix_output_format` | 16.04 | **GTR015** (partial) | covered for sole-data-input; residual is ambiguous | [note](16_04_fix_output_format.md) |
| `21_09_fix_from_work_dir_whitespace` | 21.09 | **GTR014** (full) | fully solved (always-safe strip) | [note](21_09_fix_from_work_dir_whitespace.md) |
| `24_2_fix_test_case_validation` | 24.2 | none | low — needs Galaxy's param-model validator; mostly detect-only | [note](24_2_fix_test_case_validation.md) |

## `consider` codes

| Code | Profile | Mechanical feasibility | Note |
|---|---|---|---|
| `16_04_consider_implicit_extra_file_collection` | 16.04 | none (fires unconditionally) | [note](16_04_consider_implicit_extra_file_collection.md) |
| `16_04_exit_code` | 16.04 | possible *legacy-restore* (`<stdio>`), but pins worse behaviour | [note](16_04_exit_code.md) |
| `17_09_consider_provided_metadata_style` | 17.09 | none (niche) | [note](17_09_consider_provided_metadata_style.md) |
| `18_01_consider_structured_like` | 18.01 | partial/hard (qualify names) | [note](18_01_consider_structured_like.md) |
| `18_01_consider_home_directory` | 18.01 | possible *legacy-restore* (`use_shared_home="true"`), but pins worse behaviour | [note](18_01_consider_home_directory.md) |
| `18_09_consider_python_environment` | 18.09 | none (deps invisible in XML) | [note](18_09_consider_python_environment.md) |
| `20_05_consider_inputs_as_json_changes` | 20.05 | none (fix is in the script) | [note](20_05_consider_inputs_as_json_changes.md) |
| `20_09_consider_output_collection_order` | 20.09 | none (test-order semantics) | [note](20_09_consider_output_collection_order.md) |
| `20_09_consider_set_e` | 20.09 | possible *legacy-restore* (`strict="false"`), but pins worse behaviour | [note](20_09_consider_set_e.md) |
| `21_09_consider_python_environment` | 21.09 | none (deps invisible in XML) | [note](21_09_consider_python_environment.md) |
| `23_0_consider_optional_text` | 23.0 | none (Cheetah-template behaviour) | [note](23_0_consider_optional_text.md) |
| `24_0_consider_python_environment` | 24.0 | none (deps invisible in XML) | [note](24_0_consider_python_environment.md) |
| `24_0_request_cleaning` | 24.0 | none (request contract invisible in XML) | [note](24_0_request_cleaning.md) |

## Cross-cutting investigations

Not per-code — capability research that several codes depend on:

- [`cheetah_variable_rewriting.md`](cheetah_variable_rewriting.md) — feasibility of
  locating/rewriting variables in the Cheetah-templated sections (`<command>`,
  inline `<configfile>`, …). An honest, evolving assessment (most fixes that touch a
  command body need this). Backed by the standing `cheetah-command-complexity`
  measure → [`../cheetah_command_stats.md`](../cheetah_command_stats.md).

## Reading the corpus counts

The "stuck" counts in [`../upgrade_behavior_block_stats.md`](../upgrade_behavior_block_stats.md)
are **first-blocker** counts: a tool is attributed to the lowest-profile applicable
code that halts it, so a `consider` code sharing a profile with a catalogue-earlier
code (e.g. `16_04_exit_code` behind `16_04_consider_implicit_extra_file_collection`)
shows 0 there even when many tools trip it. For raw per-code applicability across the
corpus, run the `upgrade-codes-applicability` measure
(`uv run python -m scripts.measure upgrade-codes-applicability`). Per-code counts in
the notes are labelled accordingly; approximate `grep`-based figures are marked.

## Where this points

- **Auto-fixed already:** `21_09_fix_from_work_dir_whitespace` (GTR014, full),
  `16_04_fix_output_format` (GTR015, the unambiguous subset).
- **Shipped:** `16_04_fix_interpreter` → **GTR016** `FixInterpreter`, a conservative
  bucket-A `RuntimeGatedFix` — the largest behaviour-block, dropped 1,726 → 316 stuck.
- **Legacy-restore opt-ins** (mechanical but pin the older behaviour, so not
  best-practice): `16_04_exit_code`, `20_09_consider_set_e`,
  `18_01_consider_home_directory`. The distinguishing criterion: a code qualifies as
  a legacy-restore opt-in iff its detector fires on the **absence** of the restore
  attribute, so a single attribute/element injection faithfully pins the old default.
  (`17_09` does not qualify — its detector fires on attribute *presence*, see its
  note — so there is no inject-to-restore fix.)
- **Everything else:** detect/report-only — the fix needs author intent, the wrapped
  script, dependency knowledge, or Galaxy's full parameter model.
