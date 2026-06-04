# Cheetah in a Galaxy tool XML file: where it runs, and what's in scope

A reference for tool authors and tool-tooling developers: **which parts of a `<tool>`
document Galaxy evaluates with the Cheetah template engine**, *where* in each element the
Cheetah lives (element text vs. an attribute value), and **what variables Galaxy injects**
into the template namespace at each location (the set is not the same everywhere).

> Source of truth: the Galaxy server (`lib/galaxy/...`), read at commit `c6e0ee3`. Cheetah
> evaluation funnels through a single entry point, `galaxy.util.template.fill_template`;
> every location below is a call to it. Citations give the file + function (line numbers
> drift across releases). Intended to be neutral/general — suitable to contribute upstream.

Cheetah runs at **job-build time**, *after* macro expansion (`<expand>` / `@TOKEN@`) and
*before* the shell sees anything: each location's text is filled with the run's parameter
values, then handled per its kind (flattened to a command line, written to a file, compared,
split, …). A tool author references a value as `$name` (or `${name}`, `$name.attr`).

## 1. Where Cheetah runs

Two positions are possible: the Cheetah lives in an element's **text/CDATA body**, or in an
**attribute value**.

### Cheetah in element text / CDATA body

| Location | What it is | Post-Cheetah handling | Source (`lib/galaxy/...`) |
|---|---|---|---|
| `<command>` | the command line | each line stripped, newlines → spaces (**flattened to one line**), wrapped in a `set -e` job script | `tools/evaluation.py` `_build_command_line` |
| inline `<configfile>` (under `<configfiles>`) | a config/script file built from inputs | written to a working-dir file (optional `strip`); a `<configfile>` with `eval_engine="ecmascript"` uses JavaScript, **not Cheetah** | `tools/evaluation.py` `_build_config_files` → `_write_workdir_file` |
| `<environment_variable>` (under `<environment_variables>`) | an env-var value | written to an env file `cat`-ed into the job; values with `inject=` (`api_key` / `oidc_*` / `entry_point_path_for_label`) **bypass Cheetah** | `tools/evaluation.py` `_build_environment_variables` |
| `<redirect_url_params>` (a `data_source` tool) | URL params for the redirect | newline → space | `tools/__init__.py` (`Tool.parse` / data-source eval) |

### Cheetah in an attribute value

| Location | Attribute(s) | What it is | Post-Cheetah handling | Source |
|---|---|---|---|---|
| output `<data>` / `<collection>` | `label` | the dataset's display name | used directly as the history name | `tools/actions/__init__.py` (`_get_data_name…`) |
| `<change_format><when>` | `input` | a value compared to the `<when>`'s `value` to pick the output format | compared to `value=`; on match the `format=` is applied | `tools/actions/__init__.py` (change_format) |
| InteractiveTool `<entry_point>` | `url`, `port`, `name`, `label`, `requires_path_in_header_named` (each as an attribute **or** a child element — e.g. `<url>` / `<port>`) | entry-point fields | per-line stripped, newlines → spaces (flattened, like `<command>`) | `tools/evaluation.py` `_create_interactivetools_entry_points` |
| dynamic `<options>` | `from_url`, `request_body`, `request_headers` | the HTTP request that fetches options | builds the request; **user-only namespace — see §4** | `tools/parameters/dynamic_options.py` |
| output `<actions><action type="metadata">` | `default` | a default metadata value | result `.split(",")` and set as metadata | `tool_util/parser/output_actions.py` |

### Worked examples (one per location)

```xml
<!-- <command> body: single-quote so a value with spaces stays one argument -->
<command><![CDATA[
samtools sort '$input' -o '$output' --threads \${GALAXY_SLOTS:-1}
#if $advanced.enable
  --extra '$advanced.opts'
#end if
]]></command>

<!-- inline <configfile> body: a file assembled from the inputs, by name -->
<configfiles>
  <configfile name="samples">#for $s in $series
${s.label}\t${s.data.file_name}
#end for</configfile>
</configfiles>

<!-- <environment_variable> body: a value derived from an input dataset's metadata -->
<environment_variables>
  <environment_variable name="REF_PATH">$reference.fields.path</environment_variable>
</environment_variables>

<!-- output <action type="metadata"> default body: split on commas after templating -->
<actions>
  <action type="metadata" name="dbkey" default="$input.metadata.dbkey"/>
</actions>

<!-- output <data label="..."> attribute: names the dataset in the history -->
<data name="out" format="txt" label="${tool.name} on ${on_string}: sorted"/>

<!-- <change_format><when input="..."> attribute: pick the format from a select param -->
<data name="out" format="tabular">
  <change_format>
    <when input="out_format" value="bam" format="bam"/>
  </change_format>
</data>

<!-- InteractiveTool <entry_point> attribute -->
<entry_point name="Jupyter" requires_domain="true">
  <port>8888</port>
  <url>ipython/$__galaxy_url__/notebook</url>
</entry_point>

<!-- dynamic <options from_url="...">: USER-ONLY namespace (no datasets) -->
<param name="db" type="select">
  <options from_url="https://api.example.org/dbs?user=$__user_email__"/>
</param>

<!-- data_source <redirect_url_params> body -->
<redirect_url_params>GENOME=$dbkey tool_id=my_tool</redirect_url_params>
```

