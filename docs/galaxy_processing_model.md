# How Galaxy processes tool-XML text: Cheetah sections & `<help>`

Cross-tier reference: what Galaxy's own code actually *does* with the
text-bearing sections of a tool XML — the **Cheetah-templated** sections
(`<command>` and its siblings) at job-build time, and the **`<help>`** section at
display time. This is the ground truth that the rationale and detection-soundness
of any text-oriented rule must rest on — in particular the reserved advisory
checks **GTR031** (single-quote Cheetah variables) and **GTR032** (`&&` vs lone
`&`); see [`iuc_best_practices.md`](iuc_best_practices.md) Bucket 4.

It is reference, not a corpus-frequency decision, so there is no measurement
backing it — only source citations (one exception: the `<help>` format
distribution, which has a standing measure).

## Sources

Verified by reading a shallow `dev`-branch clone of `galaxyproject/galaxy`
(commit `c6e0ee3`, 2026-06-01) — backend **and** Vue client — plus this project's
own vendored schema and the vendored `galaxy.util` runtime (`galaxy_util` 26.0.0
in `.venv`). General principle for this kind of work: **clone and read the source
locally rather than relying on web search** (the summarizer paraphrases — an
earlier `<help>` draft was wrong because of it).

Upstream files (`github.com/galaxyproject/galaxy`):

| File | What it owns here |
|---|---|
| `lib/galaxy/util/template.py` | `fill_template` — the **single Cheetah entry point** — **vendored locally** |
| `lib/galaxy/tools/evaluation.py` | `ToolEvaluator.build` order; Cheetah for `<command>` (`_build_command_line`), `<configfile>`/`<environment_variables>` (`_write_workdir_file`), InteractiveTool entry-points; `_build_version_command` (`string.Template`); `do_eval` (ecmascript) |
| `lib/galaxy/tools/actions/__init__.py` | Cheetah for output `label` and `<change_format><when input=…>` |
| `lib/galaxy/tool_util/parser/output_actions.py` | Cheetah for output `<actions><action>` default values |
| `lib/galaxy/tools/parameters/dynamic_options.py` | Cheetah for dynamic `<options from_url>` + option filter templates |
| `lib/galaxy/tools/__init__.py` | `Tool.parse_command`; `data_source` `redirect_url_params` (Cheetah); help (`parse_help`/`raw_help`, `help_html`, `render_help`, `to_json`/`to_dict` help serialization) |
| `lib/galaxy/jobs/__init__.py` | `MinimalJobWrapper.get_command_line` (`version_command_line + command_line`) |
| `lib/galaxy/jobs/command_factory.py` | `build_command`, `__externalize_commands` (the `#!<shell>` script + `set -e`) |
| `lib/galaxy/tool_util/parser/xml.py` | `parse_command`, `parse_interpreter`, `parse_strict_shell`, `parse_stdio`, `parse_help` |
| `lib/galaxy/tool_util/parser/stdio.py` | `error_on_exit_code`, `aggressive_error_checks` |
| `lib/galaxy/util/rst_to_html.py` | `rst_to_html` (docutils RST→HTML) — **vendored locally** |
| `client/src/components/Tool/{ToolHelp,ToolHelpMarkdown,ToolHelpRst,ToolCard}.vue` | client-side help format dispatch + markdown/RST rendering |

Project-local corroboration: `galaxy-tool-xml/src/galaxy_tool_xml/schema/galaxy-26.1.xsd`
(`Command` and `Help` complexTypes); `.venv/.../galaxy/util/{template,rst_to_html}.py`.

---

## Overview

### How Cheetah-templated sections are processed (broad summary)

At **job-build time**, Galaxy runs many tool-XML text fields through **Cheetah**
(a Python templating engine) via the single entry point
`galaxy.util.template.fill_template`. The mechanics are shared across every
Cheetah section:

- **Context.** The template is filled against a `param_dict` whose values include
  the tool's inputs/outputs as *wrapper objects* — `$input`/`$output` stringify
  to **filesystem paths** — plus Galaxy specials (`$__tool_directory__`,
  `$__root_dir__`, …). (A few sections use a narrower context — see the table.)
