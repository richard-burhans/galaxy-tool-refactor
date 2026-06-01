---
name: corpus-measurement
description: >
  The evidence-first workflow for galaxy-tool-refactor design decisions that turn on
  how often a pattern occurs in the Galaxy tool corpus. Before asking the user (or
  picking an approach), build the measurement as a STANDING command in
  scripts/measure.py (pure _measure_ helper + _report_ + registry slug), pin it with a
  synthetic-fixture unit test, run it, and present the headline numbers WITH the
  clarifying question. Never leave a cited number as a one-off script. Use when a
  scoping/design fork depends on corpus frequency, or when a decision doc cites a
  number that isn't yet reproducible by a committed command.
---

# Corpus measurement

Two standing rules for this repo, one workflow:

- **Measure before asking.** When a design or scoping decision hinges on how often a
  pattern actually occurs in the corpus, generate the numbers *first* and present them
  **inside** the clarifying question — don't ask on speculation and measure afterward.
  A measurement is worth building even if it might flip the answer you were leaning
  toward (it de-risks irreversible design choices).
- **Standing commands, not one-offs.** Any number cited in a `docs/decisions.md` must
  come from a committed, re-runnable command so it regenerates on every corpus refresh
  and can be audited — never a throwaway script whose result rots.

(QA investment is valued here — build the measurement properly rather than eyeballing.)

## Procedure

1. **Prefer extending an existing measurement.** Scan `scripts/measure.py --list`
   (`uv run python -m scripts.measure --list`). If a slug already covers the topic,
   add to it rather than minting a new one (e.g. the cross-source match-key sanity
   numbers live inside `cross-source-presence`, not a separate slug).

2. **Add the measurement** in `scripts/measure.py`, following the established triple:
   - `_measure_<slug>(...) -> <ResultDataclass>` — **pure**, no printing; takes
     `corpus_root: Path` (walks `.local/corpus/`) or `rows: list[dict]` (the committed
     `docs/corpus_data/combined_corpus_data.json`). All counting logic lives here.
   - `_report_<slug>(result) -> None` — formats/prints, shaped so the headline numbers
     lift straight into a decision-doc entry or a question.
   - `_run_<slug>(args) -> None` — the thin arg wrapper.
   - Register the slug in the `_MEASUREMENTS` dict at the bottom.

3. **Pin it with a test** in `galaxy-tool-xml/tests/test_measure.py`: import
   `_measure_<slug>`, build a small **synthetic fixture** (hand-written tool/macro XML
   or a few `rows`), and assert the exact counts. This locks the counting rule so a
   later refactor can't silently shift a published number.

4. **Run it** — `uv run python -m scripts.measure <slug>`. (Needs the corpus on disk
   for `corpus_root` measurements: `uv run python -m scripts.fetch_toolshed` /
   `fetch_schemas` if not present; row-based measurements read the committed JSON.)

5. **Cite it** — in the relevant `docs/decisions.md` entry add a **`Reproduced by:`**
   line naming the exact command. The decision's numbers and the command must agree
   (the `/pre-pr-audit` stat-consistency check enforces this).

6. **Present numbers with the question.** When the decision needs the user, put the
   headline figures directly in the `AskUserQuestion` (or the design fork) — e.g.
   "0 of 46 shared profile-macro files have diverging importers → fork-on-shared
   buys nothing; edit-in-place?" — not "should we fork? (I'll measure after)."

## Notes

- `_measure_` pure / `_report_` impure keeps measurements testable and composable
  without output noise — match that split exactly.
- Don't fabricate or hand-edit a measured number; if it changed, re-run the sweep.
- Some measurements feed `docs/*_stats.md` artifacts (regenerated on a full
  `corpus_check` sweep); ad-hoc decision-backing measurements are print-only and the
  numbers are folded into the decision doc they back.
