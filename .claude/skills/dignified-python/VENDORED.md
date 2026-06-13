# Vendored: dignified-python

This skill is copied verbatim from a third-party repository — it is not original
to this repository.

| Field | Value |
|---|---|
| Vendored from | `dagster-io/erk`, directory `.agents/skills/dignified-python` |
| Vendored-from URL | https://github.com/dagster-io/erk/tree/master/.agents/skills/dignified-python (now 404; see "Upstream relocated" below) |
| Vendored commit | 2656c0e1a830f42cf7b9b6ed36f59a0ced7e3b97 |
| Retrieved | 2026-05-22 |
| Current canonical home | `dagster-io/skills`, directory `skills/dignified-python/skills/dignified-python` |
| Current canonical URL | https://github.com/dagster-io/skills/tree/master/skills/dignified-python/skills/dignified-python |
| Author | Dagster Labs (dagster-io) |
| License | See the `dagster-io/skills` repository for its license terms. |

## Upstream relocated (checked 2026-06-13)

The original `dagster-io/erk` location now returns 404. dignified-python's
canonical home is the dedicated **`dagster-io/skills`** repository
(`skills/dignified-python/skills/dignified-python/`), described in Dagster's blog
post "Dignified Python: 10 Rules to Improve Your LLM Agents"
(https://dagster.io/blog/dignified-python-10-rules-to-improve-your-llm-agents).

The vendored copy here is **still the 2026-05-22 `dagster-io/erk` snapshot**
(commit `2656c0e`); it has **not** been updated to the current `dagster-io/skills`
version. That newer version **softens the core stance**: the "Cornerstone: LBYL
Over EAFP / NEVER use exceptions for control flow" rule becomes "Default Stance:
Prefer Explicit Preconditions" (LBYL for routine branching, but EAFP when the
operation itself is the authoritative test or when translating failures at a
boundary), the `.exists()`-before-`.resolve()` rule is relaxed (adds
`resolve(strict=True)` as an accepted alternative), and `references/` is
reorganized under `references/advanced/`. Adopting it is a deliberate
governing-standard decision (this repo's `CLAUDE.md`, every package's
`docs/decisions.md`, and the `/pre-pr-audit` skill all cite the stricter rule),
so it is intentionally deferred, not silently re-vendored.

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
Python in this repository. The xsdata-generated `src/galaxy_tool_source/models/`
directory is exempt (it is generated code, not hand-written). On any conflict
with the `optimized-python` reference skill, **dignified-python governs**.
