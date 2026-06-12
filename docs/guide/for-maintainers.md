# For IUC maintainers & tool authors

> **In one sentence:** it does the mechanical parts of tool upkeep for you — canonical
> formatting, a safe profile bump, and a best-practice report — so a PR arrives (or gets
> reviewed) already clean.

## The chore it removes

Whether you're **submitting** a tool or **reviewing** one, a chunk of the work is
mechanical: is it indented the IUC way, are attributes in the conventional order, is
`<command>` wrapped in CDATA, is the `profile=` current, are there tests and pinned
requirements? That's exactly what this automates — and it's tuned against **9,374 real
tools**, so it matches how IUC tools are actually written.

## Three things you'll run

### 1. `format` — make it canonical (safe, never changes behaviour)

Preview with `--diff`; it writes nothing until you drop the flag:

```diff
$ galaxy-tool-refactor format --diff tools/coverm/macros.xml
 <macros>
-        <param argument="--sharded" type="boolean" ... help="..." />
+        <param argument="--sharded" type="boolean" ... help="..."/>
```

Indentation, attribute/element order, empty-element shorthand, CDATA wrapping —
idempotent and behaviour-preserving. `format --check` is a clean CI gate.

### 2. `upgrade` — repair, and bump the profile only when needed

```diff
$ galaxy-tool-refactor upgrade --modernize --diff tools/bandage/bandage_info.xml
-<tool id="bandage_info" … profile="18.01">
+<tool id="bandage_info" … profile="25.1">
```

By default it moves `profile=` **only when strictly needed for validity**: a
tool that validates at its declared profile keeps it byte-untouched, an
undeclared tool stays undeclared, and an invalid tool moves to the minimum
valid profile at or above its baseline (no bump "for no reason", and never to
a pre-release a public server cannot run). `--modernize` opts into the walk
shown above, which advances the profile **only as far as behaviour provably
stays the same**: it stops below the first Galaxy `must_fix` change that
applies to your tool and that it cannot fix with a repair proven safe on that
tool, and never past the deployment ceiling, the newest profile every major
public Galaxy server runs (`--target-profile` is the explicit way past it). A stop is a normal, successful outcome: the report names the blocking
code and links to the [per-boundary reference](../profile_boundaries.md),
which tells you what changed and what to do;
`--modernize --allow-behavior-change` takes the bump anyway. Read
[soundness](soundness.md); that boundary is what makes it trustworthy for review.

### 3. `check` — a best-practice report

```text
$ galaxy-tool-refactor check --ruleset strict tools/qualimap/qualimap_macros.xml
tools/qualimap/qualimap_macros.xml:3   GTR001  Canonical 4-space indentation; no tabs.
…
4 fixable finding(s) in 1 file(s).
```

Fixable (GTR) findings are what `format` would fix and **fail CI** (non-zero exit).
Advisory (IUC) findings — missing tests, no version pins, no error handling — are
**informational** signals for a reviewer, not hard failures (unless you pass `--strict`).

## In a pull request

- **Authors:** run `format` then `check --ruleset strict` before you open the PR — land it
  already tidy, and see the advisory gaps a reviewer would flag.
- **Reviewers:** run `check` on the diff to separate "mechanical nits a bot can fix" from
  "judgement calls that need a human." The mechanical layer stops eating review time.

> The community's existing tools still apply — this is **complementary** to planemo, not
> a replacement (see [vs planemo](vs-planemo.md)). planemo tests and deploys; this
> formats, upgrades, and reports.

## Honest limits

- On an already-IUC-compliant tool, `format`/`check` are often quiet — the value then is
  mostly in `upgrade` and in catching the occasional advisory gap.
- `upgrade`'s default guarantee is bounded: it stops rather than cross a breaking
  behaviour change it cannot prove fixed, and the result is structurally valid at the
  profile it declares ([soundness](soundness.md)). Under the default, a
  `behavior_preserving: false` can only come from advisory (`consider`) changes;
  treat it as "needs a human look," not "rejected."
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
