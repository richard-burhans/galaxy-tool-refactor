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

## Adding to this document

When a new re-implementation lands (or a deliberate keep is decided), add a
touchpoint section with: where the Galaxy code lives and how isolated our use
is, the measured advantage (cite a standing `scripts.measure` command, never a
one-off), the parity oracle that bounds the risk, and the verdict. The pre-PR
audit's doc-accuracy step treats a re-implementation without an entry here as
a finding.
