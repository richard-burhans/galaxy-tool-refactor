# Data sources, and how each one moved the project

This project is empirical: almost every rule, soundness boundary, and design
decision is grounded in real data rather than in what we imagined Galaxy tools
look like. This page enumerates the external sources we mined and what each one
actually unblocked. (Provenance for individual artifacts lives alongside them:
`corpus_sources.json`, the schema `PROVENANCE.md`, `docs/galaxy_reimplementations.md`,
`docs/galaxy_server_versions.json`.)

## 1. The Galaxy tool corpus (the central asset)

**What.** ~9,373 unique tools after sha256 dedup, drawn from **21 community GitHub
repositories** (`corpus_sources.json` — tools-iuc, bgruening, devteam, galaxyp,
metabolomics, ecology, and more) plus the **Galaxy ToolShed** (7,672 cloned repos,
`scripts/fetch_toolshed.py`). About 46% of raw entries are cross-source byte
duplicates, removed by the dedup.

**How it moved the project.** This is the workhorse. It is simultaneously:
- the **QA suite** — `scripts/corpus_check` sweeps every tool through each tier's
  API and checks tier invariants (idempotence, post-codemod validity, detect/fix
  parity), retaining every violating tool as a permanent regression fixture;
- the **sizing oracle** — `scripts/measure` turns "how often does X occur?" into a
  committed number, so design forks (quote text params? park the blank-line rule?
  which output conversions are safe?) are settled with data, not opinion;
- the **bug-finding oracle** — diffing our verdict against planemo's / Galaxy's
  across the corpus caught a real false positive in *every* planemo-parity batch,
  and the bulk-normalizer sweep just surfaced the GTR036 expression-output bug;
- the empirical source from which the **upgrade codemod set was grown** (the sweep
  names the exact profiles where real tools stall, pinpointing the next codemod).

## 2. The vendored Galaxy XSD schemas (the validity oracle)

**What.** **28 per-release Galaxy tool-XML schemas** vendored at
`galaxy-tool-source/.../schema/` (downloaded once by `scripts/fetch_schemas.py`;
`PROVENANCE.md` + `manifest.json` record their origin), including in-memory fixes
for the releases libxml2 refuses to compile.

**How it moved the project.** They make validation **profile-aware** (each tool is
checked against the schema for its declared profile) and they are the **oracle for
the upgrade soundness boundary**: "validity-as-oracle is sound for structural
changes, not for behaviour," so structural repairs are gated on the schema while
behaviour changes are gated separately. The per-release diff (`scripts/measure
xsd-tightenings`) also surfaces where a newer schema strands an older tool.

## 3. Galaxy's own source code (the behaviour oracle)

**What.** A clone of `galaxyproject/galaxy` (`.local/galaxy-src`), read directly
rather than paraphrased from documentation.

**How it moved the project.** Every behaviour-preservation claim is checked against
how Galaxy *actually* parses a construct. This is what justified (and bounded) the
codemods: that `<output type="data">` parses identically to `<data>` (GTR036), how
macro expansion works (the faithful-expansion anchor), the per-profile behaviour
changes (`PROFILE_UPGRADE_CODES`), and the Cheetah/command model. It is also where
the GTR036 fix came from: Galaxy routes an expression output by its `from`
attribute, which is why `from` is invalid on `<data>`.

## 4. Galaxy's and planemo's linters/validators (the parity oracles)

**What.** Galaxy's `galaxy.tool_util` linters and validators — the 146 planemo
linters, the 24.2 test-case validator, and the datatype linters.

**How it moved the project.** Planemo's linters are the **parity target**: we mapped
all 146, porting the mechanically-reimplementable ones as *fixers* and binding to
Galaxy's own for the rest. Crucially, running our detection beside Galaxy's verdict
over the corpus turned their linters into a **bug oracle for us** (e.g. the
datatypes-pair parity check, `scripts/measure datatype-validation-truth`, gated on
zero false positives). Where reimplementation is unsound (the test-validation
pydantic models, GTR100/101) we bind to Galaxy at runtime instead. Each
keep-vs-reimplement call is recorded in `docs/galaxy_reimplementations.md`.

## 5. The IUC tool-XML best-practice standards (the convention source)

**What.** The IUC standards
(`galaxy-iuc-standards.readthedocs.io/.../tool_xml.html`), mapped in
`docs/iuc_best_practices.md`.

**How it moved the project.** They are the source of the *canonical form* the
toolchain normalizes toward (element order, attribute order, CDATA wrapping, command
quoting) and the citation behind each rule (`RuleMeta.cite`, guarded so every
advisory rule points somewhere). They also define the boundary of what we may
enforce: where a convention is documented and uncontroversial it is gate-eligible;
where it is contested (attribute reordering) it is blocked pending an IUC decision.

## 6. The tools-iuc pull-request corpus (human-reviewed ground truth)

**What.** A three-ref snapshot (base / first-commit / head) of real merged and open
tools-iuc pull requests (`scripts/fetch_iuc_prs.py` -> `.local/pr-corpus`).

**How it moved the project.** Real, human-reviewed edits are the ground truth for
"would our toolchain have helped?" (`scripts/pr_impact.py`) and for "does the
canonical-form backlog re-accumulate?" — `scripts/gate_reaccumulation.py` found that
**96.7% of 452 recently merged PRs are still non-canonical in their merged state**,
which is the evidence for the forward-enforcement gate. The bulk-normalizer fork
proof over this same repository is what surfaced the GTR036 bug.

## 7. Major public Galaxy servers' deployed versions (the deployment reality)

**What.** A poll of the Galaxy release each major public server runs
(`scripts/poll_galaxy_servers.py` over usegalaxy.org/.eu/.org.au/.fr/.ca ->
`docs/galaxy_server_versions.json`).

**How it moved the project.** It defines the **deployment ceiling**: a tool whose
profile exceeds the lowest-deployed release cannot install on the lagging servers,
so the opt-in `upgrade --modernize` walk is capped at the newest profile *every*
polled server runs (vendored + drift-guarded in the registry). This keeps an
"upgrade" from silently making a tool un-installable.

## 8. (Forward-looking) Bioconda package-to-wrapper pairs

**What.** The existing corpus of Bioconda packages and their Galaxy wrappers.

**How it would move the project.** The destination direction (a Bioconda-to-Galaxy
wrapping agent) reuses this as training data, with the deterministic toolchain as
the verification/reward oracle. The same corpus then does triple duty: QA suite,
bug oracle, and training data.

---

**The throughline.** No capability here was designed in the abstract. The corpus
sized it, the schemas and Galaxy's source proved it sound, planemo and Galaxy's
validators kept it honest, the IUC standards told us what "canonical" means and
where to stop, the PR corpus showed it mattered, and the server poll kept it
deployable.
