# Locating & rewriting variables in Cheetah-processed sections — feasibility

> **Status: open research (v1).** Expected to change a lot before any implementation
> decision. This note is deliberately honest about what is hard and what is unknown;
> the "Open questions" section is the live worklist.
>
> **Update (2026-06):** the easiest corner — use-case (1), known-literal injection —
> has since shipped as **GTR016 `FixInterpreter`**, and the CDATA-preservation contract
> in the section below is now implemented (`Cursor.set_text` / `Cursor.is_cdata_wrapped`).
> The harder use-cases (2)–(4) remain open research.
>
> Galaxy-source citations are from the local clone `.local/galaxy-src/` @ `c6e0ee3`.
> Corpus numbers come from the standing measure `cheetah-command-complexity`
> ([`../cheetah_command_stats.md`](../cheetah_command_stats.md)); regenerate with
> `uv run python -m scripts.measure cheetah-command-complexity`.

## The question

Can we **mechanically locate, and safely rewrite, variable references inside the
Cheetah-templated sections of a Galaxy tool** — reliably enough to power codemods?
"Variable" = a Cheetah placeholder like `$x`, `${x}`, `$x.y`, `$x['k']`, `$x(...)`,
and the names bound by `#set` / `#for` / `#def`.

Why we'd want it (concrete use cases, hardest last):

1. **Inject a known literal** at a known spot — e.g. the `16_04_fix_interpreter`
   rewrite prepends `$__tool_directory__/` to the script token
   ([`16_04_fix_interpreter.md`](16_04_fix_interpreter.md)).
2. **Detect** references to a named parameter (read-only) — e.g. "is `$foo` used in
   the command?" for dead-param or rename-impact analysis.
3. **Rename a parameter everywhere** it is referenced (command + configfiles), e.g.
   to normalise a misspelled or non-idiomatic input name.
4. **Rewrite expressions** (change `$x.y` semantics, migrate the `23.0` optional-text
   `None`-vs-`""` behaviour). Effectively arbitrary program transformation.

Feasibility drops steeply from (1) to (4). The honest headline: **(1) is tractable
with care; (2) is mostly tractable; (3) is hard; (4) is out of reach mechanically.**

## What Cheetah is, and which sections Galaxy runs through it

Cheetah is a full text-templating language (Python-backed): placeholders (`$x`,
`${...}`), directives (`#if`/`#for`/`#set`/`#def`/`#import`/`#echo`/`#raw`/`#slurp`/
`#while`/`#try`), `##` comments, `\$`/`$$` escaping, and **arbitrary embedded Python**
(`#set $x = re.sub(...)`, `${ ... }` expressions). Galaxy applies it via
`fill_template` (`lib/galaxy/util/template.py`), passing
`python_template_version=tool.python_template_version` (`evaluation.py:767-768`) —
the tool's explicit attribute (`xml.py:752-756`) or, when absent, `Version("3.5")`
for profile ≥ 19.05 else `Version("2.7")` (`tools/__init__.py:1353-1358`). The
literal `"3"` is only `fill_template`'s signature default (`template.py:115`), which
the evaluation path never hits. Either way there is **no dialect restriction** that
helps a rewriter — the whole language is in play. For a tool on a profile below
19.05 (a minority of the corpus), Cheetah compiles under **2.7** and succeeds only
via the futurize / lib2to3 (`fissix`) py2 retry (`template.py:138-152, 195-211`).

Sections Galaxy Cheetah-processes (so a complete tool would have to handle all of
them):

- `<command>` — `lib/galaxy/tools/evaluation.py:767`.
- inline `<configfile>` — `evaluation.py:951-952` (XML tools' default engine is
  `cheetah`; YAML configfiles use `ecmascript`).
- `<environment_variable>` templates — `evaluation.py` (the env-var build path).
- output `<data label=...>` / `<collection label=...>` —
  `lib/galaxy/tools/actions/__init__.py:1091`.
- InteractiveTool port config — `evaluation.py:695`.

**Not Cheetah** (an honest trap): `<version_command>` uses Python `string.Template`
`safe_substitute` (`evaluation.py:791-793`), so a `$var` there is *not* a Cheetah
reference. So "find `$things`" is section-dependent, not uniform.

