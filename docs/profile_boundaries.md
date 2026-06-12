# Profile boundary reference: what changes at each upgrade point, and what to do

This is the reference `galaxy-tool-refactor upgrade` points you at when it
stops. The default upgrade is **minimal-bump**: it moves `profile=` only when
strictly needed for validity, so most tools never meet these boundaries.
`upgrade --modernize` opts into the **behavior-preserving walk**: it walks
your tool's `profile=` toward the latest Galaxy profile, but stops at the
newest profile it can reach without crossing a Galaxy behaviour change that
(a) applies to your tool and (b) it cannot fix automatically with a fix
proven on your tool. A stop is not a defect in your tool; it means the tool
is not yet provably safe to upgrade further, and this page tells you exactly
why and what to do next.

How to read it:

- Sections are profile boundaries, in release order. Your stop note names the
  blocking code(s); find the matching section below.
- `must_fix` changes stop the modernize walk when they apply (unless an
  automatic fix clears them). `consider` changes are warned about and never
  stop the walk.
- Every entry carries Galaxy's own description of the change (often including
  a recipe to restore the legacy behaviour) and the Galaxy release link.
- After updating your tool, rerun `galaxy-tool-refactor upgrade --modernize`.
  To upgrade past a boundary without changing the tool, rerun with
  `--modernize --allow-behavior-change` and review the warnings it prints.
- A walk that clears every behaviour boundary still stops at the
  **deployment ceiling**, the newest profile every major public Galaxy
  server runs (the note names it); only an explicit `--target-profile`
  declares past it.

Related documents: [`profile_upgrades.md`](profile_upgrades.md) is the
maintainer-facing ledger of the *structural* (XSD) requirements of each bump
and the validity-as-oracle soundness boundary;
[`upgrade_behavior_block_stats.md`](upgrade_behavior_block_stats.md) reports
where the modernize walk stops across the public tool corpus.

Everything between the markers below is generated from the vendored Galaxy
behaviour-code catalogue and the auto-fix registry; regenerate with
`uv run python -m scripts.gen_profile_boundaries` (a freshness test enforces
it).

<!-- BEGIN GENERATED: profile boundary reference (scripts/gen_profile_boundaries.py) -->
## Profile 16.04

`upgrade --modernize` stops below this profile when one of its `must_fix` changes applies to your tool and cannot be fixed automatically.

### `16_04_fix_interpreter`

