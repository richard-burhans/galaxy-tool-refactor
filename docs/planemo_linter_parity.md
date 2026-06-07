# Planemo / `galaxy.tool_util` linter parity map

A reimplementation roadmap: every tool-XML linter `planemo lint` runs, mapped to where
it would live in **our** framework, and — the interesting column — whether we could
**auto-fix** it (our edge: planemo only *reports*).

## GTR coverage table (keyed by our rule)

The scannable view: every GTR rule we ship, the planemo linter(s) it covers, whether we
**detect** and/or **fix** it, the implementing **tier**, and a one-line description. Rows
with planemo "—" are our own best-practices with no planemo equivalent. Use this to spot
where a today-detect-only rule could grow a fix. *(Maintained as rules land; upgrade-only
codemods GTR007–GTR016 are applied by `upgrade`, not the default `format`.)*

| GTR | planemo linter(s) covered | detect | fix | tier | description |
|---|---|:--:|:--:|---|---|
| GTR001 | — | ✓ | ✓ | fmt | canonical 4-space indentation |
| GTR002 | — | ✓ | ✓ | codemod | reorder `<param>` attributes to IUC order |
| GTR003 | — | ✓ | ✓ | fmt | one blank line between top-level `<tool>` children |
| GTR004 | — | ✓ | ✓ | fmt | collapse empty-with-whitespace leaves to `<foo/>` (skips content-bearing) |
| GTR005 | — | ✓ | ✓ | codemod | reorder root `<tool>` attributes |
| GTR006 | (XSD) | ✓ | ✓ | codemod | repair near-miss typos so an invalid tool validates |
| GTR007 | ToolProfile\* | ✓ | ✓ | upgrade | bump an inline `@PROFILE@` / `profile=` to newest valid |
| GTR008 | — | ✓ | ✓ | upgrade | 19.01→19.05 migration (name unnamed outputs) |
| GTR009 | — | ✓ | ✓ | upgrade | 24.0→24.1 (hoist identical collection filters) |
| GTR010 | ValidDatatypes (case) | ✓ | ✓ | upgrade | 24.1→24.2 format/ftype lowercase-token normalize |
| GTR011 | — | ✓ | ✓ | upgrade | 25.1→26.0 (drop obsolete `<trackster_conf>`) |
| GTR012 | — | ✓ | ✓ | upgrade | orchestrator: loop to newest reachable profile |
| GTR013 | **XMLOrder** | ✓ | ✓ | codemod | reorder `<tool>` child elements (planemo only flags) |
| GTR014 | — | ✓ | ✓ | upgrade | `from_work_dir` strip (<21.09 crossing) |
| GTR015 | **OutputsFormatInput** | ✓ | ✓ | upgrade | `format="input"`→`format_source` (single data input) |
| GTR016 | **CommandInterpreterDeprecated** | ✓ | ✓ | codemod | inline a deprecated `interpreter=` (planemo only flags) |
| GTR017 | (XSD) | ✓ | ✓ | codemod | normalize Python-style booleans to `xs:boolean` |
| GTR018.1 | — | ✓ | ✓ | codemod | wrap a pure-text `<command>` in CDATA |
| GTR018.2 | — | ✓ | ✗ | check | `<command>` CDATA residual (mixed-content / `]]>` / `\r`) |
| GTR019.1 | — | ✓ | ✓ | codemod | wrap a pure-text `<help>` in CDATA |
| GTR019.2 | — | ✓ | ✗ | check | `<help>` CDATA residual |
| GTR020.1 | — | ✓ | ✓ | codemod | single-quote provably-single-valued `<command>` Cheetah vars |
| GTR020.2 | — | ✓ | ✗ | check | unquoted-`$var` non-provable residual |
| GTR021 | **TestsMissing** | ✓ | ✗ | check | tool should ship a functional `<test>` |
| GTR023 | **ToolIDValid** | ✓ | ✗ | check | tool id charset (lowercase / `_.+-`) |
| GTR024 | **ToolVersionPEP404** | ✓ | ✗ | check | version should be PEP 440 (or a `@…@` macro) |
| GTR025 | — | ✓ | ✗ | check | tool should declare `<requirements>` |
| GTR026 | **StdIOAbsence** | ✓ | ✗ | check | declare error handling (`detect_errors`/`<stdio>`) |
| GTR027 | **EDAMTermsValid**, BioToolsValid | ✓ | ✗ | check | declare EDAM topics/operations or `<xrefs>` |
| GTR028 | **HelpMissing**, HelpEmpty | ✓ | ✗ | check | provide non-empty `<help>` |
| GTR029 | — | ✓ | ✗ | check | provide a non-empty `<description>` |
| GTR032 | — | — | ✗ | check | lone `&` vs `&&` (no-op stub; needs a shell parser) |
| GTR033 | **RequirementVersionMissing** | ✓ | ✗ | check | package `<requirement>`s should pin a version |
| GTR034 | — | ✓ | ✗ | check | input `<param>` never referenced |
| GTR035 | **ToolNameWhitespace**, **RequirementVersionWhitespace** | ✓ | ✓ | codemod | trim accidental whitespace (name / requirement version) |
| GTR036 | **OutputsOutput** | ✓ | ✓ | codemod | `<output type="data">` → `<data>` |
| GTR037 | **InputsNameRedundantArgument** | ✓ | ✓ | codemod | drop a `<param>` `name` its `argument` implies |
| GTR038 | CitationsMissing, CitationsNoText | ✓ | ✗ | check | tool should declare a non-empty `<citation>` |
| GTR039 | CommandTODO, HelpTODO | ✓ | ✗ | check | `<command>`/`<help>` should not contain `TODO` placeholder text |
| GTR040 | **OutputsNameDuplicated** | ✓ | ✗ | check | output `<data>`/`<collection>` names must be unique |
| GTR041 | OutputsNameInvalidCheetah | ✓ | ✗ | check | output `name` must be a valid Cheetah placeholder |
| GTR042 | OutputsCollectionType | ✓ | ✗ | check | output `<collection>` should declare a structure `type` |
| GTR043 | OutputsFormatSourceIncomp | ✓ | ✗ | check | output should not set both `format_source` and `format`/`ext` |
| GTR044 | **CommandMissing**, CommandEmpty | ✓ | ✗ | check | tool should define a non-empty `<command>` |
| GTR045 | ToolProfileInvalid | ✓ | ✗ | check | declared `profile` must be a valid `<year>.<minor>` version |
| GTR046 | **RequirementNameMissing** | ✓ | ✗ | check | a package `<requirement>` must name its package |
| GTR047 | ToolVersionWhitespace | ✓ | ✗ | check | tool `version` should not be wrapped in whitespace (advisory-by-design — identity) |
| GTR048 | **OutputsMissing** | ✓ | ✗ | check | tool should define an `<outputs>` section |
| GTR049 | **OutputsFormat** | ✓ | ✗ | check | each output should define its datatype format |
| GTR050 | OutputsLabelDuplicated\* | ✓ | ✗ | check | outputs should not share an *explicit* `label` (low-noise narrowing) |
| GTR051 | **ContainerImageShape** | ✓ | ✗ | check | a `<container>` identifier should match a recognized shape |
| GTR052 | **OutputsFilterExpression** | ✓ | ✗ | check | an output `<filter>` should be a valid Python expression |
| GTR053 | **StdIORegex** | ✓ | ✗ | check | a `<stdio>` `<regex match>` should be a valid regular expression |
| GTR054 | InputsName | ✓ | ✗ | check | an input `<param>` must declare a `name` or `argument` |
| GTR055 | InputsNameEmpty, InputsNameValid | ✓ | ✗ | check | an input `<param>` name must be a valid Cheetah placeholder |
| GTR056 | InputsNameDuplicate | ✓ | ✗ | check | input `<param>` names must be unique within their scope |
| GTR057 | InputsNameDuplicateOutput | ✓ | ✗ | check | an output name must not duplicate an input param name |
| GTR058 | InputsSelectOptionsDef, …DefConditional | ✓ | ✗ | check | a `select` must define options exactly one valid way |
| GTR059 | InputsSelectOptionValueMissing | ✓ | ✗ | check | a static `select` `<option>` must carry a `value` |
| GTR060 | InputsSelectOptionDuplicateValue, …Text | ✓ | ✗ | check | a `select`'s static options should be distinct |
| GTR061 | InputsSelectOptionsMultiple | ✓ | ✗ | check | a `select` may have at most one `<options>` element |
| GTR062 | InputsSelectOptionsDefinesOptions | ✓ | ✗ | check | a dynamic `<options>` must define an option source |
| GTR063 | InputsSelectOptionsFromDatasetAndDatatable, …MetaFileKey | ✓ | ✗ | check | a dynamic `<options>` source combination must be coherent |
| GTR064 | InputsSelectDynamicOptions, …DeprecatedAttr | ✓ | ✗ | check | a `select` should not use a deprecated options mechanism |
| GTR065 | ValidatorParamIncompatible, …AttribIncompatible | ✓ | ✗ | check | a `<validator>` must be compatible with its param type + attributes |
| GTR066 | ValidatorHasText, ValidatorHasNoText | ✓ | ✗ | check | a `<validator>` body should match its type (expr/regex carry text) |
| GTR067 | ValidatorExpression, …ExpressionFuture | ✓ | ✗ | check | an `expression`/`regex` `<validator>` body must be valid |
| GTR068 | ValidatorMinMax, …MetadataCheckSkip, …TableName, …MetadataName, …DatasetMetadataEqualValue, …OrJson | ✓ | ✗ | check | a `<validator>` must carry the attributes its type requires |
| GTR069 | ConditionalParamType, …ParamTypeBool | ✓ | ✗ | check | a `<conditional>`'s first `<param>` should be a `select` |
| GTR070 | ConditionalParamIncompatibleAttributes | ✓ | ✗ | check | a `<conditional>` test param must not be optional/multiple |
| GTR071 | ConditionalWhenMissing, …OptionMissing, …OptionMissingBoolean | ✓ | ✗ | check | a `<conditional>`'s `<when>` blocks must match the test options |
| GTR072 | InputsMissing | ✓ | ✗ | check | most tools should define input parameters |
| GTR073 | InputsTypeChildCombination | ✓ | ✗ | check | a `<param>` child element must be valid for the param type |
| GTR074 | InputsDataOptionsMultiple, …Attrib, …FilterAttribFiltersType, …FiltersType, …FiltersRef | ✓ | ✗ | check | a `data` param's `<options>` (metadata filtering) must be valid |
| GTR075 | InputsBoolDistinctValues, InputsBoolProblematic | ✓ | ✗ | check | a `boolean` param's truevalue/falsevalue must be distinct and sane |
| GTR076 | InputsSelectSingleCheckboxes, …MandatoryCheckboxes, …MultipleRadio, …OptionalRadio | ✓ | ✗ | check | a select's `display` must agree with `multiple`/`optional` |
| GTR077 | InputsOptionsFiltersRequiredAttributes, …RemoveValueFilterRequiredAttributes, …FiltersAllowedAttributes | ✓ | ✗ | check | an `<options>/<filter>` must carry the attributes its type allows |
| GTR078 | InputsOptionsRegexFilterExpression | ✓ | ✗ | check | a `regexp` `<options>/<filter>` value must be a valid regex |
| GTR079 | InputsOptionsFiltersCheckReferences | ✓ | ✗ | check | an `<options>/<filter>` ref/meta_ref must name a real param |
| GTR080 | TestsAssertsMultiple, …HasNQuant, …HasSizeQuant, …HasSizeOrValueQuant | ✓ | ✗ | check | a `<test>`'s assertions must be well formed |
| GTR081 | TestsOutputCompareAttrib | ✓ | ✗ | check | a test output's attributes must agree with its `compare` mode |
| GTR082 | TestsOutputName | ✓ | ✗ | check | a test `<output>` must declare a name |
| GTR083 | TestsOutputDefined, …Corresponding, …CollectionCorresponding | ✓ | ✗ | check | a test output must name a declared output of the matching kind |
| GTR084 | TestsOutputCheckDiscovered, …CollectionCheckDiscovered, …Nested | ✓ | ✗ | check | a test of a discovering output must assert on the discovered datasets |
| GTR085 | TestsParamInInputs | ✓ | ✗ | check | a test `<param>` must name a tool input |
| GTR086 | TestsOutputFailing, TestsExpectNumOutputsFailing | ✓ | ✗ | check | an `expect_failure` test must not assert outputs |
| GTR087 | TestsExpectNumOutputs | ✓ | ✗ | check | a test should set `expect_num_outputs` for filtered outputs |
| GTR088 | TestsHasExpectations (TestsValid subsumed) | ✓ | ✗ | check | a test should assert outputs or expectations |

