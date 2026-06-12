# Planemo / `galaxy.tool_util` linter parity map

A reimplementation roadmap: every tool-XML linter `planemo lint` runs, mapped to where
it would live in **our** framework, and — the interesting column — whether we could
**auto-fix** it (our edge: planemo only *reports*).

## GTR coverage table (keyed by our rule)

The scannable view: every GTR rule we ship, the planemo linter(s) it covers, whether we
**detect** and/or **fix** it, the implementing **tier**, the **ruleset** it lands in, and a
one-line description. Rows with planemo "—" are our own best-practices with no planemo
equivalent. Use this to spot where a today-detect-only rule could grow a fix. *(Maintained as
rules land; upgrade-only codemods GTR007–GTR016 are applied by `upgrade`, not the default
`format`.)*

The **ruleset** column shows the *narrowest* named set a rule belongs to; the sets nest
(`cosmetic` ⊂ `default` = `iuc` ⊂ `strict`), so a rule is also in every wider set. `—` marks
the rules that are not ruleset-selectable: the upgrade-only rules (the `upgrade` command
applies them) and the opt-in `convert-help` conversion codemod (GTR092).
Membership is declared per-rule (`RuleMeta.rulesets`); see registry `docs/decisions.md` D15.

> The table below is **generated** from rule metadata by `uv run python -m
> scripts.gen_planemo_parity` (a freshness test keeps it in sync) — do not hand-edit
> between the markers. Each rule's planemo coverage comes from `RuleMeta.planemo_linters`;
> `—` = our own rule with no planemo equivalent (the cosmetic rules + the XSD-restoring
> repairs GTR006/GTR017). The planemo names also work in `--select` / `--ignore`.

