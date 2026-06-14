# Galaxy code we use, and where our own implementation wins

The standing convention this document encodes: **whenever this toolchain
re-implements something Galaxy's libraries already do, the advantage must be
documented here** (what we gain, why it is safe), alongside the parity story
that keeps the re-implementation honest. The inverse holds too: where we
deliberately keep Galaxy's own code, the reason is recorded so the choice is
not re-litigated casually.

The audit below is the complete inventory of Galaxy *code* this workspace
executes (vendored *data*, the per-release XSDs in
`galaxy-tool-source/schema/` and `PROFILE_UPGRADE_CODES` in
`profile_semantics.py`, is provenance-tracked where it lives and is not
repeated here). The surface is deliberately tiny and isolated; each touchpoint
has a verdict.

## Why we hold a structural advantage at all

Galaxy's tool-handling code re-derives everything per call: it re-parses the
XML into its own tree, builds intermediate object models, and (for test-case
validation) dynamically generates a pydantic class per tool. This toolchain
keeps one **resident, mutable lxml tree as the source of truth** (tier 1),
with the macro-expanded view, per-profile typed models, and qualified-path
resolution already computed and shared by every rule. A decision Galaxy
reaches by building machinery is often, for us, a direct structural query
against a tree we already hold. That is the recurring advantage; the recurring
*risk* is divergence from Galaxy's semantics, which is why every
re-implementation below carries a parity oracle.

## Touchpoint 1: macro expansion (`galaxy.util.xml_macros`) — KEEP

- **Where:** `galaxy-tool-source/src/galaxy_tool_source/macros.py`, the
  declared sole `galaxy-util` adapter (one call site,
  `load_with_references`; all Galaxy exceptions converted to `MacroError` at
  the boundary). Pinned `galaxy-util[template]>=24,<27`.
- **Could we re-implement it?** Technically yes (imports, tokens,
  `<expand>`/`<yield>` splicing). **We deliberately do not.** Everything
  downstream, XSD validation (the structural oracle), per-tool behaviour-code
  detection, and the behavior gate's probe, is sound *because* detection runs
  on the same expanded view Galaxy itself would see. An off-by-one in token
  recursion or yield parameterisation would silently corrupt every oracle in
  the stack. Expansion is also nowhere near the hot path (XSD compilation and
  validation dominate), so a faster expander buys nothing measurable.
- **Verdict:** Galaxy's own expander is the faithfulness anchor. Keep.

## Touchpoint 2: the Cheetah lexer (CT3, via `galaxy-util[template]`) — KEEP

- **Where:** `galaxy-tool-source/src/galaxy_tool_source/cheetah_cdm.py`
  subclasses CT3's parser to harvest exact source spans; `command_text`,
  `cheetah_refs`, and `rename-param` ride it, with a regex fallback for the
  ~0.4% of bodies CT3 cannot compile (tier-1 decisions §19).
- **History runs the other way here:** we *replaced our own implementation
  with Galaxy's engine*, because CT3 is the very engine Galaxy renders
  templates with, so a `$var` inside `#raw`, a comment, or behind `\$` is
  classified exactly as production Galaxy would. Re-implementing the lexer
  would reverse a hard-won correctness upgrade for no measurable speed gain.
- **Verdict:** keep. The lesson generalises: re-implement for *efficiency*
  only where faithfulness can be proven by an oracle; otherwise prefer
  Galaxy's own engine.

## Touchpoint 3: the 24.2 test-case validator (`galaxy-tool-util`) — RE-IMPLEMENT (the shipped path)

- **What Galaxy does per tool:** `get_tool_source` re-parses the XML (own
  macro expansion), `input_models_for_tool_source` builds a parameter-model
  tree, and `test_case_validation` **generates a pydantic model class per
  tool** (`create_model`) to validate each test case. Measured cost: roughly
  200ms per tool across the corpus, plus the whole
  `galaxy-tool-util`/pydantic dependency chain.
