# Vendored: dignified-python

This skill is copied verbatim from a third-party repository; it is not original to
this repository.

| Field | Value |
|---|---|
| Source | `dagster-io/skills`, directory `skills/dignified-python/skills/dignified-python` |
| Source URL | https://github.com/dagster-io/skills/tree/master/skills/dignified-python/skills/dignified-python |
| Commit | fa3d023d6700767d3950f94ebe8ea73b5abbd015 |
| Retrieved | 2026-06-13 |
| Author | Dagster Labs (dagster-io) |
| License | See the `dagster-io/skills` repository for its license terms. |
| Blog | https://dagster.io/blog/dignified-python-10-rules-to-improve-your-llm-agents |

## Updated 2026-06-13: re-vendored from the relocated upstream, softer stance adopted

The skill's original home (`dagster-io/erk`, `.agents/skills/dignified-python`,
commit `2656c0e`, retrieved 2026-05-22) now returns 404; the canonical home moved
to the dedicated **`dagster-io/skills`** repository. This copy was **re-vendored
from that new upstream** (commit `fa3d023`, 2026-06-13), replacing the earlier erk
snapshot.

The current version **softens the earlier strict stance**, and we adopted it
deliberately:

- The "Cornerstone: LBYL Over EAFP / NEVER use exceptions for control flow" rule
  becomes "Default Stance: Prefer Explicit Preconditions": LBYL for routine
  branching, but EAFP is acceptable when the operation itself is the authoritative
  test or when translating failures at a boundary.
- The `.exists()`-before-`.resolve()` rule is relaxed (adds `resolve(strict=True)`
  as an accepted alternative).
- `references/` is reorganized under `references/advanced/` (plus `checklists.md`
  and `module-design.md`).

**Doc reconciliation note.** This repo's `CLAUDE.md`, several packages'
`docs/decisions.md`, and the `/pre-pr-audit` skill still describe the *stricter*
rule ("LBYL over try/except; exceptions only at the CLI and third-party
boundaries"). Those references now overstate the standard; reconciling their
wording to the softer stance is follow-up work (flagged for the architecture
audit that accompanied this update). No source code was changed by this
re-vendor; existing code that follows the stricter rule still conforms (the softer
rule is a superset of the stricter one).

## How it was vendored

Copied with a sparse, blobless clone:

```sh
git clone --depth 1 --filter=blob:none --sparse https://github.com/dagster-io/skills "$tmp"
git -C "$tmp" sparse-checkout set skills/dignified-python/skills/dignified-python
find .claude/skills/dignified-python -mindepth 1 -not -name VENDORED.md -delete
cp -r "$tmp/skills/dignified-python/skills/dignified-python/." .claude/skills/dignified-python/
```

The directory is reproduced verbatim (except this `VENDORED.md`, which is our own
provenance record and not part of the upstream skill).

## Role in this repository

`dignified-python` is the **governing** coding standard for all hand-written
Python in this repository. The xsdata-generated `src/galaxy_tool_source/models/`
directory is exempt (it is generated code, not hand-written). On any conflict with
the `optimized-python` reference skill, **dignified-python governs**.
