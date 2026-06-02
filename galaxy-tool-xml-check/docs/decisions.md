# Decisions — galaxy-tool-xml-check

Each entry records a decision once it lands: a date, the decision, and the
rationale. Mirrors the conventions of the sibling packages' `docs/decisions.md`.

## D1 (2026-05-30) — A new advisory-check tier for detect-only IUC rules (PR4)

### Decision

A new tier-3.5 package, `galaxy-tool-xml-check`, hosts the **detect-only**
(advisory) IUC best-practice checks: a `CheckRule` ABC (`rules.py`), the concrete
checks (`checks.py`, `IUC001`–`IUC012`), and the registry + runner (`detect.py` —
`all_checks()` / `detect_violations()`). Each check is an LBYL query over a
tier-1 `ToolDocument` that yields the shared tier-0.5 `Violation`; each carries a
`RuleMeta` with the new `detect_only=True` flag (added to tier 0.5 in this PR).
PR4 of the detect/fix rule-split effort (PR1–5, merged in #15).

### Rationale

- **A separate package, not the app or a mutating tier.** These checks are
  conceptual peers of the GTX rules (they carry codes in the same registry) but
  are read-only and depend only on tier 1 + tier 0.5 — never on codemod/fmt or
  the app. A dedicated package keeps them independently consumable and keeps the
  app a pure composer (it runs codemod + fmt + check detect), consistent with
  `format`/`upgrade`. This realises the architecture sketched in
  `../../docs/iuc_best_practices.md` ("a small check library").
- **Advisory, not fixable.** Unlike a GTX finding ("`format`/a codemod would
  change this"), an IUC finding is a judgment call ("consider adding tests").
  `RuleMeta.detect_only` marks them so the `check` CLI treats them as
  informational (shown, but exit stays 0 unless `--strict`) rather than a
  failing gate — a canonical tool that merely lacks EDAM xrefs should not fail
  CI.

### Scope

Implemented (10): `IUC001` tests present · `IUC002` `<command>` CDATA · `IUC003`
id charset · `IUC004` version PEP 440 / `@…@` macro · `IUC005` requirements
present · `IUC006` error handling (`detect_errors` / `<stdio>`) · `IUC007`
EDAM/xrefs present · `IUC008` non-empty `<help>` · `IUC009` non-empty
`<description>` · `IUC010` `<help>` CDATA.

Reserved placeholders (`detect()` is a no-op stub, pending tuning to avoid
noise): `IUC011` single-quote Cheetah variables, `IUC012` `&&`-vs-lone-`&`
command joining — both require parsing shell/Cheetah text inside `<command>`
CDATA and are deferred. A standalone "profile recency" check is intentionally
omitted: it overlaps `GTX007` / the `upgrade` command.

**The deferral is now backed by data** (2026-05-30, combined corpus;
Reproduced-by: `uv run python -m scripts.measure command-iuc-heuristics`). Of
9,318 tools with a `<command>`, the crude `IUC011` heuristic (any `$var` not
immediately preceded by a single quote) would fire on **8,126 tools (87.2%),
115,007 findings** — confirming the noise concern: most matches are Cheetah
directives (`#if $x`), not unquoted shell arguments, so a literal-text `IUC011`
is not worth shipping without real Cheetah-aware parsing. `IUC012` (a lone `&`)
is far rarer — **431 tools (4.6%), 640 findings** — so it is the tractable one
to implement first should we revisit these. The measurement is the sizing tool
for that decision.

### Caveats

- CDATA detection (`IUC002`/`IUC010`) works by re-serialising the element, since
  lxml exposes CDATA as plain `.text` (the tree is parsed `strip_cdata=False`,
  so a CDATA section round-trips as `<![CDATA[…]]>`).
- The checks read the **un-expanded** tree, so a practice satisfied via a macro
  (e.g. `<expand macro="requirements"/>`) can still be flagged — the same
  macro-awareness limitation the rest of the framework carries today. Advisory
  status makes the resulting noise tolerable.

### Reproduction

```sh
uv run --package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/
# per-check corpus hit rates: see docs/corpus_check_stats.md (full sweep, the
# authoritative source). PR4 first validated with a 2,000-tool sanity sample;
# none of the 10 active checks fire at 0% or 100% (the IUC011/IUC012
# placeholders correctly flag nothing). Regenerate with:
uv run python -m scripts.corpus_check check
```

## D2 (2026-05-30) — `corpus_check check` sweep + per-rule violation counts (PR5)

### Decision

A fifth `scripts/corpus_check.py` subcommand, `check`, sweeps the corpus through
the exact unified detect the `galaxy-tool-refactor check` command runs (canonical
codemods + cosmetic fmt + advisory IUC) and tallies, per rule code, how many
tools carry the finding and the total findings — covering the detect-only IUC
rules. It writes `docs/corpus_check_stats.md` (a *fixable* GTX table and an
*advisory* IUC table). PR5 (final) of the detect/fix rule-split effort.

### Rationale

- **Genuine violation counts, not the isolation page's edit count.** The existing
  `rules` sweep (`corpus_rule_stats.md`) runs each rule *alone* and counts every
  emitted `Edit` — including no-ops — to QA that each rule is idempotent and
  crash-free in isolation. That over-counts (an fmt rule emits a `SetText` per
  element regardless of need; see fmt D14). The `check` sweep instead counts the
  per-occurrence `Violation`s the detect phases actually report, which is what a
  user sees. The two pages are complementary: isolation = per-rule QA, check =
  how often each rule fires.
- **Covers detect-only rules naturally.** Because it runs the same composed
  detect as the CLI, the IUC checks are tallied alongside GTX with no separate
  machinery, and the fixable/advisory split is read straight off
  `RuleMeta.detect_only`.
- **No app dependency in the script.** `_check_detect` re-composes the three
  detect phases locally (codemod + fmt + check) rather than importing the cli
  package, keeping the maintainer script above no tier it shouldn't be.

### Result (combined corpus)

9,289 parseable tools; all 9,289 carry a finding (9,287 fixable, 9,037 advisory),
0 crashes. Headlines: GTX003 blank-line 99.4% · GTX001 indent 71.7% · GTX002
param-order 71.3% · GTX013 child-order 53.9%; IUC007 EDAM/xrefs 89.6% · IUC005
requirements 57.3% · IUC002 command-CDATA 35.2% · IUC010 help-CDATA 39.6%;
placeholders IUC011/IUC012 0%. See `docs/corpus_check_stats.md` for the full
table (the authoritative source).

### Reproduction

```sh
uv run python -m scripts.corpus_check check            # full sweep + stat page
uv run python -m scripts.corpus_check check --limit 200 --no-stats
uv run --package galaxy-tool-xml-fmt pytest \
  galaxy-tool-xml-fmt/tests/test_corpus_check.py       # helper unit tests
```

## D3 (2026-06-02) — IUC012 (`&&`-vs-lone-`&`) stays deferred: the anti-pattern is ~absent

### Decision

`IUC012` (`CommandAndJoining` — "join shell commands with `&&`, not a lone `&`")
**remains a reserved no-op placeholder**, now on a data-backed basis rather than a
hunch. A literal-text IUC012 is not worth implementing: the genuine anti-pattern
it targets is essentially absent from the corpus, and the crude lone-`&` signal is
dominated by constructs that are *not* command joining.

### Evidence

Reproduced-by: `uv run python -m scripts.measure command-lone-amp` (combined
corpus, 2026-06-02; classifier pinned by
`galaxy-tool-xml/tests/test_measure.py::test_classify_lone_amps_buckets`). Of the
**431** tools the crude `_LONE_AMP` heuristic flags (what `command-iuc-heuristics`
counts), classifying every lone-`&` occurrence gives:

| Class | Occurrences | Command joining? |
|---|---|---|
| `redirect` (`2>&1`, `&>file`, `<&3`) | 562 | no — a redirection |
| `quoted` (a literal `&` inside `'…'`/`"…"`, e.g. sed/awk's "matched text") | 74 | no — an argument |
| `pipe` (`\|&`) | 2 | no — a pipe operator |
| `background` (lone `&` at end of a command) | 1 | no — intentional |
| `joining` (`cmd1 & cmd2` — the IUC012 anti-pattern) | **1** | **yes** |

So **2 tools** carry a *genuine* lone `&` (1 background + 1 joining), and the true
"meant `&&`, wrote `&`" mistake appears in **1 tool** across the whole corpus.

### Rationale

- **No payoff.** A crude check flags 431 tools, ~99.5% false positives; a *precise*
  check flags ~1. Neither is worth a rule.
- **Precision needs the deferred lexer.** Excluding the `quoted` class reliably
  (the 74 sed/awk literals) requires shell-string tokenisation — the M5 Cheetah/
  shell lexer (`../../galaxy-tool-xml-codemod/PLAN.md`), not a regex. The
  `command-lone-amp` quote scan is a heuristic good enough to *size* the question,
  not to ship as detection.
- **The reserved code stays.** `IUC012` keeps its slot and no-op `detect` (the
  registry/`corpus_check` already report it at 0%); revisit only if the M5 lexer
  lands or the corpus shifts. `IUC011` (single-quoted Cheetah, 87% crude noise per
  `command-iuc-heuristics`) was already deferred on the same "needs a real parser"
  grounds (D1).
