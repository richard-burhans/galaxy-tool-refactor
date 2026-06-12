# Using it from the command line

> **TL;DR.** Install, then run one of ten commands on a tool file or a directory:
> `format` (fix), `upgrade` (bump profile safely), `check` (report), `find-references`
> (locate a param's Cheetah `$var` uses across a tool **and its imported macros**),
> `rename-param` (rename a param everywhere — tool **and its imported macros** —
> atomically), `rulesets`/`rules` (introspect), `normalize-macros` (opt-in macro-library
> fix), `convert-help` (opt-in RST → Markdown help conversion, equivalence-gated).
> `format`/`upgrade`/`rename-param`/`convert-help`/`tokenize-version` support `--check` (and
> `format`/`upgrade` `--diff`) to preview without writing; all five mutating commands
> take `--backup` (`<file>.bak` before overwrite).

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

The ten commands:

```text
check            Report where tools deviate from the selection, without changing them.
format           Apply a ruleset's fixable rules then cosmetic formatting (never profile=).
upgrade          Repair and upgrade tools as far as behaviour provably stays the same,
                 then format. Stops at the behaviour ceiling with an actionable report;
                 --allow-behavior-change walks to the latest profile anyway, and
                 --target-profile caps the walk at an explicit vendored profile.
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
convert-help     Convert an RST <help> to Markdown (format="markdown") when provably
                 render-equivalent and the profile is >= 24.2 (run upgrade first below it);
                 anything unprovable is skipped with the reason (opt-in; never part of
                 format/upgrade — it swaps Galaxy's rendering engine).
```

## Preview before you write

Both `format` and `upgrade` take `--diff` (print a unified diff, write nothing) and
`--check` (exit non-zero if anything would change — handy in CI).

**A real `format --diff`** (cosmetic normalisation — note it never changes meaning):

```diff
$ galaxy-tool-refactor format --diff tools/coverm/macros.xml
--- tools/coverm/macros.xml (original)
+++ tools/coverm/macros.xml (rewritten)
@@ -1,3 +1,4 @@
+<?xml version='1.0' encoding='utf-8'?>
 <macros>
@@ -48,7 +49,7 @@
-        <param argument="--sharded" type="boolean" ... help="..." />
+        <param argument="--sharded" type="boolean" ... help="..."/>
```

**A real `upgrade --diff`** (the profile bump is the semantic part):

```diff
$ galaxy-tool-refactor upgrade --diff tools/bandage/bandage_info.xml
-<tool id="bandage_info" name="Bandage Info" version="@TOOL_VERSION@+galaxy2" profile="18.01">
+<tool id="bandage_info" name="Bandage Info" version="@TOOL_VERSION@+galaxy2" profile="26.1">
```

See [soundness](../soundness.md) for exactly what `upgrade` guarantees.

## My upgrade stopped — now what?

The default `upgrade` is behavior-preserving: when a Galaxy `must_fix` behaviour
change applies to your tool and has no automatic fix, the walk stops below that
boundary and tells you why:

```text
$ galaxy-tool-refactor upgrade tools/mytool/mytool.xml
upgraded tools/mytool/mytool.xml
  profile upgrade stopped at 24.1 (latest is 26.1): 24_2_fix_test_case_validation
  (must_fix at 24.2) applies to this tool and cannot be fixed automatically yet;
  see docs/profile_boundaries.md for what changes there and how to update the
  tool, or rerun with --allow-behavior-change to upgrade anyway.
```

This is a successful partial upgrade, not an error (exit code 0). Your options:

1. Open [`docs/profile_boundaries.md`](../../profile_boundaries.md), find the
   named code's section, and update the tool following Galaxy's description;
   then rerun `upgrade` to continue past the boundary.
2. Rerun with `--allow-behavior-change` to take the bump anyway, and review the
   crossed-boundary warning it prints.
3. Pin a specific stopping point with `--target-profile PROFILE` (composes with
   the gate; the lower wins).

When the upgrade crosses a boundary it *fixed* for you, the note says so
(`crossed 21.09 21_09_fix_from_work_dir_whitespace: fixed automatically
(GTR014).`) — those fixes are verified on your tool by re-detection before
being credited.

## Report only

```text
$ galaxy-tool-refactor check --ruleset strict tools/qualimap/qualimap_macros.xml
tools/qualimap/qualimap_macros.xml:3   GTR001  Canonical 4-space indentation; no tabs.
tools/qualimap/qualimap_macros.xml:16  GTR001  Canonical 4-space indentation; no tabs.
…
4 fixable finding(s) in 1 file(s).
```

`check` exits non-zero on any *fixable* finding; advisory findings are
informational unless you add `--strict`.

## Choosing rules (shared across format / upgrade / check)

```sh
galaxy-tool-refactor check  --ruleset strict  tools/      # +advisory checks
galaxy-tool-refactor format --select GTR001,GTR003 tool.xml  # only these rules
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
