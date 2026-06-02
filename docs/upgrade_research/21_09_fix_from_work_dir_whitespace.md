# `21_09_fix_from_work_dir_whitespace` — research note

| | |
|---|---|
| **Code** | `21_09_fix_from_work_dir_whitespace` |
| **Profile** | 21.09 |
| **Level** | `must_fix` |
| **Auto-fix today** | **GTX014** `FixFromWorkDirWhitespace` (full) |
| **Stuck tools** (must_fix-only) | **0** — always cleared (see `../upgrade_behavior_block_stats.md`) |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/12536 |

> Galaxy-source citations from `.local/galaxy-src/` @ `c6e0ee3`.

## What the feature is

An output can declare `<data from_work_dir="out.txt"/>`, telling Galaxy to copy a
named file from the job working directory into the output dataset after the tool
runs.

## What changed at 21.09 (verified)

Before 21.09, Galaxy **stripped** the `from_work_dir` value, so surrounding
whitespace had no effect. From 21.09 the value is **quoted**, so leading/trailing
whitespace becomes a literal part of the filename — a tool with
`from_work_dir=" out.txt "` would suddenly look for a file whose name has spaces.

`lib/galaxy/tool_util/parser/xml.py:596-603`:

```python
output.from_work_dir = data_elem.get("from_work_dir", None)
output.precreate_directory = data_elem.get("precreate_directory") or False
profile_version = Version(self.parse_profile())
if output.from_work_dir and profile_version < Version("21.09"):
    # We started quoting from_work_dir outputs in 21.09.
    # Prior to quoting, trailing spaces had no effect.
    # This ensures that old tools continue to work.
    output.from_work_dir = output.from_work_dir.strip()
```

So Galaxy strips for profile < 21.09 and **does not** strip for ≥ 21.09. Bumping a
tool with a whitespace `from_work_dir` past 21.09 changes the filename it reads.

## Detection

Our `_detects_from_work_dir_whitespace` scans `.//data[@from_work_dir]` for any value
where `value != value.strip()`. (Galaxy's own advisor for 21.09 has a transcription
bug — it calls `advice_collection.add("")` with an empty code — documented in
`profile_semantics.py`; we add the intended code.)

## The faithful fix

Strip surrounding whitespace from the `from_work_dir` attribute. For the upgrade
scenario this targets — a tool **crossing** from profile `<21.09` to `>=21.09` —
the strip is **behaviour-preserving**: pre-21.09 Galaxy already stripped the value
(`xml.py:603`), so the stripped path is the one the tool ran with. (For a tool
*already* at `>=21.09`, stripping is a correctness fix to an already-broken
whitespace path, not behaviour preservation — but the whitespace `from_work_dir`
occurrences are a handful of **pre-21.09** tools, GTX014's entire applicable
population, none already at ≥ 21.09; codemod `docs/decisions.md` §25,
`scripts/measure.py upgrade-codes-applicability`.) There is no ambiguity and no
author intent required.

## What GTX014 already does

`codemods/fix_from_work_dir_whitespace.py` (`FixFromWorkDirWhitespace`,
`RuntimeGatedFix`, `introduced_profile="21.09"`): `detect_Data` reads
`from_work_dir`, and if `value != value.strip()` yields a `Change` that sets it to
`value.strip()`. Every tripped case is cleared, so this code **never blocks** a
behaviour-preserving upgrade.

## Mechanical-fix feasibility / status

Fully solved by GTX014 — the canonical "always-safe runtime-gated fix." No further
work needed; included here for completeness of the must_fix set.