Severity: `must_fix` (the tool's behaviour or output changes).

**What the toolchain does:** `upgrade` fixes this automatically when the fix is provable for your tool (GTR016: Inline a deprecated `<command interpreter=I>`script ...`</command>` as `<command>`I '$__tool_directory__/script' ...`</command>` (any non-empty interpreter, literal-script first token).). When it cannot prove the construct gone (the fix is verified by re-detection), the `--modernize` walk stops below 16.04; update the tool by hand and rerun, or rerun with `--modernize --allow-behavior-change` to upgrade anyway.

**Galaxy's description:**

```text
This tool uses an interpreter on the command block, this was disabled with 16.04. The command line needs to be rewritten to call the language runtime with a full path to the target script using `$tool_directory` to refer to the path to the tool and its script.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/1688](https://github.com/galaxyproject/galaxy/pull/1688).

### `16_04_consider_implicit_extra_file_collection`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with profile 16.04 tools, Galaxy no longer attempts to just find tool outputs keyed on the output ID in the working directory. Tool outputs need to be explicitly declared and dynamic outputs need to be specified in a 'galaxy.json' file or with a 'discover_datasets' block.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/1688](https://github.com/galaxyproject/galaxy/pull/1688).

### `16_04_fix_output_format`

Severity: `must_fix` (the tool's behaviour or output changes).

**What the toolchain does:** `upgrade` fixes this automatically when the fix is provable for your tool (GTR015: Replace output `<data format="input">` with format_source for a tool with a sole data input (qualified name when nested).). When it cannot prove the construct gone (the fix is verified by re-detection), the `--modernize` walk stops below 16.04; update the tool by hand and rerun, or rerun with `--modernize --allow-behavior-change` to upgrade anyway.

**Galaxy's description:**

```text
Starting with 16.04 tools, having format='input' on a tool output is disabled. The behavior was not well defined for these outputs. Please add format_source="a_specific_input_name" for a specific input to inherit the format from.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/1688](https://github.com/galaxyproject/galaxy/pull/1688).

### `16_04_exit_code`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with 16.04 tools the exit code of the command executed will be used to detect errors by default. This tool previously would have discovered errors by checking if any content is written to standard error. Add '<stdio><regex match=".*" source="stderr" level="fatal" description="Unknown error encountered" /></stdio>' to your tool to restore the legacy behavior or restructure your command block to rely on the exit code.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/1688](https://github.com/galaxyproject/galaxy/pull/1688).


## Profile 17.09

No `must_fix` change lands here; the `--modernize` walk crosses this boundary freely (with warnings where a `consider` change applies).

### `17_09_consider_provided_metadata_style`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with 17.09 tools, the format of 'galaxy.json' (a rarely used file that can be used to dynamically collect datasets or metadata about datasets produced by the tool) changed - the original behavior can be restored by adding 'provided_metadata_style="legacy"' to the tool's outputs tag.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/4437](https://github.com/galaxyproject/galaxy/pull/4437).


## Profile 18.01

No `must_fix` change lands here; the `--modernize` walk crosses this boundary freely (with warnings where a `consider` change applies).

### `18_01_consider_structured_like`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with 18.01 tools, the 'structured_like` attribute must reference inputs in a fully qualified manner - using '|' to describe parent conditionals for instance.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/6162](https://github.com/galaxyproject/galaxy/pull/6162).

### `18_01_consider_home_directory`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with profile 18.01 tools, each job is given its own home directory. Most tools should not depend on global state in a home directory, if this is required though set 'use_shared_home="true"' on the command tag of the tool.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/5193](https://github.com/galaxyproject/galaxy/pull/5193).


## Profile 18.09

No `must_fix` change lands here; the `--modernize` walk crosses this boundary freely (with warnings where a `consider` change applies).

### `18_09_consider_python_environment`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with profile 18.09 tools, data managers run without Galaxy's virtual environment. Be sure your requirements reflect all the data manager's dependencies.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/6466](https://github.com/galaxyproject/galaxy/pull/6466).


## Profile 20.05

No `must_fix` change lands here; the `--modernize` walk crosses this boundary freely (with warnings where a `consider` change applies).

### `20_05_consider_inputs_as_json_changes`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with 20.05, the format of data in 'inputs' config files changed slightly. Unselected optional `select` and `data_column` parameters get json null values instead of the string 'None' and multiple `select` and `data_column` parameters are lists (instead of comma separated strings).
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/9776/files](https://github.com/galaxyproject/galaxy/pull/9776/files).


## Profile 20.09

No `must_fix` change lands here; the `--modernize` walk crosses this boundary freely (with warnings where a `consider` change applies).

### `20_09_consider_output_collection_order`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting in profile 20.09 tools, the order elements defined in tool test became relevant in order to verify collections are properly sorted. This may cause tool tests to fail after the upgrade, rearrange the elements defined in output collections if this occurs.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/10434](https://github.com/galaxyproject/galaxy/pull/10434).

### `20_09_consider_set_e`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with profile 20.09 tools, tool scripts are executed with the 'set -e' instruction. The 'set -e' option instructs the shell to immediately exit if any command has a non-zero exit status. If your command uses multiple sub-commands and you'd like to allow them to execute with non-zero exit codes add 'strict="false"' to the command tag to restore the tool's legacy behavior.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/9962](https://github.com/galaxyproject/galaxy/pull/9962).


## Profile 21.09

`upgrade --modernize` stops below this profile when one of its `must_fix` changes applies to your tool and cannot be fixed automatically.

### `21_09_fix_from_work_dir_whitespace`

Severity: `must_fix` (the tool's behaviour or output changes).

**What the toolchain does:** `upgrade` fixes this automatically when the fix is provable for your tool (GTR014: Strip surrounding whitespace from `<data from_work_dir>` (literal at profile >= 21.09).). When it cannot prove the construct gone (the fix is verified by re-detection), the `--modernize` walk stops below 21.09; update the tool by hand and rerun, or rerun with `--modernize --allow-behavior-change` to upgrade anyway.

**Galaxy's description:**

```text
Starting with 21.09 tools, from_work_dir output file names are quoted so white space needs to be stripped out of attribute.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/12536](https://github.com/galaxyproject/galaxy/pull/12536).

### `21_09_consider_python_environment`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with 21.09 data source tools, Galaxy's virtual environment is no longer included in the tool's runtime environment. Tools that require it, should include the galaxy-util package in their requirements.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/12515](https://github.com/galaxyproject/galaxy/pull/12515).


## Profile 23.0

No `must_fix` change lands here; the `--modernize` walk crosses this boundary freely (with warnings where a `consider` change applies).

### `23_0_consider_optional_text`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Text parameters that are inferred to be optional (i.e the `optional` tag is not set, but the tool parameter accepts an empty string) are set to `None` for templating in Cheetah. Previous to this version tools would receive the empty string "" as the templated value.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/15491/files](https://github.com/galaxyproject/galaxy/pull/15491/files).


## Profile 24.0

No `must_fix` change lands here; the `--modernize` walk crosses this boundary freely (with warnings where a `consider` change applies).

### `24_0_consider_python_environment`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with 24.0 async data source tools, Galaxy's virtual environment is no longer included in the tool's runtime environment. Tools that require it, should include the galaxy-util package in their requirements.
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/17422](https://github.com/galaxyproject/galaxy/pull/17422).

### `24_0_request_cleaning`

Severity: `consider` (a runtime default changes; worth reviewing).

**What the toolchain does:** warns when this applies to your tool; the change is advisory (`consider`), so it does not stop the `--modernize` walk. Review Galaxy's description below at your leisure.

**Galaxy's description:**

```text
Starting with 24.0 data source tools, Galaxy requires explicit `request_param_translation` for each parameter sent to the tool. If this tools depends on unspecified parameters - new xml elements will need to be added for these parameters.
```


## Profile 24.2

`upgrade --modernize` stops below this profile when one of its `must_fix` changes applies to your tool and cannot be fixed automatically.

### `24_2_fix_test_case_validation`

Severity: `must_fix` (the tool's behaviour or output changes).

**What the toolchain does:** `upgrade` fixes this automatically when the fix is provable for your tool (GTR096: Fully-qualify a flat `<test>` parameter name to its unique nested parent|...|child input path (required at profile >= 24.2).). When it cannot prove the construct gone (the fix is verified by re-detection), the `--modernize` walk stops below 24.2; update the tool by hand and rerun, or rerun with `--modernize --allow-behavior-change` to upgrade anyway.

**Galaxy's description:**

```text
Starting with 24.2 tools, test cases must validate against a more stringent schema. Unknown parameters are disallowed (prevents misspellings), select parameters must be specified by value (to prevent ambiguity and match the API), column parameters must be specified as integers, and parameters must be full qualified ('|' separation to include parent repeat, cond, and sections).
```

Introduced by [https://github.com/galaxyproject/galaxy/pull/18679](https://github.com/galaxyproject/galaxy/pull/18679).
<!-- END GENERATED: profile boundary reference (scripts/gen_profile_boundaries.py) -->