- **Python version is profile-gated.** `python_template_version` decides whether
  the embedded Python runs as py3 or py2; unspecified, it **defaults by profile**
  (`>=19.05` → py3, else py2, where a `futurize_preprocessor` rewrites the code).
- **The result is consumed differently per section** — some are whitespace-
  flattened to one line (`<command>`, entry-point values), some written to a
  work-dir file (`<configfile>`, env vars), some compared or split.

The **canonical** Cheetah section is `<command>` (templated → flattened →
embedded in a `set -e` shell script). But it is **not the only one** — the full
inventory:

| Cheetah-templated construct | Consumer | Post-Cheetah handling / notes |
|---|---|---|
| **`<command>`** | `evaluation._build_command_line` | line-strip + newline→space **flatten**; then `<version_command>` prepend + job-script assembly (details below) |
| **`<configfile>` / `<configfiles>`** | `evaluation._build_config_files` → `_write_workdir_file` | written to a work-dir file (optional `strip`); `ecmascript` type uses JS `do_eval` instead |
| **`<environment_variables>`** (value) | `evaluation._build_environment_variables` | written to an env file; values with `inject=` (`api_key`/`oidc_*`/`entry_point_path_for_label`) **bypass Cheetah** |
| **output `label`** (`<data>`/`<collection>`) | `actions._get_data_name_for_…` | becomes the dataset name; context adds `$on_string` and `$tool` |
| **`<change_format><when input="…">`** | `actions` (change_format) | templated, then compared to `value=` to pick the output format |
| **output `<actions><action>` default value** | `tool_util/parser/output_actions` | only the `default` value is treated as Cheetah; result `.split(",")` |
| **dynamic `<options from_url>`** (`from_url`, `request_body`, `request_headers`) + option **filter** templates | `parameters/dynamic_options` | builds the HTTP request / filters options; context = `User.user_template_environment` (**no datasets**) |
| **InteractiveTool `<entry_point>` attrs** (`url`/`port`/`name`/`label`/…) | `evaluation._create_interactivetools_entry_points` | line-strip **flatten** like `<command>` |
| **`data_source` `redirect_url_params`** | `tools.__init__` (data-source eval) | newline→space strip |

**Not Cheetah** (common confusions):

- **`<version_command>`** — templated with `string.Template.safe_substitute`,
  substituting only `$__tool_directory__`. Different engine, different escaping.
- **`expression` tools** and **`ecmascript`-typed configfiles** — evaluated as
  JavaScript via `do_eval`, not Cheetah.
- **`<help>`** — documentation markup, not templated at all (see below).

### How the `<help>` section is processed (broad summary)

`<help>` is **documentation**, rendered for **display** (not job execution) and
**never run through Cheetah**. Two markup languages are supported, and the
rendering is *split* between server and client:

- **reStructuredText** (the default) is rendered to HTML **server-side** by
  `galaxy.util.rst_to_html` (docutils).
- **Markdown** is **not** rendered server-side; the server ships the **raw
  markdown text** plus a `help_format` field to the Vue client, which renders it
  **in the browser** (`ToolHelpMarkdown.vue`).

So both are first-class; `Tool.help_html`'s `restructuredtext` assert is just a
guard on the RST-only helper, which every caller gates behind a format check.
(Corpus: 35 tools / 0.4% use markdown — details and citations below.)

---

## Cheetah processing — details

### `<command>`

```
<command> CDATA text  (parse: command_el.text, then .lstrip())
    │
    │  1. Cheetah templating  (galaxy.util.template.fill_template)
    │       context = param_dict: $input/$output → DatasetFilenameWrapper (str() == path),
    │                 plus $__tool_directory__, $__root_dir__, …
    │       python_template_version selects py2-vs-py3 Cheetah (default profile-gated @19.05)
    ▼
rendered command string
    │
    │  2. Whitespace flatten   (ToolEvaluator._build_command_line)
    │       every line .strip()-ed, newlines → spaces → ONE line
    │       (then: if interpreter=, prepend `interpreter <abs first token>`)
    ▼
single-line tool command
    │
    │  3. Prepend version command  (job_wrapper.get_command_line)
    │       base = f"{version_command_line or ''}{command_line}"   (<version_command>, ;-joined)
    │
    │  4. Assemble the job script  (jobs/command_factory.build_command + CommandsBuilder)
    │       prepend: dependency-resolution env setup, `cd working`, container monitor
    │       append:  `> tool_stdout 2> tool_stderr`, return-code capture, metadata
    │       (segments joined with `; `)
    ▼
    │  5. Externalize  (command_factory.__externalize_commands)
    │       "#!<shell>\n{integrity?}{set -e?}{source_env?}{assembled_commands}"
    │       shell defaults to /bin/sh; shell="none" skips the script
    ▼
executed as:  <shell> <script>
```

