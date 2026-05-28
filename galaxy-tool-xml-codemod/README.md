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
`CodemodCommand`), the two structural codemods (`ReorderParamAttributes`,
`ReorderToolAttributes`), the `CANONICAL_CODEMODS` public contract
consumed by fmt's CLI, and a `corpus_check.py codemod` subcommand that
sweeps a codemod across the corpus and retains failures as regression
fixtures.

Two validation-driven codemods also ship and now run in the canonical
pipeline: `FixTypos` (repairs near-miss spelling typos so a
well-formed-but-globally-invalid tool validates) and `UpdateProfile`
(declares the newest profile the tool validates at, bump-up-only). The
canonical order is `FixTypos → UpdateProfile → ReorderParamAttributes →
ReorderToolAttributes`. See `docs/decisions.md` §11–13.

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
| `codemods.update_profile.UpdateProfile` | Declare the newest profile the tool validates at, bump-up-only (canonical). |
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
