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
| GTR024 | **ToolVersionPEP404**, ToolVersionMissing | ✓ | ✗ | check | version should be PEP 440 (or a `@…@` macro) |
| GTR025 | RequirementNameMissing | ✓ | ✗ | check | tool should declare `<requirements>` |
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
| **HAVE** | 17 | already covered (mostly as fixers). Incl. **GTR035** (`name`/req-`version` whitespace), **GTR036** (`<output type="data">`→`<data>`), **GTR037** (redundant `name`), 2026-06-06 |
| **FIX** (new, auto-fixable) | 0 | **complete** — GTR035/036/037 shipped; the rest of the original FIX candidates reclassified to advisory/detect on inspection (identity-changing or no mechanical equivalent) |
| **DETECT** (new advisory) | ~80 | correctness checks for the `check` tier (report-only); incl. `ToolIDWhitespace`/`ToolVersionWhitespace` (advisory-by-design — §33) |
| **SKIP** (pass-state) | ~21 | `valid`/`info` reporters — nothing to build |
| **n/a** (out of scope) | ~20 | CWL, filesystem, network/ontology, runtime |
| **Total** | 146 | |

> **Reclassified by homework (2026-06-06).** The whitespace cluster started as 4 "FIX"
> rows; building **GTR035** split it honestly: `name` + `requirement version` are
> behaviour-preserving to trim (**fixed**), but `id` + tool `version` are used *raw* as
> the tool's identity (trimming changes identity) → **advisory-by-design**. Expect
> similar per-rule reclassification as the rest are built — "FIX" is an upper bound, not
> a promise. Worked before/afters live in [`examples/planemo_fixable_issues.md`](examples/planemo_fixable_issues.md).

