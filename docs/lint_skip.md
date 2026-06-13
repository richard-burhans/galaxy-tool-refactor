# `.lint_skip` reconciliation

`galaxy-tool-refactor lint-skip` is a convenience for cleaning up the planemo
`.lint_skip` sidecars that Galaxy tool directories accumulate. It applies the
fixes the toolchain already has and then removes a suppression line **only when
it can prove the line is no longer needed**. Anything it cannot fix, cannot
prove, or does not cover is left untouched and unmentioned — the author
suppressed it deliberately, and `check` already reports the full picture.

## What a `.lint_skip` is

When planemo lints a tool, it reads a `.lint_skip` file in the tool's directory:
one planemo linter class name per line (blank and `#` comment lines ignored).
Each name tells planemo to skip that linter for the tool(s) in the directory.
Authors add them because planemo reports a linter failure without saying which
file or line is at fault, so the whole linter gets suppressed — and the
suppression then lingers long after the underlying issue could have been fixed.

## What `lint-skip` does

```sh
galaxy-tool-refactor lint-skip tools/vg/            # fix + prune, in place
galaxy-tool-refactor lint-skip --check tools/vg/    # preview, exit non-zero if it would change
galaxy-tool-refactor lint-skip --backup tools/      # keep <file>.bak before overwriting
```

For each directory under `PATHS` that carries a `.lint_skip`, it loads **every**
`<tool>` in that directory (the sidecar governs them all), applies the covering
fixes, and removes each suppression line it can prove is resolved. It writes the
repaired tool files (only the ones a fix actually changed) and the rewritten
`.lint_skip` (deleting the file when nothing but blank lines remains). Comments,
blank lines, and names it leaves alone are preserved verbatim.

On the real `tools/vg` directory, whose `.lint_skip` is `CitationsNoValid` +
`HelpInvalidRST` over three tools (`convert.xml`, `deconstruct.xml`,
`view.xml`):

- `HelpInvalidRST` → the invalid reStructuredText in `deconstruct.xml` is
  repaired (GTR089.1, behind the render-equivalence gate); `convert.xml` and
  `view.xml` had no RST problem and are left byte-identical. The linter is now
  clean across all three, so the line is **removed**.
- `CitationsNoValid` → all three tools lack citations and the toolchain cannot
  invent them, so the line is **kept**, silently.

## When is a line *provably* removable?

Two conditions, both required:

1. **Complete coverage.** Every GTR rule carrying that planemo name is a
   faithful reimplementation of the whole linter, so "our rules are clean"
   implies "planemo would pass". The faithful set is derived, not hand-curated
   (registry `docs/decisions.md` D24): a covering rule qualifies iff it is a
   detect-only **check**-tier rule (the planemo-parity ports, verified against
   planemo) or a **canonical codemod** (a targeted, behaviour-preserving fix
   whose detector is exactly the linter's complaint). A name covered only
   *incidentally* by a profile-upgrade codemod is **not** completely covered —
   for example `ValidDatatypes`, whose only covering rule (GTR010) normalises
   datatype casing but does not validate against the datatype registry. Its
   suppression is never removed.
2. **Clean after fixing, directory-wide.** After applying the covering fixes,
   none of the covering rules detects on **any** tool in the directory. A line
   is removed only when it is safe for every tool the `.lint_skip` governs.

This is conservative on purpose. The cost of an unsound removal is only a
re-surfaced planemo lint message — visible and recoverable, not a behaviour
change — but the feature's value is that its removals can be trusted unattended,
so it removes only what it can stand behind.

## What it does not do

- It does not report, locate, or comment on suppressions it leaves in place.
  Use `check` (or `check --ruleset strict`) for the full picture.
- It does not apply profile upgrades or any fix outside the faithful set; the
  only tool-XML changes are the canonical, behaviour-preserving fixes that earn
  a removal.
- It is never part of `format` or `upgrade`: it rewrites files other than the
  one named (the tool XML and its `.lint_skip`), so it is a deliberate, separate
  command (cli `docs/decisions.md` §D19).

## Sizing

`uv run python -m scripts.measure lint-skip-corpus` reports the corpus-wide
bucket distribution (auto-removable vs kept), using the same coverage gate as
the command, so the sizing and the command never disagree.