- **Our advantage (SHIPPED, `galaxy_tool_codemod/test_case_check.py`,
  decisions §47):** the decision needs only structural facts we already hold:
  does each test parameter name resolve to a qualified input path; is a static
  select value in the option set; is a `data_column` value an integer; does a
  conditional's test value select a when. `all_test_cases_provably_clean`
  walks our resident expanded tree and answers in milliseconds with zero new
  dependencies; `_detects_test_case_validation` fires only when a tool ships a
  `<test>` and its tests are not provably clean.
- **How it stays honest:** the re-implementation is **one-directional** (it
  may only *suppress* the 24.2 blocker when every test is provably clean under
  rules justified from Galaxy's model code; every construct it cannot model
  stays blocked). `scripts.measure test-case-validation-truth` is the
  **standing parity oracle**: it runs Galaxy's real validator (a dev-only
  dependency, never shipped in a tier) beside the checker over every
  test-shipping corpus tool, and the hard gate is **zero unsound suppressions**
  (ours-clean but Galaxy returns an invalid *verdict*), re-verified on every
  corpus refresh; an in-CI fixture parity test pins the same agreement without
  the corpus. A Galaxy validator *raise* is a separate bucket, not a verdict:
  Galaxy's own advisor has no try/except around the call, so a raise is Galaxy
  failing to advise (malformed XML, an unexpandable macro, or a pydantic
  model-name collision under the bulk sweep), and those tools are handled
  upstream in the shipped pipeline. Galaxy's verdicts define correctness; the
  checker is trusted only as far as the oracle proves it.
- **Measured stakes** (2026-06-12, `test-case-validation-truth`): of 6,648
  test-shipping tools, 4,517 (67.9%) validate cleanly and were needlessly
  stopped by the ships-a-`<test>` approximation; 1,972 (29.7%) are true
  blockers; 159 crash Galaxy's own parser (no verdict). The checker recovers
  the provably-clean subset with zero unsound suppressions.
- **It also enables a fix.** The same input-tree resolution drives
  `FixTestParamQualification` (GTR096, codemod decisions §48), which qualifies a
  flat `<test>` parameter name to its unique nested `parent|...|child` path,
  the migration Galaxy prescribes. It is the first auto-fix for the 24.2 code,
  parity-proven by `scripts.measure test-param-qualification` (every tool it
  unblocks must validate clean under Galaxy's real validator on the *qualified*
  tree, zero unsound verdicts).

## Touchpoint 4: the datatype linters (`galaxy.tool_util.linters.datatypes`) — RE-IMPLEMENT

- **Where it lives.** `ValidDatatypes` and `DatatypesCustomConf` in
  `galaxy/tool_util/linters/datatypes.py`. `ValidDatatypes` checks `format`/`ftype`/`ext`
  against the datatype extensions parsed from a `datatypes_conf.xml.sample` Galaxy
  *bundles next to the linter* — it does **not** consult a live datatype registry.
  `DatatypesCustomConf` is a filesystem check (a sibling `datatypes_conf.xml`).
- **The re-implementation.** GTR098/GTR099 (galaxy-tool-lint `checks/datatypes.py`, lint
  decisions D36). The membership set is a **vendored snapshot** of the bundled sample
  (`data/datatypes_conf.xml.sample`), parsed with the same logic as Galaxy's
  `_parse_datatypes`; the rule branches (`auto`/`input` special-casing, the profile ≤ 16.04
  `input` free pass, comma-split, `<help>` skip) port Galaxy's exactly. No runtime
  `galaxy-tool-util` dependency.
- **Why re-implement, not depend.** Galaxy's linter only knows its *bundled* sample, so
  matching that snapshot **is** faithful parity — a dependency would buy nothing. This is
  the same vendored-snapshot pattern as the per-release XSDs and the deployment ceiling.
- **The advantage.** Independence (no heavy dep for a membership check) and the snapshot is
  shared corpus-wide via `@cache`. The accepted asymmetry: a datatype newer than the
  snapshot would false-positive — the identical limitation Galaxy's own linter has against a
  plugin-registered type.
