# Cheetah-lex + bashlex boundary oracle — sub-project record

> **Status: design + Phase-0 feasibility spike COMPLETE (2026-06-04); no shipped code yet.**
> This is the consolidated, durable record of the sub-project: the idea, the
> correctness proof, the three-layer architecture, the phased build plan, and the
> spike's source-grounded feasibility verdicts (with the reproducible probe code).
> It is the in-repo home for material that previously lived only in the session plan
> `~/.claude/plans/how-difficult-would-it-noble-trinket.md`. Companion: the broader
> feasibility survey [`cheetah_variable_rewriting.md`](cheetah_variable_rewriting.md)
> (this oracle is its sanctioned "D + E" pipeline made concrete).

## 1. The idea

Mechanically edit the **Cheetah source** of a Galaxy tool's `<command>` (e.g.
single-quote a `$var`) and *guarantee* the edit is behavior-preserving — the deep
version of the long-deferred **M5** Cheetah/shell lexer. Today the project reasons
about Cheetah only with regex heuristics (`galaxy_tool_xml/command_text.py` quote-state
lexer + `command_vars.py` root-name classifier); GTR020.1 (`single_quote_command_vars.py`)
auto-quotes only the *value-domain-provable* subset `{safe, attr_safe, builtin_path}`
and leaves the rest advisory (GTR020.2).

```
Cheetah <command> template          ← the ONLY thing a codemod edits
        │  render (strategy TBD)
        ▼
final shell string                  ← never edited; analysis artifact only
        │  bashlex  (read-only AST visitor)
        ▼
argument boundaries + redirections + output files   ← ground truth = "what the shell sees"
```

**Safety predicate.** A Cheetah-source edit is **certified behavior-preserving iff the
realized command's boundary signature is unchanged** — same word/argument partition,
same full fd→target redirection map, same output-file set. The shell string is an
*oracle that defines "safe,"* not an output.

## 2. Correctness proof (sketch)

The research doc `cheetah_variable_rewriting.md` already contains the soundness argument
and its boundary (its "D + E" pipeline, lines 189–233, 323–332). This sub-project makes
E concrete and improves it.

**Equivalence relation.** Galaxy's behavior for a command is: render Cheetah → final
string → the shell's `argv` partition + redirection/fd topology (`evaluation.py`, then
the shell). Define `behavior ≡ boundary_signature(realized string)` = (word/argument
partition) ∧ (full fd→target redirection map) ∧ (output-file set). bashlex computes this
*faithfully* because it is bash's own grammar — the improvement over the doc's "outputs
match modulo the intended change": the boundary signature is the *exact* semantic
invariant a quoting edit must preserve (quoting deliberately changes bytes while
preserving the argv partition, so byte-compare is wrong and signature-compare is right).

**Theorem.** A Cheetah-source edit is behavior-preserving **iff** for every value `v` in
the parameter's value-domain `V`, `boundary_signature(render(orig, v)) ==
boundary_signature(render(edited, v))`.

**Discharging the ∀ soundly** (you cannot enumerate `V`; a single sentinel is *not* a
proof):
- *Value-domain argument (static).* If `V ⊆ {strings with no IFS whitespace and no
  single-quote}`, single-quoting cannot change the partition for ALL `v`. That set is
  exactly today's `command_vars.provably_quotable` subset. The oracle then only verifies
  the *structural premise* for one sentinel (the placeholder really is a standalone word,
  not a redirection target, not inside `$(...)`).
- *Adversarial probing (dynamic).* Render under boundary-relevant extremes — empty,
  embedded-space, embedded-quote, multi-value — and require signature-invariance across
  the quoted/unquoted pair for all probed classes (airtight only if the probe classes
  provably exhaust bash word-splitting).
- **The sound method is the conjunction:** the value-domain argument supplies the ∀; the
  bashlex oracle verifies the structural premise.

**Two load-bearing soundness conditions (both must hold):**
1. **Conditional opacity → the vacuous-certificate trap** (research doc lines 216–222):
   an edit inside an *unexercised* `#if`/`#elif` branch renders identically for orig and
   edited, so verification passes **vacuously** — a *false* certificate. ⇒ the oracle is
   sound **only on the directive-free subset** the locator accepts, **or** with exhaustive
   all-branch forcing. Concretely: the locator must bail on any `#if` reaching the edit.