1. **Cheetah templating.** The `<command>` body is filled by `fill_template`
   (a Cheetah `Template.compile`), called from `_build_command_line`, against the
   `param_dict` (input/output wrappers whose `str()` is a **filesystem path**,
   plus `$__tool_directory__` etc.). `python_template_version` selects py2-vs-py3
   Cheetah; unspecified it **defaults by profile** (`>=19.05` → `3.5`, else `2.7`,
   with the py2 `futurize_preprocessor` pass). At parse time the only transform is
   `command.lstrip()`; the CDATA is otherwise raw.
2. **Whitespace flatten.** Every line is individually `.strip()`-ed and all
   newlines collapse to spaces → a **single-line** command. This is exactly why
   Cheetah `##` comments and `\` line continuations matter: literal newlines do
   not survive to the shell. (A deprecated `interpreter=` is prepended *here*,
   after templating — see the attribute table.)
3. **Prepend the version command.** `get_command_line()` returns
   `f"{version_command_line or ''}{command_line}"` — the `<version_command>` runs
   *first*, `;`-joined ahead of the tool command, output redirected to a version
   file. `<version_command>` is `string.Template`, **not Cheetah**.
4. **Assemble the job script.** The tool command is just **one `; `-joined
   segment** in a larger script built by `command_factory.build_command` via a
   `CommandsBuilder`: dependency-resolution shell commands (conda/env setup from
   `<requirement>`s) and `cd working` are *prepended*; `> tool_stdout 2>
   tool_stderr`, return-code capture, work-dir output copies, and metadata
   commands are *appended*.
5. **Externalize + shell execution — always.** The assembled commands are written
   into `#!<shell>\n{integrity?}{set -e?}{source_env?}{commands}` by
   `__externalize_commands` and run as `<shell> <script>` (shell defaults to
   `/bin/sh`; `"none"` disables the wrapper). So a tool command is normally always
   interpreted by a POSIX shell, alongside Galaxy's own setup/teardown segments.

#### Tools that do **not** run a shell

`Tool.parse_command` tolerates a missing `<command>` (`self.command = ""`), and
`_build_command_line` early-returns on empty — no shell line is built. Several
tool types bypass the pipeline above:

- **`data_source` / `data_source_async`** — fetch from an external service; no local program.
- **`expression`** — `parse_command` sets a *fixed* `cd ../; <expression-script call>`,
  and the JS expression is evaluated via `do_eval` (`ecmascript`), not Cheetah-into-shell.
- **`manage_data`** (data managers), **`interactive`**, **`cwl`** — special handling.

So "every tool's `<command>` is shell" is false; command-oriented rules should
treat a shell command as the *classic* case, not the only one.

#### `<command>` attributes (from vendored `galaxy-26.1.xsd`, `Command` complexType)

| Attribute | Type | Behaviour |
|---|---|---|
| `interpreter` | `xs:string`, **`gxdocs:deprecated="true"`** | Prefixes the command with `interpreter + tool_dir` to run a shipped script. Honoured only for legacy/no-profile tools; on modern profiles it is **ignored with a warning** (`parse_interpreter`). XSD recommends `'$__tool_directory__/<exe>'`. |
| `strict` | `xs:boolean` | Forces `set -e` into the shell script so any failing sub-command fails the job. **Default `True` for `profile>=20.09`**, `False` for legacy (`parse_strict_shell`) — the well-known "20.09 changed error handling" behaviour. Injected by `__externalize_commands`. |
| `detect_errors` | `DetectErrorType` (`default`/`exit_code`/`aggressive`) | Post-hoc job-failure detection (`parse_stdio` → `stdio.py`). `exit_code`: any non-zero exit = FATAL. `aggressive`: that plus stderr/stdout regex scanning (OOM + generic `error:`/`exception:`). `default`: for `profile>=16.04` with no explicit `<stdio>`, Galaxy implicitly applies exit-code checking. **Orthogonal to `strict`/`set -e`** — in-shell fail-fast vs post-hoc output inspection. |
| `oom_exit_code` | `xs:integer` | Only with `detect_errors="exit_code"`; marks one exit code as out-of-memory. |
| `use_shared_home` | `xs:string` | Do not isolate `$HOME` within the job directory. |

