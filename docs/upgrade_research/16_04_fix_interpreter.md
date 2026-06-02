# `16_04_fix_interpreter` — research note

| | |
|---|---|
| **Code** | `16_04_fix_interpreter` |
| **Profile** | 16.04 |
| **Level** | `must_fix` |
| **Auto-fix today** | **none** |
| **Stuck tools** (must_fix-only) | **1,726** (see `../upgrade_behavior_block_stats.md`) |
| **Galaxy PR** | https://github.com/galaxyproject/galaxy/pull/1688 |

> Galaxy-source citations are from the local clone `.local/galaxy-src/` @ `c6e0ee3`
> (2026-06-01). Our detector/message live in
> `galaxy-tool-xml-codemod/src/galaxy_tool_xml_codemod/profile_semantics.py`.

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

## Corpus reality

~2,000+ raw files carry `interpreter=` (deduped/applicable/sub-16.04 = the 1,726
stuck). Value mix (approximate `grep`, not a standing measure): `python` ~59%,
`perl` ~22%, `bash`/`sh` ~12%, `Rscript` ~3%, long tail (`python2.7`, `python3`,
`Rscript --no-save`, `python -W ignore`, `java -jar`, `docker`, `/usr/bin/php`,
full paths). Shapes:

- **(A) Clean** — body *starts* with a literal co-located script filename + args
  (maybe trailing Cheetah). In every sampled case the script existed beside the XML.
- **(B) Leading Cheetah** — the script is not the literal first token (e.g. `#if …`
  precedes it, or it sits inside both branches).
- **(C) Non-script interpreters** — `java -jar`, `docker`, `export …; java -jar`:
  the "interpreter" is itself a command prefix; the first token is a `.jar`, not a
  tool-dir script.
- **(D) Interpreter carries flags** — `Rscript --no-save`, `python -W ignore`.

## Mechanical-fix feasibility

Galaxy chose the script **after Cheetah substitution** (`split()[0]` on the rendered
line). A codemod sees only the unrendered XML, so *"the script is the first token"*
holds reliably **only for bucket A**. B/C/D defeat a naive first-token rule. The
conservative, GTX015-style scope is to auto-fix only bucket A — a single leading
literal script token + a single-token standard interpreter (optionally requiring the
script file to exist beside the XML) — and leave B/C/D to detect/warn.

## Where a fix would plug in

A new `RuntimeGatedFix` (the GTX014/GTX015 family;
`codemods/_runtime_gated.py` + `runtime_fixes.py`), `introduced_profile="16.04"`,
next code **GTX016**, upgrade-only. Detection already exists (`_detects_interpreter`).
Mutation via `Cursor`: `delete_attribute("interpreter")`, read body via `cursor.text`,
rewrite via `cursor.set_text(...)` (CDATA preserved by tier-1 `strip_cdata=False`).
No code in the repo currently emits `$__tool_directory__` — this would be the first.

## Status / recommendation

No auto-fix exists. A conservative bucket-A `FixInterpreter` codemod is feasible and
would be the single highest-impact behaviour-preserving fix. Size bucket A precisely
with a standing measure before committing.