- **The parity oracle.** Two layers. (1) A **drift guard**
  (`test_datatypes_registry.py::test_vendored_snapshot_matches_installed_galaxy_tool_util`)
  pins our parsed set == the installed `galaxy-tool-util`'s, so a dep bump that moves the
  sample fails CI naming the re-vendor (snapshot from `galaxy-tool-util` 26.0.0). (2)
  `scripts.measure datatype-validation-truth` runs Galaxy's REAL linters over the corpus
  beside ours: on **macro-free tools** ours matches Galaxy EXACTLY, on macro tools ours may
  only under-report (it skips `@…@` / macro-injected formats), never over-report.
- **Measured stakes.** 9,331 corpus tools (42 crash Galaxy's own parser, no verdict): GTR098
  **0 over-reports** (zero false positives), **0 divergence on all 4,202 macro-free tools**
  (exact parity), 49 under-reports all on macro tools; GTR099 perfect (9,331/9,331).
- **Verdict:** re-implement. Galaxy's verdict defines correctness; the snapshot + oracle make
  ours faithful with zero false positives, no dependency.

## Touchpoint 5: the test-validation linters (`assertions.py` / `parameters.py`) — KEEP

The two remaining planemo DETECT linters, `TestsAssertionValidation` and
`TestsCaseValidation`, were assessed for reimplementation (the same exercise as
Touchpoint 4). Verdict: **keep the dependency** — and the reason is architectural, not
just size.

- **`TestsAssertionValidation` → `tool_util_models/assertions.py` (~4,175 lines).** This
  file is auto-generated, but **not by hand and not from the XSD** — Galaxy's bespoke
  `tool_util/verify/codegen.py` introspects the hand-written Python assertion functions
  (`verify/asserts/*.py`, whose signatures carry `Annotated[…, AssertionParameter(…)]`
  metadata) and emits **both** the pydantic models **and** the XSD `<TestAssertion>` group
  (`rewrite_galaxy_xsd`). So for assertions the **XSD is a derived projection of the Python
  functions** — the *reverse* of our architecture, where the XSD is the source of truth and
  we xsdata-codegen read-only models from it. The validation richness (the pydantic
  `BeforeValidator`s, e.g. `check_bytes` / `check_center_of_mass`) lives in the Python
  functions and is not expressible in the XSD, so our XSD-codegen cannot absorb it.
- **`TestsCaseValidation` → `tool_util_models/parameters.py` (~2,591 lines).** This one is
  **hand-written** — a semantic parameter-validation model (`requires_value`, conditional
  descent, test-case state coercion) far richer than the XSD's structural layer. Again not
  derivable from our source of truth.
- **Why not reimplement.** Both encode validation *semantics* that sit above the XSD layer.
  This is genuinely not "hand-rolled for lack of schema tooling our pipeline would provide"
  (the question that prompted the investigation, 2026-06-14) — it is logic the XSD does not
  carry. We already reimplement the sound *one-directional* slice of `TestsCaseValidation`
  (`test_case_check.py`, the 24.2 behavior-gate checker, parity-oracled by
  `scripts.measure test-case-validation-truth`); the full bidirectional linter stays a
  `galaxy-tool-util` dependency.
- **Upstream thread (future).** `codegen.py` is bespoke and self-describes its pydantic
  generation as still maturing ("in the future it will also build Pydantic models for these
  functions"). A possible contribute-back later — but the direction is function→schema, so
  our specific schema→model (xsdata) pipeline does not transfer directly.

## Adding to this document

When a new re-implementation lands (or a deliberate keep is decided), add a
touchpoint section with: where the Galaxy code lives and how isolated our use
is, the measured advantage (cite a standing `scripts.measure` command, never a
one-off), the parity oracle that bounds the risk, and the verdict. The pre-PR
audit's doc-accuracy step treats a re-implementation without an entry here as
a finding.
