# Using it from the command line

> **TL;DR.** Install, then run one of twelve commands on a tool file or a directory:
> `format` (fix), `upgrade` (repair; bump profile only when needed), `check` (report), `find-references`
> (locate a param's Cheetah `$var` uses across a tool **and its imported macros**),
> `rename-param` (rename a param everywhere, tool **and its imported macros**,
> atomically), `rulesets`/`rules` (introspect), `normalize-macros` (opt-in macro-library
> fix), `convert-help` (opt-in RST → Markdown help conversion, equivalence-gated),
> `tokenize-version` (opt-in version-token extraction), `bump-version-suffix` (opt-in:
> increment the Galaxy revision suffix, `…+galaxy7` → `…+galaxy8`), `lint-skip` (opt-in:
> prune planemo `.lint_skip` suppressions we can prove are resolved).
> `format`/`upgrade`/`rename-param`/`convert-help`/`tokenize-version`/`bump-version-suffix`/`lint-skip`
> support `--check` (and `format`/`upgrade` `--diff`) to preview without writing; all
> seven mutating commands take `--backup` (`<file>.bak` before overwrite).

## Install & run

Install from PyPI:

```sh
pip install galaxy-tool-refactor             # the `galaxy-tool-refactor` CLI
pip install "galaxy-tool-refactor[mcp]"      # also installs the agent-facing MCP server
galaxy-tool-refactor --help
galaxy-tool-refactor --version               # print the installed version
```

To work on the toolkit itself, clone the workspace and use `uv` instead:

```sh
uv sync
uv run galaxy-tool-refactor --help
```

The twelve commands:

```text
check            Report where tools deviate from the selection, without changing them.
format           Apply a ruleset's fixable rules then cosmetic formatting (never profile=).
upgrade          Repair tools, bump profile= only when strictly needed for validity
                 (the minimum valid profile; a valid tool keeps its declaration), then
                 format. --modernize opts into the behavior-preserving walk: as far as
                 behaviour provably stays the same, stopping at the behaviour ceiling
                 with an actionable report and never past the deployment ceiling (the
                 newest profile every major public Galaxy server runs);
                 --allow-behavior-change (walk modes only) lifts the behaviour gate,
                 and --target-profile walks to an explicit vendored profile (implies
                 the walk; the one way past the deployment ceiling).
find-references  Report every Cheetah $var reference to a parameter across a tool AND its
                 imported macro files (read-only).
rename-param     Rename a parameter OLD->NEW across every Cheetah section, cross-ref attribute,
                 and <tests> mirror, plus the definition — across a tool AND its imported
                 macros, atomically. --repo-root proves a touched macro is sole-owned before
                 editing it (a shared macro is skipped + reported, or renamed across all its
                 importers in lockstep with --across-importers); --check previews.
rulesets         List the available rulesets and the rule codes each one selects.
rules            List the baked-in rules: code, family, fixable/advisory, rulesets.
normalize-macros Lowercase literal format/ftype in <macros>-root files (opt-in, repo-scoped).
tokenize-version Factor a literal version into @TOOL_VERSION@/@VERSION_SUFFIX@
                 (opt-in; kept only when the macro expansion is provably unchanged).
                 --macros-file NAME puts the tokens in a macros file the tool imports
                 (created, or merged/shared when provably inert) instead of inline.
                 --adopt-suffix (identity-changing) adds +galaxy0 to a bare version
                 matching a requirement, then tokenizes (1.20 -> 1.20+galaxy0).
bump-version-suffix
                 Increment a tool's integer Galaxy revision suffix (...+galaxy7 ->
                 ...+galaxy8). Identity-changing (the published revision moves), so
                 opt-in and never part of format/upgrade. --scope per-tool|suite
                 (default suite) governs a shared imported @VERSION_SUFFIX@ token:
                 suite bumps it once, moving every importer in lockstep.
convert-help     Convert an RST <help> to Markdown (format="markdown") when provably
                 render-equivalent and the profile is >= 24.2 (run upgrade first below it);
                 anything unprovable is skipped with the reason (opt-in; never part of
                 format/upgrade — it swaps Galaxy's rendering engine).
lint-skip        Clean up planemo .lint_skip sidecars: apply the toolchain's fixes and
                 delete a suppression line only when it is provably resolved (the linter
                 is completely covered AND clean on every tool in the directory after
                 the fix). Leaves what it cannot prove untouched and unmentioned (opt-in;
                 --check previews). See docs/lint_skip.md.
```

## Preview before you write

Both `format` and `upgrade` take `--diff` (print a unified diff, write nothing) and
`--check` (exit non-zero if anything would change, handy in CI).

**A real `format --diff`** (cosmetic normalisation; note it never changes meaning):

```diff
$ galaxy-tool-refactor format --diff tools/coverm/macros.xml
--- tools/coverm/macros.xml (original)
+++ tools/coverm/macros.xml (rewritten)
@@ -48,7 +48,7 @@
-        <param argument="--sharded" type="boolean" ... help="..." />
+        <param argument="--sharded" type="boolean" ... help="..."/>
```

**A real `upgrade --modernize --diff`** (the profile bump is the semantic
part; the bare `upgrade` keeps a valid tool's `profile=` untouched):

```diff
$ galaxy-tool-refactor upgrade --modernize --diff tools/bandage/bandage_info.xml
-<tool id="bandage_info" name="Bandage Info" version="@TOOL_VERSION@+galaxy2" profile="18.01">
+<tool id="bandage_info" name="Bandage Info" version="@TOOL_VERSION@+galaxy2" profile="25.1">
```

See [soundness](../soundness.md) for exactly what `upgrade` guarantees.

## My upgrade stopped. Now what?

The default `upgrade` bumps minimally, so it rarely meets a behaviour
boundary; this section is about the opt-in `--modernize` walk. The walk is
behavior-preserving: when a Galaxy `must_fix` behaviour change applies to
your tool and has no automatic fix, it stops below that boundary and tells
you why:

```text
$ galaxy-tool-refactor upgrade --modernize tools/mytool/mytool.xml
upgraded tools/mytool/mytool.xml
  profile upgrade stopped at 24.1 (latest is 26.1): 24_2_fix_test_case_validation
  (must_fix at 24.2) applies to this tool and cannot be fixed automatically yet;
  see docs/profile_boundaries.md for what changes there and how to update the
  tool, or rerun with --allow-behavior-change to upgrade anyway.
```

This is a successful partial upgrade, not an error (exit code 0). Your options:

1. Open [`docs/profile_boundaries.md`](https://github.com/richard-burhans/galaxy-tool-refactor/blob/main/docs/profile_boundaries.md), find the
   named code's section, and update the tool following Galaxy's description;
   then rerun `upgrade --modernize` to continue past the boundary.
2. Rerun with `--modernize --allow-behavior-change` to take the bump anyway,
   and review the crossed-boundary warning it prints.
3. Pin a specific stopping point with `--target-profile PROFILE` (composes with
   the gate; the lower wins).

When the upgrade crosses a boundary it *fixed* for you, the note says so
(`crossed 21.09 21_09_fix_from_work_dir_whitespace: fixed automatically
(GTR014).`); those fixes are verified on your tool by re-detection before
being credited.

A walk that meets no behaviour boundary still stops at the **deployment
ceiling**: the newest profile every major public Galaxy server runs (the
note names it, with the snapshot date). That is deliberate, because a newer
profile could not install on the lagging servers yet, and `--target-profile`
is the explicit way past it.

## Report only

```text
$ galaxy-tool-refactor check --ruleset strict tools/qualimap/qualimap_macros.xml
tools/qualimap/qualimap_macros.xml:3   GTR001  Canonical 4-space indentation; no tabs.
tools/qualimap/qualimap_macros.xml:16  GTR001  Canonical 4-space indentation; no tabs.
…
4 fixable finding(s) in 1 file(s).

References (what each code means + how to fix):
  GTR001  https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html
  Run `galaxy-tool-refactor rules` for the full reference.
```

`check` exits non-zero on any *fixable* finding; advisory findings are
informational unless you add `--strict`. The closing **References** block points
each fired code at its documentation, so any finding `check` cannot auto-fix still
tells you where to read what to do.

## Choosing rules (shared across format / upgrade / check)

```sh
galaxy-tool-refactor check  --ruleset strict  tools/      # +advisory checks
galaxy-tool-refactor format --select GTR001,GTR004 tool.xml  # only these rules
galaxy-tool-refactor format --ignore GTR006   tool.xml      # everything-but typo repair
```

Precedence is ruff-style: `--ignore` ▸ `--select` ▸ `--ruleset` (and `--select` replaces
the rulesets' set). `--ruleset` is repeatable / comma-separated and takes the union
of the named sets. Rulesets: `cosmetic`, `default` (the default), `iuc`, `strict`; see
`galaxy-tool-refactor rulesets`. A `--select`/`--ignore` token may also be a **planemo
linter name** (`--select HelpMissing`, case-insensitive); it resolves to the covering
GTR code(s); see the [parity table](https://github.com/richard-burhans/galaxy-tool-refactor/blob/main/docs/planemo_linter_parity.md).

<details>
<summary>Directories, quiet mode, and exit codes</summary>

- `PATHS` may be files or directories (searched recursively for `*.xml`; non-tool XML
  is skipped). Macro-library files get the cosmetic checks too.
- `-q/--quiet` suppresses per-file lines, leaving the summary.
- `format --check` / `upgrade --check` make good CI gates (non-zero = "would change").
</details>

## Every command, with an example

All twelve commands, each with a real (trimmed) invocation and its output. The
mutating ones (`format`, `upgrade`, `rename-param`, `normalize-macros`,
`convert-help`, `tokenize-version`, `bump-version-suffix`, `lint-skip`) take
`--check` to preview and write nothing; the bare form writes.

<details open>
<summary><b>Fix &amp; report: <code>format</code>, <code>upgrade</code>, <code>check</code></b></summary>

```console
$ galaxy-tool-refactor format --diff tools/coverm/macros.xml   # canonicalize (preview)
$ galaxy-tool-refactor upgrade tools/mytool/mytool.xml         # repair + minimal profile bump
$ galaxy-tool-refactor check --ruleset strict tools/qualimap/qualimap_macros.xml
```

These are shown in depth in the sections above (preview, the stop-and-explain
upgrade, report-only).
</details>

<details>
<summary><b>Introspect: <code>rulesets</code>, <code>rules</code></b></summary>

```console
$ galaxy-tool-refactor rulesets
cosmetic: Cosmetic whitespace only (indent, blank lines, shorthand).
  rules: GTR001, GTR004
default (default): The opinionated canonical formatter: structural repair + …
  rules: GTR001, GTR002, GTR004, GTR005, GTR006, GTR013, GTR017, GTR018.1, …

$ galaxy-tool-refactor rules
GTR001  [fmt/fixable]      rulesets:cosmetic,default,iuc,strict  planemo:-  Canonical 4-space indentation; no tabs.
GTR002  [codemod/fixable]  rulesets:default,iuc,strict           planemo:-  Reorder every <param> element's attributes to the IUC convention.
```
</details>

<details>
<summary><b>Query &amp; rename: <code>find-references</code>, <code>rename-param</code></b></summary>

```console
$ galaxy-tool-refactor find-references input tools/taxonomy_krona_chart/taxonomy_krona_chart.xml
…/taxonomy_krona_chart.xml:13  [command]  $type_of_data.input
…/taxonomy_krona_chart.xml:23  [command]  $type_of_data.input
2 reference(s) to 'input' across 1 tool(s)

$ galaxy-tool-refactor rename-param input reads tools/taxonomy_krona_chart/taxonomy_krona_chart.xml --check
would rename …/taxonomy_krona_chart.xml: 7 site(s) across 1 file(s)
would rename 1 tool(s); skipped 0
```

`find-references` is read-only; `rename-param` rewrites the tool **and its imported
macros** atomically (pass `--repo-root` to touch a macro shared with other tools).
</details>

<details>
<summary><b>Opt-in transforms: <code>tokenize-version</code>, <code>bump-version-suffix</code>, <code>convert-help</code>, <code>normalize-macros</code>, <code>lint-skip</code></b></summary>

```console
$ galaxy-tool-refactor tokenize-version tools/taxonomy_krona_chart/taxonomy_krona_chart.xml --check
would tokenize …/taxonomy_krona_chart.xml          # version="2.7.1+galaxy0" → @TOOL_VERSION@+galaxy@VERSION_SUFFIX@
1 tokenized, 0 skipped

$ galaxy-tool-refactor bump-version-suffix tools/taxonomy_krona_chart/taxonomy_krona_chart.xml --check
would bump …/taxonomy_krona_chart.xml to 2.7.1+galaxy1 (published revision changed)
1 bumped, 0 skipped

$ galaxy-tool-refactor convert-help tools/pangolin/pangolin.xml --check
skipped …/pangolin.xml: not provably render-equivalent (a non-CommonMark construct, unrepairable RST, or a render mismatch)
0 converted, 1 skipped

$ galaxy-tool-refactor normalize-macros tools/emboss/macros.xml --check
no macro-library files needed normalization        # reports "would normalize <file>" when a literal format/ftype needs lowercasing

$ galaxy-tool-refactor lint-skip tools/crispr_studio --check
no .lint_skip suppressions could be provably removed   # removes a line only when the toolchain fully covers + clears it
```

Each acts **only when the change is provable**; a skip with a reason is the normal,
safe result. These never run inside `format`/`upgrade`: they change a tool's identity
(`bump-version-suffix`), its rendering engine (`convert-help`), its structure
(`tokenize-version`), or files other than the one named (`normalize-macros`,
`lint-skip`).
</details>
