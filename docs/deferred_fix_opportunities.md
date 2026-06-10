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

### A1. Collection-type whitespace — **SHIPPED 2026-06-10 as `Upgrade21_09` / GTR093** (codemod §41)

Closed, third item worked top-down. The proof the decline never sought:
Galaxy's runtime strips each comma token itself
(`DataCollectionToolParameter.__init__`), so the rewrite is a behaviour no-op
that gains 22.01 validity. Scoped precisely by the same runtime line —
`collection_type=""` drops (falsy = absent), whitespace-only stays (a
matches-nothing restriction), colon-inner whitespace and the single-value
`CollectionType` sites stay (no runtime strip — construction, not corpus).
The 1 corpus tool remains sweep-invisible (eligibility-anchor artifact) but
`UpgradeToLatest` reaches it; novel tools writing `"list, paired"` now upgrade
cleanly. Full record: codemod `docs/decisions.md` §41.

### A2. Phase-3c version tokenization — **SHIPPED 2026-06-10 as GTR094 / `tokenize-version`** (codemod §43)

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

### A3. GTR032 joining detector — **SHIPPED 2026-06-10** (check D34)

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

### C1. GTR015 nested sole data input — **SHIPPED 2026-06-10** (codemod §40)

Closed, second item worked top-down. The Galaxy-source proof held exactly as the
entry predicted (qualified `format_source` resolves against the prefixed-name
`input_datasets` map — and is upstream-tested in
`test/functional/tools/format_source_in_conditional.xml`), plus a corner the
entry hadn't named: the absent-at-runtime case (unselected branch / empty
optional) is also behaviour-matched — both sides resolve to `"data"`.
Conditional/section nesting now auto-fixes via `cond|name`; repeat nesting
(instance-indexed prefix) is the only nested shape left to the warning — and the
corpus's single nested tool turns out to be exactly that, so the widening
rescues **0 corpus tools** (the residual stays 41: 38 multi-input under Galaxy's
own nondeterminism, 2 zero-input, 1 repeat-nested). Pure novel-tool insurance in
the GTR036 spirit — the cleanest possible instance of the ledger's principle.
Full record: codemod `docs/decisions.md` §40 + the updated
`docs/upgrade_research/16_04_fix_output_format.md`.

### C2. GTR016 `interpreter=` — **SHIPPED 2026-06-10** (codemod §39)

Closed, first item worked top-down from the ranking below. The proof turned out
stronger than the entry hypothesised: Galaxy interpolates the interpreter value
**verbatim in every composition form it ever shipped** (prepend,
`release_16.04`–`release_20.01`; token-splice + `shlex.quote`,
`release_20.09`–`dev:781-787` today — the attribute was never removed, it is
still honored for `legacy_defaults` tools), so the widening admits *any*
non-empty interpreter, not just the flags slice. Bucket C dissolved (25 → A,
26 → B); codemod target 1,410 → 1,435 by shape, sweep rewrites 1,127 → 1,144
(all clean), and the `16_04_fix_interpreter` stuck-tool residual dropped
**316 → 299**. Full record: codemod `docs/decisions.md` §39 + the rewritten
`docs/upgrade_research/16_04_fix_interpreter.md`.

### C3. GTR036 collection variant — **SHIPPED 2026-06-10** (codemod §34 addendum)

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
| 1 | **C2 — GTR016 bucket-C flags slice** | ✅ **shipped** (codemod §39): the proof admitted all of bucket C, not just flags — 25 tools by shape, 17 rescued from the stuck residual (316 → 299) |
| 2 | **C1 — GTR015 nested sole input** | ✅ **shipped** (codemod §40): qualified `format_source` for conditional/section nesting; 0 corpus tools (the 1 nested corpus tool is repeat-nested — correctly still bailed), pure novel-tool insurance |
| 3 | **A1 — collection-type whitespace** | ✅ **shipped** (`Upgrade21_09` / GTR093, codemod §41): runtime comma-token strip proves the no-op; 1 corpus tool + novel-tool insurance |
| 4 | **C3 — GTR036 collection variant** | ✅ **shipped** (§34 addendum): the remap mirrored exactly; `unicodify(None)` corner settled; degenerate case stays advisory |
| 5 | **A2 — 3c version tokenization** | ✅ **shipped** (GTR094 + the `tokenize-version` command, codemod §43): expansion-equality gate; second opt-in-command-only codemod |
| 6 | **A3 — GTR032 precise detector** | ✅ **shipped** (check D34): the measure's classifier moved to the check tier; joining-only, no-op mechanism retired |

Ranking approved by the maintainer 2026-06-10; work proceeds top-down.

---

## Profile-step (Upgrade_vN) gap audit — 2026-06-10

A systematic answer to "which profile crossings could we provably auto-fix but
don't?": diff **every adjacent pair of the 28 vendored XSDs** for tool-stranding
deltas (`scripts.measure xsd-tightenings` — typed / required / pattern-changed /
enums-removed; enum *additions* are widenings and ignored), then verify each
candidate against Galaxy source. The corpus side is nearly exhausted: the
authoritative upgrade-discovery residual is **41 tools** below latest — 39 at
24.1 (the documented §14 residual: macro-reachable via `normalize-macros`, junk,
comma-lists), 1 at 21.05 (a tool bug, `has_size/@delta_frac`, recorded in
`PLAN.md`), and 1 at 21.09 (fixed by GTR093). So everything below is
**novel-tool insurance**, sized at ~0 corpus tools by construction-level greps
(1,795 `<exit_code>` elements: 0 use the `value=` alias, 0 lack both attrs; 0
spaced `has_size` values).

