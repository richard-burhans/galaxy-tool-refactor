# Deferred fix opportunities — the corpus-incidence ledger

A standing inventory of every fix opportunity in the **codemod** and **fmt**
tiers that was missed, narrowed, or deferred **because the corpus showed few or
no examples** — as opposed to being genuinely unprovable. Compiled 2026-06-10
from a full sweep of both tiers' decision records, source comments, `PLAN.md`,
and `docs/upgrade_research/`, with every claim re-verified against source.

## The principle

> **Fix as much as possible automatically while maintaining behavior. Corpus
> incidence sizes *impact*, never *soundness* — novel tools matter.**

The corpus (~9,358 deduped tools) is evidence, not a proof: a provable fix
declined on rarity still fails the first novel tool that needs it, and a
soundness guard skipped on "zero incidence" breaks the first novel tool that
trips it. Two in-repo precedents already embody this:

- **GTR036 `ReplaceOutputElement`** shipped for a **1-tool** corpus population
  with the explicit note *"Low incidence, but correct for novel tool XML — not
  gated on corpus frequency"* (codemod `docs/decisions.md` §34).
- **GTR001's mixed-content/payload guard** (fmt §D19, 2026-06-10) reversed a
  "zero corpus incidence" deferral from the behavior-preservation audit — and
  the sweep then showed 245 corpus edits had been landing in unprovable spots
  after all.

Items here are classified **A** (provable fix declined purely on rarity),
**C** (scope narrowed to the corpus-common provable case, with a further
provable slice left behind), or **closed/out-of-scope** (for the record).
Class B (soundness guard skipped on zero incidence — the GTR001 class) is
**empty** after the §D19 fix; any new B item should be treated as a bug, not a
backlog entry.

---

## Open opportunities

### A1. Collection-type whitespace normalization (a would-be `Upgrade22_1`)

- **Where:** codemod `PLAN.md` ("Considered and declined — collection-type
  whitespace normalization").
- **What:** strip stray whitespace from `collection_type` / `type` values
  (`"list, list:paired"` → `"list,list:paired"`) on the 22.01 boundary — the
  exact mechanical class as the shipped `Upgrade24_1` `format`/`ftype`
  normalization.
- **Why deferred:** *"exactly **1** corpus value is whitespace-fixable … a
  one-tool codemod … does not earn its keep. Not built."* Pure rarity; the
  transform itself is provably safe by the same argument as 24.1's.
- **Sizing:** 1 corpus tool (`measure.py collection-type-normalization`);
  vs `Upgrade24_1`'s ~97.
- **What it would take:** small — a 24.1-pattern codemod; the corpus *sweep*
  additionally needs an eligibility-anchor relaxation to exercise its one tool
  (a harness concern, not a soundness one).

### A2. Phase-3c `@TOOL_VERSION@` / `@VERSION_SUFFIX@` extraction (parked, PR #31)

- **Where:** PR #31 (the `version-tokenization` measure; the parking record is
  the PR — this ledger is its first in-repo record).
- **What:** factor a literal `version="<base>+galaxy<suffix>"` into the
  canonical IUC `@TOOL_VERSION@`/`@VERSION_SUFFIX@` tokens when `<base>` equals
  a package `<requirement>` version (the provable precondition).
- **Why deferred:** *"a <1% opportunity (75 tools) — far smaller than the
  profile work (~1,485)"*. Rarity relative to the profile epic, not
  unprovability.
- **Sizing:** 75 clean candidates (0.8%); 70 of them need a `<macros>` block
  created.
- **What it would take:** medium — token+macros creation machinery; style /
  maintainability payoff (IUC best practice), not a validity or behavior
  unlock. Opt-in-command shaped if built.

### A3. GTR032 precise lone-`&` joining detector — its revisit condition is met

- **Where:** check `docs/decisions.md` D3.
- **What:** a *precise* "join with `&&`, not a lone `&`" advisory (the current
  GTR032 is a reserved no-op).
- **Why deferred:** dual grounds — the genuine anti-pattern is ~1 corpus tool,
  **and** precision needed shell-string tokenisation: *"revisit only if the M5
  lexer lands or the corpus shifts."* **The M5 lexer has landed** (CT3 /
  `cheetah_cdm` is a tier-1 base dep), so the stated revisit condition is
  satisfied; only the rarity leg remains.
