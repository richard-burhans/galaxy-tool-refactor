# `16_04_fix_interpreter` — research note

| | |
|---|---|
| **Code** | `16_04_fix_interpreter` |
| **Profile** | 16.04 |
| **Level** | `must_fix` |
| **Auto-fix today** | **GTR016** `FixInterpreter` (bucket A — any non-empty interpreter since the 2026-06-10 widening; runtime-gated) |
| **Stuck tools** (must_fix-only) | **302** now (post-widening; see `../upgrade_behavior_block_stats.md`, re-measured 2026-06-12 with the shipped gate: token-resolved baselines + macro-expanded detection) — 299 under the pre-gate raw-tree measurement, 316 pre-widening, and **1,726** without this codemod |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/1688 |

> Galaxy-source citations are from the local clone `.local/galaxy-src/` @ `c6e0ee3`
> (2026-06-01). Our detector/message live in
> `galaxy-tool-codemod/src/galaxy_tool_codemod/profile_semantics.py`.

## What the feature was

A tool could write `<command interpreter="python">myscript.py $input</command>`.
The `interpreter` attribute told Galaxy: *"the command body names a script that
ships with this tool — run it with this language runtime."* The author wrote
neither the `python` prefix nor a path to the script; Galaxy supplied both.

## What it did at runtime (verified)

`lib/galaxy/tools/evaluation.py:755-788` (`_build_command_line`):

1. Cheetah-substitute the command body (`fill_template`), strip each line, collapse
   newlines → a single line.
2. `executable = command_line.split()[0]` — the first whitespace token **of the
   substituted line**.
3. `abs_executable = os.path.join(os.path.abspath(tool_dir), executable)`.
4. `command_line.replace(executable, f"{interpreter} {shlex.quote(abs_executable)}", 1)`
   — replace the **first occurrence** with `<interpreter> '<abs path>'`.

The interpreter value is interpolated **verbatim** — never quoted, never split. That
holds across every composition form Galaxy ever shipped: `release_16.04`
(`evaluation.py:478-484`) through `release_20.01` *prepended* it
(`command_line = interpreter + " " + command_line` after an unquoted abspath
replace); `release_20.09` (`:501`) switched to the token-splice + `shlex.quote`
form above, which survives in `dev` today. The two forms are equivalent whenever
the script is the first content token of the rendered line — exactly the bucket-A
shape — and the verbatim interpolation is what makes flag-bearing / non-script
interpreter values (`Rscript --no-save`, `java -jar`, `export …;`) mechanically
rewritable (the 2026-06-10 widening, codemod `docs/decisions.md` §39).

So `<command interpreter="python">myscript.py $input</command>` in a tool at
`/galaxy/tools/mytool/` executed as `python '/galaxy/tools/mytool/myscript.py' <input>`.
Path resolution and the runtime prefix were implicit.

## What changed / why a bump breaks it

`interpreter` is honoured **only** when `legacy_defaults` is true, i.e. profile
**== 16.01** (`lib/galaxy/tool_util/parser/xml.py:179`). For any other profile the
parser drops it with a warning (`parser/xml.py:315-323`):

```python
def parse_interpreter(self):
    interpreter = None
    command_el = self._command_el
    if command_el is not None:
        interpreter = command_el.get("interpreter", None)
    if interpreter and not self.legacy_defaults:
        log.warning("Deprecated interpreter attribute on command element is now ignored.")
        interpreter = None
    return interpreter
```

A no-`profile` tool defaults to 16.01, so it still works today; the instant
`upgrade` bumps it to ≥ 16.04, Galaxy ignores `interpreter` and runs the bare body
(`myscript.py …`) with no runtime and no path resolution → broken. That is why
this is `must_fix` rather than advisory.

## The faithful fix

For interpreter `I` and leading script token `S`:
`<command interpreter="I">S <rest></command>` →
`<command>I '$__tool_directory__/S' <rest></command>` (drop the attribute).

- **Token gotcha.** Galaxy's advice message (mirrored in `profile_semantics.py:101`)
  says `$tool_directory`, but the real runtime variable is **`$__tool_directory__`**
  (double underscores; `evaluation.py:639,794`). A fix must emit `$__tool_directory__`.
- A faithful rewrite changes **only** the runtime prefix and the first token's path.
  It must NOT re-quote arguments or add `detect_errors` — those alter behaviour.
- **The literal `'$__tool_directory__/S'` vs Galaxy's `shlex.quote` — accepted bound.**
  Galaxy emitted `shlex.quote(os.path.join(os.path.abspath(tool_dir), token))`
  (`evaluation.py:785-787`), whose escaping adapts to the *actual* install path. A
  codemod cannot know that abspath, so it emits the static literal
  `'$__tool_directory__/S'`. This is byte/behaviour-faithful for every path: spaces and
  globs are safe (both forms single-quote), `$__tool_directory__` resolves to the same
  `os.path.abspath(tool.tool_dir)` at runtime (`evaluation.py:639` → `jobs/__init__.py:1075-1079`),
  and the token is already quote/space-free (`_SCRIPT_TOKEN`). The **sole** divergence is
  an embedded single quote in the resolved tool-directory abspath — declared out of scope
  as a pathological, admin-controlled install path.

