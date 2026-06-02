# Locating & rewriting variables in Cheetah-processed sections — feasibility

> **Status: open research (v1).** Expected to change a lot before any implementation
> decision. This note is deliberately honest about what is hard and what is unknown;
> the "Open questions" section is the live worklist.
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
`fill_template` (`lib/galaxy/util/template.py`) with the **default Cheetah compiler**
and `python_template_version="3"` — i.e. **no dialect restriction**; the whole
language is in play.

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
- Hazards for naive rewriting: `##` comments **19.7%**, escaped `\$` **18.3%**.
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
| **B. Cheetah compile → AST of generated Python** | High (Cheetah's own parser) | **Cheetah is NOT installed** in our venv (verified) — would add the CT3 dependency; relies on the private `_CHEETAH_generatedModuleCode`; maps placeholders to `VFFSL(...)` calls but mapping edits *back* to source offsets is non-trivial; fails on templates Galaxy only compiles via the py2 futurize retry | Promising for **analysis/validation**; awkward for **source rewriting** |
| **C. Custom Cheetah grammar** (lark/pyparsing) | Can be high for the subset we model | Large effort; perpetual drift from real Cheetah; re-implements a moving target | Only if B proves unworkable and the payoff is large |
| **D. Hybrid, scoped** — regex/structured detection that **bails out** on any hazard (directive, dotted target, `#raw`, comment, configfile coupling, `<expand>`) and only acts on a provably-simple shape | High *on the subset it accepts* | Low coverage by design; must `log()`/report what it skipped | **Most realistic first step** for any rewrite |

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
  miniature. Approach D, guarded hard, fits.
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

## Open questions (live worklist)

- [ ] **Size the truly-safe subset.** Extend the measure (or add a sibling) to count
  tools whose command is directive-free **and** has no dotted/indexed/call shapes, no
  `##`/`\$`, no inline configfile, and no `<expand>` — the population a hazard-bailing
  rewriter (Approach D) could touch. This is the real "addressable" number.
- [ ] **Prototype Approach B offline.** Is Cheetah/CT3 installable as a *dev-only*
  tool (not a runtime dep of any tier)? Measure parse-success rate across the corpus
  and whether the generated-AST placeholder set can be mapped back to source spans.
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
loudly on every construct it can't prove safe), and only consider Approach B once a
measurement shows the safe subset is too small and CT3-as-dev-dep parses the corpus
reliably. Treat use cases (3)/(4) as research, not roadmap.