The **search list** (what a `$name` can resolve to) is built at runtime in
`evaluation.py` (~625-656 + input/output wrapper population): tool inputs (wrapped
objects with dynamic attributes — `$input.ext`, `$input.metadata.x`), outputs,
`$__tool_directory__` and friends, `$on_string`, `$GALAXY_SLOTS`, user-defined
template macros, etc. Many names are **objects with attributes resolved
dynamically**, so `$x.y` cannot be type-checked statically without modelling Galaxy's
wrapper classes.

## Why this is fundamentally hard

1. **Only Cheetah parses Cheetah correctly.** There is no lightweight, faithful
   grammar; Cheetah compiles templates to Python. A regex cannot reliably tell a
   placeholder from a directive, a `##` comment, a `#raw`…`#end raw` block, an
   escaped `\$`, or a `$` inside an embedded Python string literal.
2. **Scope.** `#set`, `#for $x in …`, and `#def f($x)` bind **Cheetah-local** names
   that *shadow* tool parameters. A rename keyed on the bare name `$x` will corrupt a
   loop variable or local that merely shares the name. Doing this right needs real
   scope/binding analysis over the template.
3. **Conditional opacity.** `#if`/`#elif` mean a variable may be referenced only on
   some paths; "is `$foo` used?" needs control-flow awareness, not a substring check.
4. **Dotted/dynamic access.** `$input.element_identifier`, `$x.get($k)`, `$x[$i]`
   resolve against runtime wrapper objects; the same `$input` can be different types
   across tools. Rewrites that depend on what `.y` *means* need Galaxy's data model.
5. **Two more layers underneath.** Macro `@TOKEN@`s are substituted **textually
   before** Cheetah, and `<expand macro=…>` **injects XML (often command fragments
   and variable references) that aren't visible inline**. A faithful pass would have
   to expand macros first, then analyse the realised template — and then map edits
   *back* to the un-expanded source (or edit the macro file), which is its own hard
   problem.
6. **`<configfile>` is also Cheetah.** A parameter used in both `<command>` and a
   `<configfile>` must be rewritten in both, consistently.

## Corpus reality (from `cheetah_command_stats.md`, 9,358 unique tools)

- **99.6%** have a `<command>`; **99.7%** have some Cheetah text.
- **42.2%** of commands are **trivial** (no Cheetah directive) — bigger than folklore
  suggests, and the natural first target. **57.8%** contain at least one directive.
- Directives among Cheetah-text tools: `#if` **54.8%**, `#set` **16.4%**, `#for`
  **15.4%**, `#import` **7.6%**; the genuinely gnarly `#def` is only **0.2%** (21
  tools), `#raw` 0.2%, `#while`/`#try` ~0.
- Variable shapes: `$x.y` dotted **56.8%**, `${...}` braced **42.3%**, `$x(...)` call
  **12.5%**, `$x[...]` indexing **2.6%**, `$__x__` specials **29.0%**, `$UPPER`
  env-style **17.7%**.
- Hazards for naive rewriting: `##` comments **19.7%** (an *upper bound* — the `##`
  regex also matches shell `${var##*/}`, so the true Cheetah-comment share is lower
  and the hazard-free addressable subset is correspondingly a conservative
  under-estimate; see `../cheetah_command_stats.md`), escaped `\$` **18.3%**.
- Macro interplay: **48.4%** of tools use `<expand>`; **15.9%** of Cheetah text
  carries an `@TOKEN@`.

Read this honestly: even the 42% "trivial" (directive-free) commands are mostly *not*
plain — **56.8% use dotted attribute access**, which is fine to *detect* but risky to
*rewrite* without type knowledge. The directive-free subset is the sweet spot for
**reference detection** and **known-literal injection**, not for semantic edits.

## Approaches and their honest trade-offs

