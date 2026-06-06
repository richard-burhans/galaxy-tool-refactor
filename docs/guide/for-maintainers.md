# For IUC maintainers & tool authors

> **In one sentence:** it does the mechanical parts of tool upkeep for you — canonical
> formatting, a safe profile bump, and a best-practice report — so a PR arrives (or gets
> reviewed) already clean.

## The chore it removes

Whether you're **submitting** a tool or **reviewing** one, a chunk of the work is
mechanical: is it indented the IUC way, are attributes in the conventional order, is
`<command>` wrapped in CDATA, is the `profile=` current, are there tests and pinned
requirements? That's exactly what this automates — and it's tuned against **9,358 real
tools**, so it matches how IUC tools are actually written.

## Three things you'll run

### 1. `format` — make it canonical (safe, never changes behaviour)

Preview with `--diff`; it writes nothing until you drop the flag:

```diff
$ galaxy-tool-refactor format --diff tools/coverm/macros.xml
+<?xml version='1.0' encoding='utf-8'?>
 <macros>
-        <param argument="--sharded" type="boolean" ... help="..." />
+        <param argument="--sharded" type="boolean" ... help="..."/>
```

Indentation, attribute/element order, empty-element shorthand, CDATA wrapping —
idempotent and behaviour-preserving. `format --check` is a clean CI gate.

### 2. `upgrade` — bump the profile, safely

```diff
$ galaxy-tool-refactor upgrade --diff tools/bandage/bandage_info.xml
-<tool id="bandage_info" … profile="18.01">
+<tool id="bandage_info" … profile="26.1">
```

It advances to the newest profile the tool **validates** at, applying only the repairs
it can prove safe. **It does not blindly preserve behaviour** — read
[soundness](soundness.md); that boundary is what makes it trustworthy for review.

### 3. `check` — a best-practice report

```text
$ galaxy-tool-refactor check --preset strict tools/qualimap/qualimap_macros.xml
tools/qualimap/qualimap_macros.xml:3   GTR001  Canonical 4-space indentation; no tabs.
…
4 fixable finding(s) in 1 file(s).
```

Fixable (GTR) findings are what `format` would fix and **fail CI** (non-zero exit).
Advisory (IUC) findings — missing tests, no version pins, no error handling — are
**informational** signals for a reviewer, not hard failures (unless you pass `--strict`).

## In a pull request

- **Authors:** run `format` then `check --preset strict` before you open the PR — land it
  already tidy, and see the advisory gaps a reviewer would flag.
- **Reviewers:** run `check` on the diff to separate "mechanical nits a bot can fix" from
  "judgement calls that need a human." The mechanical layer stops eating review time.

> The community's existing tools still apply — this is **complementary** to planemo, not
> a replacement (see [vs planemo](vs-planemo.md)). planemo tests and deploys; this
> formats, upgrades, and reports.

## Honest limits

- On an already-IUC-compliant tool, `format`/`check` are often quiet — the value then is
  mostly in `upgrade` and in catching the occasional advisory gap.
- `upgrade`'s guarantee is **structural validity**, not behaviour preservation in general
  ([soundness](soundness.md)). Treat a `behavior_preserving: false` upgrade as
  "needs a human look," not "rejected."
- The `format` fixes *are* behaviour-preserving — and that's not just asserted: every
  fixable rule is adversarially audited, with genuine breaks fixed (regression-pinned)
  and the verdicts recorded in the [behaviour-preservation ledger](../behavior_preservation.md)
  ([soundness](soundness.md#how-we-know-format-is-behaviour-preserving--the-audit)).
- The often-discussed *batch automation* (a bot that opens fix-PRs across a whole repo)
  is **not built** — the per-tool engine above is what it would stand on. See the
  [capabilities matrix](capabilities.md) for the Shipped/Partial/Roadmap split.

## Go deeper

[Use it from the CLI](usage/cli.md) · [capabilities](capabilities.md) ·
[soundness](soundness.md) · [where this fits the ecosystem](leverage.md)