## 2. What is *not* Cheetah (common confusions)

| Location | Engine | Notes |
|---|---|---|
| `<version_command>` | `string.Template.safe_substitute` | substitutes **only** `$__tool_directory__`; different syntax/escaping than Cheetah | `tools/evaluation.py` `_build_version_command` |
| `<help>` | none (markup) | RST or `markdown` rendered to HTML; never variable-substituted (only a `${static_path}`/`${host_url}` string replace at render) | `tools/__init__.py` (`parse_help`) |
| `expression`-tool bodies; `ecmascript` configfiles; some `<options><filter>` post-process expressions | JavaScript via `do_eval` | a separate evaluator, not Cheetah | `tools/expressions/` |

## 3. The variables Galaxy injects (the Cheetah namespace)

For the main contexts (`<command>` / `<configfile>` / `<environment_variable>` /
`<entry_point>`), Galaxy builds one `param_dict` (`tools/evaluation.py` `build_param_dict`).
It contains:

**The tool's own parameters and outputs**, as wrapper objects (see §5):
- every `<inputs>` `<param>` by name (`$myparam`); nested as `$cond.sub`, `$repeat[i].x`, `$section.x`
- every `<outputs>` `<data>` / `<collection>` by name (`$myoutput`)

**Galaxy-provided built-ins** (most are dunder-named `$__x__`):

| Variable | Meaning |
|---|---|
| `$__tool_directory__` | the tool's install directory (for bundled scripts) |
| `$__root_dir__` / `GALAXY_ROOT_DIR` | Galaxy root directory |
| `$__datatypes_config__` / `GALAXY_DATATYPES_CONF_FILE` | path to the datatypes registry config |
| `$__tool_data_path__` / `GALAXY_DATA_INDEX_DIR` | tool `.loc` data directory |
| `$__new_file_path__` | new-dataset path (**deprecated**) |
| `$__app__` | the Galaxy app object (e.g. `$__app__.config…`) |
| `$__admin_users__` | configured admin user emails |
| `$__user__` / `$__user_id__` / `$__user_email__` / `$__user_name__` (`$userId` / `$userEmail`) | the current user (or `"Anonymous"`) |
| `$__galaxy_url__` | the Galaxy server URL |
| `$__local_working_directory__` | the job's local working directory |
| `$__get_data_table_entry__` | a function to query a tool data table |
| `$on_string` | a human label of the input dataset(s) — **only added for output `label`** (§4) |
| `$chromInfo` | path to the chrom-info file for the input build (added at action time) |

(Most input values are wrapped with a safe-string sanitiser; the built-ins and `chromInfo`
are not.) Sources: `tools/evaluation.py` `build_param_dict` / `__populate_non_job_params`;
`model.User.user_template_environment`.

## 4. The namespace differs by location

Not every location gets the full `param_dict`. This matters for correctness **and security**:

| Location | Namespace available |
|---|---|
| `<command>` / `<configfile>` / `<environment_variable>` / `<entry_point>` / `<redirect_url_params>` | the **full** `param_dict` (§3) |
| output `<data label>` | the command `param_dict` **plus** `$on_string` and `$tool`; used to name the dataset |
| `<change_format><when input>` | **wrapped inputs only** — no outputs, no working-dir vars |
| output `<action type="metadata" default>` | outputs **and** inputs, plus `$__python_template_version__` |
| dynamic `<options from_url>` (`request_body` / `request_headers`) | **user-only** — `$__user__` / `$__user_id__` / `$__user_email__` / `$__user_name__` and nothing else. **No datasets, no input values, no paths.** This is deliberate: option-fetch URLs must not be able to leak dataset contents or server paths. (`tools/parameters/dynamic_options.py`; `model.User.user_template_environment`.) |