By our tier, for the **buildable** rows (HAVE + FIX + DETECT):
- **codemod** (structural fix): the FIX rows below + GTR013/015/016/**035** — ~15
- **check** (advisory): ~80 (the DETECT bulk + the advisory HAVEs)
- **parse/validate**: 1 (XSD)

**Headline:** planemo only *reports*; we *fix* the provably-safe subset — now **complete**:
**GTR035** (whitespace trims), **GTR036** (`<output type="data">`→`<data>`), **GTR037**
(redundant `name`). Every other original FIX candidate, on inspection, is either
identity-changing (advisory-by-design) or has no mechanical modern equivalent (detect).
The next planemo-parity frontier is the ~80 *correctness* checks → the advisory `check` tier.

---

## citations.py (4)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| CitationsMissing | warn | check | **HAVE** | **GTR038** |
| CitationsNoText | error | check | **HAVE** | **GTR038** (empty doi/bibtex) |
| CitationsNoValid | warn | check | DETECT | no parseable citation (doi/bibtex) |
| CitationsFound | valid | — | SKIP | pass-state |

## command.py (5)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| CommandInterpreterDeprecated | warn | codemod | **HAVE** | = **GTR016** (we inline `interpreter=`) |
| CommandMissing | error | check | DETECT | no `<command>` |
| CommandEmpty | error | check | DETECT | empty command |
| CommandTODO | warn | check | **HAVE** | **GTR039** |
| CommandInfo | info | — | SKIP | pass-state |

## containers.py (1)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| ContainerImageShape | warn | check | DETECT | biocontainers/quay shape; pattern-matchable (no network) |

## cwl.py (9) — **all n/a** (CWL, not Galaxy tool XML)

`CWLValid` · `CWLInValid` · `CWLVersionMissing` · `CWLVersionUnknown` · `CWLVersionGood` ·
`CWLDockerMissing` · `CWLDockerGood` · `CWLDescriptionMissing` · `CWLHelpTODO` → **n/a**.

## datatypes.py (2)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| ValidDatatypes | error | check | DETECT | `format`/`ext` is a real datatype; we *normalize case* in `upgrade` (GTR010) but don't validate membership |
| DatatypesCustomConf | warn | check | DETECT | discouraged custom `datatypes_conf.xml` |

## general.py (19)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| ToolNameWhitespace | warn | codemod | **HAVE** | **GTR035** trims it (display-only — safe) |
| RequirementVersionWhitespace | warn | codemod | **HAVE** | **GTR035** trims it (whitespace breaks the conda solve, so a working tool never has it — repair-safe) |
| ToolVersionWhitespace | warn | check | DETECT | **advisory-by-design**: trimming `version` changes the tool's version identity (used raw); see §33 |
| ToolIDWhitespace | warn | check | DETECT | **advisory-by-design**: trimming `id` changes the registration identity; see §33 |
| ToolIDValid | valid/err | check | **HAVE** | id charset = **GTR023** |
| RequirementVersionMissing | warn | check | **HAVE** | = **GTR033** (pin requirement version) |
| EDAMTermsValid | warn | check | **HAVE\*** | ≈ **GTR027**; full EDAM-ontology validation needs network |
| ToolVersionMissing | error | check | DETECT | |
| ToolVersionPEP404 | warn | check | DETECT | version not PEP 440 |
| ToolNameMissing | error | check | DETECT | |
| ToolIDMissing | error | check | DETECT | |
| ToolProfileInvalid | error | parse | DETECT | invalid profile (we resolve profiles in tier 1) |
| RequirementNameMissing | error | check | DETECT | |
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
| InputsSelectDynamicOptions | warn | check | DETECT | `dynamic_options="<python expr>"` has no mechanical modern equivalent — advisory, not fixable |
| InputsSelectOptionsDeprecatedAttr | warn | check | DETECT | `from_file`/`from_parameter`/`transform_lines`/`options_filter_attribute` need restructuring (e.g. a data table) — advisory, not fixable |
| InputsDataFormat | warn | check | DETECT | no `format` → defaults to `data` (fix = risky, leave advisory) |

**DETECT (the remaining ~52)** — group view:
- *naming/identity:* `InputsName` · `InputsNameEmpty` · `InputsNameValid` (Cheetah-placeholder) · `InputsNameDuplicate` · `InputsNameDuplicateOutput`
- *type/structure:* `InputsMissing` · `InputsTypeChildCombination` · `InputsDataOptionsMultiple` · `InputsDataOptionsAttrib` · `InputsDataOptionsFilterAttribFiltersType` · `InputsDataOptionsFiltersType` · `InputsDataOptionsFiltersRef`
- *select/options correctness:* `InputsSelectOptionsDef` · `InputsSelectOptionsDefConditional` · `InputsSelectOptionValueMissing` · `InputsSelectOptionDuplicateValue` · `InputsSelectOptionDuplicateText` · `InputsSelectOptionsMultiple` · `InputsSelectOptionsDefinesOptions` · `InputsSelectOptionsFromDatasetAndDatatable` · `InputsSelectOptionsMetaFileKey`
- *option filters:* `InputsOptionsFiltersRequiredAttributes` · `InputsOptionsRemoveValueFilterRequiredAttributes` · `InputsOptionsFiltersAllowedAttributes` · `InputsOptionsRegexFilterExpression` · `InputsOptionsFiltersCheckReferences`
- *display/idiom:* `InputsSelectSingleCheckboxes` · `InputsSelectMandatoryCheckboxes` · `InputsSelectMultipleRadio` · `InputsSelectOptionalRadio` · `InputsBoolDistinctValues` · `InputsBoolProblematic`
- *validators:* `ValidatorParamIncompatible` · `ValidatorAttribIncompatible` · `ValidatorHasText` · `ValidatorHasNoText` · `ValidatorExpression` · `ValidatorExpressionFuture` · `ValidatorMinMax` · `ValidatorDatasetMetadataEqualValue` · `ValidatorDatasetMetadataEqualValueOrJson` · `ValidatorMetadataCheckSkip` · `ValidatorTableName` · `ValidatorMetadataName`
- *conditionals:* `ConditionalParamTypeBool` · `ConditionalParamType` · `ConditionalParamIncompatibleAttributes` · `ConditionalWhenMissing` · `ConditionalOptionMissing` · `ConditionalOptionMissingBoolean`

**SKIP:** `InputsNum` · `InputsMissingDataSource` · `InputsDatasourceTags` (info).

## output.py (14)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| OutputsOutput | warn | codemod | **HAVE** | **GTR036** rewrites `<output type="data">` → `<data>`; `type="collection"` / expression outputs left advisory (§34) |
| OutputsFormatInput | warn | upgrade | **HAVE** | = **GTR015** (`format="input"` → `format_source`) |
| OutputsMissing | warn | check | DETECT | no outputs |
| OutputsNameInvalidCheetah | warn | check | DETECT | output name not a valid placeholder |
| OutputsNameDuplicated | error | check | DETECT | |
| OutputsFilterExpression | warn | check | DETECT | invalid filter expression |
| OutputsLabelDuplicatedFilter / NoFilter | warn | check | DETECT | duplicate output labels |
| OutputsCollectionType | warn | check | DETECT | collection without `type` |
| OutputsFormat | warn | check | DETECT | output without a format (fix=risky) |
| OutputsFormatSourceIncomp | warn | check | DETECT | both `format` + `format_source` (≈ our GTR014 area) |
| OutputsStructuredLikeReference · OutputsFormatSourceReference | warn | check | DETECT | cross-reference integrity |
| OutputsNumber | info | — | SKIP | |

## required_files.py (1) — **n/a** (filesystem)

`RequiredFilesExist` (error) → **n/a** (needs the file tree).

## stdio.py (3)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| StdIOAbsence / StdIOAbsenceLegacy | info | check | **HAVE** | ≈ **GTR026** (error handling present) |
| StdIORegex | error | check | DETECT | invalid `<regex>` match expression |

## tests.py (23)

| Linter | sev | tier | disp | note |
|---|---|---|---|---|
| TestsMissing | warn | check | **HAVE** | = **GTR021** |
| (21 correctness checks) | error/warn | check | DETECT | assertion quantifiers, output/collection correspondence, `expect_num_outputs`, param-in-inputs, discovered-output rules, failing-test rules — author intent needed |
| TestsMissingDatasource · TestsNoValid | info/valid | — | SKIP | |

DETECT list: `TestsAssertsMultiple` · `TestsAssertsHasNQuant` · `TestsAssertsHasSizeQuant` ·
`TestsAssertsHasSizeOrValueQuant` · `TestsAssertionValidation` · `TestsCaseValidation` ·
`TestsExpectNumOutputs` · `TestsParamInInputs` · `TestsOutputName` · `TestsOutputDefined` ·
`TestsOutputCorresponding` · `TestsOutputCollectionCorresponding` · `TestsOutputCompareAttrib` ·
`TestsOutputCheckDiscovered` · `TestsOutputCollectionCheckDiscovered` ·
`TestsOutputCollectionCheckDiscoveredNested` · `TestsOutputFailing` ·
`TestsExpectNumOutputsFailing` · `TestsHasExpectations` · `TestsValid`.

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
