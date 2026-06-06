# Behavior-preservation ledger

Every rule the `format` and `upgrade` pipelines apply makes a **behaviour claim**:
applying it does not change what Galaxy runs (or, for the profile-upgrade family,
makes only a structurally-bounded change whose runtime effect is surfaced
separately). This ledger records each claim, the proof that backs it, and — where an
adversarial review **refuted** the claim — the counterexample, root cause, and
remediation.

## Method

The claims were stress-tested by an adversarial-refutation pass: for each fixable
rule, independent skeptics tried to *execute a counterexample* that breaks the claim
(diverse lenses: shell, XML, Cheetah, runtime, idempotence), and a judge ruled
hold / refuted. **Adversarial agents over-claim**, so every "refuted" verdict here
was **re-verified by execution on current code** (dates below) before being recorded
as a real finding — and the few cases where the refutation itself overreached are
flagged. Treat this ledger as the source of truth over the raw verdicts.

The raw verdicts (19 rules, 88 agents, 2026-06-04) live in
`.local/behavior_preservation_verdicts.json` (gitignored). Re-verification:
2026-06-06.

## The soundness boundary (read this first)

Two *different* claims are made by two rule families, and conflating them causes
false alarms:

- **`format` / canonical codemods + runtime-gated fixes** (GTR001–006, 013, 014–020)
  claim **runtime behaviour preservation**: the command Galaxy runs, the help it
  renders, the config files it writes are byte-for-byte unchanged. A genuine runtime
  change here **is** a refutation.
- **The profile-upgrade family** (GTR007–012, `UpdateProfile` + `upgrade_vN`) claims
  only **structural soundness**: the tool stays XSD-valid at the reached profile and
  the step is idempotent. It does **not** claim runtime equivalence — a profile bump
  can legitimately change Galaxy's runtime semantics, and that is surfaced separately
  via `UpgradeResult.behavior_preserving` (`profile_semantics.upgrade_is_behavior_preserving`).
  So a *flagged* runtime change holds the claim; only an *un*-flagged one (or a
  validity/idempotence break) refutes it. See codemod `docs/decisions.md` §22.

## Verdict summary

