# Decisions — galaxy-tool-xml-check

Each entry records a decision once it lands: a date, the decision, and the
rationale. Mirrors the conventions of the sibling packages' `docs/decisions.md`.

## D1 (2026-05-30) — A new advisory-check tier for detect-only rules (PR4)

### Decision

A new tier-3.5 package, `galaxy-tool-xml-check`, hosts the **detect-only**
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
uv run --package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/
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
uv run --package galaxy-tool-xml-fmt pytest \
  galaxy-tool-xml-fmt/tests/test_corpus_check.py       # helper unit tests
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
  shell lexer (`../../galaxy-tool-xml-codemod/PLAN.md`), not a regex. The
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
  slice of the M5 Cheetah/shell lexer (`../../galaxy-tool-xml-codemod/PLAN.md`) —
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
shell lexer (`../../galaxy-tool-xml-codemod/PLAN.md`): because it classifies and
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
--package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/test_checks.py`;
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
counts are lower; see codemod `docs/decisions.md` §32.)

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

Reproduced-by: `uv run --package galaxy-tool-xml-check pytest
galaxy-tool-xml-check/tests/test_checks.py`; full sweep `uv run python -m
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
uv run --package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/test_checks.py
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
uv run --package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/test_checks.py
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
uv run --package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/test_checks.py -k gtr034
uv run python -m scripts.corpus_check check   # regenerates docs/corpus_check_stats.md
```

## D12 (2026-06-06) — planemo-parity advisory checks: GTR038 (citations), GTR039 (TODO)

**Date:** 2026-06-06. First batch of the planemo-linter reimplementation
(`../../docs/planemo_linter_parity.md`) landing as advisory checks. Reproduced-by:
`uv run --package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/test_checks.py
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
`uv run --package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/test_checks.py
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
`uv run --package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/test_checks.py
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
Reproduced-by: `uv run --package galaxy-tool-xml-check pytest
galaxy-tool-xml-check/tests/test_checks.py -k "gtr048 or gtr049 or gtr050"`.

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