2. **Render fidelity** — render must never raise `NotFound` (permissive sentinel
   namespace), must mirror Galaxy's per-tool py2.7-vs-3.5 compile, and must expand
   macros/`@TOKEN@`/`<expand>` first.

## 3. Three layers and their difficulty

- **Layer C — bashlex boundary oracle (EASIEST).** Read-only
  `boundary_signature(command_string)` → argv word spans + **full fd→target redirection
  map** + output set, via a `bashlex.ast.nodevisitor` subclass. Generalizes the user's
  `package_output.py` `nodevisitor`/`n.pos` pattern. **Verdict: easy — confirmed (§5).**
- **Layer A — cheetah-lex (MEDIUM).** Locate live `$placeholder`/`#directive` spans in the
  raw Cheetah, correctly skipping `##`/`#raw`/`\$`/embedded strings.
  - **A1** subclass CT3's `Parser` to harvest faithful spans (faithful for free; cost =
    CT3 version-pin coupling).
  - **A2** extend `command_text.py` (dependency-free; perpetual drift risk).
  - **Verdict: A1 viable (clean YES), A2 fallback — confirmed (§5).**
- **Layer B — render Cheetah → final string (HARDEST; soundness lives here).** B1 real CT3
  render / B2 pseudo-render (sentinel substitution, no Cheetah) / B3 adversarial
  multi-shape render. **Verdict: feasible but bounded (provable subset + advisory
  residual) — confirmed (§5).**

## 4. Phased build plan

Offline-first / online-second. Phase 1 is a strict sub-assembly of the faithful path —
it builds the permanent half, ships value, and de-risks CT3.

| Piece | Phase 1 (cheap, no CT3) | Phase 2 (faithful) | Fate |
|---|---|---|---|
| **C — bashlex oracle** | generalize `nodevisitor`/`n.pos` into `boundary_signature()` (argv + **full fd topology**) | identical | **built once, permanent** |
| **value-domain ∀** | reuse `command_vars.provably_quotable` | + adversarial value-shapes | **permanent, extended** |
| **A — cheetah-lex** | A2: extend `command_text.py`; bail on `#if`/`#raw`/dotted/`<expand>` | A1: subclass CT3 `Parser` | A2 stays no-CT3 fallback; A1 added |
| **B — render** | B2: pseudo-render | B1/B3: CT3 render + adversarial shapes + branch-forcing | B2 demoted to pre-filter |

**Phase 1 (ships value, no CT3):** (1) tier-1 read-only `boundary_signature()` (bashlex,
full fd topology) **behind the optional `galaxy-tool-xml[shell-oracle]` extra** (§7 GPL
decision), imported lazily via `find_spec`; + synthetic-fixture tests; (2) A2 cheetah-lex
+ B2 pseudo-render, bailing on every hazard; (3) **strengthen GTR020.1**: compose
value-domain `provably_quotable` **with** the new structural check (sentinel occupies
exactly one complete `WordNode`, not a redirection target, not glued into `prefix$var`,
not inside `$(...)`) as an **opt-in, strictly-narrowing** gate — when the extra is absent
the fixer falls back to today's value-domain-only behavior (default output unchanged,
license-clean); when present it additionally *rejects* structurally-unsafe quotes; (4)
reserve the optional `EditCertifier` protocol, shipping with `None` (= static).

**Phase 2 (coverage expansion; fills the seam):** CT3-backed `EditCertifier` behind a
`[verify]` optional extra + `--certify=static|render` toggle (render mode only **rejects**
static candidates — strictly narrowing, always sound); A1 cheetah-lex; B1/B3 render
mirroring Galaxy's `util/template.py` (per-tool py2.7/3.5 + futurize) with a permissive
sentinel namespace and all-branch forcing (respecting the vacuous-certificate trap);
expand macros first; `scripts/measure.py` oracle sweep proving static-vs-render agreement
(soundness gate: rejects 0 existing GTR020.1 fixes; promotes N of the GTR020.2 residual).

