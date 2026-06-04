# Using it from the command line

> **TL;DR.** Install, then run one of seven commands on a tool file or a directory:
> `format` (fix), `upgrade` (bump profile safely), `check` (report), `find-references`
> (locate a param's Cheetah `$var` uses), `presets`/`rules` (introspect),
> `normalize-macros` (opt-in macro-library fix). `format`/`upgrade` support `--diff`
> and `--check` so you can preview without writing.

## Install & run

```sh
uv sync
uv run galaxy-tool-refactor --help
```

The seven commands:

```text
check            Report where tools deviate from the selection, without changing them.
format           Apply a preset's fixable rules then cosmetic formatting (never profile=).
upgrade          Repair and upgrade tools to the latest profile they can reach, then format.
find-references  Report every Cheetah $var reference to a parameter across a tool (read-only).
presets          List the available presets and the rule codes each one selects.
rules            List the baked-in rules: code, family, fixable/advisory, presets.
normalize-macros Lowercase literal format/ftype in <macros>-root files (opt-in, repo-scoped).
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

## Report only

```text
$ galaxy-tool-refactor check --preset strict tools/qualimap/qualimap_macros.xml
tools/qualimap/qualimap_macros.xml:3   GTR001  Canonical 4-space indentation; no tabs.
tools/qualimap/qualimap_macros.xml:16  GTR001  Canonical 4-space indentation; no tabs.
…
4 fixable finding(s) in 1 file(s).
```

`check` exits non-zero on any *fixable* finding; advisory findings are
informational unless you add `--strict`.

## Choosing rules (shared across format / upgrade / check)

```sh
galaxy-tool-refactor check  --preset strict   tools/      # +advisory checks
galaxy-tool-refactor format --select GTR001,GTR003 tool.xml  # only these rules
galaxy-tool-refactor format --ignore GTR006   tool.xml      # everything-but typo repair
```

Precedence is ruff-style: `--ignore` ▸ `--select` ▸ `--preset` (and `--select` replaces
the preset's set). Presets: `cosmetic`, `iuc` (default), `strict` — see
`galaxy-tool-refactor presets`.

<details>
<summary>Directories, quiet mode, and exit codes</summary>

- `PATHS` may be files or directories (searched recursively for `*.xml`; non-tool XML
  is skipped). Macro-library files get the cosmetic checks too.
- `-q/--quiet` suppresses per-file lines, leaving the summary.
- `format --check` / `upgrade --check` make good CI gates (non-zero = "would change").
</details>
