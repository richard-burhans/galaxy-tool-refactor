---
name: add-codemod
description: >
  The TDD workflow for adding a structural codemod to galaxy-tool-codemod (tier 2):
  failing test first, verb-noun naming, the CodemodCommand detect-primitive pattern,
  GTR-code assignment, catalog/canonical/registry wiring, and the corpus sweep that
  retains real-world failures as regression fixtures. Use when implementing a new
  codemod, porting a structural rule into tier 2, or growing a profile-upgrade
  (`upgrade_vN`) codemod. Covers both the cursor-walk codemods and the
  validation-driven (FixTypos / UpgradeToLatest) override pattern.
---

# Add a codemod

How to add a structural codemod to `galaxy-tool-codemod`. Tier 2 is **TDD-first**
and **detect-primitive**: each codemod reports exactly what it will change.

## Conventions (non-negotiable)

- **TDD** — failing test first, then the minimum code to pass. One test module per
  source module under `galaxy-tool-codemod/tests/`.
- **Verb-noun names** describing the mutation, LibCST-style: `ReorderParamAttributes`
  (class) / `reorder_param_attributes.py` (module) — *not* `ParamAttributeOrder`. The
  name is the corpus-sweep invocation and shows up in changelogs/docs.
- **dignified-python** governs (LBYL, pathlib+encoding, kw-only after first, absolute
  imports, no re-exports/`__all__`, no import-time side effects).

## Procedure

1. **Write the failing test** — `tests/test_<verb_noun>.py`. Drive the public surface:
   `parse_module(bytes_or_path) → Module`, then `Codemod().detect(module)` (returns
   `list[Change]`, non-mutating) and `Codemod().apply(module)` (mutates in place).
   Assert on the `Change` diagnostics and on the mutated tree bytes.

2. **Create the codemod** — `src/galaxy_tool_codemod/codemods/<verb_noun>.py`:
   - Subclass `CodemodCommand`; set `meta: ClassVar[RuleMeta]` with the **next free GTR
     code** (013 is the current max → use `GTR014`), a `summary`, `since`, and
     `applies_to` (default `{"tool"}` — only opt into `"macro"` for a generic rule).
   - Define `detect_<TagPascalCase>` methods (dispatch is by tag:
     `<param>` → `detect_Param`, `<change_format>` → `detect_ChangeFormat`). Each
     yields `Change(code, sourceline, xpath, message, mutate=<thunk>)`, where `mutate`
     is a zero-arg closure over `Cursor` primitives. **Detect is the primitive;
     `apply` is derived** by the base class — don't override it for a normal codemod.
   - `Cursor` primitives: `set_attribute` / `delete_attribute` / `rename_attribute` /
     `rename_tag` / `reorder_attributes` / `reorder_children` / `remove` / `add_child`
     / `set_text` / `attribute_names` / `children()` (skips comments/PIs).
     `would_reorder_*` are the detect-side guards.

3. **Register it** so the tiers see it:
   - `catalog.py::coded_codemods()` — **always** add the class (this is what the
     cross-tier registry enumerates; the registry asserts GTR codes don't collide).
   - `canonical.py::CANONICAL_CODEMODS` — add it **only if** it's a safe, idempotent,
     `profile=`-preserving *format-time* codemod (then it becomes selectable and runs
     under `format` / the `iuc` preset). Mind the order — `FixTypos` runs first;
     attribute reorders before child reorders.
   - No registry edits needed: `galaxy-tool-refactor-registry` derives its handles
     from `coded_codemods()` / `CANONICAL_CODEMODS`.

4. **Corpus sweep + retain regressions** (QA investment is worth it — never trim this):
   ```bash
   uv run python -m scripts.corpus_check codemod \
     galaxy_tool_codemod.codemods.<verb_noun>:<ClassName>
   ```
   It checks idempotence (`apply` once == twice) + post-codemod validity across the
   corpus and **copies any failing tool into `tests/data/regressions/<id>/tool.xml`**
   (updating `PROVENANCE.md`). `tests/test_regressions.py` auto-discovers fixtures —
   no test edit needed when one lands. Investigate and fix every retained failure.

5. **Ship** — invoke `/pre-pr-audit` before opening the PR.

## Validation-driven variant

A codemod that branches on re-validation (it can't pre-compute a static change list)
— like `FixTypos`, `UpdateProfile`, `UpgradeToLatest` — **overrides `apply`** with
bespoke logic and supplies a *coarse* `detect` (see `codemods/_coarse_detect.py`).
Override `corpus_eligible` / `corpus_validation_profile` when the codemod targets a
different population than "validates somewhere" (FixTypos targets validates-nowhere).

## Growing a profile-upgrade codemod (`upgrade_vN`)

Profile upgrades are grown **empirically from the corpus**, not designed up front:

1. Run the discovery sweep on the orchestrator:
   `uv run python -m scripts.corpus_check codemod galaxy_tool_codemod.upgrades:UpgradeToLatest`
   (defaults to `--source combined`). Read the post-apply profile distribution and the
   **sticking-point** versions — the from-profiles where many tools stall because no
   `upgrade_vN` exists yet.
2. Pick the highest-leverage sticking point; write `codemods/upgrade_<from_version>.py`
   (next free GTR code, e.g. `GTR014`) implementing the one structural migration that
   makes a tool valid at the next profile. Register it in `coded_codemods()` and in
   the `UPGRADE_CODEMODS` registry in `upgrades.py` (from-version → codemod) that
   `UpgradeToLatest` loops over. These are **upgrade-only** — not in `CANONICAL_CODEMODS`,
   not user-selectable; they surface only via `list_rules(include_upgrade=True)`.
3. Re-run the sweep; confirm reach-to-latest climbed and the version is no longer
   sticky. Repeat until the residual is just genuine tool bugs. Record the numbers in
   `galaxy-tool-codemod/docs/decisions.md` (§11–14 are the precedent) with a
   `Reproduced by` line — see the `/corpus-measurement` skill.