| Approach | Correctness | Cost / risk | Verdict |
|---|---|---|---|
| **A. Regex heuristic** (what we have: `scripts/measure.py:1721` `_CHEETAH_VAR`, `_count_unquoted_vars:1736`) | Approximate — false +/− on comments, `#raw`, `\$`, strings | Zero deps, fast | Fine for **metrics** and conservative **detection**; unsafe as the sole basis for rewriting |
| **B. Cheetah compile → AST of generated Python** (stdlib `ast` or **libCST**) | High (Cheetah's own parser) | **Cheetah is NOT installed** in our venv (verified), and **neither is libCST** (verified) — would add CT3 (+ optionally libCST) as a dependency; relies on the private `_CHEETAH_generatedModuleCode`; maps placeholders to `VFFSL(...)` calls but mapping edits *back* to source offsets is non-trivial; must replicate Galaxy's per-tool 2.7-vs-3.5 compile — the py2 futurize retry is the **normal** compile mode for sub-19.05 tools, not a rare failure | Promising for **analysis/validation**; awkward for **source rewriting** |
| **C. Custom Cheetah grammar** (lark/pyparsing) | Can be high for the subset we model | Large effort; perpetual drift from real Cheetah; re-implements a moving target | Only if B proves unworkable and the payoff is large |
| **D. Hybrid, scoped** — regex/structured detection that **bails out** on any hazard (directive, dotted target, `#raw`, comment, configfile coupling, `<expand>`) and only acts on a provably-simple shape | High *on the subset it accepts* | Low coverage by design; must `log()`/report what it skipped | **Most realistic first step** for any rewrite |
| **E. Dynamic sentinel oracle** — render the template with Cheetah, binding names to locatable sentinel values, and read the *output* (see the section below) | High *as an oracle* (uses real Cheetah) | Needs CT3 and must replicate Galaxy's per-tool 2.7-vs-3.5 selection + futurize retry (or it diverges for sub-19.05 tools); needs a permissive search list; only the *taken* `#if`/`#for` branch renders; embedded Python can eat the sentinel; tells you the value's place in *output*, not its *source span* | Strong for **verification / detection**, not for **locating** edits |

Prior art confirms the difficulty: **Galaxy itself never statically extracts
variables** — it evaluates templates at runtime with a real context; its command
linter (`lib/galaxy/tool_util/linters/command.py`) checks attributes only. planemo's
relevant checks are regex-based. Our own `_count_unquoted_vars` is explicitly labelled
"heuristic, not a Cheetah/shell parser."

## Feasibility by use case (the honest matrix)

- **(1) Inject a known literal at a known spot — FEASIBLE, scoped.** This is what the
  `16_04_fix_interpreter` rewrite needs (prepend `$__tool_directory__/` to the script
  token). It works precisely when the target token is identifiable from structure
  (e.g. the literal first token of a directive-free command). The interpreter note's
  "bucket A vs B/C/D" split *is* the leading-`#if`/non-literal-first-token problem in
  miniature. Approach D, guarded hard, fits. **(Now shipped: GTR016 `FixInterpreter`
  does exactly this — Approach-D-style structural locating, a positional splice, and a
  CDATA-preserving `set_text`.)**
- **(2) Detect references to a named param — MOSTLY FEASIBLE (read-only).** Regex
  detection with conservative handling of `##`/`#raw`/`\$` gives a good
  over-approximation; safe because a *report* that errs toward "maybe used" is
  acceptable. Cannot distinguish a shadowing local without scope analysis.
- **(3) Rename a param everywhere — HARD.** Must handle shadowing (`#set`/`#for`/
  `#def`), dotted access (`$old.attr`), both `<command>` and every `<configfile>`,
  and references injected via `<expand>`/macros. Safe only on a small, hazard-free
  subset; otherwise needs Approach B/C plus back-mapping.
- **(4) Rewrite expressions / semantics — NOT FEASIBLE mechanically.** Arbitrary
  embedded Python; equivalent to program transformation.

## Two ideas evaluated (2026-06-02): libCST, and a dynamic sentinel oracle

### Can we leverage libCST?

**Not for the Cheetah source itself — only for its compiled Python, and even then it
adds little.** libCST is a *Python* concrete-syntax-tree library; a Cheetah command
block (`#if`, `$x`, `${...}`) is **not valid Python**, so libCST cannot parse it. The
only thing libCST could parse is the Python that Cheetah *compiles the template into*
(`Template.compile(...)._CHEETAH_generatedModuleCode`) — i.e. it's a variant of
Approach B's analysis side, swapping stdlib `ast` for libCST. There:

- Galaxy's generated code looks up variables as `VFFSL(SL, "name", …)` (the NameMapper;
  see `.local/galaxy-src` `lib/galaxy/util/template.py:177-180`, which itself rewrites
  those calls textually). Walking the module for `VFFSL` calls *does* enumerate the
  referenced names — but stdlib `ast` already does that; libCST's lossless,
  round-trippable CST buys nothing because **we'd never serialise the generated Python
  back into Cheetah source**. The hard part — mapping a finding back to a *source span
  in the XML* — is unsolved by either.