## 5. What a dataset/collection variable exposes

A `<param type="data">` / output `<data>` renders, by default, to its **file path**; its
attributes give more (`tools/wrappers.py`):

- `$d` → the dataset's file path (its `str()`); `$d.file_name` / `$d.extra_files_path`
- `$d.ext` / `$d.extension` — the datatype extension
- `$d.metadata.KEY` — any metadata the datatype defines (e.g. `$d.metadata.dbkey`)
- `$d.element_identifier`, `$d.name`, `$d.hid`, `$d.dataset_id`
- `$d.is_of_type("bam", …)` — datatype test
- a collection: `$c[element_identifier]`, `$c.keys()`, `$c.all_paths`, `$c.element_identifier`

Whitespace/quoting caveat: a value may contain spaces (e.g. a dataset label, a free-form
`text` param), so shell-context references are normally single-quoted (`'$d'`). A `data`
path, an integer, an `.ext`, and the `$__…__` path built-ins are space-free in any working
install; user-facing labels (`.name`, `.element_identifier`, `$on_string`) are not.

## 6. Gotchas

- **Cheetah renders to *literal text*, then the shell parses it — quote your values.** A
  rendered value can contain spaces or shell metacharacters (a dataset label, a free-form
  `text` param). Unquoted, `$x` word-splits; quote shell-context references as `'$x'`. This
  is bash's rule for *literal* text — it applies even in positions that would be safe for a
  shell *expansion*: `THREADS=$x` with `x="a b"` renders to `THREADS=a b`, which the shell
  reads as an assignment **plus** a command `b`. Quote it: `THREADS='$x'`. (Space-free values
  — a `data` path, an integer, a `.ext`, the `$__…__` path built-ins — are safe unquoted;
  user-facing labels like `.name` / `.element_identifier` / `$on_string` are not.)
- **`#` is Cheetah, not shell.** A line starting with `#if` / `#for` / `#set` / `#end` is a
  Cheetah **directive**; `##` is a Cheetah **comment** (stripped before the shell sees it).
  To write a literal `#` comment for the shell, that line still gets Cheetah-processed first.
- **Escaping `$` and `#`.** Write `\$` for a literal dollar (e.g. a shell variable
  `\${GALAXY_SLOTS}`) and `\#` for a literal hash. A `#raw` … `#end raw` block disables all
  Cheetah inside it. `$(…)` and back-ticks are **shell** command substitution, not Cheetah.
- **`<command>` whitespace is flattened.** Every line is stripped and newlines become single
  spaces, so don't rely on line breaks to separate shell statements — chain with `&&` / `;`.
  A `#`-directive line is removed entirely (it contributes no shell text).
- **Nesting changes the reference path.** A `<param name="sub">` inside `<conditional
  name="c">` is `$c.sub` (and the conditional's *selector* param drives the `<when>`
  branches); inside `<repeat name="r">` it is reached by looping: `#for $i in $r` then
  `$i.x`; inside `<section name="s">` it is `$s.x`.
- **Macros expand *before* Cheetah.** `@TOKEN@` and `<expand macro="…"/>` are substituted
  first, so a `$var` (or even a whole `#if`) a tool "uses" may come from an imported macro
  file, not the tool file. Tooling that resolves references must expand first.
- **The namespace is reduced in places (§4).** The biggest surprise: dynamic
  `<options from_url>` / `request_body` / `request_headers` see **only** the user
  (`$__user_email__`, …) — `$input` and any dataset/path are unavailable there by design.
- **`<version_command>` and `<help>` are not Cheetah.** `$input` in `<version_command>` does
  nothing (only `$__tool_directory__` is substituted, via `string.Template`); `$x` in
  `<help>` is literal documentation text.
- **Undefined names fail the job.** Referencing a name not in the namespace raises at fill
  time. Only the *taken* branch of an `#if` is evaluated, so a reference reachable on one
  branch need not be defined on another.
- **py2 vs py3 in directives.** Embedded Python in directives (`#set`, `#if` expressions)
  runs under py3 for profile ≥ 19.05, else py2 (with an automatic futurize pass). Avoid
  version-specific Python (e.g. bare `print` statements) in templates.

## See also
- `galaxy_processing_model.md` — the same material with the full `<command>` job-script
  pipeline and the `<help>` rendering details.