<!-- BEGIN GENERATED: GTR coverage table (scripts/gen_planemo_parity.py) -->
| GTR | planemo linter(s) covered | detect | fix | tier | ruleset | description |
|---|---|:--:|:--:|---|---|---|
| GTR001 | — | ✓ | ✓ | fmt | cosmetic | Canonical 4-space indentation; no tabs. |
| GTR002 | — | ✓ | ✓ | codemod | default | Reorder every `<param>` element's attributes to the IUC convention. |
| GTR003 | — | ✓ | ✓ | fmt | cosmetic | One blank line between top-level children of `<tool>`. |
| GTR004 | — | ✓ | ✓ | fmt | cosmetic | Collapse empty-with-whitespace leaves to `<foo/>` form. |
| GTR005 | — | ✓ | ✓ | codemod | default | Reorder the root `<tool>` element's attributes to the documented prefix. |
| GTR006 | — | ✓ | ✓ | codemod | default | Repair near-miss spelling typos so a globally-invalid tool validates. |
| GTR007 | — | ✓ | ✓ | upgrade | — | Set profile= to the newest profile the tool validates at (bump-up-only). |
| GTR008 | — | ✓ | ✓ | upgrade | — | Upgrade a tool stuck at profile 19.01 toward 19.05 (name output `<data>`). |
| GTR009 | — | ✓ | ✓ | upgrade | — | Upgrade a tool stuck at profile 24.0 toward 24.1 (hoist collection filters). |
| GTR010 | ValidDatatypes | ✓ | ✓ | upgrade | — | Upgrade a tool stuck at profile 24.1 toward 24.2 (normalize format). |
| GTR011 | — | ✓ | ✓ | upgrade | — | Upgrade a tool stuck at profile 25.1 toward 26.0 (drop `<trackster_conf>`). |
| GTR012 | — | ✓ | ✓ | upgrade | — | Iteratively upgrade a tool toward the latest profile. |
| GTR013 | XMLOrder | ✓ | ✓ | codemod | default | Reorder `<tool>` child elements to the IUC convention. |
| GTR014 | — | ✓ | ✓ | upgrade | — | Strip surrounding whitespace from `<data from_work_dir>` (literal at profile >= 21.09). |
| GTR015 | OutputsFormatInput | ✓ | ✓ | upgrade | — | Replace output `<data format="input">` with format_source for a tool with a sole data input (qualified name when nested). |
| GTR016 | CommandInterpreterDeprecated | ✓ | ✓ | upgrade | — | Inline a deprecated `<command interpreter=I>`script ...`</command>` as `<command>`I '$__tool_directory__/script' ...`</command>` (any non-empty interpreter, literal-script first token). |
| GTR017 | — | ✓ | ✓ | codemod | default | Normalize Python-style boolean attribute values (True/Yes/…) to canonical xs:boolean so a globally-invalid tool validates. |
| GTR018.1 | — | ✓ | ✓ | codemod | default | Wrap a pure-text `<command>` body in CDATA (IUC #34). |
| GTR018.2 | — | ✓ | ✗ | check | strict | `<command>` CDATA residual the fix can't reach (mixed-content / ]]>). |
| GTR019.1 | — | ✓ | ✓ | codemod | default | Wrap a pure-text `<help>` body in CDATA (IUC #42). |
| GTR019.2 | — | ✓ | ✗ | check | strict | `<help>` CDATA residual the fix can't reach (mixed-content / ]]>). |
| GTR020.1 | — | ✓ | ✓ | codemod | default | Single-quote provably-single-valued Cheetah variables in `<command>` (bare single-token params, $__…__ path built-ins, space-free attrs). |
| GTR020.2 | — | ✓ | ✗ | check | strict | Single-quote `<command>` Cheetah vars: the non-provable residual. |
| GTR021 | TestsMissing | ✓ | ✗ | check | strict | Tool should ship at least one functional `<test>`. |
| GTR023 | ToolIDValid, ToolIDWhitespace | ✓ | ✗ | check | strict | Tool id should use lowercase letters, digits, and '_.+-'. |
| GTR024 | ToolVersionPEP404 | ✓ | ✗ | check | strict | Tool version should be PEP 440 or a @...@ version macro. |
| GTR025 | — | ✓ | ✗ | check | strict | Tool should declare `<requirements>`. |
| GTR026 | StdIOAbsence, StdIOAbsenceLegacy | ✓ | ✗ | check | strict | Tool should declare error handling (detect_errors or `<stdio>`). |
| GTR027 | BioToolsValid, EDAMTermsValid | ✓ | ✗ | check | strict | Tool should declare EDAM topics/operations or `<xrefs>`. |
| GTR028 | HelpEmpty, HelpMissing | ✓ | ✗ | check | strict | Tool should provide non-empty `<help>`. |
| GTR029 | — | ✓ | ✗ | check | strict | Tool should provide a non-empty `<description>`. |
| GTR032 | — | ✓ | ✗ | check | strict | Join shell commands with && (a lone & backgrounds the first). |
| GTR033 | RequirementVersionMissing | ✓ | ✗ | check | strict | Package `<requirement>`s should pin a version. |
| GTR034 | — | ✓ | ✗ | check | strict | Input `<param>` is never referenced in the tool. |
| GTR035.1 | RequirementVersionWhitespace | ✓ | ✓ | codemod | default | Trim accidental leading/trailing whitespace from a `<requirement>` 'version' (a whitespace-bearing value never resolved — conda gets the spec verbatim; the `<tool>` 'name' trim is the GTR035.2 advisory). |
| GTR035.2 | ToolNameWhitespace | ✓ | ✗ | check | strict | A `<tool>` 'name' should have no leading/trailing whitespace (display-contract residual of GTR035; report-only). |
| GTR036 | OutputsOutput | ✓ | ✓ | codemod | default | Replace a deprecated `<outputs>``<output type="data">` with `<data>`, and `<output type="collection">` with `<collection>` via Galaxy's own attribute remap (expression / degenerate outputs are left for the advisory check). |
| GTR037 | InputsNameRedundantArgument | ✓ | ✓ | codemod | default | Drop a `<param>` 'name' that equals the name Galaxy derives from its 'argument' (redundant; argument implies the same name). |
| GTR038 | CitationsMissing, CitationsNoText, CitationsNoValid | ✓ | ✗ | check | strict | Tool should declare a non-empty `<citation>` (doi/bibtex). |
| GTR039 | CommandTODO, HelpTODO | ✓ | ✗ | check | strict | `<command>`/`<help>` should not contain 'TODO' placeholder text. |
| GTR040 | OutputsNameDuplicated | ✓ | ✗ | check | strict | Output `<data>`/`<collection>` names must be unique. |
| GTR041 | OutputsNameInvalidCheetah | ✓ | ✗ | check | strict | Output name should be a valid Cheetah placeholder. |
| GTR042 | OutputsCollectionType | ✓ | ✗ | check | strict | Output `<collection>` should declare a structure 'type'. |
| GTR043 | OutputsFormatSourceIncomp | ✓ | ✗ | check | strict | An output should not set both format_source and format/ext. |
| GTR044 | CommandEmpty, CommandMissing | ✓ | ✗ | check | strict | Tool should define a non-empty `<command>`. |
| GTR045 | ToolProfileInvalid | ✓ | ✗ | check | strict | A declared profile should be a valid `<year>`.`<minor>` version. |
| GTR046 | RequirementNameMissing | ✓ | ✗ | check | strict | A package `<requirement>` must name its package. |
| GTR047 | ToolVersionWhitespace | ✓ | ✗ | check | strict | Tool version should not be wrapped in whitespace. |
| GTR048 | OutputsMissing | ✓ | ✗ | check | strict | Tool should define an `<outputs>` section. |
| GTR049 | OutputsFormat | ✓ | ✗ | check | strict | Each output should define its datatype format. |
| GTR050 | OutputsLabelDuplicatedFilter, OutputsLabelDuplicatedNoFilter | ✓ | ✗ | check | strict | Outputs should not share an explicit label. |
| GTR051 | ContainerImageShape | ✓ | ✗ | check | strict | A `<container>` identifier should match a recognized shape. |
| GTR052 | OutputsFilterExpression | ✓ | ✗ | check | strict | An output `<filter>` should be a valid Python expression. |
| GTR053 | StdIORegex | ✓ | ✗ | check | strict | A `<stdio>` `<regex match>` should be a valid regular expression. |
| GTR054 | InputsName | ✓ | ✗ | check | strict | An input `<param>` must declare a name or argument. |
| GTR055 | InputsNameEmpty, InputsNameValid | ✓ | ✗ | check | strict | An input `<param>` name must be a valid Cheetah placeholder. |
| GTR056 | InputsNameDuplicate | ✓ | ✗ | check | strict | Input `<param>` names must be unique within their scope. |
| GTR057 | InputsNameDuplicateOutput | ✓ | ✗ | check | strict | An output name must not duplicate an input parameter name. |
| GTR058 | InputsSelectOptionsDef, InputsSelectOptionsDefConditional | ✓ | ✗ | check | strict | A select parameter must define its options exactly one valid way. |
| GTR059 | InputsSelectOptionValueMissing | ✓ | ✗ | check | strict | A static select `<option>` must carry a value. |
| GTR060 | InputsSelectOptionDuplicateText, InputsSelectOptionDuplicateValue | ✓ | ✗ | check | strict | A select's static options should have distinct values and text. |
| GTR061 | InputsSelectOptionsMultiple | ✓ | ✗ | check | strict | A select may have at most one `<options>` element. |
| GTR062 | InputsSelectOptionsDefinesOptions | ✓ | ✗ | check | strict | A dynamic `<options>` element must define an option source. |
| GTR063 | InputsSelectOptionsFromDatasetAndDatatable, InputsSelectOptionsMetaFileKey | ✓ | ✗ | check | strict | A dynamic `<options>` source combination must be coherent. |
| GTR064 | InputsSelectDynamicOptions, InputsSelectOptionsDeprecatedAttr | ✓ | ✗ | check | strict | A select should not use a deprecated options mechanism. |
| GTR065 | ValidatorAttribIncompatible, ValidatorParamIncompatible | ✓ | ✗ | check | strict | A `<validator>` must be compatible with its param type and attributes. |
| GTR066 | ValidatorHasNoText, ValidatorHasText | ✓ | ✗ | check | strict | A `<validator>` body should match its type (expr/regex carry text). |
| GTR067 | ValidatorExpression, ValidatorExpressionFuture | ✓ | ✗ | check | strict | An expression/regex `<validator>` body must be valid. |
| GTR068 | ValidatorDatasetMetadataEqualValue, ValidatorDatasetMetadataEqualValueOrJson, ValidatorMetadataCheckSkip, ValidatorMetadataName, ValidatorMinMax, ValidatorTableName | ✓ | ✗ | check | strict | A `<validator>` must carry the attributes its type requires. |
| GTR069 | ConditionalParamType, ConditionalParamTypeBool | ✓ | ✗ | check | strict | A conditional's first `<param>` should be a select. |
| GTR070 | ConditionalParamIncompatibleAttributes | ✓ | ✗ | check | strict | A conditional's test param must not be optional or multiple. |
| GTR071 | ConditionalOptionMissing, ConditionalOptionMissingBoolean, ConditionalWhenMissing | ✓ | ✗ | check | strict | A conditional's `<when>` blocks must match the test-param options. |
| GTR072 | InputsMissing | ✓ | ✗ | check | strict | Most tools should define input parameters. |
| GTR073 | InputsTypeChildCombination | ✓ | ✗ | check | strict | A `<param>` child element must be valid for the param type. |
| GTR074 | InputsDataOptionsAttrib, InputsDataOptionsFilterAttribFiltersType, InputsDataOptionsFiltersRef, InputsDataOptionsFiltersType, InputsDataOptionsMultiple | ✓ | ✗ | check | strict | A data param's `<options>` (metadata filtering) must be valid. |
| GTR075 | InputsBoolDistinctValues, InputsBoolProblematic | ✓ | ✗ | check | strict | A boolean param's truevalue/falsevalue must be distinct and sane. |
| GTR076 | InputsSelectMandatoryCheckboxes, InputsSelectMultipleRadio, InputsSelectOptionalRadio, InputsSelectSingleCheckboxes | ✓ | ✗ | check | strict | A select's display must agree with multiple/optional. |
| GTR077 | InputsOptionsFiltersAllowedAttributes, InputsOptionsFiltersRequiredAttributes, InputsOptionsRemoveValueFilterRequiredAttributes | ✓ | ✗ | check | strict | An `<options>`/`<filter>` must carry the attributes its type allows. |
| GTR078 | InputsOptionsRegexFilterExpression | ✓ | ✗ | check | strict | A regexp `<options>`/`<filter>` value must be a valid regular expression. |
| GTR079 | InputsOptionsFiltersCheckReferences | ✓ | ✗ | check | strict | An `<options>`/`<filter>` ref/meta_ref must name a real parameter. |
| GTR080 | TestsAssertsHasNQuant, TestsAssertsHasSizeOrValueQuant, TestsAssertsHasSizeQuant, TestsAssertsMultiple | ✓ | ✗ | check | strict | A `<test>`'s assertions must be well formed. |
| GTR081 | TestsOutputCompareAttrib | ✓ | ✗ | check | strict | A test output's attributes must agree with its compare mode. |
| GTR082 | TestsOutputName | ✓ | ✗ | check | strict | A test `<output>` must declare a name. |
| GTR083 | TestsOutputCollectionCorresponding, TestsOutputCorresponding, TestsOutputDefined | ✓ | ✗ | check | strict | A test output must name a declared output of the matching kind. |
| GTR084 | TestsOutputCheckDiscovered, TestsOutputCollectionCheckDiscovered, TestsOutputCollectionCheckDiscoveredNested | ✓ | ✗ | check | strict | A discovering output's test must assert on the discovered datasets. |
| GTR085 | TestsParamInInputs | ✓ | ✗ | check | strict | A test `<param>` must name a tool input. |
| GTR086 | TestsExpectNumOutputsFailing, TestsOutputFailing | ✓ | ✗ | check | strict | An expect_failure test must not assert outputs. |
| GTR087 | TestsExpectNumOutputs | ✓ | ✗ | check | strict | A test should set expect_num_outputs when outputs are filtered. |
| GTR088 | TestsHasExpectations, TestsValid | ✓ | ✗ | check | strict | A test should assert outputs or expectations. |
| GTR089.1 | HelpInvalidRST | ✓ | ✓ | codemod | default | Repair deterministically-fixable invalid `<help>` reStructuredText (short title underlines, missing blank lines) behind a behaviour-preserving gate. |
| GTR089.2 | HelpInvalidRST | ✓ | ✗ | check | strict | A `<help>` body should be valid reStructuredText (the non-fixable residual). |
| GTR090 | OutputsFormatSourceReference, OutputsStructuredLikeReference | ✓ | ✗ | check | strict | Output structured_like/format_source must reference an input param. |
| GTR091 | InputsDataFormat | ✓ | ✗ | check | strict | A data param should declare the format(s) it accepts. |
| GTR092 | — | ✓ | ✓ | codemod | — | Convert an RST `<help>` body to Markdown (format="markdown") when the markdown-it rendering is provably equivalent to the docutils rendering (opt-in convert-help only; requires profile >= 24.2). |
| GTR093 | — | ✓ | ✓ | upgrade | — | Upgrade a tool stuck at profile 21.09 toward 22.01 (normalize collection_type + has_size Bytes; repair stdio exit_code/regex). |
| GTR094 | — | ✓ | ✓ | codemod | — | Factor a literal version="`<base>`+galaxy`<suffix>`" into @TOOL_VERSION@/@VERSION_SUFFIX@ tokens shared with the matching package requirement (opt-in tokenize-version only). |
| GTR095 | ToolIDMissing, ToolNameMissing, ToolVersionMissing | ✓ | ✗ | check | strict | Tool must declare a non-empty id, name, and version. |
| GTR096 | — | ✓ | ✓ | upgrade | — | Fully-qualify a flat `<test>` parameter name to its unique nested parent|...|child input path (required at profile >= 24.2). |
<!-- END GENERATED -->

The remaining unmapped planemo linters (the ~80 correctness checks + the advisory-by-design
ones) are in the per-module tables below; each becomes a new GTR row here as it's built.

## Method & source

`planemo lint` delegates tool-XML linting to **`galaxy.tool_util.lint`**, which loads the
`Linter` subclasses in `galaxy/tool_util/linters/*.py`. Read locally from the `galaxy-src`
clone at commit `c6e0ee3` (2026-06-01): **146 `Linter` subclasses across 14 modules**
(AST-extracted; not run). *Caveat:* this is the `galaxy.tool_util` set (the core of
`planemo lint`); planemo adds a few of its **own** linters (Tool Shed `.shed.yml` /
repo-metadata, URL reachability) that live in the planemo repo, **not cloned here** — so
they're out of this map. Re-extract with the AST script in the PR that added this doc.

## Legend

**Our tier** — where it lands in our seven-tier framework:
`parse` (tier 1 validate) · `fmt` (tier 3 cosmetic) · `codemod` (tier 2 structural fix) ·
`check` (tier 3.5 advisory, detect-only) · `upgrade` (profile-gated) · `n/a` (out of scope).

**Disposition:**
- **HAVE** — we already implement it (≈ an existing GTR), often as a *fixer*.
- **FIX** — *not* built, but **auto-fixable** → a candidate codemod/fmt rule (planemo only reports; this is where we win).
- **DETECT** — a correctness check that needs author intent; advisory like planemo (report, don't fix).
- **SKIP** — a `valid`/`info` *pass-state* reporter (the "all good" message of another check) or a positive counter — nothing to reimplement.

The `pass-state` (`valid`/`info`) linters are paired with their problem-reporting sibling
(e.g. `ToolVersionValid` ↔ `ToolVersionMissing`); we don't emit "all good" per rule, so
they're **SKIP**.

> **This map is an initial assessment.** The tier/fixability call for each row is a
> starting hypothesis — validated for real when the rule is actually built (TDD + corpus
> sweep), since "is this safely auto-fixable?" is exactly the behaviour-preservation
> question this project takes seriously (`soundness.md`, `behavior_preservation.md`).

## Summary

| Disposition | Count | Meaning |
|---|--:|---|
| **HAVE** | 117 | already covered (mostly as fixers / advisory checks). Incl. **GTR035** (`name`/req-`version` whitespace), **GTR036** (`<output type="data">`→`<data>`), **GTR037** (redundant `name`), **GTR038**/**GTR039** (citations/TODO), **GTR040–043** (output correctness), **GTR044–047** (command/profile/requirement-name/version-whitespace), **GTR048–050** (outputs present/format/label), **GTR051–053** (container shape, output-filter & stdio-regex validity), **GTR054–057** (input param naming/identity), **GTR058–060** (static select-option correctness), **GTR061–064** (dynamic select `<options>` correctness), **GTR065–068** (validator compatibility/text/expression/required-attrs), **GTR069–071** (conditional test-param + when/option correspondence), **GTR072–074** (inputs present / param type-child / data-options validity), **GTR075–076** (boolean values + select display idiom), **GTR077–079** (option-filter attributes/expression/references), **GTR080–084** (test assertions/compare/output-correspondence/discovered), **GTR085–088** (test param-in-inputs / expect-failure / expect-num-outputs / has-expectations), **GTR089** (help RST validity, docutils), 2026-06-06; **GTR090–091** (output structured_like/format_source reference integrity + data-param format), 2026-06-10; **GTR095** (id/name/version missing-or-empty — the tier-1-residual half of the trio: `version` is not XSD-required and `""` is XSD-valid), 2026-06-11 |
| **FIX** (new, auto-fixable) | 0 | **complete** — GTR035/036/037 shipped; the rest of the original FIX candidates reclassified to advisory/detect on inspection (identity-changing or no mechanical equivalent) |
| **DETECT** (new advisory) | 4 | correctness checks for the `check` tier (report-only). 55 GTR rules landed so far (GTR038–091 + GTR095) — the **entire `inputs.py` correctness surface**, **all mechanically-reimplementable `tests.py` checks**, and **help RST validity** (GTR089, via `docutils`), plus citations/TODO, output correctness, command/profile/requirement-name, version-whitespace, container/filter/regex validity, output reference integrity, data-param format, and the id/name/version missing-or-empty trio (GTR095). **Remaining DETECT** all need external infra: `TestsAssertionValidation`/`TestsCaseValidation` (2, need Galaxy's pydantic models), `ValidDatatypes`/`DatatypesCustomConf` (2, datatype registry / filesystem) |
| **SKIP** (pass-state) | ~14 | `valid`/`info` reporters — nothing to build |
| **n/a** (out of scope) | ~11 | CWL (9), filesystem (`required_files`), `ResourceRequirementExpression` |
| **Total** | 146 | |

> **Counts recomputed 2026-06-06** module-by-module after the `inputs.py` arc — the earlier
> running `~`-totals for DETECT/SKIP/n/a had drifted; these now sum to 146.

> **Alias-reconciled 2026-06-10.** The HAVE count is now *derivable from rule metadata*
> and pinned by a registry test (`test_planemo_aliases.py`): HAVE = aliased canonical
> linters (`RuleMeta.planemo_linters`) − `ValidDatatypes` (aliased on GTR010, the
> case-normalizer, but membership validation remains DETECT) + `XSD` (covered by tier-1
> `validate_tool`, deliberately alias-free). Eight under-declared aliases were added
> (GTR023 `ToolIDWhitespace`, GTR026 `StdIOAbsenceLegacy`, GTR038 `CitationsNoValid`,
> GTR068 `…OrJson`, GTR074 ×4) and `BioToolsValid` was re-marked **HAVE\*** for
> consistency with `EDAMTermsValid` (same GTR027 presence-check approximation), moving
> HAVE 110 → 111 / n-a 12 → 11. The canonical 146-name list is vendored beside the test.

> **Reclassified by homework (2026-06-06).** The whitespace cluster started as 4 "FIX"
> rows; building **GTR035** split it honestly: `name` + `requirement version` are
> behaviour-preserving to trim (**fixed**), but `id` + tool `version` are used *raw* as
> the tool's identity (trimming changes identity) → **advisory-by-design**. Expect
> similar per-rule reclassification as the rest are built — "FIX" is an upper bound, not
> a promise. Worked before/afters live in [`examples/planemo_fixable_issues.md`](examples/planemo_fixable_issues.md).

By our tier, for the **buildable** rows (HAVE + FIX + DETECT):
- **codemod** (structural fix): the FIX rows below + GTR013/015/016/**035** — ~15
- **check** (advisory): the DETECT bulk + the advisory HAVEs — **70 GTR check rules shipped**
  (GTR021–GTR095, detect-only), 4 planemo advisories still to build
- **parse/validate**: 1 (XSD)

**Headline:** planemo only *reports*; we *fix* the provably-safe subset (**GTR035/036/037**,
complete) and **detect the rest** as advisory `check`-tier rules. As of 2026-06-10 the check
tier has **70 rules** covering the whole `inputs.py` correctness surface, **all
mechanically-reimplementable `tests.py` checks**, **help RST validity** (GTR089, via
`docutils`), and **output reference integrity + data-param format** (GTR090–091), plus
citations, command, container, general, output, and stdio. Only ~4 planemo advisories
remain, all needing external infra: the two `tests.py` linters that need Galaxy's
pydantic models (`TestsAssertionValidation`, `TestsCaseValidation`), and datatypes
(registry/filesystem). The id/name/version trio is now covered by GTR095.

---

## citations.py (4)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| CitationsMissing | warn | check | **HAVE** | **GTR038** |
| CitationsNoText | error | check | **HAVE** | **GTR038** (empty doi/bibtex) |
| CitationsNoValid | warn | check | **HAVE** | **GTR038** subsumes it — fires on an empty `<citations>` (no `<citation>` children) |
| CitationsFound | valid | — | SKIP | pass-state |

## command.py (5)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| CommandInterpreterDeprecated | warn | codemod | **HAVE** | = **GTR016** (we inline `interpreter=`) |
| CommandMissing | error | check | **HAVE** | **GTR044** no `<command>` |
| CommandEmpty | error | check | **HAVE** | **GTR044** empty `<command>` body |
| CommandTODO | warn | check | **HAVE** | **GTR039** |
| CommandInfo | info | — | SKIP | pass-state |

## containers.py (1)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| ContainerImageShape | warn | check | **HAVE** | **GTR051** recognized container shape (macro-token identifiers skipped) |

## cwl.py (9) — **all n/a** (CWL, not Galaxy tool XML)

`CWLValid` · `CWLInValid` · `CWLVersionMissing` · `CWLVersionUnknown` · `CWLVersionGood` ·
`CWLDockerMissing` · `CWLDockerGood` · `CWLDescriptionMissing` · `CWLHelpTODO` → **n/a**.

## datatypes.py (2)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| ValidDatatypes | error | check | DETECT | `format`/`ext` is a real datatype; we *normalize case* in `upgrade` (GTR010) but don't validate membership. The name is still selectable — `--select ValidDatatypes` resolves to GTR010 (the closest rule we have) — but this row stays DETECT until a real registry-membership check exists |
| DatatypesCustomConf | warn | check | DETECT (deferred) | needs the **filesystem** (a sibling `datatypes_conf.xml` on disk), not the parsed tree — out of the raw-tree check tier's reach, like `required_files.py` |

## general.py (19)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| ToolNameWhitespace | warn | codemod | **HAVE** | **GTR035** trims it (display-only — safe) |
| RequirementVersionWhitespace | warn | codemod | **HAVE** | **GTR035** trims it (whitespace breaks the conda solve, so a working tool never has it — repair-safe) |
| ToolVersionWhitespace | warn | check | **HAVE** | **GTR047** detect-only **by design**: trimming `version` changes the tool's version identity (used raw); see §33 |
| ToolIDWhitespace | warn | check | **HAVE** | caught by **GTR023** (a whitespace id fails the id charset) |
| ToolIDValid | valid/err | check | **HAVE** | id charset = **GTR023** |
| RequirementVersionMissing | warn | check | **HAVE** | = **GTR033** (pin requirement version) |
| EDAMTermsValid | warn | check | **HAVE\*** | ≈ **GTR027**; full EDAM-ontology validation needs network |
| ToolVersionPEP404 | warn | check | **HAVE** | = **GTR024** (version not PEP 440) |
| ToolProfileInvalid | error | check | **HAVE** | **GTR045** profile not `<year>.<minor>` |
| RequirementNameMissing | error | check | **HAVE** | **GTR046** package requirement names no package |
| ToolVersionMissing | error | check | **HAVE** | **GTR095** — NOT covered by tier-1 `validate`: `version` is not XSD-required (Galaxy defaults it to `1.0.0`), so the check is the only guard (check D35) |
| ToolNameMissing | error | check | **HAVE** | **GTR095** — a *missing* `name` also fails tier-1 `validate` (XSD `use="required"`); the check adds the XSD-valid `name=""` case, with planemo's name→id fallback (check D35) |
| ToolIDMissing | error | check | **HAVE** | **GTR095** — a *missing* `id` also fails tier-1 `validate` (XSD `use="required"`); the check adds the XSD-valid `id=""` case (check D35) |
| ResourceRequirementExpression | warn | n/a | — | unsupported feature warning |
| BioToolsValid | warn | check | **HAVE\*** | ≈ **GTR027** (xrefs/EDAM presence); full bio.tools validation needs network — same approximation as `EDAMTermsValid` |
| ToolVersionValid · ToolNameValid · ToolProfileLegacy · ToolProfileValid | valid | — | SKIP | pass-states |

## help.py (6)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| HelpMissing | warn | check | **HAVE** | = **GTR028** |
| HelpEmpty | warn | check | **HAVE** | GTR028 (non-empty help) |
| HelpTODO | warn | check | **HAVE** | **GTR039** |
| HelpInvalidRST | warn | check | **HAVE** | **GTR089** RST validity via `docutils` (Galaxy's `rst_to_html`); `format="markdown"` help skipped |
| HelpPresent · HelpValidRST | valid | — | SKIP | pass-states |

## inputs.py (57) — the big correctness surface

Almost all **DETECT** (`check` tier): param/option/validator/conditional correctness that
needs author intent. The **FIX** candidates (auto-fixable, our edge):

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| InputsNameRedundantArgument | warn | codemod | **HAVE** | **GTR037** drops it when `name == argument.lstrip('-').replace('-','_')` (§35) |
| InputsName | error | check | **HAVE** | **GTR054** param has neither `name` nor `argument` |
| InputsNameEmpty / InputsNameValid | error/warn | check | **HAVE** | **GTR055** name empty or not a valid Cheetah placeholder (macro-token names skipped) |
| InputsNameDuplicate | error | check | **HAVE** | **GTR056** duplicate qualified param path (disjoint `<when>` branches OK) |
| InputsNameDuplicateOutput | error | check | **HAVE** | **GTR057** output name duplicates an input param name |
| InputsSelectOptionsDef / …DefConditional | error | check | **HAVE** | **GTR058** select defines options exactly one valid way (macro-`<expand>` selects skipped) |
| InputsSelectOptionValueMissing | error | check | **HAVE** | **GTR059** static `<option>` has no `value` |
| InputsSelectOptionDuplicateValue / …Text | error | check | **HAVE** | **GTR060** duplicate option `(value, selected)` / `(text, selected)` |
| InputsSelectOptionsMultiple | error | check | **HAVE** | **GTR061** more than one `<options>` element |
| InputsSelectOptionsDefinesOptions | error | check | **HAVE** | **GTR062** `<options>` with no source (macro-`<expand>` skipped) |
| InputsSelectOptionsFromDatasetAndDatatable / …MetaFileKey | error | check | **HAVE** | **GTR063** `from_dataset`/`from_data_table`/`meta_file_key` coherence |
| InputsSelectDynamicOptions / InputsSelectOptionsDeprecatedAttr | warn | check | **HAVE** | **GTR064** deprecated `dynamic_options` attr / `from_file`/`from_parameter`/`transform_lines`/`options_filter_attribute` (advisory — needs restructuring, not mechanically fixable) |
| ValidatorParamIncompatible / ValidatorAttribIncompatible | error | check | **HAVE** | **GTR065** validator type/attribute compatibility matrices |
| ValidatorHasText / ValidatorHasNoText | error/warn | check | **HAVE** | **GTR066** expr/regex validators carry text; others do not |
| ValidatorExpression / ValidatorExpressionFuture | error/warn | check | **HAVE** | **GTR067** expr/regex body compiles (`@…@` macro bodies skipped) |
| ValidatorMinMax / …MetadataCheckSkip / …TableName / …MetadataName / …DatasetMetadataEqualValue / …OrJson | error | check | **HAVE** | **GTR068** validator type carries its required attribute(s) |
| ConditionalParamType / ConditionalParamTypeBool | error/warn | check | **HAVE** | **GTR069** test param is `select` (boolean discouraged) |
| ConditionalParamIncompatibleAttributes | warn | check | **HAVE** | **GTR070** test param not `optional`/`multiple` |
| ConditionalWhenMissing / ConditionalOptionMissing / …Boolean | warn | check | **HAVE** | **GTR071** `<when>` ↔ option correspondence (macro-`<expand>` skipped) |
| InputsMissing | warn | check | **HAVE** | **GTR072** no input params (datasource + macro-`<expand>` skipped) |
| InputsTypeChildCombination | error | check | **HAVE** | **GTR073** `<options>`/`<option>`/`<column>` valid for the param type |
| InputsDataOptionsMultiple / …Attrib / …FilterAttribFiltersType / …FiltersType / …FiltersRef | error | check | **HAVE** | **GTR074** data param `<options>` metadata-filtering validity (faithful to planemo strictness) |
| InputsBoolDistinctValues / InputsBoolProblematic | warn/error | check | **HAVE** | **GTR075** boolean truevalue/falsevalue distinct + not swapped |
| InputsSelectSingleCheckboxes / …MandatoryCheckboxes / …MultipleRadio / …OptionalRadio | error | check | **HAVE** | **GTR076** `display="checkboxes"/"radio"` ↔ `multiple`/`optional` consistency |
| InputsOptionsFiltersRequiredAttributes / …RemoveValueFilterRequiredAttributes / …FiltersAllowedAttributes | error/warn | check | **HAVE** | **GTR077** `<filter>` attribute schema per filter type |
| InputsOptionsRegexFilterExpression | error | check | **HAVE** | **GTR078** `regexp` filter `value` compiles |
| InputsOptionsFiltersCheckReferences | error | check | **HAVE** | **GTR079** filter `ref`/`meta_ref` resolves (macro-using tools skipped) |
| InputsDataFormat | warn | check | **HAVE** | **GTR091** data param with no `format` (defaults to `data`; fix = risky, stays advisory) |

**Group view — the whole `inputs.py` correctness surface is now HAVE**
(`InputsDataFormat` was the last holdout, closed by **GTR091**; the
`InputsNum`/datasource info linters are SKIP):
- *naming/identity:* **HAVE** — `InputsName` (GTR054), `InputsNameEmpty`/`InputsNameValid` (GTR055), `InputsNameDuplicate` (GTR056), `InputsNameDuplicateOutput` (GTR057)
- *static select options:* **HAVE** — `InputsSelectOptionsDef`/`…DefConditional` (GTR058), `InputsSelectOptionValueMissing` (GTR059), `InputsSelectOptionDuplicateValue`/`…Text` (GTR060)
- *dynamic select `<options>`:* **HAVE** — `InputsSelectOptionsMultiple` (GTR061), `…DefinesOptions` (GTR062), `…FromDatasetAndDatatable`/`…MetaFileKey` (GTR063), `InputsSelectDynamicOptions`/`…DeprecatedAttr` (GTR064)
- *type/structure:* **HAVE** — `InputsMissing` (GTR072), `InputsTypeChildCombination` (GTR073), `InputsDataOptionsMultiple`/`…Attrib`/`…FilterAttribFiltersType`/`…FiltersType`/`…FiltersRef` (GTR074)
- *option filters:* **HAVE** — `InputsOptionsFiltersRequiredAttributes`/`…RemoveValueFilterRequiredAttributes`/`…FiltersAllowedAttributes` (GTR077), `InputsOptionsRegexFilterExpression` (GTR078), `InputsOptionsFiltersCheckReferences` (GTR079)
- *display/idiom:* **HAVE** — `InputsBoolDistinctValues`/`InputsBoolProblematic` (GTR075), `InputsSelectSingleCheckboxes`/`…MandatoryCheckboxes`/`…MultipleRadio`/`…OptionalRadio` (GTR076)
- *validators:* **HAVE** — form: `ValidatorParamIncompatible`/`…AttribIncompatible` (GTR065), `ValidatorHasText`/`…HasNoText` (GTR066), `ValidatorExpression`/`…ExpressionFuture` (GTR067); required attributes: `ValidatorMinMax`/`…MetadataCheckSkip`/`…TableName`/`…MetadataName`/`…DatasetMetadataEqualValue`/`…OrJson` (GTR068)
- *conditionals:* **HAVE** — `ConditionalParamType`/`…ParamTypeBool` (GTR069), `ConditionalParamIncompatibleAttributes` (GTR070), `ConditionalWhenMissing`/`…OptionMissing`/`…OptionMissingBoolean` (GTR071)

**SKIP:** `InputsNum` · `InputsMissingDataSource` · `InputsDatasourceTags` (info).

## output.py (14)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| OutputsOutput | warn | codemod | **HAVE** | **GTR036** rewrites `<output type="data">` → `<data>`; `type="collection"` / expression outputs left advisory (§34) |
| OutputsFormatInput | warn | upgrade | **HAVE** | = **GTR015** (`format="input"` → `format_source`) |
| OutputsMissing | warn | check | **HAVE** | **GTR048** no `<outputs>` (macro-using tools skipped — raw-tree boundary) |
| OutputsNameInvalidCheetah | warn | check | **HAVE** | **GTR041** name not a valid placeholder (`^[a-zA-Z_]\w*$`) |
| OutputsNameDuplicated | error | check | **HAVE** | **GTR040** duplicate `<data>`/`<collection>` name |
| OutputsFilterExpression | warn | check | **HAVE** | **GTR052** filter is valid Python (macro-token filters skipped) |
| OutputsLabelDuplicatedFilter / NoFilter | warn | check | **HAVE** | **GTR050** duplicate *explicit* label; default-label collisions skipped (low-noise narrowing) |
| OutputsCollectionType | warn | check | **HAVE** | **GTR042** collection without `type` (lenient: accepts `type_source`/`structured_like`) |
| OutputsFormat | warn | check | **HAVE** | **GTR049** output without a format (galaxy.json-metadata + macro-`<expand>` exempt) |
| OutputsFormatSourceIncomp | warn | check | **HAVE** | **GTR043** both `format`/`ext` + `format_source` |
| OutputsStructuredLikeReference · OutputsFormatSourceReference | warn | check | **HAVE** | **GTR090** structured_like/format_source must resolve (top-level param, qualified `a\|b` ref, or — format_source — a sibling output); macro-using tools skipped (an `<expand>` may supply the referent: 254/360 corpus candidates) |
| OutputsNumber | info | — | SKIP | |

## required_files.py (1) — **n/a** (filesystem)

`RequiredFilesExist` (error) → **n/a** (needs the file tree).

## stdio.py (3)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| StdIOAbsence / StdIOAbsenceLegacy | info | check | **HAVE** | ≈ **GTR026** (error handling present) |
| StdIORegex | error | check | **HAVE** | **GTR053** `<regex match>` must compile |

## tests.py (23) — the remaining DETECT frontier

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| TestsMissing | warn | check | **HAVE** | = **GTR021** |
| TestsAssertsMultiple / …HasNQuant / …HasSizeQuant / …HasSizeOrValueQuant | error | check | **HAVE** | **GTR080** assertion well-formedness |
| TestsOutputCompareAttrib | error | check | **HAVE** | **GTR081** output attr ↔ `compare` mode |
| TestsOutputName | error | check | **HAVE** | **GTR082** test `<output>` needs a name |
| TestsOutputDefined / …Corresponding / …CollectionCorresponding | error | check | **HAVE** | **GTR083** test output names a declared output of the matching kind (macro-skip) |
| TestsOutputCheckDiscovered / …CollectionCheckDiscovered / …Nested | error | check | **HAVE** | **GTR084** a test of a discovering output asserts count/elements |
| TestsParamInInputs | error | check | **HAVE** | **GTR085** test `<param>` names a tool input (macro-skip) |
| TestsOutputFailing / TestsExpectNumOutputsFailing | error | check | **HAVE** | **GTR086** `expect_failure` test asserts no outputs |
| TestsExpectNumOutputs | warn | check | **HAVE** | **GTR087** set `expect_num_outputs` for filtered outputs |
| TestsHasExpectations / TestsValid | warn | check | **HAVE** | **GTR088** a test asserts outputs/expectations (TestsValid subsumed) |
| TestsMissingDatasource · TestsNoValid | info/valid | — | SKIP | |
| TestsAssertionValidation · TestsCaseValidation | warn/error | check | DETECT (deferred) | need Galaxy's pydantic assertion / parameter models (not a raw-tree query) |

The mechanically-reimplementable `tests.py` linters are now all **HAVE**; only the two
pydantic-model-dependent ones (`TestsAssertionValidation`, `TestsCaseValidation`) remain.

## xml_order.py (1)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| XMLOrder | warn | codemod | **HAVE** | = **GTR013** (we *reorder*, planemo only flags) |

## xsd.py (1)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| XSD | error | parse | **HAVE** | = tier-1 `validate_tool` (profile-aware XSD) |

---

## The "fix what they can't" shortlist (14 FIX candidates)

Planemo only *reports* these; we could auto-fix them. Highest-confidence first:

1. **Whitespace strips** (fmt): `ToolVersionWhitespace`, `ToolNameWhitespace`,
   `ToolIDWhitespace`, `RequirementVersionWhitespace` — trim a leading/trailing-space
   attribute value. Trivially behaviour-preserving; a natural fmt-tier batch (one rule).
2. **`<output>` → `<data>`/`<collection>`** (codemod, `OutputsOutput`) — a tag rename to
   the modern element; needs the type decision (data vs collection) — mostly `data`.
3. **Drop redundant `name`** (codemod, `InputsNameRedundantArgument`) — when `argument`
   implies the same name; behaviour-preserving attribute removal.
4. **Deprecated select-options attributes** (codemod, `InputsSelectDynamicOptions`,
   `InputsSelectOptionsDeprecatedAttr`) — rewrite to the current `<options>` form; needs
   per-attribute soundness checks.

These are the right *first* reimplementation targets: they exercise the codemod + fmt
tiers, and each is a concrete "we fix, planemo reports" demonstration. The ~78 DETECT
checks then grow the `check` tier toward planemo parity (report-only), and the ~20 n/a
rows (CWL, filesystem, network) stay out of scope.
