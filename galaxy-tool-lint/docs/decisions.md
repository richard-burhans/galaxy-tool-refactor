# Decisions — galaxy-tool-lint

Each entry records a decision once it lands: a date, the decision, and the
rationale. Mirrors the conventions of the sibling packages' `docs/decisions.md`.

## D1 (2026-05-30) — A new advisory-check tier for detect-only rules (PR4)

### Decision

A new tier-3.5 package, `galaxy-tool-lint`, hosts the **detect-only**
(advisory) IUC best-practice checks: a `CheckRule` ABC (`rules.py`), the concrete
checks (`checks.py`, `GTR021`–`GTR032`), and the registry + runner (`detect.py` —
`all_checks()` / `detect_violations()`). Each check is an LBYL query over a
tier-1 `ToolDocument` that yields the shared tier-0.5 `Violation`; each carries a
`RuleMeta` with the new `detect_only=True` flag (added to tier 0.5 in this PR).
PR4 of the detect/fix rule-split effort (PR1–5, merged in #15).

### Rationale

- **A separate package, not the app or a mutating tier.** These checks are
  conceptual peers of the GTR rules (they carry codes in the same registry) but
  are read-only and depend only on tier 1 + tier 0.5 — never on codemod/fmt or
  the app. A dedicated package keeps them independently consumable and keeps the
  app a pure composer (it runs codemod + fmt + check detect), consistent with
  `format`/`upgrade`. This realises the architecture sketched in
  `../../docs/iuc_best_practices.md` ("a small check library").
- **Advisory, not fixable.** Unlike a GTR finding ("`format`/a codemod would
  change this"), an advisory finding is a judgment call ("consider adding tests").
  `RuleMeta.detect_only` marks them so the `check` CLI treats them as
  informational (shown, but exit stays 0 unless `--strict`) rather than a
  failing gate — a canonical tool that merely lacks EDAM xrefs should not fail
  CI.

### Scope

Implemented (10 at PR4; `GTR031` added in D5, `GTR033` in D7): `GTR021` tests present ·
`GTR022` `<command>` CDATA · `GTR023`
id charset · `GTR024` version PEP 440 / `@…@` macro · `GTR025` requirements
present · `GTR026` error handling (`detect_errors` / `<stdio>`) · `GTR027`
EDAM/xrefs present · `GTR028` non-empty `<help>` · `GTR029` non-empty
`<description>` · `GTR030` `<help>` CDATA.

Reserved placeholders at PR4 (`detect()` a no-op stub, pending tuning to avoid
noise): `GTR031` single-quote Cheetah variables and `GTR032` `&&`-vs-lone-`&`
command joining — both require parsing shell/Cheetah text inside `<command>`
CDATA. **Both were later settled with data (see D3/D4/D5):** `GTR032` stays a
no-op (the anti-pattern is ~1 tool corpus-wide, D3); `GTR031` shipped with a
read-only command lexer (D5) once a refined measure showed its signal is real
(D4). A standalone "profile recency" check is intentionally omitted: it overlaps
`GTR007` / the `upgrade` command.

**The PR4 crude sizing** (2026-05-30, combined corpus; Reproduced-by: `uv run
python -m scripts.measure command-iuc-heuristics`): of 9,318 tools with a
`<command>`, the crude `GTR031` heuristic (any `$var` not immediately preceded by
a single quote) fired on **8,126 tools (87.2%)** — but most matches are Cheetah
directives (`#if $x`), not shell arguments. D4 refines this (directive-excluded,
quote-aware) to the genuine 73.2%, and D5 ships the check on that basis; `GTR032`
remained a lone-`&` at 431 tools but D3 shows ~all are redirects/pipes/literals.

### Caveats

- CDATA detection (`GTR022`/`GTR030`) works by re-serialising the element, since
  lxml exposes CDATA as plain `.text` (the tree is parsed `strip_cdata=False`,
  so a CDATA section round-trips as `<![CDATA[…]]>`).
- The checks read the **un-expanded** tree, so a practice satisfied via a macro
  (e.g. `<expand macro="requirements"/>`) can still be flagged — the same
  macro-awareness limitation the rest of the framework carries today. Advisory
  status makes the resulting noise tolerable.

### Reproduction

```sh
uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/
# per-check corpus hit rates: see docs/corpus_check_stats.md (full sweep, the
# authoritative source). PR4 first validated with a 2,000-tool sanity sample;
# none of the 10 active checks fire at 0% or 100% (at PR4 the GTR031/GTR032
# placeholders flagged nothing; GTR031 now ships — D5 — GTR032 still does not).
# Regenerate with:
uv run python -m scripts.corpus_check check
```

## D2 (2026-05-30) — `corpus_check check` sweep + per-rule violation counts (PR5)

### Decision

A fifth `scripts/corpus_check.py` subcommand, `check`, sweeps the corpus through
the exact unified detect the `galaxy-tool-refactor check` command runs (canonical
codemods + cosmetic fmt + advisory) and tallies, per rule code, how many
tools carry the finding and the total findings — covering the detect-only IUC
rules. It writes `docs/corpus_check_stats.md` (a *fixable* GTR table and an
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
  detect as the CLI, the checks are tallied alongside GTR with no separate
  machinery, and the fixable/advisory split is read straight off
  `RuleMeta.detect_only`.
- **No app dependency in the script.** `_check_detect` re-composes the three
  detect phases locally (codemod + fmt + check) rather than importing the cli
  package, keeping the maintainer script above no tier it shouldn't be.

### Result (combined corpus)

9,289 parseable tools; all 9,289 carry a finding (9,287 fixable, 9,037 advisory),
0 crashes. Headlines: GTR003 blank-line 99.4% · GTR001 indent 71.7% · GTR002
param-order 71.3% · GTR013 child-order 53.9%; GTR027 EDAM/xrefs 89.6% · GTR025
requirements 57.3% · GTR022 command-CDATA 35.2% · GTR030 help-CDATA 39.6%;
placeholders GTR031/GTR032 0% *(at PR5; GTR031 now 71.5% — D5)*. See
`docs/corpus_check_stats.md` for the full table (the authoritative source).

### Reproduction

```sh
uv run python -m scripts.corpus_check check            # full sweep + stat page
uv run python -m scripts.corpus_check check --limit 200 --no-stats
uv run --package galaxy-tool-fmt pytest \
  galaxy-tool-fmt/tests/test_corpus_check.py       # helper unit tests
```

## D3 (2026-06-02) — GTR032 (`&&`-vs-lone-`&`) stays deferred: the anti-pattern is ~absent

### Decision

`GTR032` (`CommandAndJoining` — "join shell commands with `&&`, not a lone `&`")
**remains a reserved no-op placeholder**, now on a data-backed basis rather than a
hunch. A literal-text GTR032 is not worth implementing: the genuine anti-pattern
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
| `joining` (`cmd1 & cmd2` — the GTR032 anti-pattern) | **1** | **yes** |

So **2 tools** carry a *genuine* lone `&` (1 background + 1 joining), and the true
"meant `&&`, wrote `&`" mistake appears in **1 tool** across the whole corpus.

### Rationale

- **No payoff.** A crude check flags 431 tools, ~99.5% false positives; a *precise*
  check flags ~1. Neither is worth a rule.
- **Precision needs the deferred lexer.** Excluding the `quoted` class reliably
  (the 74 sed/awk literals) requires shell-string tokenisation — the M5 Cheetah/
  shell lexer (`../../galaxy-tool-codemod/PLAN.md`), not a regex. The
  `command-lone-amp` quote scan is a heuristic good enough to *size* the question,
  not to ship as detection.
- **The reserved code stays.** `GTR032` keeps its slot and no-op `detect` (the
  registry/`corpus_check` already report it at 0%); revisit only if the M5 lexer
  lands or the corpus shifts. `GTR031` (single-quoted Cheetah, 87% crude noise per
  `command-iuc-heuristics`) was already deferred on the same "needs a real parser"
  grounds (D1).

## D4 (2026-06-03) — GTR031 (single-quoted Cheetah `$var`) has real signal — reconsider

### Finding

Unlike GTR032 (D3, dead at ~1 tool), **GTR031 is worth implementing.** Its
deferral rested on the crude `command-iuc-heuristics` count — any `$var` not
immediately preceded by a single quote — firing on **8,126 tools (87.2%)**, most of
which are `$var` in Cheetah *directives* (`#if $x`, `#set $y = …`): template logic,
not shell arguments the practice is about. A refined classifier
(`scripts.measure command-unquoted-var`; combined corpus, 2026-06-03;
`_classify_command_vars`, unit-tested) excludes directive/`##`-comment lines and
tracks shell quote state. The genuine target — a fully **unquoted** `$var` on a
shell line — still fires on **6,823 tools (73.2%)**, 50,380 occurrences:

| `$var` class | Occurrences | GTR031 flags it? |
|---|---|---|
| `directive` (on a `#…` line) | 49,654 | no — template logic |
| `single_quoted` (`'$x'`, the IUC-correct form) | 39,041 | no |
| `double_quoted` (`"$x"`, a lesser concern) | 10,688 | borderline |
| `unquoted` (bare `$x` on a shell line) | **50,380** | **yes** |

73.2% is **consistent with the prevalence of already-shipped advisory checks**
(GTR027 EDAM 89.6%, GTR025 requirements 57.3%) — so high prevalence is not a
disqualifier here; it is the IUC best practice, and most tools violate it.

### Open questions for shipping (not blockers, but to settle first)

- **A read-only lexer that handles multi-line shell quotes.** The
  `command-unquoted-var` scan resets quote state per *line* (fine for sizing), but a
  shipped check must track a `'…'`/`"…"` span that crosses newlines, or it will
  mis-flag a `$var` inside a multi-line quoted string. This is the small read-only
  slice of the M5 Cheetah/shell lexer (`../../galaxy-tool-codemod/PLAN.md`) —
  detection-only, so it needs none of M4 / the mutation cursors / provenance.
- **Per-occurrence verbosity.** ~7.4 findings/tool (50,380 / 6,823) vs. one per tool
  for the presence checks (GTR025/007). Decide per-occurrence (point at each `$var`)
  vs. one-per-tool ("has unquoted Cheetah vars").

The reserved `GTR031` code stays a no-op `detect` until that lexer + reporting
shape are decided; this entry records that the *signal* question is now settled —
yes.

## D5 (2026-06-03) — GTR031 ships: a read-only command-text lexer, per-occurrence

### Decision

`GTR031` (single-quote Cheetah `$var` in `<command>`) is now **implemented** —
the first command-CDATA-text check, and the first to need more than an XML query.
It reports **one advisory finding per fully-unquoted shell-line `$var`**, each
naming the variable and the fix (`single-quote it as '$x'`).

### How

A **read-only lexer**, `command_text.unquoted_cheetah_vars(text)` (originally in
this tier; **moved to tier 1** `galaxy-tool-xml/.../command_text.py` in D8 so the
GTR020 codemod can share it), does a single character scan that:
- tracks `'…'` / `"…"` quote state **across newlines** (a span may cross lines);
- skips **Cheetah directive/comment lines** (`#if`, `#set`, `##`) — but only when
  the leading `#` is *outside* a quote, so a `#` line inside a multi-line string
  stays literal;
- reports a `$var` only when **fully unquoted** (a double-quoted `$var` is a lesser
  concern, intentionally not flagged — keeps the check to the genuine
  word-splitting/injection hazard).

This is the **detection-only slice of the codemod tier's deferred M5** Cheetah/
shell lexer (`../../galaxy-tool-codemod/PLAN.md`): because it classifies and
never rewrites, it needs none of M4 / the mutation cursors / macro provenance.
`GTR032` stays a no-op (D3); the M5 mutation subsystem stays deferred.

### Reporting shape

**Per-occurrence**, not one-per-tool: each finding carries the var's own
`sourceline` (`<command>` sourceline + the lexer's newline offset) and points at a
specific `$var` to quote — more actionable for a linter, at ~7 findings per
flagged tool. (The alternative one-per-tool shape was considered and declined.)

### Corpus impact

Reproduced-by: `uv run --package galaxy-tool-xml pytest
galaxy-tool-xml/tests/test_command_text.py` (the lexer, now tier 1) and `uv run
--package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py`;
full sweep `uv run python -m
scripts.corpus_check check`. GTR031 fires on **6,646 tools (71.5% of 9,289 swept),
48,850 findings** (`docs/corpus_check_stats.md`) — slightly under the D4 sizing
(73.2% / 50,380) because the shipped lexer's multi-line-quote tracking correctly
excludes vars the per-line sizing scan over-counted. `GTR032` remains 0. (The
regen also added the previously-missing `GTR017` row — the artifact predated it.)
Advisory, so it never fails `check` unless `--strict`.

## D6 (2026-06-03) — GTR031 stays advisory: auto-quoting is partial and not behaviour-preserving

### Question

Should the GTR031 findings (D5) get an auto-fix — a codemod that single-quotes the
unquoted `$var`? Single-quoting is **not** behaviour-preserving in general: `$x`
that renders to one value is safe to wrap, but `$opts` that deliberately
word-splits into several arguments breaks if quoted. Whether a given occurrence is
safe turns on **what the `$var` references**.

### Evidence

Reproduced-by: `uv run python -m scripts.measure iuc011-fixability` (combined
corpus, 2026-06-03; reuses the shipped `unquoted_cheetah_vars` lexer, so the
population is exactly what GTR031 reports; classifiers pinned in
`galaxy-tool-xml/tests/test_measure.py`). Each occurrence's root identifier is
resolved against the tool's `<inputs>` (a `$cond.sub` resolves to the leaf
param's kind). Of **49,119** occurrences across **6,699** flagged tools:

| Reference class | Occurrences | Auto-quote? |
|---|--:|---|
| `safe` — bare/nested single-token param (data/int/float/bool/select-single/…) | 22,919 (46.7%) | **provable** |
| `text` — a `text` param (single value, but often free-form options) | 2,320 (4.7%) | judgment |
| `attr_safe` — `$param.ext` / server-path attr (space-free) | 295 (0.6%) | **provable** |
| `attr_unsafe` — `$param.name` / `.element_identifier` (dataset label) | 399 (0.8%) | unsafe |
| `builtin_path` — `$__tool_directory__` etc. (deployment-fixed path) | 1,119 (2.3%) | **provable** |
| `builtin_label` — `$on_string` (run-varying label) | 0 (0.0%) | unsafe |
| `structured` — `$cond.x` whose leaf isn't a param (rare) | 5,186 (10.6%) | unknown |
| `multi` — `multiple=` / `data_collection` param | 368 (0.7%) | **unsafe** (deliberate splat) |
| `non_input` — root resolves to no input (`#set`-assembled, loop vars) | 16,513 (33.6%) | **unsafe / unknown** |

(The `attr` / `builtin` classes were later split into space-free vs label sub-buckets
— the provable-vs-not line GTR020 fixes on; see D8. The `safe` row's `select-single`
was *also* later narrowed: `select`/`drill_down` are provable only when their option
values are statically single tokens, and the `command_text` lexer now filters escaped
`\$`/`#raw`/comment false positives — both predate this sizing, so the current GTR020.2
counts are lower; see codemod `docs/decisions.md` §32. The `safe` row's `bool` was
narrowed the same way (2026-06-11): a `boolean` is provable only when both
`truevalue`/`falsevalue` are single tokens, so the `falsevalue=""` flag idiom is no
longer auto-quoted — the provable subset is now 44.6%, not the old ~50%; codemod §44.)

### Decision

> **Revisited and partly reversed — see D8.** The provable subset *did* get an
> auto-fix (GTR020), and it *does* run under `format`; the reasoning below explains
> why the *full* fix stays out and the auto-fix is narrow.

**GTR031 stays advisory-only for now.** Two findings drive it:

- **The genuinely-dangerous case is tiny** (`multi` 0.7%) — so a fix isn't *unsafe*
  in bulk; the floor of provably-safe occurrences is large (~47%, ~50% with
  `attr`/`builtin`).
- **But the fix would be partial and is the wrong shape.** A third of occurrences
  (`non_input`, 33.6%) are `#set`-assembled or loop variables a static fixer can't
  resolve, so only **1,007 / 6,699 (15%)** of flagged tools have *every* var safe —
  for the other 85%, GTR031 still fires after a partial fix. And quoting command
  text is a **Cheetah-rewriting mutation codemod** (CDATA-preserving splice, like
  GTR016 `FixInterpreter`) — the *mutation* side of the M5 boundary, well beyond
  the read-only lexer D5 added. The cost/coverage doesn't justify it: the
  per-occurrence advisory already points the author at each exact `$var` to quote.

If revisited, the safe scope is a **narrow, opt-in GTR** that quotes only the
`safe` class (bare single-token params, incl. structured leaves) and never touches
`non_input` / `multi` — never auto-run under `format`.

## D7 (2026-06-03) — GTR033: package `<requirement>`s should pin a version

### Decision

A new advisory check, `RequirementVersionPinned` (`GTR033`), flags a
`<requirement type="package">` that carries no `version` — an unpinned conda
package is not reproducible (a later environment solve can pick a different
release). It is the first **advisory check added after the original PR4 batch**,
and a worked example that the check tier grows by one bounded `CheckRule` at a
time. Surfaced by the post-architecture-audit "next work" survey.

### Scope / predicate

- Only `type="package"` requirements (Galaxy's default when `type` is omitted —
  4 corpus tools rely on the default) carry a pinnable version; `set_environment`
  / `resource` / `binary` / `*-module` kinds are skipped. (Of 7,057 corpus
  `<requirement>`s, 7,053 are `package`.)
- A `version` that is absent or whitespace-only is "unpinned". A macro-token
  version (`@TOOL_VERSION@`) counts as pinned (it resolves to a literal).
- Per-occurrence: one `Violation` per unpinned requirement, naming the package.
- Advisory (`detect_only`), like every check — informational unless `--strict`.

### Corpus impact

Reproduced-by: `uv run --package galaxy-tool-lint pytest
galaxy-tool-lint/tests/test_checks.py`; full sweep `uv run python -m
scripts.corpus_check check`. GTR033 fires on **275 tools (3.0% of 9,289 swept),
661 findings** (`docs/corpus_check_stats.md`) — a real, actionable signal between
the rare and the near-universal advisories, not noise. The check tier is now
**13 active checks** (GTR032 remains the sole no-op stub, D3).

## D8 (2026-06-03) — GTR031's provable subset gets an auto-fix (GTR020), revisiting D6

### Decision

The **provably**-single-valued subset of the GTR031 findings is now auto-fixed by a
tier-2 codemod, **GTR020 `SingleQuoteCommandVars`** (codemod `docs/decisions.md`
§30), which runs in the `format` / `iuc` pipeline. This revisits D6's "stays
advisory-only / never auto-run under `format`" on three points:

- **The mutation is bounded, not the M5 subsystem.** D6 read the fix as a full
  Cheetah-rewriting mutation. GTR020 is a **positional splice**: it wraps `'…'`
  around the lexer's existing `start`/`end` span — no Cheetah evaluation, no
  reference resolution. Idempotent and validity-preserving on the whole corpus
  (8,607 idempotent, 0 post-validate-failed).
- **Scope is the *provable* set, wider than D6's safe-only floor.** The
  `iuc011-fixability` measure was refined to split the old `attr` / `builtin`
  classes into space-free vs label sub-buckets. GTR020 fixes
  `{safe, attr_safe, builtin_path}` — values that are space-free for any tool that
  *currently works* (a path with a space already breaks unquoted). That is **49.5%**
  of occurrences and **1,287 / 6,699** whole-tool-auto-fixable tools (vs 1,007 for
  safe-only — `builtin_path` alone adds most of the +280). `builtin_label`
  (`$on_string`) is excluded and is 0 in the corpus.
- **It runs under `format`** because every applied quote is behaviour-preserving;
  this deliberately shifts default-`format` bytes (the workspace / cli / registry
  byte-identity notes were updated). The **lexer moved to tier 1**
  (`galaxy-tool-xml/.../command_text.py`) so the codemod (tier 2) and this check
  (tier 3.5) share it without an upward dependency; `SingleQuotedCheetah` now
  imports it from there (behaviour unchanged).

GTR031 **stays advisory** and keeps reporting the non-provable residual (free-form
`text`, `multiple=` splats, `attr_unsafe` / `builtin_label` labels, `structured`,
`non_input`) — for those, single-quoting is a judgment call a static fixer can't
make, exactly as D6 found.

## D9 (2026-06-04) — The three CDATA/quoting advisories become partition `.2` sub-rules

### Decision

The three advisories that share a best-practice with a fixable codemod are now the
**advisory `.2` sub-rule** of a partition parent (registry `docs/decisions.md` D10),
and their `detect` is **restricted to the residual the fix can't reach**:

| Was | Now | Fires only on |
|---|---|---|
| `GTR022` `CommandCdata` | `GTR018.2` | mixed-content `<command>` (the fix wraps pure-text) |
| `GTR030` `HelpCdata` | `GTR019.2` | mixed-content `<help>` |
| `GTR031` `SingleQuotedCheetah` | `GTR020.2` | **non-provable** unquoted `$var` (the fix quotes the provable ones) |

(The flat advisory checks — `GTR021`, `GTR023`–`GTR029`, `GTR032`, `GTR033` — are
unchanged.) This supersedes the codes used in D5/D6/D8, which predate the partition.

### Why

Before, each advisory **overlapped** its fix (it flagged everything, including the
auto-fixable part), so `check` double-reported. Restricting each `.2` to the
*complement* of its `.1` makes the practice's two halves a clean partition: disjoint
and together exhaustive. The boundary reuses the **shared tier-1 predicates** the fix
uses — `galaxy_tool_xml.cdata.cdata_wrappable` (CDATA) and
`command_vars.provably_quotable` (quoting) — so the check (tier 3.5) and codemod
(tier 2) can never drift, without the check depending on the codemod tier. The
`is_cdata_wrapped` re-serialise helper moved to tier 1 (`galaxy_tool_xml.cdata`) with
the predicate.

### Reproduction

```sh
uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py
uv run --package galaxy-tool-refactor-registry pytest \
  galaxy-tool-refactor-registry/tests/test_partition.py   # the soundness guard
```

## D10 (2026-06-04) — GTR020.2 residual tracks the shared `quote_is_behavior_preserving`

### Decision

GTR020.2 (`SingleQuotedCheetah`) now computes its residual from the shared tier-1 policy
`galaxy_tool_xml.shell_oracle.quote_is_behavior_preserving` rather than `provably_quotable`
directly — the same predicate GTR020.1 fixes by (codemod `docs/decisions.md` §31). The
partition stays exact by construction: an occurrence is advisory iff the fixer won't quote
it. When the optional `galaxy-tool-xml[shell-oracle]` extra is present, the only delta vs
`provably_quotable` is the fd-dup *narrowing* — a value-domain-safe `2>&$fd` target the fixer
declines, which then appears in the advisory. (The no-split *widening* described in an earlier
draft of this entry was reverted as unsound — Galaxy renders Cheetah vars to literal text, so
`VAR=$x` splits; tier-1 `docs/decisions.md` §17.) Without the extra the policy is exactly
`provably_quotable`, identical to D8. A mixed-content `<command>` — which GTR020.1 skips
wholesale — reports **all** its unquoted vars, since the fixer touches none of them.

This tier still does not depend on the codemod tier: the shared predicate lives in tier 1.

### Reproduction

```sh
uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py
```

## D11 (2026-06-04) — GTR034: unused `<param>` advisory

### Decision

A new detect-only advisory, `UnusedParam` (GTR034): flag an `<inputs>` `<param name="X">`
whose name is referenced **nowhere** the tool could use it. The first *consumer-of-a-lint*
in the M5 read-only param work (`../../docs/upgrade_research/cheetah_section_editing.md`),
chosen before the rename mutator so the reference-completeness + macro-expansion handling is
built and validated read-only (a mistake here is a cheap advisory false-positive, not a
broken tool).

**Sound by conservative over-counting.** A param is flagged only if its name token appears
in the empty intersection of *every* reference channel. The reference set is the shared
tier-1 `cheetah_refs.referenced_identifiers` = all Cheetah `$X`/`$cond.X` reference segments
∪ the identifier tokens of every attribute value (skipping a param's own `name`). The key
finding that makes this sound *and* allowlist-free: **every** by-name param cross-reference
Galaxy supports (`data_ref`, `format_source`, `metadata_source`, `change_format @input`,
dynamic-options `from_dataset` / `filter @ref`, output `<collection>` `structured_like` /
`collection_type_source` / `default_identifier_source`, output-action `option @name` /
`filter @ref`, …) is carried in an **attribute** — there is no positional or free-text param
linking — so the generic attribute-token scan subsumes them all. Over-counting only ever
*protects* a param from being flagged (the safe direction).

**Handling the false-positive sources.** References are read from the **macro-expanded**
tree (so a param used only inside an `<expand>`/imported-macro body is seen); if expansion
fails the check **bails** (reports nothing). Excluded from candidates: a `<conditional>`
**selector** `<param>` (structurally used by its `<when>` branches even without a `$cond.sel`
use) and macro-supplied params (only author-written `<param>`s in the raw tree are
candidates). A param mentioned only in `<tests>` is treated as used (its test `<param @name>`
token counts) — the conservative choice.

**Philosophy.** Unlike the other advisories this is not a literal IUC practice but a general
code-quality lint (an unused param is dead wiring); the detect-only check tier accommodates
it. It is advisory (Bucket 4) — informational unless `--strict`.

**Corpus sizing** (`scripts.corpus_check check`, combined): GTR034 flags **189 tools / 467
findings** (2.0%). A first *incomplete* scan (only `$`-refs + attribute values) flagged
248/1003 but had false positives — e.g. a boolean used solely in an output `<filter>` Python
expression (`<filter>store_ext</filter>`, a bare-name reference in element text); scanning
**all element text** (not just `$`-refs) dropped those to the sound 189/467. Spot-checked
flagged params show only their own definition mention (truly orphaned).

### Reproduction

```sh
uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py -k gtr034
uv run python -m scripts.corpus_check check   # regenerates docs/corpus_check_stats.md
```

## D12 (2026-06-06) — planemo-parity advisory checks: GTR038 (citations), GTR039 (TODO)

**Date:** 2026-06-06. First batch of the planemo-linter reimplementation
(`../../docs/planemo_linter_parity.md`) landing as advisory checks. Reproduced-by:
`uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py
-k "gtr038 or gtr039"`.

- **GTR038 `CitationsPresent`** — reimplements planemo `CitationsMissing` (no
  `<citations>`) + `CitationsNoText` (an empty `doi`/`bibtex` citation),
  `galaxy.tool_util.linters.citations`. Detect-only: a citation is author-supplied
  content, never synthesised — no fix.
- **GTR039 `NoTodoText`** — reimplements planemo `CommandTODO` + `HelpTODO`: a literal
  `"TODO"` in a `<command>` / `<help>` `.text` marks an unfinished tool. Detect-only.
- **Why detect, not fix.** Both flag missing/placeholder author content; there is nothing
  to mechanically synthesise (consistent with the soundness discipline — fix only the
  provable, report the rest). They join the `strict` preset (advisory).
- **Coverage.** Several planemo `general.py`/`help.py`/`tests.py` linters were already
  covered by existing checks (GTR021/023/024/025/026/027/028/033 — see the GTR coverage
  table in the parity doc); this batch adds the citations + TODO concerns that had no
  equivalent.
- **Corpus** (`docs/corpus_check_stats.md`): GTR038 fires on **6,710 tools (72.2%)** —
  most corpus tools carry no citation; GTR039 on **47 (0.5%)**.

## D13 (2026-06-06) — planemo-parity output-correctness checks: GTR040–GTR043

**Date:** 2026-06-06. Second batch of the planemo-linter reimplementation
(`../../docs/planemo_linter_parity.md`) — the `galaxy.tool_util.linters.output`
correctness surface, landing as advisory checks. Reproduced-by:
`uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py
-k "gtr04"`.

- **GTR040 `OutputNamesUnique`** — reimplements planemo `OutputsNameDuplicated`: a
  duplicate `name` among the `<data>` / `<collection>` outputs means one silently
  shadows another. Detect-only.
- **GTR041 `OutputNameValid`** — reimplements planemo `OutputsNameInvalidCheetah`: an
  output `name` that is not a valid Cheetah placeholder (`^[a-zA-Z_]\w*$`) cannot be
  referenced as `$name`. Detect-only.
- **GTR042 `CollectionTypeDeclared`** — reimplements planemo `OutputsCollectionType`,
  **lenient**: a `<collection>` whose structure is supplied by `type_source` /
  `structured_like` is accepted, so only one with *none* of `type` / `type_source` /
  `structured_like` is flagged (more precise than planemo's bare-`type` check — avoids
  false positives on derived collections). Detect-only.
- **GTR043 `OutputFormatSourceExclusive`** — reimplements planemo
  `OutputsFormatSourceIncomp`: combining `format_source` (derive the datatype from
  another dataset) with an explicit `format` / `ext` is contradictory. Detect-only.
- **Why detect, not fix.** Each flags an authoring mistake with no single correct
  mechanical repair (which of two clashing values is right is the author's call), so
  per the soundness discipline they report, never fix. They join the `strict` preset.
- **Deferred.** The heavier `output` linters — `OutputsFormat` (`_check_format`
  recursion through `change_format`/`actions`), `OutputsLabelDuplicated` (needs the
  default-label model), `OutputsExpression`/`OutputsFilterExpression` — are a later
  sub-batch.
- **Scope: direct children only.** `_named_outputs` yields only the direct `<data>` /
  `<collection>` children of `<outputs>`, not nested ones (a `<data>` inside a
  `<collection>` is a structural child in the collection's own namespace, not a top-level
  output) — matching planemo and keeping these advisories from over-flagging novel XML.
- **Corpus** (`docs/corpus_check_stats.md`): GTR040 fires on **11 tools (0.1%)**, GTR041
  on **74 (0.8%)**, GTR043 on **7 (0.1%)**; **GTR042 is 0** — every corpus `<collection>`
  output already declares its structure, so the check is a low-noise guard for novel XML
  rather than a corpus-prevalent finding.

## D14 (2026-06-06) — planemo-parity tool-level correctness checks: GTR044–GTR047

**Date:** 2026-06-06. Third batch of the planemo-linter reimplementation
(`../../docs/planemo_linter_parity.md`) — tool-level presence/format correctness from
`galaxy.tool_util.linters.command` + `.general`, as advisory checks. Reproduced-by:
`uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py
-k "gtr04 and not gtr040 and not gtr041 and not gtr042 and not gtr043"`.

- **GTR044 `CommandPresent`** — reimplements planemo `CommandMissing` (no `<command>`)
  + `CommandEmpty` (a `<command>` whose body is empty); a tool with no command template
  cannot run. Flags a missing element and a whitespace-only/childless body. A
  macro-using tool is **skipped** for the *missing* case: a top-level `<expand>` (e.g.
  `<expand macro="version_command_config"/>`) commonly injects the `<command>` from an
  imported macro, and planemo lints the *expanded* tool — flagging it on the raw tree
  is a false positive (61% of the naive findings corpus-wide, e.g. the whole `raceid_*`
  family). Same raw-tree soundness boundary as GTR045 below. An empty literal
  `<command>` with no child `<expand>` is still flagged. Detect-only.
- **GTR045 `ProfileFormatValid`** — reimplements planemo `ToolProfileInvalid`: a declared
  `profile` that is not `<year>.<minor>` (`^[12]\d\.\d{1,2}$`) is silently ignored by
  Galaxy. Absent `profile` (the 16.01 default) is valid, not flagged. A `@…@` macro token
  (`profile="@PROFILE@"`, the corpus' single most common profile value) is **skipped**:
  planemo lints the macro-*expanded* tool, but this tier reads the raw tree, so the token
  resolves to a real version later — flagging it would be a false positive. Under-reporting
  the (unprovable) macro case beats false-positiving the dominant one. Detect-only.
- **GTR046 `RequirementNamePresent`** — reimplements planemo `RequirementNameMissing`: a
  `type="package"` requirement (the default when `type` is omitted) with an empty body
  names no package, so the conda solve has nothing to install. Detect-only. (Complements
  GTR025 *requirements present* and GTR033 *version pinned* — the third requirement gap.)
- **GTR047 `ToolVersionWhitespace`** — reimplements planemo `ToolVersionWhitespace`.
  Detect-only **by design**: unlike a `<requirement>` version (auto-trimmed by GTR035),
  the tool `version` is used *raw* as the tool's identity, so trimming it would change
  which tool this is. Closes the §33 "advisory-by-design" story for the tool version;
  tool `id` whitespace is already caught by GTR023 (the id charset check).
- **Why detect, not fix.** Each flags a missing/malformed authoring element with no single
  safe mechanical repair (or, for GTR047, a deliberately-unfixed identity field). Per the
  soundness discipline they report, never fix. They join the `strict` preset.
- **Corpus** (`docs/corpus_check_stats.md`, 9,289 tools): GTR044 flags **8 (0.1%)** —
  after the macro guard above; the naive (un-guarded) rule flagged 59, of which 51 were
  macro-supplied-command false positives. GTR047 flags **4 (0.0%)**. **GTR045 and GTR046
  are 0**: every corpus profile is either well-formed or a `@…@` macro token (skipped),
  and every package `<requirement>` names a package — both are low-noise guards for novel
  XML rather than corpus-prevalent findings (cf. GTR042 in D13).

## D15 (2026-06-06) — planemo-parity output-residual checks: GTR048–GTR050

**Date:** 2026-06-06. Fifth planemo-linter batch (`../../docs/planemo_linter_parity.md`) —
the remaining mechanical `galaxy.tool_util.linters.output` checks, as advisory checks.
Reproduced-by: `uv run --package galaxy-tool-lint pytest
galaxy-tool-lint/tests/test_checks.py -k "gtr048 or gtr049 or gtr050"`.

- **GTR048 `OutputsPresent`** — reimplements planemo `OutputsMissing`: most tools should
  declare an `<outputs>` section. A macro-using tool is **skipped** (a top-level
  `<expand>` may inject `<outputs>`) — the same raw-tree boundary as GTR044.
- **GTR049 `OutputFormatDefined`** — reimplements planemo `OutputsFormat`: a top-level
  `<data>`/`<collection>` with no `format`/`ext`/`format_source`/format `<action>`/
  `auto_format`/`structured_like`+`inherit_format`/ext-capturing `<discover_datasets>`
  defaults to the generic `data` type. Honours planemo's tool-provided-metadata gate
  (a tool writing `galaxy.json` is exempt) and resolves the named `<discover_datasets>`
  patterns (`__default__` / `*_and_ext__`) before the `(?P<ext>…)` test. An output whose
  subtree has an `<expand>` is skipped (macro may inject the format structure).
- **GTR050 `OutputLabelsDistinct`** — reimplements planemo `OutputsLabelDuplicatedFilter`
  + `OutputsLabelDuplicatedNoFilter`, **narrowed to explicit labels**. planemo also flags
  the *default*-label collision (two outputs both omitting `label` share
  `${tool.name} on ${on_string}`), but that is normal — Galaxy disambiguates by name — so
  it is noise: planemo fires on 390 corpus tools vs 104 for genuine explicit duplicates.
  Outputs with a `<filter>` may reuse a label across disjoint branches, so the message
  says to double-check rather than asserting a defect. A measured low-noise narrowing
  (`scripts.measure`-style probe in the PR), in the spirit of GTR042/GTR044.
- **Corpus** (`docs/corpus_check_stats.md`, 9,289 tools): GTR048 **4 (0.0%)**, GTR049
  **33 (0.4%)**, GTR050 **104 (1.1%)**. GTR049's named-`<discover_datasets>`-pattern
  resolution matters: without it the naive rule flags 161 (128 of them tools using
  `__name_and_ext__`-style patterns that *do* define the ext — false positives). GTR050's
  explicit-label narrowing flags 104 vs planemo's 390 (the default-label-collision noise).

## D16 (2026-06-06) — planemo-parity embedded-expression validity: GTR051–GTR053

**Date:** 2026-06-06. Sixth planemo-linter batch (`../../docs/planemo_linter_parity.md`) —
the "is this embedded shape/expression well-formed?" checks across `containers` /
`output` / `stdio`, as advisory checks. Reproduced-by: `uv run --package
galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py -k "gtr05 and not
gtr050"`.

- **GTR051 `ContainerShapeRecognized`** — reimplements planemo `ContainerImageShape`: a
  `<requirements><container>` identifier should be a known registry prefix
  (`quay.io/biocontainers/` / `docker://` / `oras://`) or a Docker-Hub `<image>[:<tag>]`
  (`DOCKER_IMAGE_RE`). An identifier carrying a `@…@` macro token is skipped (raw-tree
  boundary, cf. GTR045).
- **GTR052 `OutputFilterValid`** — reimplements planemo `OutputsFilterExpression`: an
  output `<filter>` body must `ast.parse` as a Python `eval` expression. A filter carrying
  a `@…@` token is skipped — it is still a template fragment, not yet valid Python.
- **GTR053 `StdioRegexValid`** — reimplements planemo `StdIORegex`: a `<stdio><regex
  match>` must `re.compile`. Like planemo, only a tool with exactly one `<stdio>` is checked.
- **Why try/except.** `ast.parse` / `re.compile` have no LBYL validity predicate, so the
  narrow `except (SyntaxError, ValueError)` / `except re.error` is the sanctioned
  third-party boundary (mirrors `_is_pep440`).
- **Also reclassified (no new rule).** planemo `CitationsNoValid` (an empty `<citations>`)
  is already **subsumed by GTR038** (which fires when `<citations>` has no `<citation>`
  children) — marked HAVE. planemo `DatatypesCustomConf` needs the **filesystem** (a
  sibling `datatypes_conf.xml`), out of the raw-tree tier's reach — DETECT-deferred.
- **Corpus** (`docs/corpus_check_stats.md`): GTR051 **6**, GTR052 **8**, GTR053 **2** — the
  `@…@` guards skip 44 container + 37 filter macro-token values that would otherwise
  false-positive. See the regenerated page for the authoritative per-rule counts.

## D17 (2026-06-06) — planemo-parity input naming/identity: GTR054–GTR057

**Date:** 2026-06-06. Seventh planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the first slice of the big `inputs.py` correctness surface: parameter naming/identity,
as advisory checks. Reproduced-by: `uv run --package galaxy-tool-lint pytest
galaxy-tool-lint/tests/test_checks.py -k "gtr054 or gtr055 or gtr056 or gtr057"`.

- **GTR054 `ParamNamePresent`** — reimplements planemo `InputsName`: an `<inputs>//param`
  must declare a `name` or `argument`.
- **GTR055 `ParamNameValid`** — reimplements planemo `InputsNameEmpty` + `InputsNameValid`
  (planemo notes the two overlap): the resolved name must be non-empty and a valid Cheetah
  placeholder (`^[a-zA-Z_]\w*$`). A `@…@` macro-token name is skipped (raw-tree boundary).
- **GTR056 `ParamNamesUnique`** — reimplements planemo `InputsNameDuplicate`: dedup on the
  *qualified* path (planemo's `_param_path` — name + enclosing conditional/section), so
  identically-named params in disjoint `<when>` branches don't collide.
- **GTR057 `InputOutputNamesDistinct`** — reimplements planemo `InputsNameDuplicateOutput`:
  an output name equal to an input param name clashes in the job namespace.
- **Shared helpers.** `_param_name` replicates Galaxy's `_parse_name` (name, else
  `argument.lstrip("-").replace("-","_")`) — duplicated here because the check tier cannot
  depend on the codemod tier that also derives it (GTR037's `_derived_name`). `_iter_named_params`
  / `_param_qualified_path` mirror planemo's `_iter_param` / `_param_path`. Added a `name`-bearing
  `inputs=` kwarg to the test `_tool` builder for this and the rest of the `inputs.py` surface.
- **Corpus** (`docs/corpus_check_stats.md`): GTR054 **0** (every corpus param names itself —
  a low-noise guard, cf. GTR045/046), GTR055 **13**, GTR056 **18**, GTR057 **4**.

## D18 (2026-06-06) — planemo-parity static select-option correctness: GTR058–GTR060

**Date:** 2026-06-06. Eighth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the static `select`-option slice of `inputs.py`, as advisory checks. Reproduced-by:
`uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py
-k "gtr058 or gtr059 or gtr060"`.

- **GTR058 `SelectOptionsDefined`** — reimplements planemo `InputsSelectOptionsDef` +
  `InputsSelectOptionsDefConditional`: a top-level select must define options **exactly
  one** way (`<option>` children / an `<options>` element / `dynamic_options`); a select
  controlling a `<conditional>` must use `<option>` children only. **Macro guard is
  decisive here**: a select whose subtree has an `<expand>` is skipped, because a macro
  commonly injects the options — without it the rule fires on **157** tools, **152** of
  them macro-supplied-option false positives (guarded: **5**). Largest macro exposure of
  any check so far; same raw-tree boundary as GTR044/GTR058.
- **GTR059 `SelectOptionValuePresent`** — reimplements planemo `InputsSelectOptionValueMissing`:
  a static `<option>` with no `value` cannot be selected.
- **GTR060 `SelectOptionsDistinct`** — reimplements planemo `InputsSelectOptionDuplicateValue`
  + `InputsSelectOptionDuplicateText`: duplicate `(value, selected)` or `(text, selected)`
  pairs (text defaulting to `value.capitalize()` when the body is empty, per planemo).
- **Deferred to a later sub-batch** (the *dynamic* `<options>` element):
  `InputsSelectOptionsMultiple` / `…DefinesOptions` / `…FromDatasetAndDatatable` /
  `…MetaFileKey`, plus the deprecated-attribute warnings (`InputsSelectDynamicOptions`,
  `InputsSelectOptionsDeprecatedAttr`).
- **Corpus** (`docs/corpus_check_stats.md`): GTR058 **5**, GTR059 **1**, GTR060 **31**.

## D19 (2026-06-06) — planemo-parity dynamic select `<options>` correctness: GTR061–GTR064

**Date:** 2026-06-06. Ninth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the dynamic `<options>`-element slice of `inputs.py`, finishing the select surface, as
advisory checks. Reproduced-by: `uv run --package galaxy-tool-lint pytest
galaxy-tool-lint/tests/test_checks.py -k "gtr061 or gtr062 or gtr063 or gtr064"`.

- **GTR061 `SelectOptionsSingle`** — reimplements planemo `InputsSelectOptionsMultiple`:
  at most one `<options>` element.
- **GTR062 `SelectOptionsHaveSource`** — reimplements planemo `InputsSelectOptionsDefinesOptions`:
  an `<options>` must define a source (`from_file`/`from_parameter`/`from_dataset`/
  `from_data_table`/`from_url`) or a `<filter type="add_value|data_meta">`. Skips an
  `<options>` whose subtree has an `<expand>` (macro may inject the source — raw-tree boundary).
- **GTR063 `SelectOptionsSourceCoherent`** — reimplements planemo
  `InputsSelectOptionsFromDatasetAndDatatable` + `InputsSelectOptionsMetaFileKey`:
  `from_dataset`/`from_data_table` are mutually exclusive; `meta_file_key` needs `from_dataset`.
- **GTR064 `SelectOptionsNotDeprecated`** — reimplements planemo `InputsSelectDynamicOptions`
  (the `dynamic_options` attr) + `InputsSelectOptionsDeprecatedAttr` (`from_file`/
  `from_parameter`/`options_filter_attribute`/`transform_lines`). Advisory deprecation
  signal (needs restructuring, not mechanically fixable); previously listed DETECT, now built.
- **Corpus** (`docs/corpus_check_stats.md`): GTR061 **0**, GTR062 **1**, GTR063 **0** (low-noise
  guards, cf. GTR045/061), GTR064 **151** (deprecated options mechanisms are still common —
  a genuine, accurate advisory at ~1.6%).

## D20 (2026-06-06) — planemo-parity validator form checks: GTR065–GTR067

**Date:** 2026-06-06. Tenth planemo-linter batch (`../../docs/planemo_linter_parity.md`) —
the first half of the `inputs.py` validator surface (validator *form*: compatibility,
text, expression), as advisory checks. Reproduced-by: `uv run --package
galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py -k "gtr065 or
gtr066 or gtr067"`.

- **GTR065 `ValidatorTypeCompatible`** — reimplements planemo `ValidatorParamIncompatible`
  (validator `type` must be allowed for the param `type` — the vendored
  `_PARAM_VALIDATOR_TYPES` matrix) + `ValidatorAttribIncompatible` (each validator
  attribute must be allowed for the validator `type` — `_VALIDATOR_ATTR_TYPES`). A param
  type absent from the matrix (e.g. `boolean`) accepts any validator.
- **GTR066 `ValidatorTextPresence`** — reimplements planemo `ValidatorHasText` (`expression`
  / `regex` validators need a body) + `ValidatorHasNoText` (others should not carry one).
- **GTR067 `ValidatorExpressionValid`** — reimplements planemo `ValidatorExpression` (body
  must `re.compile` / `ast.parse`, under a `warnings.simplefilter("error", FutureWarning)`)
  + `ValidatorExpressionFuture` (a `FutureWarning` is reported as a deprecation, not an
  error). A `@…@` macro-token body is skipped (the GTR052 raw-tree boundary).
- **Deferred to a later sub-batch** (validator *required attributes*): `ValidatorMinMax`,
  `ValidatorDatasetMetadataEqualValue`/`…OrJson`, `ValidatorMetadataCheckSkip`,
  `ValidatorTableName`, `ValidatorMetadataName`.
- **Helper.** `_iter_param_validators` mirrors planemo's `_iter_param_validator`
  (`<inputs>//param[@type]` × `<validator type=…>`).
- **Corpus** (`docs/corpus_check_stats.md`): GTR065 **33**, GTR066 **0** (low-noise guard),
  GTR067 **1** (14 `@…@`-token validator bodies skipped — FPs avoided).

## D21 (2026-06-06) — planemo-parity validator required-attributes: GTR068

**Date:** 2026-06-06. Eleventh planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the second half of the validator surface (required attributes), finishing `inputs.py`'s
validators, as one data-driven advisory check. Reproduced-by: `uv run --package
galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py -k gtr068`.

- **GTR068 `ValidatorRequiredAttributes`** — one rule reimplementing six planemo linters
  via a `_VALIDATOR_REQUIRED_ANY` table plus a `dataset_metadata_equal` special case:
  `ValidatorMinMax` (`in_range`/`length`/`dataset_metadata_in_range` need `min`|`max`),
  `ValidatorMetadataCheckSkip` (`metadata` needs `check`|`skip`), `ValidatorTableName`
  (the `*_data_table` validators need `table_name`), `ValidatorMetadataName` (the
  `dataset_metadata_*` validators need `metadata_name`), and `ValidatorDatasetMetadataEqualValue`
  + `…OrJson` (`dataset_metadata_equal` needs `value`/`value_json` **and** `metadata_name`,
  and not both value forms). Reuses `_iter_param_validators` (D20).
- **Validator surface complete**; `inputs.py` now has only type/structure, display/idiom,
  and option-filter groups left.
- **Corpus** (`docs/corpus_check_stats.md`): GTR068 **1** — a low-noise correctness guard
  (corpus validators almost always carry their required attributes; the XSD catches most).

## D22 (2026-06-06) — planemo-parity conditional checks: GTR069–GTR071

**Date:** 2026-06-06. Twelfth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the `<conditional>` slice of `inputs.py`, as advisory checks. Reproduced-by: `uv run
--package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py -k
"gtr069 or gtr070 or gtr071"`.

- **GTR069 `ConditionalTestParamType`** — reimplements planemo `ConditionalParamType` (the
  first `<param>` must be `select` or `boolean`) + `ConditionalParamTypeBool` (a `boolean`
  test param is discouraged — prefer a `select`).
- **GTR070 `ConditionalTestParamAttributes`** — reimplements planemo
  `ConditionalParamIncompatibleAttributes`: the test param cannot be `optional="true"` or
  `multiple="true"` (via Galaxy's `string_as_bool`).
- **GTR071 `ConditionalWhensMatchOptions`** — reimplements planemo `ConditionalWhenMissing`
  + `ConditionalOptionMissing` + `ConditionalOptionMissingBoolean`: every test-param option
  (`select` `<option value>` / `boolean` `truevalue`/`falsevalue`) needs a `<when>` and vice
  versa. A conditional whose subtree has an `<expand>` is skipped — a macro may supply
  options/whens (22 corpus FPs avoided).
- **Helper.** `_iter_conditionals` mirrors planemo's `_iter_conditional` (skips `value_from`
  conditionals and those whose first `<param>` is macro-supplied/absent).
- **Corpus** (`docs/corpus_check_stats.md`): GTR069 **220** (2.4%; mostly the
  boolean-discouraged advisory — boolean conditionals are common but genuinely
  discouraged), GTR070 **5**, GTR071 **233** (2.5%; when/option mismatches). The two
  high-incidence ones are accurate planemo-parity advisories, not false positives.

## D23 (2026-06-06) — planemo-parity input type/structure: GTR072–GTR074

**Date:** 2026-06-06. Thirteenth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the `inputs.py` type/structure group, as advisory checks. Reproduced-by: `uv run
--package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py -k
"gtr072 or gtr073 or gtr074"`.

- **GTR072 `InputsPresent`** — reimplements planemo `InputsMissing`: a tool with no
  `<inputs>//param` (and not a `data_source` tool) usually has a missing inputs section.
  A macro-using tool is skipped (a top-level `<expand>` may inject params — 216 corpus FPs
  avoided; guarded **15** vs un-guarded 231).
- **GTR073 `ParamTypeChildCombination`** — reimplements planemo `InputsTypeChildCombination`:
  `<options>` only for `data`/`select`/`drill_down`, `<options><option>` only for
  `drill_down`, `<options><column>` only for `data`/`select`.
- **GTR074 `DataOptionsValid`** — one rule reimplementing the five data-param `<options>`
  linters: `InputsDataOptionsMultiple` (one `<options>`), `…Attrib` (only
  `options_filter_attribute`), `…FilterAttribFiltersType` / `…FiltersType` (filter type/key
  rules), `…FiltersRef` (filters need `ref`). **Faithful to planemo's strictness** — it
  flags e.g. `add_value` filters and missing `ref` in a data param's `<options>` (verified
  on the qiime2 suite), which is why it fires on ~2.6% of tools; this is parity, not an
  FP relative to planemo.
- **Corpus** (`docs/corpus_check_stats.md`): GTR072 **15**, GTR073 **0** (low-noise guard),
  GTR074 **241** (2.6%; 1,071 findings — faithful planemo strictness on data-param options).

## D24 (2026-06-06) — planemo-parity input display/idiom: GTR075–GTR076

**Date:** 2026-06-06. Fourteenth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the `inputs.py` display/idiom group (boolean values + select widget consistency),
completing all of `inputs.py` except option filters. Reproduced-by: `uv run --package
galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py -k "gtr075 or gtr076"`.

- **GTR075 `BooleanValuesDistinct`** — reimplements planemo `InputsBoolDistinctValues`
  (``truevalue`` ≠ ``falsevalue``) + `InputsBoolProblematic` (``truevalue`` not a false
  string, ``falsevalue`` not a true string). planemo's severity is profile-gated
  (warn <23.1 / error ≥23.1); this report-only tier flags regardless, so no profile needed.
- **GTR076 `SelectDisplayConsistent`** — reimplements planemo `InputsSelectSingleCheckboxes`
  + `InputsSelectMandatoryCheckboxes` (``display="checkboxes"`` needs ``multiple`` and
  ``optional``) + `InputsSelectMultipleRadio` + `InputsSelectOptionalRadio`
  (``display="radio"`` incompatible with ``multiple``/``optional``), for
  ``select``/``data_column``/``drill_down``. ``optional`` defaults to ``multiple`` per Galaxy.
- **Corpus** (`docs/corpus_check_stats.md`): GTR075 **8**, GTR076 **28** — low-noise.

## D25 (2026-06-06) — planemo-parity option-filter checks: GTR077–GTR079 (`inputs.py` complete)

**Date:** 2026-06-06. Fifteenth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the `<options>/<filter>` group, **completing the entire `inputs.py` correctness surface**.
Reproduced-by: `uv run --package galaxy-tool-lint pytest
galaxy-tool-lint/tests/test_checks.py -k "gtr077 or gtr078 or gtr079"`.

- **GTR077 `OptionFilterAttributes`** — reimplements planemo
  `InputsOptionsFiltersRequiredAttributes` + `InputsOptionsRemoveValueFilterRequiredAttributes`
  + `InputsOptionsFiltersAllowedAttributes`, vendoring `FILTER_REQUIRED_ATTRIBUTES` /
  `FILTER_ALLOWED_ATTRIBUTES` and the `remove_value` one-of rule.
- **GTR078 `OptionFilterExpression`** — reimplements `InputsOptionsRegexFilterExpression`
  (a `regexp` filter's `value` must `re.compile`; reuses `_is_valid_regex`).
- **GTR079 `OptionFilterReferences`** — reimplements `InputsOptionsFiltersCheckReferences`
  (filter `ref`/`meta_ref` must name a real param). **Skips macro-using tools** — the
  param-name set is incomplete on the raw tree (6 corpus FPs avoided; guarded 1 vs 7).
- **`inputs.py` is now fully covered** (all 57 linters HAVE/SKIP/n-a except the single
  `InputsDataFormat` advisory). The remaining planemo-parity frontier is `tests.py`.
- **Corpus** (`docs/corpus_check_stats.md`): GTR077 **31**, GTR078 **0** (low-noise guard),
  GTR079 **1** (after the macro guard).

## D26 (2026-06-06) — planemo-parity test assertions: GTR080–GTR081 (`tests.py` begun)

**Date:** 2026-06-06. Sixteenth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the first `tests.py` slice (assertion well-formedness + output compare-attrs), as advisory
checks. Reproduced-by: `uv run --package galaxy-tool-lint pytest
galaxy-tool-lint/tests/test_checks.py -k "gtr080 or gtr081"`.

- **GTR080 `TestAssertionsWellFormed`** — reimplements planemo `TestsAssertsMultiple` (at
  most one ``assert_stdout``/``assert_stderr``/``assert_command`` per test) +
  `TestsAssertsHasNQuant` (``has_n_lines``/``has_n_columns`` need ``n``/``min``/``max``) +
  `TestsAssertsHasSizeQuant` (``has_size`` needs ``size``/``value``/``min``/``max``) +
  `TestsAssertsHasSizeOrValueQuant` (``has_size`` not both ``value`` and ``size``), via the
  shared ``assert_contents``/``stdout``/``stderr``/``command`` xpath.
- **GTR081 `TestOutputCompareAttributes`** — reimplements planemo `TestsOutputCompareAttrib`:
  ``sort``/``lines_diff``/``decompress``/``delta``/``delta_frac``/``metric``/``eps`` each
  valid only with specific ``compare`` modes.
- **Deferred** (need Galaxy's pydantic models, not a raw-tree query): `TestsAssertionValidation`
  (assertion list model) + `TestsCaseValidation` (test parameter model). The remaining ~14
  mechanical `tests.py` linters (output correspondence, discovered, failure expectations,
  param-in-inputs) are follow-up sub-batches.
- **Corpus** (`docs/corpus_check_stats.md`): GTR080 **1**, GTR081 **2** — low-noise guards.

## D27 (2026-06-06) — planemo-parity test output correspondence: GTR082–GTR083

**Date:** 2026-06-06. Seventeenth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the `tests.py` output-correspondence slice, as advisory checks. Reproduced-by: `uv run
--package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py -k "gtr082
or gtr083"`.

- **GTR082 `TestOutputNamed`** — reimplements planemo `TestsOutputName` (a test `<output>`
  must declare a `name`; `<output_collection>` names are XSD-required).
- **GTR083 `TestOutputsCorrespond`** — reimplements planemo `TestsOutputDefined` (the name
  is a declared output), `TestsOutputCorresponding` (a test `<output>` ↔ a `<data>`), and
  `TestsOutputCollectionCorresponding` (a `<output_collection>` ↔ a `<collection>`), via
  the shared `_declared_output_map` (planemo's `_collect_output_names`). The *unknown-name*
  case is **skipped** for a macro-using tool — the declared-output set is incomplete on the
  raw tree (~360 corpus FPs avoided by the guard); correspondence is still checked for
  names that resolve.
- **Corpus** (`docs/corpus_check_stats.md`): GTR082 **7**, GTR083 **124**.

## D28 (2026-06-06) — planemo-parity test discovered-datasets: GTR084

**Date:** 2026-06-06. Eighteenth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the `tests.py` discovered-datasets slice, one rule over three linters. Reproduced-by:
`uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py
-k gtr084`.

- **GTR084 `TestDiscoveredOutputsChecked`** — reimplements planemo
  `TestsOutputCheckDiscovered` (a test ``<output>`` for an output with
  ``<discover_datasets>`` needs ``count``/``min``/``max`` or ``<discovered_dataset>``),
  `TestsOutputCollectionCheckDiscovered` (a ``<output_collection>`` needs
  ``count``/``min``/``max`` or ``<element>``) and `TestsOutputCollectionCheckDiscoveredNested`
  (a ``list:list``/``list:paired`` collection needs nested ``<element>`` or element children
  with ``count``/``min``/``max``). Only resolved output names are checked (reuses
  `_declared_output_map`), so a macro-supplied output under-reports — no extra guard needed.
- **Corpus** (`docs/corpus_check_stats.md`): GTR084 **27**.

## D29 (2026-06-06) — planemo-parity test expectations/param-in-inputs: GTR085–GTR088

**Date:** 2026-06-06. Nineteenth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the final mechanically-reimplementable `tests.py` slice, completing all of `tests.py`
except the two pydantic-model linters. Reproduced-by: `uv run --package
galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py -k "gtr085 or gtr086
or gtr087 or gtr088"`.

- **GTR085 `TestParamsInInputs`** — reimplements planemo `TestsParamInInputs` (a test
  `<param>` resolves to an input by name or argument variant), injection-free (set
  comparison, not interpolated XPath). **Skips macro-using tools** — the input set is
  incomplete on the raw tree (~1,400 corpus FPs avoided; guarded 166 vs ~1,570).
- **GTR086 `TestExpectFailureCoherent`** — reimplements `TestsOutputFailing` +
  `TestsExpectNumOutputsFailing`: an `expect_failure` test must not define outputs or set
  `expect_num_outputs`.
- **GTR087 `TestExpectNumOutputs`** — reimplements `TestsExpectNumOutputs`: a non-failure
  test should set `expect_num_outputs` when an output has a `<filter>`.
- **GTR088 `TestHasExpectations`** — reimplements `TestsHasExpectations` (a test that
  asserts nothing — no output/assert/expect_*); **subsumes** `TestsValid` (its tool-level
  "no valid test" warning is conveyed per-test). The test `_tool` builder's baseline test
  gained `expect_num_outputs="1"` so it is a *valid* test (else GTR088 would fire on it).
- **Corpus** (`docs/corpus_check_stats.md`): GTR085 **166**, GTR086 **3**, GTR087 **618**,
  GTR088 **190** — GTR087/088 are high but faithful planemo advisories (under-asserted
  tests are genuinely common), not our false positives. `tests.py` is now complete bar the
  two pydantic-model linters.

## D30 (2026-06-06) — planemo-parity help RST validity: GTR089 (docutils dep)

**Date:** 2026-06-06. Twentieth planemo-linter batch (`../../docs/planemo_linter_parity.md`)
— the `<help>` reStructuredText check, the first check needing a real RST parser.
Reproduced-by: `uv run --package galaxy-tool-lint pytest
galaxy-tool-lint/tests/test_checks.py -k gtr089`.

- **GTR089 `HelpRstValid`** — reimplements planemo `HelpInvalidRST`
  (`galaxy.tool_util.linters.help`). Validates the `<help>` body by publishing it through
  **docutils** with a `warning_stream` that raises on any reported message and `halt_level`
  lifted so the stream is the trigger — a faithful standalone of Galaxy's
  `rst_to_html(error=True)` / `rst_invalid`. Help with `format="markdown"` is skipped (RST
  is the default); a whole-help-via-macro tool has no literal `<help>` text and is skipped.
  stderr is redirected during the parse so a noisy role/directive can't leak.
- **New dependency:** `docutils>=0.21` added to the check tier (the only check needing an
  RST parser; mirrors how lxml/packaging are external deps — the tier still depends only on
  *our* tiers 1 + 0.5). A `docutils.*` mypy override (no usable stubs) sits beside lxml's.
- **No `@…@` guard.** Unlike value-domain checks, a macro token in help prose is inert
  text; corpus spot-checks of `@`-containing invalid help confirmed the errors are
  structural (undefined RST reference targets, bad directives), not token-caused — so help
  with tokens is validated normally (planemo validates the expanded help; structural errors
  are identical).
- **Corpus** (`docs/corpus_check_stats.md`): GTR089 **220** (2.4% of tools; of ~8,671 RST
  help bodies), with 35 `format="markdown"` help bodies skipped.

## D31 (2026-06-09) — GTR089 split into the fix/advisory partition: GTR089.1 + GTR089.2

**Date:** 2026-06-09. GTR089 becomes the fourth partition practice (after GTR018/019/020;
registry D10): a fixable `.1` codemod + an advisory `.2` residual sharing one tier-1
predicate. `HelpRstValid` (`GTR089`) is renamed `HelpRstResidual` (`GTR089.2`,
`parent="GTR089"`); the new `RepairHelpRst` (`GTR089.1`, codemod §37) auto-repairs the
deterministically-fixable invalid RST. Reproduced-by: `uv run --package
galaxy-tool-lint pytest galaxy-tool-lint/tests/test_checks.py -k gtr089`.

- **The check no longer parses RST itself.** Its standalone `_rst_is_invalid` /
  `_RaisingWarningStream` moved to tier 1 (`galaxy_tool_xml.rst`, §23); the check imports
  `rst_is_invalid` / `repair_help_rst` / `has_macro_token` from there. So the **direct
  `docutils` dependency is dropped** from this tier (it is now transitive through tier 1),
  and the `docutils.*` mypy override is removed — the check tier's only external deps are
  again lxml/packaging.
- **GTR089.2 is the residual, not the whole.** It reports help that is *still* invalid
  after the behaviour-preserving repair: `rst_is_invalid(repair_help_rst(text) or text)`
  for non-macro help. A fully-fixable tool is now silent under GTR089.2 (GTR089.1 handles
  it in `format`); only the non-fixable / mixed / macro residual is reported. Macro-bearing
  help is still **validated** (reported if invalid) exactly as before — the macro guard only
  suppresses the *repair* attempt (the unprovable-macro case), not the validity check, so
  D30's no-`@`-guard rationale stands.
- **Still 66 checks** — a rename + reparent, not an addition. GTR089.2 stays
  `rulesets={"strict"}` (advisory); GTR089.1 joins `{default, iuc, strict}` (fixable).
- **Corpus** (`docs/corpus_check_stats.md`): in the unified `check` sweep (every parseable
  tool), GTR089.1 flags **63** tools and GTR089.2 reports the **177**-tool residual — down
  from the **220** the undivided GTR089 flagged (D30). Of the 63 GTR089.1 touches, **43**
  are repaired all the way to *valid* RST (220 − 177); the other ~20 are mixed bodies it
  partially repairs (a fixable error removed) whose remaining non-fixable errors keep them
  in the residual — exactly the partition's intent. (The narrower codemod-eligible `format`
  sweep — `scripts.corpus_check codemod …RepairHelpRst`, gated on the codemod's own
  eligibility, 8607 tools — modifies **54**, all idempotent with 0 validity breaks; the
  delta to 63 is the wider parseable population the `check` sweep covers.)

## D32 (2026-06-10) — GTR090/GTR091: the last infra-free planemo linters

### Decision

Close the "mechanical, buildable" remainder of the planemo DETECT backlog — the three
linters needing neither Galaxy's pydantic models, the datatype registry, the
filesystem, nor the network:

- **GTR090 `OutputReferencesValid`** (`checks/outputs.py`) — one rule reimplementing
  `OutputsStructuredLikeReference` + `OutputsFormatSourceReference` (they share
  planemo's unqualified-reference machinery, `output.py::_check_unqualified_reference`).
  A `<collection structured_like=…>` / `<data|collection format_source=…>` must
  resolve: a top-level input param passes; a `format_source` naming a sibling output
  passes (faithful skip); a `|`-qualified reference is not validated (faithful); an
  unqualified reference to a *nested* param is flagged with the qualified `cond|param`
  spelling (planemo's warn), an ambiguous one lists the candidates, an unresolvable
  one is a dangling reference (planemo's error). The qualified path prefixes only
  `conditional`/`section` ancestors — a `repeat` contributes nothing — and the name
  falls back to the argument-derived form (the shared `_param_name`).
- **GTR091 `DataParamFormatDeclared`** (`checks/inputs.py`) — reimplements
  `InputsDataFormat`: a `<param type="data">` without `format` accepts the generic
  `data` type.

### Macro-exposure soundness (the recurring pattern, sized before building)

- **GTR090 skips any macro-using tool** (`has_macros`): an `<expand>` may supply the
  referenced param — or the sibling output a `format_source` names — so the raw tree
  cannot prove a reference dangling. Pre-build sizing (ad-hoc walk): **360** tools
  carry a checkable reference, **254 (71%)** macro-using and skipped, the remainder
  splitting 41 unqualified-resolvable / 15 ambiguous / 4 dangling. The committed
  sweep reports **25 tools / 60 findings** (`docs/corpus_check_stats.md`).
- **GTR091 needs no guard**: attribute presence is raw-tree-stable (expansion cannot
  add an attribute to a literal `<param>`); macro-supplied params are unseen — the
  accepted under-report side of the boundary. The committed sweep reports **207
  tools / 650 findings** (`docs/corpus_check_stats.md`).

With this batch every planemo linter buildable on the raw tree alone is HAVE; the
~7 remaining DETECT all need external infra (parity-table Summary, now metadata-
derived at HAVE=114).

### Reproduced by

```sh
uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/ -k "gtr090 or gtr091"
uv run python -m scripts.corpus_check check   # regenerates docs/corpus_check_stats.md
```


## D33 (2026-06-10) — GTR035 partitions: the `<tool name>` trim becomes the GTR035.2 advisory

The proofs-tightening pass re-graded GTR035's two legs: the `<requirement
version>` trim is unconditionally proven (conda gets the spec verbatim), but the
`<tool name>` trim rests on a *display-contract* argument (raw `parse_name`,
HTML collapse, byte-visible in API JSON) — below the construction bar for an
auto-fix. Following the GTR018/019/020/089 pattern, the codemod narrowed to
`GTR035.1` and this tier gained **`NameWhitespace` (GTR035.2)**: detect-only,
`strict` ruleset, carrying the `ToolNameWhitespace` planemo alias (parity
coverage unchanged). Roster 68 → **69**. Reproduced-by: `uv run --package
galaxy-tool-lint pytest galaxy-tool-lint/tests/`.


## D34 (2026-06-10) — GTR032 graduates: the lone-`&` joining detector (D3's revisit condition met)

D3 deferred GTR032 on two grounds: ~1 genuine corpus instance, and precision
needing shell-string tokenisation ("revisit only if the M5 lexer lands or the
corpus shifts"). The lexer landed (CT3 is a tier-1 base dep) and the ledger's
novel-tool principle retired the rarity leg, so the reserved no-op becomes a
real detector. The engine is the `command-lone-amp` measure's classifier,
**moved** to `galaxy_tool_lint.lone_amp` (the measure imports it back —
one source, numbers stay comparable): quote/redirect/pipe-aware, flags only the
*joining* class (`cmd1 & cmd2`); redirects (`2>&1`), `|&`, quoted sed/awk
literals, and intentional trailing backgrounding never fire. Detect-only by
construction: backgrounding is valid shell, so a typo cannot be proven — no
auto-fix. The parity table's `_NO_OP_DETECT` mechanism is retired (every rule
now detects). Reproduced-by: `uv run --package galaxy-tool-lint pytest
galaxy-tool-lint/tests/ -k gtr032 -k iuc012`.

## D35 (2026-06-11) — GTR095: the id/name/version trio, the half tier-1 `validate` can't see

### Decision

Close the last *infra-free* planemo DETECT gap — `ToolIDMissing` /
`ToolNameMissing` / `ToolVersionMissing` (`galaxy.tool_util.linters.general`) —
as one rule, **`ToolIdentityPresent` (GTR095)** in `checks/tool.py`. The trio was
parked as "DETECT — XSD-required, detect TBD", on the assumption that tier-1
`validate_tool` already covered it. The homework showed that is only *half* true,
and the residual is worth a check:

- **`id` / `name`** carry XSD `use="required"` in **every** vendored schema
  (oldest `galaxy-16.10.xsd` through newest `galaxy-26.1.xsd`), so a *missing*
  one already fails `validate`. But the type is bare `xs:string` (no `pattern` /
  `minLength`), so `id=""` / `name=""` are **XSD-valid** — `validate` waves them
  through, planemo flags them. GTR095 adds exactly that empty-string case.
- **`version`** is **not** XSD-required at all (it carries `default="1.0.0"`, so
  Galaxy silently supplies a version). `validate` never flags an absent or empty
  `version`; GTR095 is the *only* guard for it.

So the rule is genuinely additive over tier-1, not a redundant re-report — it is
the planemo trio's tier-1 *residual*. Faithful to planemo's semantics: the falsy
test (`if not value`) fires on absent **or** empty; whitespace-only is truthy
(left to GTR047 for `version`); and the `name` leg mirrors `parse_name()`'s
`name or id` fallback (`tool_util/parser/xml.py:220-221`), so it fires only when
neither attribute has a value.

### Soundness on the raw tree (no `has_macros` guard)

Unlike the parity wave's element/text checks, GTR095 needs no macro guard: macro
expansion inserts *elements* and substitutes `@…@` tokens *inside* attribute
values, so it can never add a root `<tool>` attribute, and a value carrying a
token is non-empty (so an unexpanded `version="@TOOL_VERSION@"` is correctly not
flagged). The raw tree is therefore exact for this check.

Roster 69 → **70**. With this the only remaining planemo DETECT linters need
external infra: `TestsAssertionValidation` / `TestsCaseValidation` (Galaxy's
pydantic models) and `ValidDatatypes` / `DatatypesCustomConf` (the datatype
registry / filesystem). Parity Summary (metadata-derived): HAVE 114 → **117**,
DETECT 7 → **4**.

### Reproduced by

```sh
uv run --package galaxy-tool-lint pytest galaxy-tool-lint/tests/ -k gtr095
uv run python -m scripts.corpus_check check   # regenerates docs/corpus_check_stats.md
```
