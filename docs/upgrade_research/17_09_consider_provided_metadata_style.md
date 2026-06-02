# `17_09_consider_provided_metadata_style` — research note

| | |
|---|---|
| **Code** | `17_09_consider_provided_metadata_style` |
| **Profile** | 17.09 |
| **Level** | `consider` (niche) |
| **Auto-fix today** | **none** |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/4437 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What changed

`galaxy.json` is a rarely-used file a tool can write to dynamically collect datasets
or dataset metadata. At 17.09 its **format changed**. The original behaviour is
restored by adding `provided_metadata_style="legacy"` to the tool's `<outputs>`.
Galaxy's message:

> "Starting with 17.09 tools, the format of 'galaxy.json' … changed - the original
> behavior can be restored by adding 'provided_metadata_style=\"legacy\"' to the
> tool's outputs tag."

## Detection (with an upstream bug)

Galaxy's advisor (`lib/galaxy/tool_util/upgrade/__init__.py:143-145`) queries:

```python
if outputs_el is not None and outputs_el.get("`provided_metadata_style`", None) is not None:
    advice_collection.add("17_09_consider_provided_metadata_style")
```

Note the **literal backticks** in the attribute name — that key never matches, so the
predicate is effectively dead upstream (documented in our `profile_semantics.py`
module docstring). Our detector uses the **bare** attribute name
(`_detects_provided_metadata_style`: `outputs.get("provided_metadata_style") is not None`),
i.e. it fires when an `<outputs provided_metadata_style="…">` is already present.

## Mechanical-fix feasibility

Niche and low-value. The legacy-restore recipe (add `provided_metadata_style="legacy"`)
is mechanically trivial to *write*, but only matters for the handful of tools that
actually emit `galaxy.json`, which the XML doesn't reveal. Blindly adding the legacy
style would be wrong for tools that don't use `galaxy.json` or that intend the new
format.

## Status / recommendation

Detect/report-only; niche. Not worth a codemod.