- libCST is **not installed** here (verified), so it would be a new dependency.
- (Aside: the planned tier-2 *matcher language* is described as "LibCST-matcher-shaped"
  — but that's for matching the **XML/structural** tree, not Cheetah. Different problem;
  no reuse.)

**Verdict:** libCST is not a path to locating/rewriting Cheetah variables in source. At
most it's an ergonomic alternative to `ast` for analysing the generated Python, which
`ast` already covers. Don't pursue it for this.

### Render-with-a-sentinel-and-verify oracle

The idea: bind the suspected variable to a unique, locatable value (e.g.
`" GTX_a1b2 "`), render the template through Cheetah, and check **where/whether
the sentinel lands in the output** — using Cheetah itself (the only correct parser) as
an oracle. This is genuinely useful, but as a **verifier/detector**, not a locator:

- **Best use — differential verification of a candidate edit.** Render the *original*
  and a *proposed rewrite* under a battery of sentinel contexts; if every output matches
  modulo the intended change, the edit is behaviour-preserving — *without* having to
  perfectly parse or scope-analyse the template. This pairs with cheap structural/regex
  *locating* (Approach A/D): locate loosely, then **prove safe** by rendering. For the
  interpreter codemod specifically, it directly validates the "first token = script"
  guess by reproducing Galaxy's runtime `split()[0]` on the rendered line.
- **Also — reference detection.** Bind each parameter to a distinct sentinel, render,
  and see which sentinels appear → which params are actually used.

Honest obstacles (all real):
1. **Needs CT3 installed** (same cost/availability as Approach B; not installed today).
2. **The search list must never raise `NotFound`.** Galaxy binds inputs as *wrapper
   objects* with dynamic attributes/methods (`$input.ext`, `$input.metadata.dbkey`,
   `$x.get(...)`), and Cheetah's NameMapper raises on any unresolved access
   (`template.py:153-156`). So we'd need a *permissive* magic namespace whose
   `__getattr__`/`__getitem__`/`__call__`/`__str__` all return locatable sentinels —
   and which is simultaneously truthy/iterable/comparable so `#if`/`#for` don't crash.
3. **Only the taken branch renders.** `#if`/`#elif` mean a reference in the *other*
   branch never appears — the conditional-opacity problem, now dynamic. Honest detection
   needs to force all branches (re-render with the condition toggled), which is
   combinatorial in the number of conditionals. (For differential *verification* this
   is a soundness trap, not merely a detection gap: a candidate edit inside an
   unexercised `#if`/`#elif` branch renders identically for original and rewrite, so
   verification passes **vacuously** — a false behaviour-preserving certificate. This
   is precisely why E-as-verifier is sound only on the directive-free subset Approach D
   accepts: D refuses any `#if`, so the D+E pipeline never hands E a branch.)
4. **Embedded Python can eat the sentinel.** `#import re` / `#set $x = re.sub(p, r, $y)`
   may transform the marker beyond recognition → false negatives for *detection*
   (differential verification still holds, since the transform is identical on both
   sides).
5. **It reads output, not source.** The oracle confirms *that/where a value flows*, not
   *which characters in the XML to edit*. It complements locating; it doesn't replace it.

**Verdict:** worth prototyping — but framed as a **safety oracle** layered on top of a
cheap locator (locate with A/D, *verify* with E), and as a *detection* aid with the
branch/transform caveats above. It does not, by itself, solve the locate-and-rewrite
problem, and it carries the same CT3 dependency as Approach B.

## CDATA preservation across Cheetah-text tags (cross-tier contract; 2026-06-02)

Any codemod that rewrites the *content* text of a Cheetah-processed element must not
silently destroy a `<![CDATA[ … ]]>` wrapper. What we verified (Galaxy source @
`c6e0ee3`; lxml probed directly):

