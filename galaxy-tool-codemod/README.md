# galaxy-tool-codemod

A LibCST-shaped framework for structural refactors of Galaxy tool XML.
The **structure** tier of the Galaxy refactoring architecture:

| Tier | Layer | Package | Role |
|---|---|---|---|
| 0.5 | **rule metadata** | `galaxy-tool-refactor-rules` | shared `RuleMeta` descriptor |
| 1 | **parsing & validation** | `galaxy-tool-source` | parse · profile-aware validate · typed view |
| 2 | **structure** | **`galaxy-tool-codemod`** *(this repo)* | structural refactors |
| 3 | **formatting** | `galaxy-tool-fmt` | cosmetic `black`-like formatter |
| 3.5 | **advisory checks** | `galaxy-tool-lint` | detect-only checks |
| 3.6 | **rule registry / rulesets** | `galaxy-tool-refactor-registry` | unified rules + rulesets (facade) |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` | composes the tiers via the facade (`format` / `upgrade` / `check`) |

## Status

M1–M3.5 shipped: framework primitives (`Module`, `Cursor`,
`CodemodCommand`), the `corpus_check.py codemod` sweep (retains failures
as regression fixtures), and two ordered pipeline contracts run by the
tier-4 app (`galaxy-tool-refactor-cli`):

- **`canonical_codemods()`** = `FixTypos → NormalizeBooleanValues → RepairHelpRst →
  TrimAttributeWhitespace → ReplaceOutputElement → DropRedundantParamName →
  ReorderParamAttributes → ReorderToolAttributes → ReorderToolChildren →
  WrapCommandCdata → WrapHelpCdata → SingleQuoteCommandVars` — the safe
  canonical/format pipeline (the app's `format` command), **derived** from the codemods
  declaring the `"default"` ruleset and ordered by `meta.order` (no hardcoded tuple,
  §36). Never changes `profile=`.
- **`AUTO_UPGRADE_CODEMODS`** = `FixTypos → NormalizeBooleanValues →
  UpgradeToLatest` — the opt-in profile-upgrade pipeline (the app's `upgrade`
  command).

The codemods:

- `FixTypos` — repair near-miss spelling typos so a
  well-formed-but-globally-invalid tool validates (in both pipelines);
- `NormalizeBooleanValues` — rewrite Python-style boolean attribute values
  (`True`/`Yes`/…) to canonical `xs:boolean` so a globally-invalid tool
  validates; schema-type-aware and behaviour-preserving (in both pipelines);
- `UpgradeToLatest` — loop `UpdateProfile` (declare the newest profile the
  tool validates at, bump-up-only) + single-step `upgrade_vN` codemods from
  `upgrades.py` to bring a tool to the latest profile (`UpdateProfile` is a
  building block run *inside* this loop, not a separate pipeline entry);
- `ReorderParamAttributes` / `ReorderToolAttributes` — IUC `<param>` and
  documented `<tool>` attribute order;
- `ReorderToolChildren` — IUC `<tool>` child-element order (best-practice #52);
  validity-safe because the `<tool>` content model is order-free (`xs:all`).

Every bundled codemod carries a `RuleMeta` GTR code; `catalog.coded_codemods()` is the
authoritative enumeration (the prose list above is illustrative — `format` also runs the
planemo-parity fixers GTR035–037 and the partition `.1` fixers GTR018.1/019.1/020.1 and
GTR089.1 `RepairHelpRst`). See `docs/decisions.md` §15–37.

The upgrade registry is grown empirically: the `corpus_check codemod`
sweep reports `STICKING POINT` versions still needing an `upgrade_vN`, and
each `upgrade_vN`'s advance count. Upgrades shipped: `Upgrade24_1`
(24.1 → 24.2), `Upgrade25_1` (25.1 → 26.0). See `docs/decisions.md` §11–14.

M4 (matcher language) and M5 (Cheetah reference resolver) are not yet
implemented — see `PLAN.md`.

## Public API

```python
from pathlib import Path

from galaxy_tool_codemod.parse import parse_module
from galaxy_tool_codemod.canonical import canonical_codemods

module = parse_module(Path("tool.xml"))
for codemod_cls in canonical_codemods():
    codemod_cls().apply(module)
# module.document.tree now reflects the canonical structural form
```

| Symbol | Purpose |
|---|---|
| `parse.parse_module(source)` | Entry point — accepts `Path \| bytes \| ToolDocument`. |
| `module.Module` | Frozen wrapper carrying `document`, `model`, `cursor`. |
| `cursor.Cursor` | lxml-backed view with read + typed mutation primitives. |
| `codemod.CodemodCommand` | Base for user-authored codemods (tag-PascalCase dispatch). |
| `codemods.fix_typos.FixTypos` | Repair near-miss typos until a globally-invalid tool validates (canonical, runs first). |
| `codemods.normalize_boolean_values.NormalizeBooleanValues` | Normalize Python-style boolean values (`True`/`Yes`/…) to `xs:boolean` until a globally-invalid tool validates (canonical, GTR017). |
| `codemods.repair_help_rst.RepairHelpRst` | Repair deterministically-fixable invalid `<help>` reStructuredText behind a render-equivalence gate (canonical, GTR089.1; the fix half of the GTR089 partition). |
| `upgrades.UpgradeToLatest` | In `AUTO_UPGRADE_CODEMODS`. Loop UpdateProfile + single-step upgrades to reach the latest profile. |
| `codemods.update_profile.UpdateProfile` | Declare the newest profile the tool validates at, bump-up-only. Building block run *inside* `UpgradeToLatest` — not itself a pipeline member. |
| `upgrades.UPGRADE_CODEMODS` | Registry: sticking version → its single-step upgrade codemod. |
| `codemods.upgrade_24_1.Upgrade24_1` | Single-step 24.1 → 24.2 (normalize `format` / `ftype`). |
| `codemods.upgrade_25_1.Upgrade25_1` | Single-step 25.1 → 26.0 (drop obsolete `<trackster_conf>`). |
| `codemods.reorder_param_attributes.ReorderParamAttributes` | IUC `<param>` attribute order. |
| `codemods.reorder_tool_attributes.ReorderToolAttributes` | Documented `<tool>` attribute prefix. |
| `codemods.reorder_tool_children.ReorderToolChildren` | IUC `<tool>` child-element order (#52). |
| `canonical.canonical_codemods()` | Ordered canonical/format pipeline (the app's `format` command). |
| `canonical.AUTO_UPGRADE_CODEMODS` | Ordered opt-in upgrade pipeline (the app's `upgrade` command). |
| `catalog.coded_codemods` | Every GTR-coded codemod, sorted by code (for the rule registry). |
| `eligibility.corpus_test_profile` | Codemod-sweep validation-profile policy (sweep default). |

## Setup

From the workspace root:

```sh
uv sync
uv run --package galaxy-tool-codemod pytest galaxy-tool-codemod/tests/
```

## Relationship to fmt and the app

Neither `galaxy-tool-fmt`'s library nor its CLI depends on this
package — fmt is cosmetic-only. Orchestration lives one tier up: the
`galaxy-tool-refactor` app CLI (`galaxy-tool-refactor-cli`) hard-depends
on this package and on fmt, runs `canonical_codemods()` (its `format`
command) or `AUTO_UPGRADE_CODEMODS` (its `upgrade` command), and writes
the result through fmt's serializer.

## Coding standards

Hand-written code follows **dignified-python** (vendored at
`.claude/skills/dignified-python/`). See `CLAUDE.md`.