**Bold** planemo linters are ones planemo *only reports* and we *fix* (or, for the
checks, detect with our own rule). The remaining unmapped planemo linters (the ~80
correctness checks + the advisory-by-design ones) are in the per-module tables below;
each becomes a new GTR row here as it's built.

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
| **HAVE** | 109 | already covered (mostly as fixers / advisory checks). Incl. **GTR035** (`name`/req-`version` whitespace), **GTR036** (`<output type="data">`→`<data>`), **GTR037** (redundant `name`), **GTR038**/**GTR039** (citations/TODO), **GTR040–043** (output correctness), **GTR044–047** (command/profile/requirement-name/version-whitespace), **GTR048–050** (outputs present/format/label), **GTR051–053** (container shape, output-filter & stdio-regex validity), **GTR054–057** (input param naming/identity), **GTR058–060** (static select-option correctness), **GTR061–064** (dynamic select `<options>` correctness), **GTR065–068** (validator compatibility/text/expression/required-attrs), **GTR069–071** (conditional test-param + when/option correspondence), **GTR072–074** (inputs present / param type-child / data-options validity), **GTR075–076** (boolean values + select display idiom), **GTR077–079** (option-filter attributes/expression/references), **GTR080–084** (test assertions/compare/output-correspondence/discovered), **GTR085–088** (test param-in-inputs / expect-failure / expect-num-outputs / has-expectations), 2026-06-06 |
| **FIX** (new, auto-fixable) | 0 | **complete** — GTR035/036/037 shipped; the rest of the original FIX candidates reclassified to advisory/detect on inspection (identity-changing or no mechanical equivalent) |
| **DETECT** (new advisory) | ~11 | correctness checks for the `check` tier (report-only). 51 GTR rules landed so far (GTR038–088) — the **entire `inputs.py` correctness surface** plus citations/TODO, output correctness, command/profile/requirement-name, version-whitespace, container/filter/regex validity, and **all mechanically-reimplementable `tests.py` checks**. **Remaining DETECT:** `TestsAssertionValidation`/`TestsCaseValidation` (2, need Galaxy's pydantic models), general `ToolVersionMissing`/`ToolNameMissing`/`ToolIDMissing` (3), `OutputsStructuredLikeReference`/`OutputsFormatSourceReference` (2), `ValidDatatypes`/`DatatypesCustomConf` (2), `InputsDataFormat` (1), `HelpInvalidRST` (1) |
| **SKIP** (pass-state) | ~14 | `valid`/`info` reporters — nothing to build |
| **n/a** (out of scope) | ~12 | CWL (9), filesystem (`required_files`), `ResourceRequirementExpression`, `BioToolsValid` (network) |
| **Total** | 146 | |

> **Counts recomputed 2026-06-06** module-by-module after the `inputs.py` arc — the earlier
> running `~`-totals for DETECT/SKIP/n/a had drifted; these now sum to 146.

> **Reclassified by homework (2026-06-06).** The whitespace cluster started as 4 "FIX"
> rows; building **GTR035** split it honestly: `name` + `requirement version` are
> behaviour-preserving to trim (**fixed**), but `id` + tool `version` are used *raw* as
> the tool's identity (trimming changes identity) → **advisory-by-design**. Expect
> similar per-rule reclassification as the rest are built — "FIX" is an upper bound, not
> a promise. Worked before/afters live in [`examples/planemo_fixable_issues.md`](examples/planemo_fixable_issues.md).

By our tier, for the **buildable** rows (HAVE + FIX + DETECT):
- **codemod** (structural fix): the FIX rows below + GTR013/015/016/**035** — ~15
- **check** (advisory): the DETECT bulk + the advisory HAVEs — **65 GTR check rules shipped**
  (GTR021–GTR088, detect-only), ~11 planemo advisories still to build
- **parse/validate**: 1 (XSD)

**Headline:** planemo only *reports*; we *fix* the provably-safe subset (**GTR035/036/037**,
complete) and **detect the rest** as advisory `check`-tier rules. As of 2026-06-06 the check
tier has **65 rules** covering the whole `inputs.py` correctness surface and **all
mechanically-reimplementable `tests.py` checks**, plus citations, command, container,
general, help, output, and stdio. Only ~11 planemo advisories remain: the two `tests.py`
linters that need Galaxy's pydantic models (`TestsAssertionValidation`,
`TestsCaseValidation`) and a handful of scattered residuals (general missing
name/id/version, output cross-references, datatypes, `InputsDataFormat`, `HelpInvalidRST`).

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
| ValidDatatypes | error | check | DETECT | `format`/`ext` is a real datatype; we *normalize case* in `upgrade` (GTR010) but don't validate membership |
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
| ToolVersionMissing | error | check | DETECT | (XSD-required attr; detect TBD) |
| ToolNameMissing | error | check | DETECT | (XSD-required attr; detect TBD) |
| ToolIDMissing | error | check | DETECT | (XSD-required attr; detect TBD) |
| ResourceRequirementExpression | warn | n/a | — | unsupported feature warning |
| BioToolsValid | warn | n/a | — | needs bio.tools network lookup |
| ToolVersionValid · ToolNameValid · ToolProfileLegacy · ToolProfileValid | valid | — | SKIP | pass-states |

## help.py (6)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| HelpMissing | warn | check | **HAVE** | = **GTR028** |
| HelpEmpty | warn | check | **HAVE** | GTR028 (non-empty help) |
| HelpTODO | warn | check | **HAVE** | **GTR039** |
| HelpInvalidRST | warn | check | DETECT | RST validity (needs an RST parser — `docutils`) |
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
| InputsDataFormat | warn | check | DETECT | no `format` → defaults to `data` (fix = risky, leave advisory) |

**Group view — the whole `inputs.py` correctness surface is now HAVE** (only
`InputsDataFormat` stays DETECT, table above; the `InputsNum`/datasource info linters are
SKIP):
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
| OutputsStructuredLikeReference · OutputsFormatSourceReference | warn | check | DETECT | cross-reference integrity |
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
