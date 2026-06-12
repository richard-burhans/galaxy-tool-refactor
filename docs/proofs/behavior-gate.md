# The behavior gate: the `upgrade` default's soundness argument

**Contract:** the default `upgrade` crosses no Galaxy `must_fix` behaviour
boundary whose change applies to the tool, except boundaries whose change it
provably fixed on that tool. Holds by construction for novel tools; the corpus
sweep is evidence, never the argument.

Mechanism: `galaxy_tool_codemod/behavior_gate.py`; policy and default flip:
the registry facade's `upgrade`. Per-step structural soundness is the separate
[GTR012](GTR012.md) composition (validity-gated sequencing); this document is
the behavioural half that caps it.

## The claim, decomposed

The gate computes a **ceiling** before the walk starts and the walk cannot
exceed it. The claim reduces to five sub-claims:

1. **The boundary catalogue is Galaxy's own.** `PROFILE_UPGRADE_CODES` is
   vendored verbatim from Galaxy's upgrade advisor
   (`lib/galaxy/tool_util/upgrade/upgrade_codes.json` @ b45c58a2). What counts
   as a profile behaviour change, and its `must_fix`/`consider` severity, is
   Galaxy's authoritative enumeration, not ours. Scope limitation, stated
   plainly: a behaviour change Galaxy itself has not catalogued is invisible
   to the gate; we hold the same epistemic position as Galaxy's advisor.

2. **Applicability detection never under-reports.** Each code's per-tool
   detector ports the corresponding `ProfileMigration.advise` predicate
   (codemod decisions §25), runs on the **macro-expanded** view (matching
   Galaxy's advisors, which parse post-expansion), and falls back to the raw
   tree when expansion fails, the conservative direction (over-report, never
   silent). Detector tightenings are one-directional: they only suppress cases
   *provably* unaffected by the change (e.g. §28's single-simple-command
   `set -e` suppression, and the 24.2 test-case detector's own provably-clean
   checker, codemod §47), so a tightening can remove a false block but never
   admit a false pass. The 24.2 checker is itself parity-gated against Galaxy's
   real validator with zero unsound suppressions
   (`docs/galaxy_reimplementations.md` touchpoint 3).

3. **Auto-fix credit is proof by execution, per tool.** A crossed, applicable
   `must_fix` code stops being a blocker only when its mapped
   `RuntimeGatedFix`, each individually proven behaviour-preserving in its
   own document ([GTR014](GTR014.md) `21_09_fix_from_work_dir_whitespace`,
   [GTR015](GTR015.md) `16_04_fix_output_format`, [GTR016](GTR016.md)
   `16_04_fix_interpreter`), is applied to a throwaway copy of *this tool*
   and the code's detector no longer fires (`code_cleared_by_autofix`). There
   is no static "fixable codes" set: a fix's partial coverage (GTR015's
   sole-data-input subset, GTR016's bucket A) and macro-supplied constructs
   the raw-tree fix cannot reach are handled exactly, because the probe
   re-detects on the expanded view. The live run re-verifies: the facade
   credits a fix in `auto_fixed_codes` only when post-apply re-detection shows
   the code quiet.

4. **The ceiling arithmetic cannot cross a blocker.** A code at version `V`
   is crossed by a `from -> to` bump iff `from < V <= to`
   (`upgrade_codes_crossed`). The ceiling is the newest vendored profile
   strictly below the lowest surviving blocker's `V`
   (`behavior_ceiling`), so declaring the ceiling crosses no blocked
   boundary, by the range inequality. Fail-closed branches: no vendored
   profile below the lowest blocker means **no** profile advance at all
   (`blocked_below_baseline`); an unplaceable baseline (an unresolved
   `@PROFILE@` token) means the crossings cannot be ranged, so the walk does
   not run; and the gate never lowers a declared profile.

5. **The walk respects the ceiling by construction.** The ceiling threads
   through every declaration site: `newest_valid_profile(…, ceiling=…)` skips
   newer profiles, `UpdateProfile(ceiling=…)` caps `profile=` (and the
   inline-token rewrite), and `UpgradeToLatest(ceiling=…)` targets the ceiling
   instead of latest. The shared-macro `@PROFILE@` path computes each
   importer's target through the same gate, and the consensus rule
   (every importer agrees) makes the shared bump the minimum every importer's
   gate allows. Pinned by `test_behavior_gate.py`, the ceiling tests in
   `test_binding.py` / `test_update_profile.py` / `test_upgrades.py`, and the
   facade gate tests.

## What the default does NOT claim

Applicable `consider`-level changes do not stop the walk, a deliberate,
documented policy choice (blocking on them would freeze nearly every tool at
16.04 because Galaxy emits one such code unconditionally; see
`docs/upgrade_behavior_block_stats.md`). They are surfaced in the
crossed-boundary warning and an honest `behavior_preserving=False`, never
silently. `--allow-behavior-change` lifts the gate entirely and restores the
historical structural walk, with the same reporting.

## Evidence (not the argument)

`uv run python -m scripts.corpus_check upgrade` runs the gated default over
every corpus tool and asserts this contract per tool (fail-closed, gate cap,
no un-fixed `must_fix` crossing recomputed independently, validity
preservation, byte idempotence), retaining every violation as a regression
fixture. `scripts.measure upgrade-behavior-blocks` reports where the default
stops, computed with these same gate functions.

## Coverage guard

`test_proof_documents.py` asserts every `RuntimeGatedFix` (its GTR code and
its Galaxy `upgrade_code`) is named in this document, so a new auto-fix cannot
join the gate without extending this argument.