## Corpus reality

~2,000+ raw files carry `interpreter=` (deduped/applicable/sub-16.04 = the 1,726
that would be stuck without GTR016). Value mix (approximate `grep`, not a standing measure): `python` ~59%,
`perl` ~22%, `bash`/`sh` ~12%, `Rscript` ~3%, long tail (`python2.7`, `python3`,
`Rscript --no-save`, `python -W ignore`, `java -jar`, `docker`, `/usr/bin/php`,
full paths). Shapes:

- **(A) Clean** — body *starts* with a literal co-located script filename + args
  (maybe trailing Cheetah). In every sampled case the script existed beside the XML.
  **Since the 2026-06-10 widening this includes any non-empty interpreter value** —
  flags (`Rscript --no-save`, `python -W ignore`), non-scripts (`java -jar`,
  `docker`), compound prefixes (`export …; java -jar`) — because Galaxy interpolates
  the value verbatim in every composition form (above).
- **(B) Leading Cheetah** — the script is not the literal first token (e.g. `#if …`
  precedes it, or it sits inside both branches). The only genuinely unprovable
  shape: `split()[0]` of the *rendered* line is statically unknowable.

(The historical buckets **C** — non-script interpreter — and **D** — flag-carrying
interpreter — were conservatism, not soundness: the verbatim-interpolation proof
dissolved them into A (literal first token, 25 tools) and B (Cheetah-leading, 26
tools). An empty `interpreter=""` is its own degenerate non-bucket: every Galaxy
form gates on `if interpreter:`, so it was always ignored — nothing to reproduce;
0 corpus tools.)

## Mechanical-fix feasibility

Galaxy chose the script **after Cheetah substitution** (`split()[0]` on the rendered
line). A codemod sees only the unrendered XML, so *"the script is the first token"*
holds reliably **only for bucket A** — a literal leading script token. That is the
**sole** static gate: the interpreter value itself is interpolated verbatim by
every Galaxy composition form, so it needs no restriction beyond non-emptiness.
Only bucket B (leading Cheetah) defeats the rule and stays detect/warn. (The
original GTR016 scope also required a single-token standard interpreter — that
restriction was conservatism, removed by the 2026-06-10 widening, §39.)

## Where the fix plugs in

`FixInterpreter` (`codemods/fix_interpreter.py`) is a `RuntimeGatedFix` (the
GTR014/GTR015 family; `codemods/_runtime_gated.py` + `runtime_fixes.py`),
`introduced_profile="16.04"`, code **GTR016**, upgrade-only. The eligibility predicate
is the shared `codemods/_interpreter.py` core (so the codemod and the
`interpreter-bucket-split` measure agree by construction). Mutation via `Cursor`:
`cursor.set_text(new_body, cdata=True)` (CDATA wrap, the first repo code to do so) then
`cursor.delete_attribute("interpreter")`. It is the first repo code to emit
`$__tool_directory__`.

## Status / recommendation

**Shipped: `FixInterpreter` (GTR016), widened 2026-06-10 (codemod §39).** The
bucket-A codemod described above — the single highest-impact behaviour-preserving
fix. It rewrites bucket-A-by-shape tools (the `interpreter-bucket-split` measure's
**A** 1,407 + **A-missing** 28; the file-exists check is a measurement refinement,
not a codemod gate — the rewrite is faithful regardless, see codemod
`docs/decisions.md` §27). The rewrite uses a **positional splice** anchored at the
first content line so a script name in a leading `##` comment is never mistargeted,
and emits CDATA so shell operators stay literal. Corpus impact (three
population-distinct counts): the `interpreter-bucket-split` measure sizes **1,435**
tools eligible by shape (A 1,407 + A-missing 28, across all profiles; 1,410 before
the widening — the dissolved bucket C contributed 25); the `corpus_check codemod`
sweep **rewrites 1,144** of them (idempotent, 0 post-validate-failed — the gap
being bucket-A tools that don't actually cross the 16.04 boundary in the sweep,
e.g. already declaring ≥ 16.04, so the runtime gate never fires; 1,127 before the
widening); and the behaviour-block walk, which counts only sub-16.04
first-blockers, drops **1,726 → 302** (`upgrade_behavior_block_stats.md`; 316
before the widening — the 17 rescued tools are the dissolved-C tools that were
actually stuck sub-16.04), the residual 302 being bucket B.
