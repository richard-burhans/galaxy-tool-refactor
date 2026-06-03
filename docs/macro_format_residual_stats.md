# Macro-file format/ftype residual statistics

Sizes the population the imported-macro `format`/`ftype` normalization
pass (Phase 2a; `galaxy_tool_refactor_registry.macro_datatype`) unsticks:
tools stuck below the latest profile that reach a newer one once the
literal `format`/`ftype` values in their *imported* macro files are
lowercased — the value `Upgrade24_1` cannot reach from the tool's own tree
(see `upgrade_research`/`macro-aware-normalization.md`). A tool counts only
when its newest valid profile **strictly increases** after its bundle is
normalized in a temp copy and the tool is re-validated.

Regenerate with (needs the corpus, so not run in CI):

```sh
uv run python -m scripts.measure macro-format-residual
```

Unique `<tool>` files (sha256-deduped): **9,358**; importing
a macro file: **4,476**.

## Tools unstuck by macro-file normalization

- **Residual tools:** 15
- via a **shared** defining file (≥2 importers): 6
- via a **sole-owned** defining file: 9

## Defining macro files (residual tools each unblocks)

| Macro file | Tools unblocked |
|---|--:|
| `gdal/gdal_macros.xml` | 4 |
| `drep/macros.xml` | 2 |
| `coast_report/macros.xml` | 1 |
| `phage_coast_search/macros.xml` | 1 |
| `gdal_gdal_merge/gdal_macros.xml` | 1 |
| `gdal_gdal_translate/gdal_macros.xml` | 1 |
| `gdal_gdalbuildvrt/gdal_macros.xml` | 1 |
| `gdal_gdalwarp/gdal_macros.xml` | 1 |
| `checkdeep/macros.xml` | 1 |
| `modeldeep/macros.xml` | 1 |
| `paramdeep/macros.xml` | 1 |
