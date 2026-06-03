# Using it as a Python library

> **TL;DR.** The registry facade is the library-first entry point: `run` (format),
> `detect` (report), and `upgrade`, each taking a path / bytes / `ToolDocument` and a
> resolved set of rule codes, returning a structured result. No printing, no `sys.exit` —
> it's built to be embedded.

## The facade

```python
from pathlib import Path
from galaxy_tool_refactor_registry import facade, resolve

tool = Path("tools/bandage/bandage_info.xml")

# format: apply the fixable selection + cosmetic rules
fmt = facade.run(tool, codes=resolve.resolve_codes(preset="iuc"))
canonical_xml: bytes = fmt.formatted        # advisory findings in fmt.advisory

# detect: report-only over the selection (never mutates)
det = facade.detect(tool, codes=resolve.resolve_codes(preset="strict"))
for v in det.violations:                    # v.code, v.line, v.message
    print(v.code, det.is_advisory(v))

# upgrade: profile bump + the repairs proven safe, then format
up = facade.upgrade(tool, codes=resolve.resolve_upgrade_codes())
upgraded_xml: bytes = up.formatted
print(up.behavior_preserving)               # True / False / None — see soundness
```

> **Gotcha (honest).** Pass a **`Path`** (or a `ToolDocument` loaded from a path), not
> raw `bytes`, whenever the tool `<import>`s a macro file — raw bytes have no source
> directory, so the imports can't resolve and macro-expanded validation degrades. Bytes
> are fine for self-contained, in-memory tools.

## What comes back

| Result | Key fields |
|---|---|
| `FormatResult` (`run`) | `formatted: bytes`, `advisory: list[Violation]`, `notes` |
| `DetectResult` (`detect`) | `violations: list[Violation]`, `advisory_codes`, `is_advisory(v)` |
| `UpgradeResult` (`upgrade`) | `formatted: bytes`, `steps_applied`, `missing_upgrade`, `behavior_preserving`, `advisory` |

Rule selection is shared: `resolve.resolve_codes(preset=…, select=…, ignore=…)` for
`run`/`detect`; `resolve.resolve_upgrade_codes(select=…, ignore=…)` for `upgrade`
(no preset — upgrade is semantic). Precedence: `ignore` ▸ `select` ▸ `preset`.

## Introspection

```python
for info in facade.list_rules():            # include_upgrade=True adds GTR007/014–016
    print(info.code, info.family, info.fixable, info.presets)
for p in facade.list_presets():
    print(p.name, p.is_default, p.codes)
```

<details>
<summary>The lower tiers, if you need them directly</summary>

The facade composes them, but each is usable standalone:

- `galaxy_tool_xml` — `load_tool` / `parse_tool`, `validate_tool`,
  `newest_valid_profile`, typed model views. (No serializer.)
- `galaxy_tool_xml_fmt` — `format_tool_document(document) -> bytes` (the *only*
  serializer in the stack).
- `galaxy_tool_xml_codemod` — the `CodemodCommand` framework + bundled codemods.
- `galaxy_tool_xml_check` — detect-only IUC advisory checks.

The facade is library-first by design (registry `CLAUDE.md`): inputs are
path/bytes/`ToolDocument`, outputs are structured, files are written only when you
pass a `write_path`. That's exactly what lets the CLI and MCP server be thin adapters.
</details>
