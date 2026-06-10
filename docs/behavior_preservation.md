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

19 fixable rules audited in the 2026-06-04 adversarial pass — **11 hold, 8 refuted**.
Of the refuted: **6 fixed** (GTR018.1, GTR019.1, GTR020.1, GTR004, GTR016, and — since
2026-06-10 — GTR001), and **2 where the adversarial refutation
itself overreached** and there is no bug to fix (GTR006, GTR009 — both confirmed against
Galaxy source / the rule's contract; doc-clarify only). One rule shipped later carries its
claim by construction rather than via that pass: **GTR089.1 RepairHelpRst** (2026-06-09)
holds on the strength of its tier-1 render-equivalence gate (below).

| Rule | Codemod / fmt | Claim | Verdict | Basis |
|---|---|---|---|---|
| GTR001 | fmt indent | runtime | **REFUTED → FIXED** | ws-only `.tail` in mixed content → rendered-text drift; guarded by the mixed-content + payload-subtree skip (fmt §D19) |
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
| GTR089.1 | RepairHelpRst | runtime (rendered help) | hold | repair kept only when the docutils doctree is unchanged modulo the removed error (strong gate); macro/markdown help skipped |

\* GTR006 and GTR009 are cases where the adversarial refutation **overreached** — on
re-verification against Galaxy source / the rule's contract there is no behaviour
change. See their entries.

## Proofs — construction-grade, source-cited (tightened 2026-06-10)

Each pre-2026-06-10 entry was attacked by ≥2 executed skeptics; none produced a
verified break. The 2026-06-10 **proofs-tightening pass** then upgraded every
basis from "argued" to **source-cited**: each entry below names the exact Galaxy
code (clone `.local/galaxy-src`, `dev` @ `c6e0ee3` unless a release branch is
named) or spec clause the invariant rests on. The standing bar: *a fixable
rule's preservation claim must hold by construction for novel tools — corpus
incidence sizes impact, never soundness.*

- **GTR002 / GTR005** (attribute reorder, shared `_attribute_ordering.py`): two
  legs. (i) XML 1.0 §3.1: *"the order of attribute specifications … is not
  significant."* (ii) Galaxy consumes attributes exclusively by name —
  `elem.get("…")` throughout `lib/galaxy/tool_util/parser/xml.py` — and its
  parser (like every conformant one) exposes no attribute order. No text/tail
  is touched. Idempotent, validity-preserving.
- **GTR003** (blank-line trivia; fmt D4): `<tool>` has an **element-only content
  model** (`xs:all` in all 28 vendored XSDs), where XML 1.0 declares
  inter-element whitespace non-significant; the rule emits `SetTail` only for
  `<tool>`'s non-last children and `safe_set_tail` writes only a None/ws tail.
  (Contrast GTR001's fmt §D19 guard: *mixed* content is exactly where that
  spec clause stops holding.)
- **GTR013 ReorderToolChildren** (codemod §17): same two legs at the element
  level — `xs:all` (order-free by schema) and Galaxy's child access is
  tag-keyed (`root.find("command")`, `findall("…")` — never positional) across
  `tool_util/parser/xml.py`.
- **GTR017 NormalizeBooleanValues** (codemod §26): every Galaxy boolean read
  goes through `galaxy.util.string_as_bool` —
  `str(string).lower() in ("true", "yes", "on", "1")`
  (`lib/galaxy/util/__init__.py:1104-1108`) — so `True` ≡ `true` at runtime;
  the rewrite restores XSD validity with a provable runtime no-op.
- **GTR018.1 / GTR019.1** (CDATA wraps; codemod §29): a CDATA section and the
  equivalently-escaped character data parse to the **identical** `.text` (XML
  1.0 §2.7) — Galaxy reads tool XML through its parser, never the raw bytes —
  and the `cdata_wrappable` predicate excludes the one representable-but-lossy
  case (`\r`, which CDATA cannot carry; the #112 fix).
- **GTR007 / GTR008 / GTR011** (`UpdateProfile` + `upgrade_vN`; codemod §22):
  **structural-only** claim — XSD-valid at the reached profile + idempotent;
  runtime behaviour changes are the `upgrade` contract's point and are surfaced
  via `behavior_preserving` + the §23 warnings. Verified on that boundary.
- **GTR010 Upgrade24_1** (format/ftype normalization): the strongest cite of
  the pass — the codemod **is Galaxy's own parse applied statically**:
  `parse_extensions` returns
  `[extension.strip().lower() for extension in self.get("format", "data").split(",")]`
  (`tool_util/parser/xml.py:1453`), the registry lowercases datatype extensions
  at load (`datatypes/registry.py:1028-1042` `get_extension`), and a test
  `ftype` that misses the registry never matched (repair class).
- **GTR093 Upgrade21_09** (collection_type + stdio + has_size; codemod §41-§42):
  each slice carries its own runtime cite — the comma-token strip mirrors
  `DataCollectionToolParameter.__init__` (`parameters/basic.py:2717`); the
  stdio repairs mirror the parser's alias-fallback and log-and-skip paths
  (`parser/xml.py:1248-1280`, `:1318-1324`); the Bytes canonicalizer mirrors
  `galaxy.util.bytesize.parse_bytesize`.
- **GTR014** (from_work_dir strip; codemod §24): byte-identical to Galaxy's own
  pre-21.09 compatibility shim — `parser/xml.py:596-603`: for
  `profile < 21.09`, `output.from_work_dir = output.from_work_dir.strip()`
  (*"Prior to quoting, trailing spaces had no effect … ensures that old tools
  continue to work"*) — applied only under the crossing gate
  `baseline < 21.09 <= reached`.
- **GTR015** (format=input→format_source; codemod §24 + §40): the sole data
  input — top-level or qualified-nested — is runtime-addressable because Galaxy
  keys `input_datasets` by prefixed name (`tools/actions/__init__.py:222`) and
  `determine_output_format` looks `format_source` up in exactly that map
  (`:1283-1286`); the absent-at-runtime corner resolves to `"data"` on both
  sides (`random_input_ext` walk vs the parsed `get("format", "data")` default,
  `parser/xml.py:1453`); qualified references are upstream-tested
  (`test/functional/tools/format_source_in_conditional.xml`). Repeat nesting
  (instance-indexed prefix) and multi-input (Galaxy's own `TODO`-marked
  random-ext nondeterminism) are construction-unprovable and stay out.
- **GTR016 FixInterpreter** (codemod §27 + §39): the interpreter attribute is
  interpolated **verbatim in every composition form Galaxy ever shipped**
  (prepend, `release_16.04` `evaluation.py:478-484` … `release_20.01`;
  token-splice + `shlex.quote`, `release_20.09` … `dev:781-787`), the forms
  coinciding exactly on the literal-leading-token shape the codemod requires;
  the mixed-content skip and positional splice close the audited break classes.
- **GTR020.1 SingleQuoteCommandVars** (codemod §30/§32 + tier-1 §16): the
  value-domain proof — quote only references whose every possible runtime value
  is a single shell word (param-type domains; select/drill_down narrowed to
  provable single-token option sets after the §32 audit); the bashlex-oracle
  widening was **reverted as unsound** (Cheetah renders values as literal text)
  and the full record lives in
  `docs/upgrade_research/cheetah_bashlex_boundary_oracle.md`.
- **GTR035 TrimAttributeWhitespace** (codemod §33): two attribute-specific
  proofs. `<requirement version>`: Galaxy composes the conda spec **verbatim**
  — `package_specifier = f"{self.package}={self.version}"`
  (`tool_util/deps/conda_util.py:461-465`), passed as a CLI argument — so a
  whitespace-bearing version never resolved; trimming only repairs. `<tool
  name>`: a **display-contract** claim (the GTR089.1 style): `parse_name` reads
  the attribute raw (`parser/xml.py:220-221`) but the name is a display/metadata
  string — not an addressing key (tools are addressed by `id`) — and HTML
  rendering collapses edge whitespace. `id`/`version` are excluded precisely
  because they ARE raw identity keys.
- **GTR036 ReplaceOutputElement** (codemod §34): Galaxy routes an
  `<output type="data">` through the same `_parse` as `<data>`
  (`tool_util/parser/xml.py:548-563`) — a parse-level no-op rename.
- **GTR037 DropRedundantParamName** (codemod §35): Galaxy derives the name as
  `argument.lstrip("-").replace("-", "_")` (`tool_util/parser/util.py:44`); the
  codemod drops `name` only when byte-equal to that derivation, mirrored in
  `_derived_name`.
- **GTR092 ConvertHelpToMarkdown** (codemod §38; tier-1 xml §24): proof **by
  execution** — kept only when the markdown-it rendering (exactly Galaxy's
  client path) is semantically equal to the docutils rendering (exactly
  Galaxy's server path); negative-controlled.
- **GTR004 EmptyElementShorthand** (fmt D5 + D18): the positive leg — a
  whitespace-only `.text` on an element-only-content leaf is layout (the same
  XML 1.0 clause as GTR003), and a whitespace-only `<help>` renders empty
  either way; the verbatim-payload leg is the D18 denylist
  (`command`/`configfile`/`token`, Galaxy reads them `strip=False`).

### Proposals from the tightening pass (not applied — maintainer decision)

- **GTR004's `_CONTENT_BEARING_TAGS` could be derived from the XSD** instead of
  hand-maintained: an element whose schema type carries text content is exactly
  the set whose ws-only body may be payload. The hand list is correct today
  (and the GTR001 §D19 `_PAYLOAD_TAGS` mirrors it +`help`); a derivation would
  make both robust to future schema additions. Medium effort; the explicit-list
  convention (N2) argues for the status quo — flagging, not recommending.
- **GTR035's `<tool name>` leg is a display-contract claim**, now stated as
  such (the GTR089.1 style): the trimmed name is byte-visible in API JSON but
  render-identical in HTML. If a stricter bar is ever wanted, the name trim
  could move to the advisory residual; the conda-version leg is unconditional
  either way.
- **GTR089.1 RepairHelpRst** (codemod §37; tier-1 `rst` §23): proof by
  execution, like GTR092 — repairs invalid `<help>`
  reStructuredText, but the claim is on the *rendered* help (Galaxy renders RST to HTML
  server-side). The tier-1 gate keeps a repaired round only when it strictly reduces
  serious docutils messages, adds no new error class, **and** leaves the doctree
  structurally identical modulo the removed system messages — i.e. the edit changed
  nothing but the error. Edits are vetted individually before the batch is re-gated; an
  ungated case returns `None` (no-op). The gate correctly **vetoes** the trailing-transition
  fix (a `----` renders as an `<hr>`). Macro-bearing (`@TOKEN@`) and `format="markdown"`
  help are skipped; CDATA wrapping is preserved.

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

### GTR001 — whitespace-tail rewrite in mixed content — FIXED (was: documented, PR #116)

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

**Fix (2026-06-10, fmt §D19):** the zero-incidence deferral was reversed on the
maintainer's standing principle — soundness arguments must hold *by construction*
for novel tools, not by corpus absence. The indent rule now skips the whole subtree
of (a) any element holding **mixed content** and (b) any **payload element with
children** (`<command>`/`<configfile>`/`<token>` — the GTR004 verbatim set — plus
RST-sensitive `<help>`). (b) closes a hazard the original verdict missed: a
whitespace-only tail *between* `<expand>` children of `<command>` is not mixed
content by the textbook definition, yet rewriting its space to newline+indent turns
a shell word separator into a command separator. The strict `xfail` fixture flipped
to a positive test plus three new guards (`test_rule_indent.py`).

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
5. ~~**GTR001 — doc-tighten**~~ — **DONE (PR #116)**: mixed-content limitation documented at `serializer.safe_set_tail` + fmt §D3. ~~The optional guard stays deliberately deferred (zero corpus incidence); the `xfail` fixture remains as the known-limitation marker.~~ **Superseded 2026-06-10: the guard SHIPPED (fmt §D19)** — the corpus-incidence deferral conflicted with the novel-tool soundness principle; the `xfail` flipped positive.
6. ~~**GTR006 — doc-clarify the validity-restoration contract**~~ — **DONE (PR #116)**: codemod §11 now states the contract (preserve valid tools, repair invalid ones); no code change.

**Backlog complete.** All 8 refuted findings are resolved: 6 fixed (GTR001, GTR004,
GTR016, GTR018.1, GTR019.1, GTR020.1) and 2 refutation-overreach documented (GTR006,
GTR009). No residual: GTR001's guard — initially deferred on zero corpus incidence —
shipped 2026-06-10 (fmt §D19) under the novel-tool soundness principle.

Each *open* refuted finding has a `xfail(strict=True)` regression fixture in its owning
test module, tagged with its GTR code, so a future scope-widening that re-introduces
the break trips immediately and a fix flips the test to a positive assertion. When a
fix lands, its fixture is flipped to a positive assertion (as GTR018.1/GTR019.1 were).