19 fixable rules audited — **11 hold, 8 refuted**. Of the refuted: **5 fixed**
(GTR018.1, GTR019.1, GTR020.1, GTR004, GTR016), **1 open** (GTR001 — doc-tighten,
zero corpus incidence), and **2 where the adversarial refutation itself overreached**
and there is no bug to fix (GTR006, GTR009 — both confirmed against Galaxy source /
the rule's contract; doc-clarify only).

| Rule | Codemod / fmt | Claim | Verdict | Basis |
|---|---|---|---|---|
| GTR001 | fmt indent | runtime | **REFUTED** | ws-only `.tail` in mixed content → rendered-text drift (zero corpus incidence) |
| GTR002 | param attr order | runtime | hold | attribute reorder, no value/text touched |
| GTR003 | blank-line trivia | runtime | hold | writes only None/ws tails of `<tool>` children |
| GTR004 | empty-element | runtime | **REFUTED → FIXED** | cleared ws-only `.text` on content-bearing leaves (`<configfile>`/`<command>`/`<token>`) (PR #113) |
| GTR005 | tool attr order | runtime | hold | attribute reorder only |
| GTR006 | FixTypos | validity-restore | **REFUTED*** | case-folds `format="RestructuredText"`→`restructuredtext` (*nuance: validity-restoration contract, see below) |
| GTR007 | UpdateProfile | structural | hold | sets newest-valid `profile=`; runtime surfaced separately |
| GTR008 | Upgrade19_01 | structural | hold | XSD-valid + idempotent; runtime surfaced separately |
| GTR009 | Upgrade24_0 | structural | **REFUTED\*** | hoist reads `.text` — but so does Galaxy (`eval(filter.text.strip())`), so the dropped post-comment tail is dead at runtime → over-claim, behaviour-preserving |
| GTR010 | Upgrade24_1 | structural | hold | format/ftype pattern-facet normalize; idempotent |
| GTR011 | Upgrade25_1 | structural | hold | 25.1→26.0 validity + idempotence |
| GTR013 | ReorderToolChildren | runtime | hold | `<tool>` is `xs:all` (order-free); reorder is validity-safe |
| GTR014 | from_work_dir strip | runtime (conditional) | hold | matches Galaxy's own `<21.09` `strip()`; crossing-gated |
| GTR015 | format=input→source | runtime | hold | single-top-data-input; format_source-guarded |
| GTR016 | FixInterpreter | runtime | **REFUTED → FIXED** | mixed-content `<command>`: `set_text` kept comment/`<expand>` children → flag duplicated (PR #114) |
| GTR017 | NormalizeBooleanValues | runtime | hold | `True`→`true` only where the lenient model already accepts it; validity-restore |
| GTR018.1 | WrapCommandCdata | runtime | **REFUTED → FIXED** | body with `\r` → CDATA can't carry `&#13;` → CR lost, non-idempotent (PR #112) |
| GTR019.1 | WrapHelpCdata | runtime | **REFUTED → FIXED** | same `\r`-through-CDATA bug (shared `cdata_wrappable` predicate) (PR #112) |
| GTR020.1 | SingleQuoteCommandVars | runtime | **REFUTED → FIXED** | quoted multi-flag `select` values (PR #110) |

\* GTR006 and GTR009 are cases where the adversarial refutation **overreached** — on
re-verification against Galaxy source / the rule's contract there is no behaviour
change. See their entries.

## Holds — the proof basis

Each was attacked by ≥2 executed skeptics; none produced a verified break, and the
refutation pass's own evidence affirmed the invariant. Concise basis:

- **GTR002 / GTR005** (codemods `reorder_param_attributes.py` /
  `reorder_tool_attributes.py`, sharing the canonical order in `_attribute_ordering.py`):
  reorder a `<param>`'s / the `<tool>`'s attributes into a canonical order. Attribute
  order is semantically irrelevant in XML; no element text/tail is touched. Idempotent
  and validity-preserving.
- **GTR003** (blank-line trivia; fmt D4): emits `SetTail` only for the non-last
  children of a `<tool>` root and `safe_set_tail` writes only when the current tail is
  None/whitespace — never touches significant text.
- **GTR013 ReorderToolChildren** (codemod §17): `<tool>` is `xs:all` in every vendored
  XSD (order-free), so reordering its children cannot change validity or runtime.
- **GTR017 NormalizeBooleanValues** (codemod §26): rewrites `True`/`False` →
  `true`/`false` only on a tool the lenient model already accepts; a validity-restoring
  case fix with no runtime change.
- **GTR007 / GTR008 / GTR010 / GTR011** (`UpdateProfile` + `upgrade_vN`; codemod §22):
  **structural-only** claim — XSD-valid at the reached profile + idempotent; runtime
  surfaced via `behavior_preserving`. Verified on that (correct) boundary.
- **GTR014** (from_work_dir strip; codemod §24): byte-identical to Galaxy's own
  `output.from_work_dir.strip()` for `profile < 21.09`, applied only under the crossing
  gate `< 21.09 <= reached`.
- **GTR015** (format=input→format_source; codemod §24): runtime-equivalent on the
  single-top-level-data-input subset, format_source-guarded, profile unchanged.

## Refuted — counterexamples, root cause, remediation

Each counterexample below was **re-verified by execution on 2026-06-06**.

### GTR020.1 — `select`/`drill_down` multi-flag values — FIXED (PR #110)

Quoting `$param` for a `<param type="select">` whose option packed several flags into
one value (`<option value="-b -h">`) fused argv words into one token. **Shipped**:
narrowed to the provable option-value subset + faithful-lexer var extraction. See
codemod `docs/decisions.md` §32; regression fixtures in
`test_single_quote_command_vars.py` / `test_command_vars.py`.

### GTR018.1 / GTR019.1 — carriage return lost through CDATA wrap (one shared bug) — FIXED (PR #112)

Both derive from the tier-1 `cdata_wrappable` predicate (`cdata.py`), which accepted a
body containing a carriage return (`\r` / U+000D). A `\r` has no in-CDATA form
(`<![CDATA[…]]>` cannot carry `&#13;`), so on the next parse XML line-end
normalization rewrites it to `\n`. Re-verified: `<command>echo a&#13;echo b</command>`
→ wrapped body re-parses as `echo a\necho b` (CR→LF); `<help>` with `&#13;` was
**non-idempotent** (two `apply`s differ). Both are runtime/value changes.
**Fixed:** `cdata_wrappable` now returns False when the body contains `\r`, so both
`.1` rules leave a CR-bearing body unwrapped (the CR survives as `&#13;`); the `.2`
advisory residuals (`needs_cdata and not cdata_wrappable`) flag it instead, in
lockstep. One predicate, both findings. Codemod §29; tier-1 `cdata.py`.

### GTR009 — Upgrade24_0 and the collection-filter comment tail — refutation OVERREACHED (no bug)

The refutation observed that hoisting identical per-child `<filter>`s reads
`Element.text`, which in lxml stops at the first child node: for
`<filter>cond_one <!-- x --> and cond_two</filter>`, `.text` is `'cond_one '` and
` and cond_two` (on the comment's tail) is dropped — concluding the hoist loses part
of the condition. **But Galaxy evaluates an output filter the same way**:
`galaxy/tools/execution_helpers.py:filter_output` runs
`eval(filter.text.strip(), …)` — `.text`, not `itertext`. So Galaxy *itself* never
evaluates ` and cond_two`; the tool already behaves as `cond_one` before the codemod,
and the hoisted `<filter>cond_one </filter>` evaluates to `cond_one` after — **runtime
behaviour is identical**. The comparison (`{.text.strip()}`) likewise matches Galaxy's
own notion of "same condition", so it can't false-equate two filters Galaxy would run
differently. The dropped tail is dead text (and a `<!-- -->` comment), not behaviour.
**No code change.** Confirmed via Galaxy source; pinned by
`test_hoists_mixed_content_filter_by_galaxy_evaluated_text` (asserts the hoist
preserves the Galaxy-evaluated condition). Codemod §14.

### GTR016 — FixInterpreter duplicates a flag in a mixed-content `<command>` — FIXED (PR #114)

`detect()` builds the new body from `"".join(command.itertext())` (absorbing child
tails) but `cursor.set_text` overwrites only `.text` and left the children + their
tails in place. Re-verified: `<command interpreter="python">script.py <!-- note -->
--x</command>` → effective command `script.py  --x` → `python '…/script.py'  --x --x`
(the `--x` flag passed twice). **Fixed:** FixInterpreter now **skips** a mixed-content
`<command>` (`cursor.child_node_count() != 0`), matching the other command-rewriting
codemods (`SingleQuoteCommandVars`/`WrapCommandCdata`). Clearing the children was
rejected — a child `<expand>` carries macro command content that must not be dropped;
skipping is the safe choice (the §23 warning still covers it). Corpus: ~9 mixed-content
interpreter commands no longer rewritten. Codemod §27, `fix_interpreter.py`.

### GTR004 — clears whitespace-only `.text` on content-bearing leaves — FIXED (PR #113)

The empty-element rule's safe-to-clear predicate protected an empty-string CDATA body
but not a whitespace-only one. Re-verified: `<configfile><![CDATA[   ]]></configfile>`
→ `<configfile/>` (`.text` None). Galaxy reads `<configfile>.text` verbatim as the
template content (`fill_template`, `strip=False`), so the generated config file's
content silently dropped from `"   "` to empty. **Fixed (scope-narrow):** the rule now
skips a small denylist of content-bearing tags — `<command>`, `<configfile>`,
`<token>` (elements whose `.text` is runtime/expansion payload). `<help>` is *not* in
the set (whitespace-only help renders empty either way, so the opinionated formatter
still tidies it to `<help/>` — the guard stays surgical). Corpus delta is a handful of
degenerate whitespace-only command/token bodies now conservatively preserved. fmt
`rule_empty_element.py`; regression fixture in `test_rule_empty_element.py`.

### GTR001 — whitespace-tail rewrite in mixed content (zero corpus incidence) — DOCUMENTED (PR #116)

The indentation rule's `strip()` oracle rewrites a whitespace-only `.tail` without
checking whether the parent holds **mixed content** (text interspersed with
elements), where inter-element whitespace **is** significant. Re-verified:
`<help>See <b>this</b> <i>tool</i> docs.</help>` → the word-separating space before
`<i>` becomes `\n        `, so rendered help changes from `See this tool docs.` to
`See this\n        tool docs.`. **Zero corpus incidence** (no real tool triggers it).
**Remediation (doc-tighten + optional guard):** the claim/decisions should drop the
universal "any XML document" framing and the inaccurate "XML 1.0 = inter-element
whitespace non-significant" justification (true for element content, not mixed
content); add `xml:space="preserve"` + mixed content to the rule's known limitations.
An optional guard (skip ws-tail rewrite inside a mixed-content parent) is low-priority
given zero incidence. fmt `docs/decisions.md` D3.

### GTR006 — FixTypos case-folds a `format`/`type` enum value (contract nuance) — DOCUMENTED (PR #116)

FixTypos rewrites `help format="RestructuredText"` → `restructuredtext` (re-verified).
The verdict called this a runtime change (Galaxy compares `format` case-sensitively:
the input value routes client-side, the rewrite routes server-side RST).
**Nuance — the refutation overreaches:** FixTypos *only* fires on a tool that is
already **XSD-invalid** (the input value fails validation at every profile); its
contract is **validity restoration**, not runtime preservation of invalid tools.
Restoring an invalid tool to its canonical value inherently changes how the
(previously broken) tool behaves. **Remediation (doc-clarify, not a bug):** state
GTR006/FixTypos' contract correctly in the ledger and codemod §11 — it preserves
behaviour of *valid* tools and restores validity of invalid ones; it does not promise
runtime-equivalence for the invalid inputs it repairs. No scope change needed unless a
case-only near-miss can occur on an otherwise-valid tool (none found). Codemod §11.

## Remediation backlog (follow-up PRs)

Refuted findings are **not** silently fixed here; this ledger + the xfail regression
fixtures are the record. Suggested order (cleanest/highest-value first):

1. ~~**GTR018.1 + GTR019.1 — CDATA `\r` guard**~~ — **DONE (PR #112)**: one shared `cdata_wrappable` fix resolved both findings.
2. ~~**GTR004 — content-bearing `.text` scope-narrow**~~ — **DONE (PR #113)**: empty-element rule skips `<command>`/`<configfile>`/`<token>`.
3. ~~**GTR016 — FixInterpreter mixed-content**~~ — **DONE (PR #114)**: skips mixed-content `<command>`.
4. ~~**GTR009 — Upgrade24_0 mixed-content filter**~~ — **RESOLVED (PR #115)**: refutation overreached; Galaxy evaluates `filter.text.strip()`, so the hoist is behaviour-preserving (no code change).
5. ~~**GTR001 — doc-tighten**~~ — **DONE (PR #116)**: mixed-content limitation documented at `serializer.safe_set_tail` + fmt §D3. The optional guard stays deliberately deferred (zero corpus incidence); the `xfail` fixture remains as the known-limitation marker.
6. ~~**GTR006 — doc-clarify the validity-restoration contract**~~ — **DONE (PR #116)**: codemod §11 now states the contract (preserve valid tools, repair invalid ones); no code change.

**Backlog complete.** All 8 refuted findings are resolved: 5 fixed (GTR004, GTR016,
GTR018.1, GTR019.1, GTR020.1), 2 refutation-overreach documented (GTR006, GTR009), and
GTR001's mixed-content limitation documented (the only residual; a guard is deferred on
zero incidence).

Each *open* refuted finding has a `xfail(strict=True)` regression fixture in its owning
test module, tagged with its GTR code, so a future scope-widening that re-introduces
the break trips immediately and a fix flips the test to a positive assertion. When a
fix lands, its fixture is flipped to a positive assertion (as GTR018.1/GTR019.1 were).
