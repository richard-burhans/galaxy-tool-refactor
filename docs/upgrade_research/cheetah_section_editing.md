# Editing code inside Cheetah sections — feasibility spike + roadmap (M5)

> **Status: spike COMPLETE (2026-06-04); M5.1 lexer SHIPPED (2026-06-05,
> `galaxy_tool_xml.cheetah_cdm`); M5.2 read-only consumers SHIPPED (#95, #96).** This is
> the data-backed verdict + sequenced roadmap for the long-deferred **M5** capability:
> mechanically refactoring the code *inside* a tool's `<command>` / inline `<configfile>`
> (the Cheetah-templated sections). Companion: `cheetah_bashlex_boundary_oracle.md` (the
> bashlex boundary oracle + the GTR020.1 quoting story + the no-split-widening revert).

## The goal & the three fix families the spike scoped

Edit Cheetah-section *code* safely. Three families (user-selected, hardest last):
1. **Param refactors** — find-references, dead-param detection, rename a param across
   command + configfiles.
2. **Shell-structure fixes** — quoting, `&&` vs lone `&`, redirections, `set -e`, output
   handling — fixes about the *realized shell* command.
3. **Cheetah/Galaxy modernization** — rewrite deprecated idioms / version-specific
   constructs (e.g. the 23.0 optional-text `None`-vs-`""` migration).

All three want one substrate — a **Cheetah Document Model (CDM)**: a faithful, editable
span/scope model of the raw section that re-serialises byte-for-byte except where edited.

## Building blocks & their spike verdicts

### ① Faithful cheetah-lex (CT3 `Parser` subclass) — **CONFIRMED, 99.6% corpus; SHIPPED as `cheetah_cdm` (M5.1)**
A `Cheetah.Parser.Parser` subclass overriding `eatPlaceholder`/`eatDirective`/`eatComment`
records `(kind, start, end, text)` for every placeholder / directive / comment, inheriting
correct `##` / `#raw` / escaped `\$` / embedded-string handling from the real parser
(`DirectiveAnalyzer` is CT3's own proof of the pattern). Spike `.local/spike_cdm.py` +
`.local/spike_cdm_sweep.py`:

| metric | value |
|---|---|
| pure-text command bodies scanned | 9,256 |
| **CT3 parse CLEAN (spans harvested)** | **9,220 (99.6%)** |
| BAIL | 36 (0.4%) — 26 `ParseError` (py2-isms), 10 `ModuleNotFoundError` (`#import` of an uninstalled module) |
| clean tools with directives | 5,346 |
| clean tools with `#set`/`#for`/`#def` locals (rename-shadowing hazard) | 2,089 (≈23%) |
| placeholders harvested | 94,819 |

Verdict: the faithful locator covers essentially the whole corpus and faithfully
distinguishes editable placeholders from comments/raw/escapes — a clear green light, and a
strict upgrade over the regex `command_text` lexer. ~77% of tools have **no** local
bindings, so rename is trivially shadow-safe there; the ~23% need a scope model, and the
directive-head spans give exactly the text to extract bindings from.

### ② Sentinel-provenance render + back-map — **REAL BUT PARTIAL (~⅓ whole-tool clean)**
Replace each placeholder span with a unique locatable sentinel, render via Galaxy's
`fill_template` (permissive sentinel namespace), bashlex the rendered shell, map each shell
word back to its source span. Spike `.local/spike_provenance.py` (2,000-tool sample):

| outcome | share |
|---|---|
| render + bashlex OK | 1,575 / 2,000 (78.8%) |
| render_fail (CT3 raised) | 172 (8.6%) |
| bashlex_fail (`[[ ]]` / `$(( ))` / odd shell) | 253 (12.6%) |
| per-placeholder back-map | 63.6% standalone word + 10% glued (mappable); ~26% vanish |
| **whole-tool clean (all sentinels back-map)** | ~33% (491 directive-free + 167 directive-ful) |

Verdict: the back-map mechanism works, but the actionable subset is **bounded** — shell-
structure fixes via render must be scoped to back-mappable occurrences and **bail loudly**
elsewhere.

**Deeper breakdown (`.local/spike_provenance2.py`, per-tool timeout-guarded) — the ceiling
is mostly *recoverable*:**

| vanished placeholder, by enclosing directive | count | recoverable? |
|---|---|---|
| `#if` (untaken branch) | 3,274 (95%) | **yes — all-branch forcing** |
| `#for` (loop transform) | 140 (4%) | hard |
| top-level (Python transform / `#set` binding) | 34 (1%) | hard |

So the vanished ~26% is **95% conditional opacity**, not fundamental transforms — recoverable
by re-rendering with each `#if` condition toggled. The genuinely-hard residual is ~174
placeholders (≈1.3% of 13,102). Failure kinds: render_fail (172) = `TypeError` 92 (the
permissive sentinel choking on numeric/operator ops — shrinkable with a richer sentinel),
`NotFound` 69, other 11; bashlex_fail (253) = mostly `other` (234, uncategorised), `backtick`
9, `$(( ))` 7, `[[ ]]` 3. **A render HANG** (40-min CT3 wedge) occurred once on the first,
un-guarded run and did **not** recur under a 5s/3s per-tool timeout — so the render path
**must carry a per-tool timeout** (documented robustness requirement), but deterministic
template hangs appear rare. py2.7 tools bail (no futurize replication).

Net: with `#if` branch-forcing + a richer sentinel, the back-mappable fraction climbs well
past the raw 74% toward the ~90s, leaving a ~1–2% hard transform residual — so M5.4 is more
attractive than the whole-tool ⅓ first suggested, at the cost of branch-forcing combinatorics
and the ~12% bashlex-parse gap.

### ③ Differential render-verify & ④ constraint-aware value-domain
Unchanged from `cheetah_bashlex_boundary_oracle.md`: ③ certifies any edit behaviour-
preserving by render-diff (universal safety net); ④ reads `<validator>`/`<option>`/
sanitizer constraints to prove more params space-free (cheap static widening of quoting).

## Two soundness invariants (both already drew blood)
- **Cheetah renders to literal text** — reason about the *realized shell*, not the template
  (this is what made the no-split widening unsound; see the companion doc §KU-5).
- **Conditional opacity** — a fix under `#if` is sound only with all-branch forcing or a
  bail; it accounts for most of ②'s vanished 26%.

## Roadmap (data-backed; early value, risk back-loaded)

- **M5.1 — CDM faithful lexer (tier 1). SHIPPED (2026-06-05).** The `Parser`-subclass
  span model is `galaxy_tool_xml.cheetah_cdm` (`cheetah_spans` → ordered, disjoint,
  round-trip-faithful `CheetahSpan`s), behind the optional `galaxy-tool-xml[cheetah-cdm]`
  extra (CT3, MIT, via `galaxy-util[template]`; same pattern as `[shell-oracle]`), with the
  regex `command_text` / `cheetah_refs` lexer as the dependency-free fallback (bail →
  `None`). The shipped lexer reproduces the spike: `cheetah-cdm-coverage` reports 99.6%
  parse-clean / 0.4% bail / 22.6%-of-clean scope-hazard. Tier-1 `docs/decisions.md` §19.
  The read-only consumers (M5.2) keep the regex until the first mutator consumes the
  faithful lexer.
- **M5.2 — read-only param consumers (highest coverage, lowest risk).** find-references /
  dead-param / used-params, built on M5.1 + a scope model (bindings from `#set`/`#for`/`#def`
  heads). Zero mutation risk; validates the locator + scope model corpus-wide.
  **SHIPPED (first slice, 2026-06-04):** the tier-1 reference model `galaxy_tool_xml.cheetah_refs`
  (conservative regex v1 — the faithful CT3 CDM is the precision drop-in reserved for the
  first mutator) + the `find-references` CLI/facade query (cli `docs/decisions.md` §D8,
  tier-1 §18). **dead-param deferred** — it must prove a *negative* and has real
  false-positive sources (refs inside imported macros / `<expand>`, `data_ref`/attribute
  cross-refs, intentionally-unused params) + a GTR-code/stat-regen; design its false-positive
  handling (macro-expanded-tree scan, attribute cross-refs) before shipping it.
- **M5.3 — rename codemod.** CDM + scope; rewrites placeholder spans + configfile +
  `<param name>`; bails on the ~23% shadowing cases.
- **M5.4 — shell-structure fixes via ② provenance-render.** Scoped to the render-clean +
  back-mappable subset (~⅓ whole-tool, more per-occurrence); behind the `[verify]` extra;
  bails loudly; each corpus-swept like every codemod. First targets: the deferred GTR032
  (`&&` vs lone `&`) and redirection fixes, where bashlex provenance is decisive.
- **M5.5 — modernization (research tail).** Semantic migrations, case-by-case, gated behind
  ③ render-verify; smallest sound subset.

## Risks
- CT3 coupling + py2.7 (bail; behind the extra) — same posture as the boundary oracle.
- Scope analysis is genuinely new surface (`#def`/closures/`#import`).
- ②'s ~⅓ whole-tool ceiling means shell-structure coverage is partial by construction;
  size each specific fix before building it (the `command-*` / `shell-oracle-quoting`
  measures are the template).

## Spike artifacts (gitignored `.local/`)
`spike_cdm.py` (the `Parser`-subclass harvester), `spike_cdm_sweep.py` (the 99.6% sweep),
`spike_provenance.py` (the back-map probe), `.local/cheetah3@3.4.0.post5`, `.local/.spike-venv`
(bashlex + CT3 + galaxy-util[template] + lxml).