### `<configfile>` / `<configfiles>` and `<environment_variables>`

Both are templated by the **same** Cheetah engine as `<command>`, via
`_write_workdir_file(..., template_type="cheetah")`, then written to files in the
job working directory:

- **`<configfile>` / `<configfiles>`** — the CDATA body is Cheetah-templated and
  written to a named file the command references. (A `template_type="ecmascript"`
  configfile is JS-evaluated via `do_eval` instead.)
- **`<environment_variables>`** — each variable's value is Cheetah-templated and
  written to an env file sourced before the command. Values declared with
  `inject="api_key" | "oidc_*" | "entry_point_path_for_label"` are filled by
  Galaxy directly and **bypass Cheetah**.

The practical upshot for our rules: these sections carry Cheetah just like
`<command>`, so the "don't naively reflow CDATA / preserve Cheetah constructs"
caution applies to them too.

### Other Cheetah-templated constructs

Smaller author-facing fields that also go through `fill_template`:

- **output `label`** (`<data label="…">` / `<collection label="…">`) — templated
  with `$on_string` and `$tool` added to the context; becomes the dataset name.
- **`<change_format><when input="…">`** — the `input` expression is templated,
  then compared to the `value=` to select the output datatype.
- **output `<actions><action>` default value** — only the `default` value is
  treated as Cheetah (then `.split(",")`).
- **dynamic `<options from_url>`** — `from_url`, `request_body`, `request_headers`
  are templated to build the HTTP request, and option **filter** templates are
  templated too. Context here is `User.user_template_environment` (user vars
  only — **no datasets**), unlike the job `param_dict`.
- **InteractiveTool `<entry_point>` attributes** (`url`/`port`/`name`/`label`/…) —
  templated and line-strip-flattened like `<command>`.
- **`data_source` `redirect_url_params`** — templated, then newline→space
  stripped.

### Not Cheetah

- **`<version_command>`** — `string.Template.safe_substitute`, only
  `$__tool_directory__`. No Cheetah, no `param_dict`.
- **`expression` tools / `ecmascript` configfiles** — JavaScript via `do_eval`.

---

## `<help>` processing — details

1. **Default markup is reStructuredText.** `parse_help` reads the `<help>` text
   and defaults `format` to `"restructuredtext"`, passing any `format` value
   through unchanged (no rejection). The vendored 26.1 XSD `HelpFormatType`
   enumerates `restructuredtext` and `markdown` (the upstream parser model also
   carries `plain_text`).
2. **Both RST and Markdown are supported — rendering is *split* server/client.**
   - **RST** → HTML **server-side** by `galaxy.util.rst_to_html` (docutils), via
     `Tool.help_html` / `Tool.render_help`.
   - **Markdown** → the server passes the **raw markdown text** plus a
     `help_format` field to the client, rendered **in the browser**.

   In `Tool.to_json` (the tool-form API), the help block is explicitly:
   ```python
   tool_help = ""
   tool_help_format = "restructuredtext"
   if self.raw_help and self.raw_help.format == "restructuredtext":
       tool_help = self.render_help(...)      # RST -> HTML server-side
   elif self.raw_help:
       tool_help = self.raw_help.content      # markdown: raw text passed through
       tool_help_format = self.raw_help.format
   # ... tool_model.update({"help": tool_help, "help_format": tool_help_format, ...})
   ```
   `Tool.to_dict(..., tool_help=True)` mirrors this (`help` + `help_format` keys).
   The Vue client's `ToolHelp.vue` dispatches on the format:
   `format == 'markdown'` → `ToolHelpMarkdown.vue` (renders via Galaxy's `markup()`
   with `admin=false`, then `v-html`); `restructuredtext` → `ToolHelpRst.vue` (the
   server HTML); anything else → plain text.
