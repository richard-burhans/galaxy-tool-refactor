# Using it from the command line

> **TL;DR.** Install, then run one of twelve commands on a tool file or a directory:
> `format` (fix), `upgrade` (repair; bump profile only when needed), `check` (report), `find-references`
> (locate a param's Cheetah `$var` uses across a tool **and its imported macros**),
> `rename-param` (rename a param everywhere — tool **and its imported macros** —
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
`--check` (exit non-zero if anything would change — handy in CI).

**A real `format --diff`** (cosmetic normalisation — note it never changes meaning):

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

1. Open [`docs/profile_boundaries.md`](../../profile_boundaries.md), find the
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
of the named sets. Rulesets: `cosmetic`, `default` (the default), `iuc`, `strict` — see
`galaxy-tool-refactor rulesets`. A `--select`/`--ignore` token may also be a **planemo
linter name** (`--select HelpMissing`, case-insensitive) — it resolves to the covering
GTR code(s); see the [parity table](../../planemo_linter_parity.md).

<details>
<summary>Directories, quiet mode, and exit codes</summary>

- `PATHS` may be files or directories (searched recursively for `*.xml`; non-tool XML
  is skipped). Macro-library files get the cosmetic checks too.
- `-q/--quiet` suppresses per-file lines, leaving the summary.
- `format --check` / `upgrade --check` make good CI gates (non-zero = "would change").
</details>
