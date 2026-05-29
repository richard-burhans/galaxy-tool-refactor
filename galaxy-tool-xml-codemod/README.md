# galaxy-tool-xml-codemod

A LibCST-shaped framework for structural refactors of Galaxy tool XML.
The **structure** tier of a three-layer architecture:

| Tier | Layer | Package | Role |
|---|---|---|---|
| 1 | **parsing & validation** | `galaxy-tool-xml` | parse · profile-aware validate · typed view |
| 2 | **structure** | **`galaxy-tool-xml-codemod`** *(this repo)* | structural refactors |
| 3 | **formatting** | `galaxy-tool-xml-fmt` | cosmetic `black`-like formatter |

## Status

M1–M3.5 shipped: framework primitives (`Module`, `Cursor`,
`CodemodCommand`), the `corpus_check.py codemod` sweep (retains failures
as regression fixtures), and the `CANONICAL_CODEMODS` public contract
consumed by fmt's CLI. That contract now runs four codemods, in order:

`FixTypos → UpgradeToLatest → ReorderParamAttributes → ReorderToolAttributes`

- `FixTypos` — repair near-miss spelling typos so a
  well-formed-but-globally-invalid tool validates;
- `UpgradeToLatest` — loop `UpdateProfile` (declare the newest profile the
  tool validates at, bump-up-only) + single-step `upgrade_vN` codemods from
  `upgrades.py` to bring a tool to the latest profile (`UpdateProfile` is a
  building block run *inside* this loop, not a separate canonical entry);
- `ReorderParamAttributes` / `ReorderToolAttributes` — IUC `<param>` and
  documented `<tool>` attribute order.

The upgrade registry is grown empirically: the `corpus_check codemod`
sweep reports `STICKING POINT` versions still needing an `upgrade_vN`, and
each `upgrade_vN`'s advance count. Upgrades shipped: `Upgrade24_1`
(24.1 → 24.2), `Upgrade25_1` (25.1 → 26.0). See `docs/decisions.md` §11–14.

M4 (matcher language) and M5 (Cheetah reference resolver) are not yet
implemented — see `PLAN.md`.

## Public API

```python
from pathlib import Path

from galaxy_tool_xml_codemod.parse import parse_module
from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS

module = parse_module(Path("tool.xml"))
for codemod_cls in CANONICAL_CODEMODS:
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
| `upgrades.UpgradeToLatest` | Canonical. Loop UpdateProfile + single-step upgrades to reach the latest profile. |
| `codemods.update_profile.UpdateProfile` | Declare the newest profile the tool validates at, bump-up-only. Building block run *inside* `UpgradeToLatest` — not itself a `CANONICAL_CODEMODS` member. |
| `upgrades.UPGRADE_CODEMODS` | Registry: sticking version → its single-step upgrade codemod. |
| `codemods.upgrade_24_1.Upgrade24_1` | Single-step 24.1 → 24.2 (normalize `format` / `ftype`). |
| `codemods.upgrade_25_1.Upgrade25_1` | Single-step 25.1 → 26.0 (drop obsolete `<trackster_conf>`). |
| `codemods.reorder_param_attributes.ReorderParamAttributes` | IUC `<param>` attribute order. |
| `codemods.reorder_tool_attributes.ReorderToolAttributes` | Documented `<tool>` attribute prefix. |
| `canonical.CANONICAL_CODEMODS` | The full ordered set fmt's CLI runs by default. |
| `eligibility.corpus_test_profile` | Codemod-sweep validation-profile policy (sweep default). |

## Setup

From the workspace root:

```sh
uv sync
uv run --package galaxy-tool-xml-codemod pytest galaxy-tool-xml-codemod/tests/
```

## Relationship to fmt

`galaxy-tool-xml-fmt`'s library does not depend on this package. Its
**CLI** does: `pip install galaxy-tool-xml-fmt[canonical]` pulls in
this codemod package, and the CLI then runs `CANONICAL_CODEMODS`
before fmt's cosmetic rules. Without the `[canonical]` extra, fmt
applies cosmetic rules only.

## Coding standards

Hand-written code follows **dignified-python** (vendored at
`.claude/skills/dignified-python/`). See `CLAUDE.md`.