**Known measure limitation (no silent caps):** `xsd-tightenings` diffs
*attribute* sites; an element-**content** typing (e.g. 21.01's
`MacroImportType` on `<import>` text, which forbids path separators) is found
only via its NEW-simpleType row — listed below by hand.

### Already covered

- 21.09→22.01 `collection_type` ×4 sites — GTR093 (param list site; the
  single-value sites are construction-unprovable, §41).
- 24.1→24.2 `Format`/`FormatList` ×5 sites — GTR010.
- Off-enum values at every step (`DetectErrorType`, `HelpFormatType`,
  `InputsConfigfileDatastyleType`, the 23.2 `ParamType` `library_data`
  removal…) — `FixTypos` (GTR006), whose validation-driven near-miss repair is
  generic over enum-typed attributes.
- Widenings/moot: 22.05 `Bytes` (now allows 0), 25.0 collection types (new
  alternatives).

### Gap candidates (G-series) — all closed 2026-06-10 (see the ranking below)

| ID | Delta (boundary) | Status of proof | What it would take |
|---|---|---|---|
| **G1 (+G3, G5)** | the 22.01 **stdio tightening**: `ExitCode.range` required, `Regex.match` required, `RangeType` pattern (whose *sole* consumer is `ExitCode.range`) | **All proven** (Galaxy `xml.py:1248-1280`, `1318-1324`): `range` falls back to the `value` attribute (aliases); an `<exit_code>` with neither — or with `range=""` (the only stranded `RangeType` form; `int("")` path) — is silently skipped, as is a `<regex>` without `match`; the runtime range parser strips all whitespace | one codemod, three fixes: rename `value=`→`range=`; delete runtime-dead `<exit_code>`/`<regex>` elements |
| **G2** | `AssertHasSize.value`/`delta` → `Bytes` (22.01) | **Proven** (follow-up read): values flow through `galaxy.util.size_to_bytes`, which accepts forms the pattern rejects (`"2 TB"`, `"1 MiB"`, decimals); any parseable value canonicalizes to its exact integer byte count — always pattern-valid | normalize to `str(size_to_bytes(v))` when pattern-invalid + parseable |
| **G4** | `Repeat.name` (22.01) / `Conditional.name` (24.0) required | **Declined (verified 2026-06-10):** `Group.__init__` stores `name=None`, but every downstream prefixed-name construction concatenates it (`prefix + input.name` → `TypeError`) — a nameless group was *broken at runtime all along*, so there is no working behavior to preserve; and any synthesized name would leak into the workflow-addressable API surface | none — documented decline |
| **G6** | `MacroImportType` element-content pattern (21.01) — forbids `/` in `<import>` paths | **unprovable** (the path is meaningful; no rewrite preserves it) | document-only |
| — | `ParamConversion`/`RequestParameter` required ×4 (18.01) | **Verified 2026-06-10** (`input_translation.py:59-93`): a missing `remote_name` registers the translation under dict key `None` — dead at lookup (no request param is named `None`); neither attribute is synthesizable (`remote_name` is site-specific semantics, `galaxy_name` an enum choice). A dead-entry *deletion* is likely provable (the G1 pattern) but deliberately not built — `data_source` is a niche tool_type; revisit on demand | documented decline (verified) |

### Proposed ranking

1. **G1 (+G3, G5)** — ✅ **shipped** (codemod §42): the stdio repair joined
   `Upgrade21_09` — `value=`→`range=` alias rename, dead-`value` drop, and
   deletion of runtime-skipped `<exit_code>`/`<regex>` elements.
2. **G2** — ✅ **shipped** (codemod §42): the `has_size` Bytes canonicalizer.
   One proof correction along the way: the runtime parser is
   `galaxy.util.bytesize.parse_bytesize`, *not* `size_to_bytes` — so
   plain-`B`/word-suffix forms were never runtime-working and stay out; the
   provable class is whitespace, suffix case, and integral scientific forms.
3. **G4** — ✅ **declined as predicted** (verified: nameless groups were
   runtime-broken — `TypeError` in prefixed-name construction — plus the
   API-surface hazard). Recorded above; no code.
4. **G6 / 18.01 row** — document-only.

**G-series complete (2026-06-10):** every gap shipped (§42), declined with a
verified reason (G4), or documented as unprovable (G6, 18.01).

G-series ranking approved by the maintainer 2026-06-10. The follow-up source
reads then *collapsed* G3 and G5 into G1 (RangeType's sole consumer is
`ExitCode.range`; `<regex>` shares the skip pattern) and completed G2's proof —
the approved order is preserved, just denser.

**Ledger complete (2026-06-10):** every opportunity and gap is shipped,
declined with a verified reason, or documented as unprovable.