**CT3 architecture (decided):** runtime-switchable, static default, dependency-injected so
CT3 is never a hard dep of any tier. py2.7-profile tools bail (advisory) by default.

## 5. Phase-0 spike — feasibility verdicts (2026-06-04)

Read-only spike grounded in local clones (clone-over-websearch standing pref), not
recollection: `idank/bashlex` (`.local/bashlex`), `CheetahTemplate3/cheetah3` @ tag
`3.4.0.post5` (`.local/cheetah3` — the `ct3==3.4.0.post5` Galaxy pins; `CT3>=3.3.3` in
`.local/galaxy-src/pyproject.toml:32`), the user's `package_output.py`
(`richard-burhans/galaxytools`, kegalign), and Galaxy's
`.local/galaxy-src/lib/galaxy/util/template.py`. Throwaway env `.local/.spike-venv`
(bashlex + CT3 3.4.0.post5). All `.local/` artifacts are gitignored.

### KU-1 — bashlex boundary oracle: FEASIBLE / easy
- `bashlex.parse(s, strictmode=False)` returns a list of AST nodes; every node carries
  `.pos = (start, end)` character offsets (`bashlex/ast.py`; README example shows
  `WordNode(pos=(0,4), word='true')`).
- `nodevisitor` dispatches on `n.kind`; `visitredirect(self, n, n_input, n_type, output,
  heredoc)` exposes the source fd (`n_input`), operator (`n_type`, e.g. `>`,`>>`,`<`,`>&`),
  and target — a **word node** (`output.word`) for file redirects, or an **int** for
  fd-dups (`2>&1` → `output=1`), or `'-'` for close (`>&-`).
- `$(...)`/`<(...)`, pipes, `&&`/`||`/`;`/`&`, and background appear as their own node
  kinds (`commandsubstitution`, `processsubstitution`, `pipeline`, `list`, `operator`).
  `bashlex.split` gives an argv that understands substitutions (unlike `shlex`).
- **User decision (2026-06-04): track the FULL fd topology, not just 0/1/2.** The seed
  `package_output.py` `sys.exit`s on any fd outside 0–2; bashlex hands us arbitrary fds
  for free. Proven: a `fdvisitor` capturing `(src_fd, op, target)` read `3> custom.fd`,
  `4>&2`, `2>&1`, `>&-`, and order-sensitive `2>&1 1>file` in ~15 lines. Tracking all fds
  strictly strengthens the equivalence relation.
