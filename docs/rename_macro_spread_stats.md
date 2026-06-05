# Cross-file rename: macro spread + sole-owned gate

Reproduced by `uv run python -m scripts.measure rename-macro-spread` (needs the corpus + the `galaxy-tool-xml[cheetah-cdm]` extra).

- Tools with renameable input definitions: **8888**
- Rename attempts (one per definition): **71935**
  - tool-only (no macro touched): **65691** (91.3%)
  - spills into a macro: **1101** (1.5%)
    - every touched macro **sole-owned** (v1 applies with `--repo-root`): **918** (1.3%)
    - some touched macro **shared** (v1 skips + reports): **183** (0.3%)
  - bailed: **5143**

**Silent-break-today: 1101** (1.5% of attempts) — renames the *old* single-file path reported as success while leaving a `$old` reference dangling in an imported macro. This is the correctness bug the bundle rename fixes.

Bundle bail reasons:

- `shadowed`: 212
- `mixed-content`: 359
- `lexer-bail`: 373
- `filter-bare-ref`: 4159
- `cross-ref-residual`: 40