**The tags whose element *text* this applies to** (attributes like output `label`
don't carry CDATA):

| Tag | Cheetah-templated? | CDATA-conventional? |
|---|---|---|
| `<command>` | yes (`evaluation.py:767`) | yes (GTR018.2) |
| inline `<configfile>` | yes (`evaluation.py:952`) | yes |
| `<environment_variable>` | yes unless `inject=…` (`evaluation.py:851`) | sometimes |
| `<help>` | **no** (RST/markdown, not templated) | yes (GTR019.2) |
| `<token>` | **no** (expanded textually *before* Cheetah) | sometimes |
| `<yield>` | n/a | no (always empty) |

**It's a quality/idempotence concern, not a correctness bug.** Galaxy reads the
lxml-*decoded* command text (`lib/galaxy/tool_util/parser/xml.py:261-263`:
`return … command_el.text`), so `<![CDATA[a && b]]>` and the entity-escaped
`a &amp;&amp; b` yield the **identical** string `a && b` to Cheetah/Galaxy. So losing
CDATA does **not** change what the tool runs — it just produces an ugly,
GTR018.2-violating, non-idempotent diff (and re-escapes shell `&&`/`<`).

**lxml facts (probed):** parsing with `strip_cdata=False` (tier-1
`binding.py:128`) preserves CDATA; assigning a plain `str` to `.text` **destroys the
wrapper and entity-escapes** `&&`→`&amp;&amp;`, `<`→`&lt;`; assigning `etree.CDATA(s)`
preserves it; and **lxml exposes no live flag for "was this CDATA"** — `.text` is a
plain `str` either way. The only way to tell is to re-serialise
(`b"<![CDATA[" in etree.tostring(el)` — reliable for these text-only elements, which
have no element children).

**fmt already handles its half correctly.** Tier-3 is the only serialiser, and every
text edit routes through `serializer.safe_set_text`, which **writes only when the
existing text is absent or pure whitespace** (`galaxy-tool-fmt/.../serializer.py:23-25`;
`edits.py` dispatch). So no formatting rule (indent / blank-line / empty-element) ever
touches CDATA *content*, and `test_regressions.py`'s byte-idempotence sweep guards it.

**The codemod tier is where the gap *was* — now closed.** `Cursor.set_text`
(`cursor.py:125`) takes a keyword-only `cdata: bool = False` (→ `etree.CDATA` when set),
and `Cursor.is_cdata_wrapped()` (`cursor.py:98`) re-serialises to detect the original
framing. Callers: the `@PROFILE@` `<token>` rewrite (`update_profile.py:99`, plain
bare-version text), `FixInterpreter` (GTR016, `fix_interpreter.py:57`, `cdata=True`),
and the shared CDATA-wrap helper behind `WrapCommandCdata`/`WrapHelpCdata`
(GTR018/GTR019, `_cdata.py:35,44`). Rewriting a `<command>`/`<configfile>` body — once
genuinely new surface — is now exercised by GTR016.

**Contract for content-rewriting codemods (shipped):** *preserve the original framing*.
The detect phase records the framing via `Cursor.is_cdata_wrapped()` (re-serialises and
tests for a leading `<![CDATA[`); the mutate thunk calls
`Cursor.set_text(value, cdata=…)`, writing `etree.CDATA(value)` when the body was CDATA
and a plain `str` otherwise (which lxml re-escapes to match the element's original
escaped framing). This is faithful **both** ways — CDATA stays CDATA, escaped stays
escaped, both decode to the same string — so it never regresses the diff.
`16_04_fix_interpreter` (GTR016) was the first consumer (`fix_interpreter.py:57`,
`cdata=True`); `WrapCommandCdata`/`WrapHelpCdata` (GTR018/GTR019, codemod
`docs/decisions.md` §29) followed, with the shared logic in `codemods/_cdata.py`.

## Open questions (live worklist)

- [x] **CDATA across Cheetah-text tags** — mapped + verified 2026-06-02 (section above):
  command/configfile/env-var (templated) + help/token (CDATA-conventional); losing CDATA
  is cosmetic not a behaviour bug (Galaxy reads decoded text); fmt is safe via
  `safe_set_text`; content-rewriting codemods must preserve framing via `etree.CDATA`.
- [ ] **Size the truly-safe subset.** Extend the measure (or add a sibling) to count
  tools whose command is directive-free **and** has no dotted/indexed/call shapes, no
  `##`/`\$`, no inline configfile, and no `<expand>` — the population a hazard-bailing
  rewriter (Approach D) could touch. This is the real "addressable" number.
- [ ] **Prototype Approach B + the sentinel oracle (E) offline.** Is Cheetah/CT3
  installable as a *dev-only* tool (not a runtime dep of any tier)? Then: (B) measure
  parse-success across the corpus and whether the generated-AST `VFFSL` set maps back
  to source spans; (E) build a permissive sentinel search list and measure how often a
  render succeeds without `NotFound`, and prototype *differential verification* of a
  trivial edit. Both share the CT3 dependency.
- [x] **libCST?** Evaluated 2026-06-02 — **no**: libCST parses Python, not Cheetah;
  it would only apply to Cheetah's *generated* Python (where stdlib `ast` already
  suffices) and doesn't solve source back-mapping. Not installed either. (See section
  above.)