3. **`Tool.help_html` is an RST-only helper, not a bug.** It does assert
   `help_content.format == "restructuredtext"` and only calls `rst_to_html` — but
   **every caller guards it behind a `format == "restructuredtext"` check**
   (`to_json`, `to_dict`, `to_archive`, `workflow/modules.py`), so the assert
   never fires for markdown tools. (An earlier draft mis-read this as "markdown
   errors / isn't rendered"; tracing the API + client paths corrected it.)
4. **Help is *not* run through Cheetah.** The only server-side substitution is
   `render_help`'s literal `${static_path}` / `${host_url}` `str.replace` (RST
   path only), plus an RST `.. image::` path rewrite for tool-shed repositories
   (`Tool.__get_help_with_images`).
5. **Render paths:**
   - RST: `parse_help` → `HelpContent` → `self.raw_help` → `Tool.help_html`
     (→ `rst_to_html`) → `Tool.render_help` → API `help` (HTML) → `ToolHelpRst.vue`.
   - Markdown: `parse_help` → `HelpContent` → `self.raw_help` → API `help` (raw)
     + `help_format="markdown"` → `ToolHelpMarkdown.vue` (`markup()` → `v-html`).
6. **Sanitization.** Server RST uses docutils defaults (raw-HTML / file-insertion
   disabled). Client markdown calls `markup(content, /* admin */ false)`, which
   disallows raw HTML.

**Corpus reality:** across 9,358 unique corpus tools, **35 (0.4%) declare
`format="markdown"`** — markdown is the *only* explicit `format` value that
appears (nobody writes `restructuredtext` explicitly; no `plain_text`); 8,997
help-bearing tools use the implicit RST default, 326 have no `<help>`.
*Reproduced by:* `uv run python -m scripts.measure help-formats`. These 35 tools
use a supported feature — there is **no defect to flag**, so this is *not* an
advisory-check candidate.

---

## Implications for this project's rules

| Finding | Consequence for our work |
|---|---|
| `<command>` vars resolve to **filesystem paths** that may contain spaces/special chars | Confirms the **GTR031** rationale (single-quoting `'$var'` guards word-splitting/globbing). But sound detection needs Cheetah-aware parsing of the CDATA — consistent with the prior ~87%-noise literal-heuristic measurement. Stance: measure-first, likely keep deferred. |
| `<command>` is flattened to a **single shell line**, one `; `-joined segment in a larger `set -e` script | Confirms the **GTR032** rationale: a lone `&` truly backgrounds a sub-command and breaks sequencing (should be `&&`). The single-line, always-shell model makes this the cleaner first heuristic check. A `<command>` can't assume it is the only thing in the script. |
| **Cheetah is not `<command>`-only** — `<configfile>`/`<configfiles>`, `<environment_variables>`, output `label`, `<change_format>`, output `<actions>`, dynamic `<options>`, entry-points, and `redirect_url_params` are all Cheetah-templated | The "don't reflow CDATA / preserve Cheetah" caution applies to **all** of these. A formatter/codemod touching any Cheetah-bearing text must treat it as Cheetah — `<configfile>` especially (it carries large CDATA bodies like `<command>`). |
| `<version_command>` uses `string.Template` (`$__tool_directory__` only); expression/ecmascript use JS `do_eval` — **not Cheetah** | A rule must not apply Cheetah assumptions (or `$var` single-quoting heuristics) to `<version_command>` or expression tools — different engines, different escaping. |
| `<help format="markdown">` is a **supported** feature (server sends raw markdown + `help_format`; the Vue client renders it) — 35 corpus tools / 0.4% | **No advisory check** — no defect. A future fmt/codemod rule touching `<help>` must respect *both* markup languages and must **not** assume RST. |
| `interpreter=` is deprecated and profile-gated | A future advisory/codemod could flag `interpreter=` on modern-profile tools and suggest the `$__tool_directory__` form. |

These follow-ups are recorded here as candidates; each would be picked up as its
own TDD increment, not bundled into this reference doc.
