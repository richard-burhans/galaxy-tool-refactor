<!-- Thanks for contributing! Keep this short — delete sections that don't apply. -->

## What & why

<!-- The change and the problem it solves. Link any issue. -->

## Checklist

- [ ] `bash scripts/qa_gate.sh` is green (ruff + strict mypy + pytest, all packages).
- [ ] Docs the change implicates are updated — tier tables / package counts,
      `docs/guide/` capability matrix, and any `docs/*_stats.md` a rule change affects.
- [ ] A new decision is recorded in the owning package's `docs/decisions.md`
      (date + a `Reproduced by` command if it cites a measurement), if applicable.
- [ ] New rules/behaviour are test-first, and behaviour-preserving fixes hold
      **by construction** (see `docs/behavior_preservation.md`).

<!-- Maintainers: before merging, run the /pre-pr-audit skill for the full
     code + documentation audit. `main` requires the `ci` check to pass. -->