- [ ] **Macro/`<expand>` strategy.** Decide expand-first-then-analyse vs
  inline-only-and-skip-expanders. Back-mapping edits to macro files is a sub-project.
- [ ] **Per-use-case scoping rules**, written as explicit bail-out predicates, with a
  corpus sweep that reports coverage and (crucially) what was skipped.
- [ ] **Joint command+configfile** handling contract (rename must touch both).
- [ ] Where would this live? A tier-2 capability (the codemod `Cursor` can already
  read/replace `<command>` text via `cursor.text`/`set_text`), but variable analysis
  is new surface — decide if it's a shared helper or per-codemod.

## Tentative position (subject to change)

No implementation yet. If/when we build anything, start at use case (1)/(2) on the
**hazard-free subset**, using Approach **D** (structured detection that bails out
loudly on every construct it can't prove safe). The most promising *upgrade* to that is
**D + E**: locate cheaply (D), then **verify each candidate edit by differential
sentinel rendering** (E) — letting Cheetah itself certify behaviour-preservation rather
than trusting a static parse. Approach **B** (and libCST) are analysis-only and gated on
a CT3 dev-dependency proving itself; **C** is a last resort. Treat use cases (3)/(4) as
research, not roadmap.

## Phase 0 spike — feasibility verdicts (2026-06-04)

A read-only spike resolved the four estimate-gating known-unknowns behind the
**cheetah-lex + bashlex boundary-oracle** design. **The full sub-project record — design,
correctness proof, architecture, phased build plan, and the reproducible spike probes — is
[`cheetah_bashlex_boundary_oracle.md`](cheetah_bashlex_boundary_oracle.md)** (session plan:
`~/.claude/plans/how-difficult-would-it-noble-trinket.md`). Evidence is from local
clones, not recollection: `idank/bashlex` (`.local/bashlex`), `CheetahTemplate3/cheetah3`
@ tag `3.4.0.post5` (`.local/cheetah3` — the `ct3==3.4.0.post5` Galaxy pins,
`pinned-requirements.txt:63`, `CT3>=3.3.3` in `pyproject.toml:32`), and the user's
`package_output.py` (kegalign tool, `richard-burhans/galaxytools`).

- **KU-1 — bashlex boundary oracle: FEASIBLE / easy.** `bashlex.parse(s, strictmode=False)`
  returns AST nodes each carrying `.pos = (start, end)` char offsets (`bashlex/ast.py`).
  `nodevisitor.visitredirect(self, n, n_input, n_type, output, heredoc)` exposes the
  source fd as `n_input`, the operator as `n_type`, and the target as `output.word`
  (a word node) **or an int** for fd-dups like `2>&1`. `bashlex.split` gives argv;
  `$(...)`/pipes/lists/background appear as their own node kinds (`commandsubstitution`,
  `pipeline`, `list`, operator `&`). **Decision (user, 2026-06-04): track the FULL fd
  topology, not just 0/1/2.** The seed `package_output.py` `sys.exit`s on any fd outside
  0–2; bashlex hands us arbitrary fds for free — a `fdvisitor` capturing
  `(src_fd, op, target)` correctly read `3> custom.fd`, `4>&2`, `2>&1`, `>&-` (close),
  and order-sensitive `2>&1 1>file` in ~15 lines (spike `.local/spike_fd_topology.py`).
  Tracking all fds strictly strengthens the equivalence relation (an edit that perturbs
  any redirection is caught).
  - **bashlex documentation notes (README + `setup.py` + LICENSE, verified 2026-06-04):**
    - **LICENSE = GPL v3+** (`LICENSE` is GPLv3; `setup.py: license='GPLv3+'` + OSI
      classifier; README "same as GNU bash, GNU GPL v3+"). **This is a load-bearing
      decision input:** the design makes bashlex a *runtime* dep of **tier 1**
      (`galaxy-tool-xml`, the foundational parsing package), and GPLv3 is strong copyleft.
      Resolve before the Phase-1 build — options: (a) isolate `boundary_signature()` +
      bashlex behind an **optional extra** (same treatment as CT3's `[verify]`) so the
      base tier stays unencumbered; (b) put it in its own dedicated package; (c) accept
      GPL for the relevant package. **Owner decision required.**
    - **Documented parse limitations:** no support for arithmetic `$((..))`; "the more
      complicated parameter expansions such as `${parameter#word}` are taken literally and
      do not produce child nodes." The latter intersects the `##`-vs-`${var##*/}` hazard
      noted in `cheetah_command_stats.md` — for the boundary oracle this is acceptable
      (the *word partition* is still computed; such a word is just opaque), but the
      cheetah-lex/locator must treat `$((..))` and `${var#…}` as bail-out hazards.
    - The README/`examples/commandsubstitution-remover.py` confirm the canonical
      `nodevisitor` → collect `n.pos` → reverse → splice idiom (identical to the user's
      `package_output.py`), and that `bashlex.split` understands `$(...)`/`<(...)` where
      `shlex` does not.
- **KU-2 — CT3 `Parser`-subclass span harvesting: FEASIBLE (the gating unknown is a
  clean YES).** `SourceReader.pos()` tracks an absolute char offset
  (`Cheetah/SourceReader.py`); the parse loop is matcher/eater based
  (`Parser.py` `_HighLevelParser.parse`), so a subclass can record
  `(kind, start, end)` by reading `self.pos()` around overridden `eatPlaceholder` /
  `eatDirective`. `##` comments, `#raw…#end raw`, and escaped `\$`/`\#` are consumed
  *inside* the parse loop (regex matchers use an `escCharLookBehind`), so a span-harvester
  inherits correct skipping for free — exactly what a regex lexer gets wrong. **CT3
  already ships the proof of the pattern: `DirectiveAnalyzer.py` is
  `class Analyzer(Parser.Parser)` overriding `eatDirective` to tally directives without
  a full compile.** ⇒ Layer A1 (faithful lex via Parser-subclass) is viable; the only
  cost is the CT3 version-pin coupling. A2 (extend `command_text.py`) remains the
  dependency-free fallback.
- **KU-3 — render fidelity & cost: feasible, bounded.** `galaxy.util.template.fill_template(
  template_text, context=…, python_template_version=…)` is the render entry point
  (`util/template.py:108`). `NotFound` is raised by the NameMapper on any unresolved
  name/attr ⇒ a permissive sentinel namespace must implement `__getattr__`/`__getitem__`/
  `__call__`/`__str__` **and** be truthy/iterable/comparable so `#if`/`#for` don't crash.
  Sub-19.05 / `python_template_version="2.7"` tools take a `lib2to3`/`fissix` futurize
  retry path — **default decision: bail (leave advisory) on py2.7 tools** rather than
  replicate Galaxy's py2 dance. The **vacuous-certificate trap** (an edit inside an
  unexercised `#if` branch renders identically on both sides ⇒ false certificate, lines
  216–222) means the locator must bail on any `#if` reaching the edit, or force all
  branches.
- **KU-4 — is the Phase-1 win real? YES.** A minimal `boundary_signature` over a
  pseudo-rendered line (sentinel swapped in for the live `$var`) flags the sentinel as
  **structurally unsafe** in 4/6 probe cases today's value-domain-only GTR020.1 would
  quote: glued `--prefix=PRE$var`, glued `$var.bam`, redirection target `> $var`, and
  fd redirect `2> $var` (spike `.local/spike_ku4_probe.py`). So composing the existing
  `command_vars.provably_quotable` value-domain test **with** a bashlex structural check
  (sentinel must occupy exactly one complete `WordNode`, not be a redirection target,
  not be glued into a larger word) is a genuine soundness upgrade over today's fixer —
  achievable in **Phase 1 with zero Cheetah dependency**.

**Net verdict:** all three layers are feasible; the design's effort estimate holds
(C easy, A1 viable / A2 fallback, B bounded). Recommended next step is the Phase-1
build: a tier-1 read-only `boundary_signature()` (bashlex, full fd topology) + the
structural-check soundness upgrade to GTR020.1 + the reserved `EditCertifier=None`
seam — shipping value with no CT3 in the runtime path.