- **Documentation notes (README/`setup.py`/`LICENSE`):**
  - **LICENSE = GPL v3+** ("same as GNU bash"; `setup.py: license='GPLv3+'` + OSI
    classifier). **DECIDED (§7): isolate behind an optional extra** (like CT3's `[verify]`)
    so tier 1 stays license-clean; the structural check becomes opt-in / strictly-narrowing.
  - Documented limitations: **no `$((..))` arithmetic**; complex parameter expansions like
    `${parameter#word}` are **taken literally / not decomposed** (acceptable for the word
    partition, but the locator must treat these as bail-out hazards).
  - `examples/commandsubstitution-remover.py` confirms the canonical idiom: visit → collect
    `n.pos` → `positions.reverse()` → splice (identical to `package_output.py`).

### KU-2 — CT3 `Parser`-subclass span harvesting: clean YES (the estimate-gating unknown)
- `SourceReader.pos()` tracks an absolute char offset (`Cheetah/SourceReader.py`); also
  `setPos`, `getRowCol`, `peek`, `readTo`.
- The parse loop (`Parser.py` `_HighLevelParser.parse`) is **matcher/eater** based:
  `matchCommentStartToken`/`matchDirective`/`matchVariablePlaceholderStart` (no consume)
  then `eatComment`/`eatDirective`/`eatPlaceholder` (consume + advance `pos()`). A subclass
  records `(kind, start, end)` by reading `self.pos()` around an overridden `eat*`.
- `##` comments, `#raw…#end raw`, and escaped `\$`/`\#` are consumed **inside** the parse
  loop (matchers use an `escCharLookBehind`; `eatRaw` reads opaquely to `#end raw`) — a
  span-harvester inherits correct skipping for free, exactly what a regex lexer gets wrong.
- **CT3 already ships the proof of the pattern: `DirectiveAnalyzer.py` is
  `class Analyzer(Parser.Parser)` overriding `eatDirective`** to tally directives without
  a full compile. `parserClass` is an overridable class attribute on the Compiler.
- ⇒ A1 (faithful lex via Parser-subclass) is viable; only cost is CT3 version-pin coupling.
  A2 (extend `command_text.py`) remains the dependency-free fallback.

### KU-3 — render fidelity & cost: feasible, bounded
- `galaxy.util.template.fill_template(template_text, context=None, retry=10,
  compiler_class=Compiler, …, python_template_version="3", **kwargs)` (`util/template.py:108`);
  builds `Template.compile(source=…, compilerClass=…)` then `klass(searchList=[context])`.
- `NotFound` (Cheetah NameMapper) raises on any unresolved name/attr ⇒ a **permissive
  sentinel namespace** must implement `__getattr__`/`__getitem__`/`__call__`/`__str__`
  **and** be truthy/iterable/comparable so `#if`/`#for` don't crash. Galaxy itself retries
  via `TreeDict` on `NotFound`.
- Sub-19.05 / `python_template_version="2.7"` tools take a `lib2to3`/`fissix` futurize
  retry path. **Default decision: bail (leave advisory) on py2.7 tools** rather than
  replicate Galaxy's py2 dance.
- The **vacuous-`#if` trap** (§2 condition 1) stands: never certify an unexercised branch.

### KU-4 — is the Phase-1 win real? — **CORRECTED (2026-06-04): the original "standalone word" predicate was WRONG**

The first spike used a "the var must be exactly one standalone `WordNode`, not glued, not
a redirect target" predicate and reported a 4/6 "win". **Re-examination overturned that
conclusion.** Single-quoting a **space-free** value (the value-domain-provable set) is
behaviour-preserving *even when the var is glued or a redirect target* — the shell
concatenates `pre'val'` → `preval` and `> 'val'` → file `val`. Verified by comparing the
realized argv of the original vs the single-quoted source (`.local/spike_recheck.py`,
bashlex):

| case (space-free value) | argv(orig) vs argv(quoted) | actually safe? | old predicate said |
|---|---|---|---|
| glued `--prefix=PRE$var` | identical | **SAFE** | ❌ "WIN" (veto) |
| glued `$var.bam` / `${var}.bam` | identical | **SAFE** | ❌ "WIN" (veto) |
| redirect-to-file `> $var` | identical | **SAFE** | ❌ "WIN" (veto) |
| fd-redirect-to-file `2> $var` | identical | **SAFE** | ❌ "WIN" (veto) |
| **fd-dup `2>&$var`** (numeric value) | `INT-dup` vs `WORD-file` (`spike_dup.py`) | **UNSAFE** | not tested |

So the naive predicate would have **removed valid fixes** (and broken
`test_quotes_only_the_provable_classes`, which quotes `$__tool_directory__` glued to
`/s.py`). The correct oracle use is **differential / context classification**, not "standalone
word". The only genuine structural hazard for a space-free value is the **fd-dup position**
`2>&$var` (numeric → dup flips to file), which is ~0 in the corpus.

### KU-5 — widening: where the oracle genuinely *adds* coverage (2026-06-04)

> **CORRECTED 2026-06-04 (PR-reverted) — the no-split widening below is UNSOUND.** The
> table's "assignment RHS → yes, any value (WIDEN)" row applies bash's no-split rule for a
> shell *expansion* (`VAR=$shellvar`). But Galaxy renders a Cheetah `$x` to its value as
> **literal text** *before* the shell runs, so the realized script is `VAR=foo bar`
> (literal), which **does** split (`['VAR=foo','bar']`) — quoting `VAR='$x'` therefore
> changes behaviour for a space-bearing value. The shipped Phase-1 widening was reverted:
> `quote_is_behavior_preserving` now treats `NO_SPLIT` like `SPLIT` (defer to the
> value-domain rule); only the `DUP_TARGET` narrowing remains. The classifier still reports
> `NO_SPLIT` (it is correct about *shell* structure) but the quoting policy must not act on
> it. Sound widening of Cheetah-rendered command values needs adversarial-value-shape render
> verification and is deferred research (the would-be Phase 2 render gate is what surfaced
> this). The original (wrong) reasoning is kept below for the record.

Because the common positions are already safe, the value of the oracle is **widening** —
promoting part of the GTR020.2 advisory residual to provably-fixable. The lever is bash's
**word-splitting rules**: an expansion in a **no-split context** is safe to single-quote
for *any* value, including a free-form `text` or a `multiple=` splat. Verified AST shapes
(`.local/spike_context.py`):

| context | example | bashlex AST | word-splits? | single-quote safe? |
|---|---|---|---|---|
| bare command word | `tool --in $x` | `WordNode` w/ `ParameterNode` | yes | only if value space-free (value-domain) |
| **assignment RHS** | `THREADS=$x` | **`AssignmentNode`** w/ `ParameterNode` | **no** | **yes, any value (WIDEN)** |
| redirect-file target | `tool > $x` | `RedirectNode` type `>`, word output | yes (ambiguous if spaces) | only if value space-free |
| fd-dup target | `tool 2>&$x` | `RedirectNode` type `>&` | n/a | **no (NARROW)** |
| `[[ … ]]` / `$(( … ))` | — | parse error | — | `UNKNOWN` → fall back |
| inside `$(…)` | `tool $(f $x)` | nested `CommandsubstitutionNode` | yes (inner shell) | value-domain |

Crucial soundness point: the var must be kept **as a bash expansion** (`$x`), *not*
value-substituted — bash word-splits *expansion results*, not literal text, so substituting
a value would mis-model splitting (`foo=$x` with `x="a b"` keeps one value, but the literal
`foo=a b` is assignment + command). The classifier therefore replaces each Cheetah var with a
simple `$SENTINEL` expansion and reads the *syntactic context* of the target from the AST.

**Phase-1 policy (shipped — `quote_is_behavior_preserving`, tier 1):** `NO_SPLIT` → quote
(any value); `DUP_TARGET` → never quote (conservative: vetoes even file-valued dups); `SPLIT`
/ `UNKNOWN` → defer to `provably_quotable` (today's behaviour). Without the `[shell-oracle]`
extra it *is* `provably_quotable` — the license-clean default. Known tiny gap (documented):
a Cheetah var used as a literal fd-number prefix `$intvar>file` is classified `SPLIT` and may
be quoted; this requires `$integer_param` immediately before `>` with no space — essentially
absent in real tools.

**Net verdict:** all three layers feasible; the oracle's real contribution is widening
(no-split contexts) plus a narrow, near-zero-incidence safety narrowing (fd-dup). The
common "glued / redirect-file" cases are already safe and must **not** be vetoed.

**Corpus sizing (`scripts.measure shell-oracle-quoting`, sha-deduped, after the revert):**
over 6,670 pure-text `<command>`s / 48,789 unquoted occurrences, the oracle now **widens 0**
and **narrows 0** — the 66/22 widening reported pre-revert was the unsound no-split case
above, and the fd-dup narrowing has no value-domain-safe occurrence corpus-wide. Net: the
shell oracle's *current* effect on GTR020.1 is nil beyond the value-domain rule (the
infrastructure + the sound dup veto remain for future render-verified widening). The honest
takeaway: sound widening of Cheetah command values is scarce and needs the deferred render
path; Phase 1's headline widening did not survive scrutiny.

## 6. Reproducible spike probes

The probes below are the proof artifacts (in `.local/`, gitignored; retained here verbatim
so the findings reproduce). The findings they back are now covered by the committed tests
`galaxy-tool-xml/tests/test_shell_oracle.py`. **`spike_ku4_probe.py` implements the
*discarded* "standalone word" predicate (KU-4 correction above) — kept only to show what was
ruled out.** The widening research lives in `spike_recheck.py` (glued/redirect quotes are
safe), `spike_dup.py` (fd-dup is the one real hazard), and `spike_context.py` (assignment-RHS
no-split AST shapes).

### `spike_recheck.py` — glued / redirect-file single-quotes are behaviour-preserving

```python
import bashlex
def argv(line):
    try:
        return list(bashlex.split(line))
    except Exception as e:
        return f"<parse error: {e}>"
# value is space-free; $var -> "VAL". orig `pre$var` -> shell `preVAL`;
# quoted source `pre'$var'` -> shell `pre'VAL'`.
cases = [
    ("glued prefix",   "tool --prefix=PREVAL",  "tool --prefix=PRE'VAL'"),
    ("glued suffix",   "tool VAL.bam",          "tool 'VAL'.bam"),
    ("redirect file",  "tool > VAL",            "tool > 'VAL'"),
    ("fd redirect 2>", "tool 2> VAL",           "tool 2> 'VAL'"),
    ("standalone arg", "tool --in VAL",         "tool --in 'VAL'"),
]
for desc, orig, quoted in cases:
    print(desc, argv(orig) == argv(quoted))   # all True -> all safe
```

### `spike_dup.py` — fd-dup is the one genuine structural hazard

```python
import bashlex, bashlex.ast
class V(bashlex.ast.nodevisitor):
    def __init__(self): self.redirs = []
    def visitredirect(self, n, n_input, n_type, output, heredoc):
        kind = "INT-dup" if isinstance(output, int) else "WORD-file:%r" % getattr(output, "word", output)
        self.redirs.append((n_input, n_type, kind))
def sig(line):
    v = V()
    for t in bashlex.parse(line, strictmode=False): v.visit(t)
    return v.redirs
print(sig("tool 2>&1"))    # [(2,'>&','INT-dup')]   -> duplicate fd
print(sig("tool 2>&'1'"))  # [(2,'>&',"WORD-file:'1'")] -> redirect to FILE '1' (behaviour change!)
```

### `spike_context.py` — assignment RHS is a no-split context (the widening lever)

```python
import bashlex
def dump(line):
    print(f"\n=== {line!r} ===")
    try:
        for t in bashlex.parse(line, strictmode=False): print(t.dump())
    except Exception as e:
        print(f"<parse error: {type(e).__name__}: {e}>")
for line in ["tool --in $GTXVAR", "THREADS=$GTXVAR", "[[ $GTXVAR == foo ]]",
             "tool 2>&$GTXVAR", "tool > $GTXVAR", "tool $(basename $GTXVAR)"]:
    dump(line)
# THREADS=$GTXVAR -> AssignmentNode (no split); --in $GTXVAR -> WordNode (split);
# 2>&$GTXVAR -> RedirectNode type='>&' (dup); [[ ]] -> ParsingError (UNKNOWN).
```

### `spike_ku4_probe.py` — the DISCARDED "standalone word" predicate (what was ruled out)

```python
import bashlex, bashlex.ast
SENTINEL = "GTXKU4SENTINEL"

class _wordspans(bashlex.ast.nodevisitor):
    def __init__(self):
        self.word_spans = []
        self.redirect_target_spans = []
    def visitword(self, n, word):
        self.word_spans.append(tuple(n.pos))
    def visitredirect(self, n, n_input, n_type, output, heredoc):
        if isinstance(output, bashlex.ast.node):
            self.redirect_target_spans.append(tuple(output.pos))

def boundary_words(line):
    v = _wordspans()
    for tree in bashlex.parse(line, strictmode=False):
        v.visit(tree)
    return v

def sentinel_is_standalone_word(line):
    occ = line.find(SENTINEL)
    if occ == -1:
        return False, "sentinel vanished (inside $()/expansion or directive)"
    occ_end = occ + len(SENTINEL)
    v = boundary_words(line)
    containing = [s for s in v.word_spans if s[0] <= occ and occ_end <= s[1]]
    if not containing:
        return False, "sentinel not inside any WordNode (operator/redirect/lost)"
    smallest = min(containing, key=lambda s: s[1] - s[0])
    if smallest in v.redirect_target_spans:
        return False, f"sentinel is a redirection target (span {smallest})"
    span_text = line[smallest[0]:smallest[1]]
    if span_text != SENTINEL:
        return False, f"sentinel glued into a larger word: {span_text!r}"
    return True, "standalone complete word"
```

### `spike_fd_topology.py` — full fd topology extraction (≈15 lines)

```python
import bashlex, bashlex.ast

class fdvisitor(bashlex.ast.nodevisitor):
    def __init__(self):
        self.redirs = []                       # (src_fd, op, target)
    def visitredirect(self, n, n_input, n_type, output, heredoc):
        if isinstance(output, bashlex.ast.node):
            target = output.word
        elif isinstance(output, int):
            target = f"&{output}"              # fd dup, e.g. 2>&1
        else:
            target = repr(output)             # '-' = close
        src = n_input
        if src is None:                        # default fd when omitted
            src = 0 if n_type in ("<", "<<", "<<-", "<<<", "<>") else 1
        self.redirs.append((src, n_type, target))

def fd_topology(line):
    v = fdvisitor()
    for t in bashlex.parse(line, strictmode=False):
        v.visit(t)
    return v.redirs
```

Observed output (verifies arbitrary fds, dups, closes, order-sensitivity):

```
tool > out.txt                      -> [(1, '>', 'out.txt')]
tool 2> err.log                     -> [(2, '>', 'err.log')]
tool > out 2>&1                     -> [(1, '>', 'out'), (2, '>&', '&1')]
tool 3> custom.fd                   -> [(3, '>', 'custom.fd')]
tool 4>&2                           -> [(4, '>&', '&2')]
tool < in.txt > out.txt 2>> err.txt -> [(0, '<', 'in.txt'), (1, '>', 'out.txt'), (2, '>>', 'err.txt')]
tool >&-                            -> [(1, '>&', "'-'")]
tool 2>&1 1>file                    -> [(2, '>&', '&1'), (1, '>', 'file')]
```

## 7. Open decisions & remaining unknowns

- **DECIDED (2026-06-04, owner) — bashlex (GPL v3+) is isolated behind an optional extra,
  the same treatment as CT3's `[verify]`.** The base **tier 1** (`galaxy-tool-xml`) stays
  unencumbered (permissive license, no GPL in its hard deps); bashlex enters only via an
  optional extra (proposed `galaxy-tool-xml[shell-oracle]` — exact name is a build-time
  detail) pulled in for the boundary oracle. `boundary_signature()` is imported lazily,
  guarded by `importlib.util.find_spec("bashlex")`.
  **Consequence:** the Phase-1 oracle changes GTR020.1 output **only when the
  `[shell-oracle]` extra is installed**; without it the fixer is exactly today's
  dependency-free `provably_quotable` (graceful degradation) — license-clean and reproducible.
  When present, the oracle's only sound effect on top of the value-domain rule is the
  **fd-dup narrowing** (0 corpus incidence). The no-split **widening** shipped briefly in
  Phase 1 was **reverted as unsound** (§KU-5 correction: Cheetah renders values as literal
  text, so `VAR=$x` splits) — so the oracle does not currently widen. A future render-verified
  widening (the deferred Phase 2/3 `--certify=render` path, behind a `[verify]` CT3 extra) is
  the only sound way to widen Cheetah command values; it surfaced this very bug while being
  designed.
- (Phase 2) How often does conditional opacity / py2-only Cheetah block B1/B3 on real
  tools? (a render-success measure over the corpus).
- (Phase 2) Does `--certify=render` earn its keep — how much GTR020.2 residual does the CT3
  oracle promote beyond the Phase-1 static fixer, and does it ever reject a static fix
  (must be zero)?

## 8. Key files

- **Reuse / generalize:** `galaxy-tool-xml/src/galaxy_tool_xml/command_text.py`,
  `command_vars.py`; `single_quote_command_vars.py` (GTR020.1); the existing
  macro-expansion machinery; Galaxy's `.local/galaxy-src/lib/galaxy/util/template.py`
  (B1 reference).
- **New (Phase 1):** a tier-1 read-only `boundary_signature` module; the GTR020.1
  structural-check upgrade; the reserved `EditCertifier` seam.
- **Spike artifacts (gitignored `.local/`, retained inline in §6):** `.local/bashlex`,
  `.local/cheetah3@3.4.0.post5`, `.local/kegalign_package_output.py`, `.local/.spike-venv`,
  `.local/spike_ku4_probe.py`, `.local/spike_fd_topology.py`.
- **Full session design:** `~/.claude/plans/how-difficult-would-it-noble-trinket.md`.