- **Sizing:** ~1 genuine joining occurrence; 431 crude-heuristic false
  positives the lexer would now suppress.
- **What it would take:** small-medium — a CT3+quote-aware classifier (the
  `command-lone-amp` measure's logic, hardened). Detect-only: `cmd1 & cmd2` is
  valid shell, so author intent (background vs typo) is not provable — no
  auto-fix.

### C1. GTR015 `format="input"` — the nested sole-data-input case is provable

- **Where:** `docs/upgrade_research/16_04_fix_output_format.md` (the 41-tool
  residual: 38 multi-input, 2 zero-input, 1 nested-single).
- **What:** GTR015 rewrites `format="input"` → `format_source="<name>"` only
  for a sole **top-level** data input; a sole *nested* one (inside a
  conditional/section) was left out because *"the unqualified name wouldn't
  resolve"*.
- **Verified against Galaxy source (2026-06-10):** `determine_output_format`
  looks `format_source` up in `input_datasets`, which is keyed by the
  **prefixed (qualified) name** (`lib/galaxy/tools/actions/__init__.py` —
  `input_datasets[prefixed_name] = …`). A sole nested data input is therefore
  addressable via its qualified name; the rewrite is provable.
- **Sizing:** 1 corpus tool; the 38 multi-input cases stay out by construction
  (Galaxy resolves bare `format="input"` to a *random* input's extension —
  there is no deterministic behavior to preserve), and the 2 zero-input cases
  have nothing to inherit from.
- **What it would take:** small — extend `_sole_top_level_data_input_name` to a
  qualified-name variant + a Galaxy-version check that qualified
  `format_source` is honoured at the tool's profile.

### C2. GTR016 `interpreter=` — the flags slice of bucket C may be rewritable

- **Where:** `docs/upgrade_research/16_04_fix_interpreter.md` +
  `docs/interpreter_bucket_stats.md`.
- **What:** GTR016 auto-fixes bucket A (single-token standard interpreter +
  literal leading script; 1,410 tools). Bucket **C — "non-standard
  interpreter"** (51 tools, 3.0%) bundles two different things: true
  non-scripts (`docker`, `java -jar`) *and* standard interpreters carrying
  flags (`Rscript --no-save`, `python -W ignore`). If legacy Galaxy composed
  the command by verbatim concatenation (`interpreter + " " + command`), the
  flags slice is mechanically rewritable with the same proof as bucket A.
- **Why deferred:** conservative bucket-A scoping; the flags slice was never
  separately sized or proof-checked.
- **Proof obtained (2026-06-10, legacy Galaxy source):** `evaluation.py`'s
  interpreter block is **byte-identical from `release_16.04` through
  `release_20.01`** (the whole era honoring `interpreter=`; removed by 20.09):
  `executable = command_line.split()[0]` (post-Cheetah) → abspath against
  `tool_dir` → replace-first-occurrence → **`command_line = interpreter + " "
  + command_line`** — verbatim string concatenation. So for a command whose
  first token is *literal* (the existing bucket-A requirement), the rewrite
  `<command>{interpreter} '$__tool_directory__/{token}' {rest}</command>`
  reproduces legacy behavior for **any** interpreter value — flags
  (`Rscript --no-save`), `java -jar`, even `export X=1; docker …`. The
  "single-token standard interpreter" gate was conservatism, not soundness.
- **Sizing:** ≤51 corpus tools (bucket C; the provable slice = those whose
  command leading token is literal — a sub-split measure quantifies it).
  Bucket B (267 tools, leading Cheetah) stays genuinely unprovable —
  `split()[0]` of the *rendered* line is statically unknowable.
- **What it would take:** the proof is done; remaining work is a bucket-C
  sub-split measure, the eligibility-predicate widening (TDD), the GTR016
  corpus sweep + stats/research-note regen. Highest potential population on
  this list, and `interpreter=` is a `must_fix` that blocks the whole
  profile-upgrade chain for affected tools.

### C3. GTR036 `<output type="collection">` → `<collection>`

- **Where:** codemod `docs/decisions.md` §34 ("Scope homework").
- **What:** the deprecated-element rewrite ships only for `type="data"`;
  `type="collection"` was deferred because *"a literal rename is not provably
  equivalent"* — Galaxy remaps `collection_type` → `type` /
  `collection_type_source` → `type_source` (filling `type_source` via
  `unicodify(None)` when absent).
- **The opening:** the remap is precisely documented from Galaxy source in §34
  itself; a codemod that applies the *same remap* (element rename + attribute
  renames) is provable by the same source-mirroring method that proved the
  `type="data"` case.
- **Sizing:** ~0 corpus tools (not separately counted; the `type="data"` case
  was 1). Pure novel-tool insurance on a deprecated construct.
- **What it would take:** small — extend the existing codemod with the
  attribute remap + tests mirroring the Galaxy parse.

---

## Closed or already principle-conformant (for the record)

- **GTR001 mixed-content / payload-subtree guard** — the class-B instance;
  **fixed** (fmt §D19, 2026-06-10).
- **`Upgrade24_1`'s 18-tool imported-macro residual** — **closed** by the
  repo-scoped `normalize-macros` command (macro epic Phase 2a); kept out of
  per-tool `format`/`upgrade` by design (cli §D7), not by rarity.
- **GTR020.1 quoting partition** — already the principle in action: the
  provable subset is auto-fixed, the 406 unsound-before occurrences were
  correctly retracted, and the residual (299 no-static-options + the
  runtime-sourced classes) is unprovable **by construction**, not by corpus.
- **Macro provenance layer (M1)** — re-deferred on a measured **0-tool**
  residual (`docs/macro_token_residual_stats.md`). Unlike the items above this
  is heavyweight *infrastructure* with no identified provable fix behind it;
  zero incidence is being used to size infrastructure ROI, not to skip a
  soundness guard. Re-evaluate only when a structural macro codemod needs
  expansion provenance.

## Confirmed out of scope (unprovable / undecidable, not corpus-gated)

| Item | Why it stays deferred |
|---|---|
| GTR015 multi-input residual (38) | Galaxy resolves `format="input"` to a **random** input ext — no deterministic behavior exists to preserve; author intent required |
| GTR016 bucket B (267) | script position depends on rendered Cheetah — statically unprovable |
| GTR018/019 mixed-content CDATA residual | XML child elements cannot live inside a CDATA section — impossibility, not rarity |
| `16_04_exit_code` injection | would pin worse legacy semantics + double-inject past macro-supplied `<stdio>` |
| `23_0_consider_optional_text` | behavior lives in template semantics (`None` vs `""`) — no deterministic XML edit |
| `24_2` test-case fixing | needs Galaxy's pydantic validator; fixes are context-ambiguous |
| GTR037 `id`/`version` whitespace | identity attributes read raw — trimming changes a working tool's identity |
| GTR020 residual classes | dynamic/no-static-options selects — value domain unknowable statically |

---

## Proposed impact ranking

Criteria: **(i)** novel-tool benefit (likelihood × severity of the gap),
**(ii)** provability confidence (proof in hand vs needs research),
**(iii)** corpus-measured size, **(iv)** implementation cost.

| Rank | Item | Why here |
|---|---|---|
| 1 | **C2 — GTR016 bucket-C flags slice** | the only item with a real population (≤51 tools, sub-split TBD) *and* a `must_fix` payoff — each rescued tool's entire profile-upgrade chain unblocks; needs a legacy-source proof first |
| 2 | **C1 — GTR015 nested sole input** | proof already verified in Galaxy source; smallest cost on the list; completes a shipped rule's coverage exactly in the GTR036 spirit |
| 3 | **A1 — collection-type whitespace** | fully provable today by a shipped precedent's argument; trivially small; unblocks the 22.01 crossing for novel tools |
| 4 | **C3 — GTR036 collection variant** | provable by source-mirroring (method already used for the data case); modernizes a deprecated construct; ~0 corpus so pure novel-tool insurance |
| 5 | **A2 — 3c version tokenization** | the largest corpus count (75) but style-tier payoff (no validity/behavior unlock) and the highest cost (macros creation) |
| 6 | **A3 — GTR032 precise detector** | revisit condition met, but advisory-only payoff on a ~1-tool pattern; build when the CT3 classifier is wanted for other command checks anyway |

Ranking approved by the maintainer 2026-06-10; work proceeds top-down.
