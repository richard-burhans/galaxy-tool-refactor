# Vendored: dignified-python

This skill is copied verbatim from a third-party repository — it is not original
to this repository.

| Field | Value |
|---|---|
| Source | `dagster-io/erk`, directory `.agents/skills/dignified-python` |
| Source URL | https://github.com/dagster-io/erk/tree/master/.agents/skills/dignified-python |
| Commit | 2656c0e1a830f42cf7b9b6ed36f59a0ced7e3b97 |
| Retrieved | 2026-05-22 |
| Author | Dagster Labs (dagster-io) |
| License | See the `dagster-io/erk` repository for its license terms. |

## How it was vendored

Copied with a sparse, blobless clone:

```sh
git clone --depth 1 --filter=blob:none --sparse https://github.com/dagster-io/erk "$tmp"
git -C "$tmp" sparse-checkout set .agents/skills/dignified-python
cp -r "$tmp/.agents/skills/dignified-python" .claude/skills/
```

The directory is reproduced verbatim; no files were modified.

## Role in this repository

`dignified-python` is the **governing** coding standard for all hand-written
Python in this repository. The xsdata-generated `src/galaxy_tool_xml/models/`
directory is exempt (it is generated code, not hand-written). On any conflict
with the `optimized-python` reference skill, **dignified-python governs**.
