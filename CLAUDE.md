# CLAUDE.md — galaxy-tool-refactor workspace

> New here? Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first — a map of the major
> abstractions across the seven tiers and the cross-tier contracts between them —
> and [`docs/design_principles.md`](docs/design_principles.md) for the two
> governing contracts (fix only what is provably behavior-preserving; every other
> warning points to docs) and how each is CI-enforced.

## Layout

```
galaxy-tool-refactor/
├── galaxy-tool-refactor-rules/ Tier 0.5 (shared RuleMeta + glossary renderer)
├── galaxy-tool-source/          Tier 1 (parsing & validation)
├── galaxy-tool-codemod/  Tier 2 (structure)
├── galaxy-tool-fmt/      Tier 3 (formatting)
├── galaxy-tool-lint/    Tier 3.5 (advisory detect-only checks)
├── galaxy-tool-refactor-registry/ Tier 3.6 (unified rule registry + rulesets; library-first facade)
├── galaxy-tool-refactor-cli/ Tier 4 (app CLI: format + upgrade + check + find-references + rename-param + rulesets/rules + normalize-macros + convert-help + tokenize-version + lint-skip)
├── galaxy-tool-refactor-mcp/ Tier 4 (MCP server over the registry facade; thin FastMCP adapter)
├── galaxy-tool-refactor-meta/ Front-door metapackage (dist `galaxy-tool-refactor`; deps cli + `[mcp]` extra; no code)
├── scripts/                  Shared maintainer scripts (not installed)
│   ├── corpus_check.py         validate | fmt | codemod | rules | check | upgrade subcommands
│   ├── fetch_schemas.py        download release XSDs
│   ├── fetch_toolshed.py       clone Toolshed repos
│   ├── measure.py              ad-hoc corpus queries
│   ├── regenerate.py           regenerate per-version xsdata models
│   ├── gen_planemo_parity.py   regenerate the GTR coverage table (docs/planemo_linter_parity.md)
│   ├── gen_profile_boundaries.py regenerate the per-boundary upgrade reference (docs/profile_boundaries.md)
│   ├── gen_gate_eligibility.py  regenerate the auto-fix eligibility table (docs/gate_eligibility.md)
│   ├── bump_version.py         set the lockstep version across all 9 packages
│   ├── poll_galaxy_servers.py  poll major Galaxy servers' /api/version -> deployment floor + profile ceiling (docs/galaxy_server_versions.json)
│   └── galaxy_blog.py          scaffold/lint a Galaxy Hub news/blog post
├── docs/
│   └── corpus_data/            per-tool JSON/TSV from corpus sweeps
├── corpus_sources.json       list of GitHub repos to clone (committed seed list)
└── .local/                   machine-local scratch, gitignored (NOT committed)
    ├── corpus/                 cloned Galaxy tool repos (seeded from corpus_sources.json)
    └── galaxy-src/             clone of galaxyproject/galaxy for source inspection
```

## Install

```bash
uv sync          # installs the eight packages + the metapackage + dev deps into .venv
```

## Test

```bash
uv run --package galaxy-tool-refactor-rules pytest galaxy-tool-refactor-rules/tests/
uv run --package galaxy-tool-source            pytest galaxy-tool-source/tests/
uv run --package galaxy-tool-codemod    pytest galaxy-tool-codemod/tests/
uv run --package galaxy-tool-fmt        pytest galaxy-tool-fmt/tests/
uv run --package galaxy-tool-lint      pytest galaxy-tool-lint/tests/
uv run --package galaxy-tool-refactor-registry pytest galaxy-tool-refactor-registry/tests/
uv run --package galaxy-tool-refactor-cli   pytest galaxy-tool-refactor-cli/tests/
uv run --package galaxy-tool-refactor-mcp   pytest galaxy-tool-refactor-mcp/tests/
```

`make test-coverage` (= `scripts/coverage_report.sh`) runs every suite with
coverage — **reporting only, not a gate** (no threshold; generated `models/v*`
excluded, so it shows the honest hand-written number). A non-gating `coverage.yml`
job also uploads the HTML report as an artifact on `main`.

## Lint / type-check

```bash
uv run ruff check galaxy-tool-refactor-rules/src galaxy-tool-source/src galaxy-tool-codemod/src galaxy-tool-fmt/src galaxy-tool-lint/src galaxy-tool-refactor-registry/src galaxy-tool-refactor-cli/src galaxy-tool-refactor-mcp/src
uv run mypy --config-file galaxy-tool-refactor-rules/pyproject.toml galaxy-tool-refactor-rules/src
uv run mypy --config-file galaxy-tool-source/pyproject.toml         galaxy-tool-source/src
uv run mypy --config-file galaxy-tool-codemod/pyproject.toml galaxy-tool-codemod/src
uv run mypy --config-file galaxy-tool-fmt/pyproject.toml     galaxy-tool-fmt/src
uv run mypy --config-file galaxy-tool-lint/pyproject.toml   galaxy-tool-lint/src
uv run mypy --config-file galaxy-tool-refactor-registry/pyproject.toml galaxy-tool-refactor-registry/src
uv run mypy --config-file galaxy-tool-refactor-cli/pyproject.toml galaxy-tool-refactor-cli/src
uv run mypy --config-file galaxy-tool-refactor-mcp/pyproject.toml galaxy-tool-refactor-mcp/src
uv run mypy --config-file pyproject.toml scripts
```

## Pre-push QA gate

`scripts/qa_gate.sh` runs the deterministic quality slice — ruff, mypy (strict,
per package **plus the maintainer `scripts/` tree** under the root
`pyproject.toml`'s `[tool.mypy]`, **at the 3.10 support floor** via
`--python-version 3.10`, so a version-floor break is caught locally rather than
only in CI's 3.10 job), and pytest for all eight packages — and exits non-zero
(naming the failing step) if
anything fails. A `git push` **PreToolUse hook** (`.claude/settings.json`) runs
it and **blocks the push** on failure. For a **bare** `git push` it also adds
**`QA_GATE_REQUIRE_CLEAN=1`**, blocking on an **uncommitted tracked tree** (the gate
validates the working tree but the push sends commits, so a dirty tree would
validate code that isn't being pushed; commit or stash first). A command that
**commits in the same invocation** (`git commit … && git push`) skips that
clean-check — the commit makes the tree match what is pushed, so the combined
command is safe and no longer trips the hook — while the gate itself still runs.
So code never leaves the machine with a red gate or a
validated-tree-that-differs-from-the-push. Green runs are **cached per
working-tree state** (`.git/qa-gate-green`): a re-run on an unchanged tree —
e.g. the hook right after a manual run — is a free cache hit; any file change
invalidates it (`QA_GATE_FORCE=1` bypasses). CI (`.github/workflows/ci.yml`)
runs this same script (without `QA_GATE_REQUIRE_CLEAN`, on a clean checkout), so
the package roster lives in exactly one place. Run it manually any time:

```bash
bash scripts/qa_gate.sh
```

This is a mechanical backstop only — it does **not** replace the full pre-PR
code + documentation audit (standards, doc/code agreement, stale-doc and
stat-consistency review). That audit is the **`/pre-pr-audit` skill**
(`.claude/skills/pre-pr-audit/`) — invoke it before opening any PR; it owns the
six-step checklist and calls `qa_gate.sh` as its final step. For deeper,
design-level reviews of the abstractions there is the **`/architecture-audit`
skill**. To **merge** a PR and clean up the branch safely — without the
`gh pr merge --delete-branch` checkout that has twice wiped the `.local` corpus —
use the **`/ship-pr` skill** (`.claude/skills/ship-pr/`), which drives
`scripts/ship-pr.sh` (the same script a non-agent maintainer runs via
`make ship-pr`). New contributors approve the project hook on first use; in a
session that predates the hook, open `/hooks` once (or restart) to load it.

**Dual on-ramp (standing convention).** Every workflow has a human path (a `make`
target / script) and, for Claude Code users, an agent path (a skill) — kept
single-source (the skill calls the script). [`docs/workflows.md`](docs/workflows.md)
is the map. When you add a *procedural* skill, also add its script + a `make`
target + a `workflows.md` row in the same change, so non-agent collaborators are
never second-class.

## Corpus scripts

```bash
# Tier-1 invariants (parsing/validation): sweep validity vectors, retain crashes.
# Parallel by default (--jobs N, cpu_count-2; byte-identical to serial); --jobs 1 / --limit = serial.
uv run python -m scripts.corpus_check validate [--source github|toolshed|combined] [--limit N] [--jobs N]

# Tier-3 invariants (cosmetic formatting): sweep format()→format() idempotence. Parallel (--jobs N).
uv run python -m scripts.corpus_check fmt [--source github|toolshed|combined] [--repo NAME] [--limit N] [--jobs N]

# Tier-2 invariants (one structural codemod at a time): sweep idempotence + post-codemod validity.
uv run python -m scripts.corpus_check codemod <dotted.module>:<ClassName> [--repo NAME] [--limit N]

# Per-rule isolation QA (every GTR rule alone, fmt + codemod): idempotence (+ post-validity
# for codemods), retain failures, write docs/corpus_rule_stats.md. Each isolated sweep is
# parallel (--jobs N).
uv run python -m scripts.corpus_check rules [--source github|toolshed|combined] [--repo NAME] [--limit N] [--jobs N]

# Unified-detect violation counts (what `check` reports: canonical codemods + fmt + advisory
# IUC): per-rule tools-flagged + total findings, write docs/corpus_check_stats.md. Parallel
# by default (--jobs N, cpu_count-2; ~12x, byte-identical to serial); --jobs 1 / --limit = serial.
uv run python -m scripts.corpus_check check [--source github|toolshed|combined] [--repo NAME] [--limit N] [--jobs N]

# Upgrade-contract sweep: run the shipped `upgrade` over every tool in one or both
# modes and assert each mode's contract — minimal (the DEFAULT: fail-closed,
# undeclared stays undeclared, kept when valid at the baseline, minimum profile when
# bumped, validity, idempotence) and modernize (the opt-in gated walk: fail-closed /
# gate-cap / no un-fixed must_fix crossing / validity / idempotence) — retaining
# violations as fixtures + docs/corpus_data/upgrade_gate_errors.json.
uv run python -m scripts.corpus_check upgrade [--mode minimal|modernize|both] [--source github|toolshed|combined] [--repo NAME] [--limit N]

uv run python -m scripts.fetch_schemas         # download release XSDs
uv run python -m scripts.fetch_toolshed        # clone Toolshed repos
# Poll a curated list of major public Galaxy servers (usegalaxy.org/.eu/.org.au/.fr/.ca)
# for the Galaxy release each runs, and report the DEPLOYMENT FLOOR (lowest release across
# the set) + the newest vendored profile at or below it (the deployment ceiling).
# A tool whose profile exceeds the floor cannot install on the lagging servers. Writes a
# dated snapshot to docs/galaxy_server_versions.json — the source of truth for the
# vendored DEPLOYMENT_CEILING that caps `upgrade --modernize` (registry deployment.py,
# drift-guarded; registry decisions D23). After a re-poll moves the snapshot, update
# deployment.py to match (the guard test names both). Needs network, not in CI:
uv run python -m scripts.poll_galaxy_servers   # --no-write to report only
uv run python -m scripts.regenerate            # regenerate per-version models
uv run python -m scripts.gen_planemo_parity    # regenerate the GTR coverage table in docs/planemo_linter_parity.md (from rule metadata; freshness-tested)
uv run python -m scripts.gen_profile_boundaries # regenerate the per-boundary upgrade reference docs/profile_boundaries.md (from PROFILE_UPGRADE_CODES + the auto-fix registry; freshness-tested)
uv run python -m scripts.gen_gate_eligibility  # regenerate the auto-fix eligibility table docs/gate_eligibility.md (from rule metadata + gate_eligibility classification; freshness-tested)
uv run python -m scripts.measure               # ad-hoc corpus queries (--list)

# Macro organisation across the corpus (inline vs imported macro files,
# shared-macro importer distribution, the inverse imports-per-tool bundle-size
# histogram with a transitive/direct split, token names, <yield>, stale
# macro-token profiles). Writes docs/macro_corpus_stats.md (manually-regenerated
# artifact; needs the corpus, so it is not run in CI):
uv run python -m scripts.measure macro-topology
uv run python -m scripts.measure macro-profile-tokens

# Phase-3b decision input: where profile tokens are defined (inline / directly
# imported / deeper), sole-owned vs shared defining files, whether shared files'
# importers agree on the target profile (the fork-vs-edit-in-place question),
# and <import> scan-soundness (`..`/absolute). Writes
# docs/macro_profile_ownership_stats.md (manually-regenerated; needs the corpus):
uv run python -m scripts.measure macro-profile-ownership

# Decision-augmenting sizing sweeps (print-only; numbers folded into the
# decisions docs they back). command-iuc-heuristics sizes the GTR020.2/GTR032
# placeholders (check §D1); command-lone-amp classifies every lone `&` by class
# (redirect/quoted/pipe/background/joining) to settle the GTR032 deferral with
# data — the genuine `cmd1 & cmd2` anti-pattern is ~1 tool (check §D3);
# command-unquoted-var sizes GTR020.2 honestly — excluding Cheetah directive lines +
# tracking shell quotes, a genuinely-unquoted `$var` still fires on 73.2% of tools,
# so GTR020.2 (unlike GTR032) has real signal (check §D4); iuc011-fixability then
# resolves each unquoted `$var` against <inputs> and splits it into provable-vs-not
# classes — the provable subset {safe, attr_safe, builtin_path} (44.6% of
# occurrences) is auto-fixed by GTR020.1 (codemod §30/§32/§44 / check §D8), while the
# non-provable residual (30.2% #set/loop, plus text/multi/label/flag-idiom-boolean)
# keeps GTR020.2 advisory; shell-oracle-quoting sizes the bashlex-oracle delta on GTR020.1 vs the
# pure value-domain rule — now WIDENED 0 (the no-split/assignment-RHS widening was
# reverted as unsound: Cheetah renders values as literal text, so VAR=$x splits) /
# NARROWED 0 (no value-domain-safe fd-dup target corpus-wide); needs the
# galaxy-tool-source[shell-oracle] extra (tier-1 §17, codemod §31);
# select-quoting-safety sizes the GTR020.1 select/drill_down scope-narrowing (codemod
# §32): of the bare select/drill_down refs GTR020.1 would quote, 85.0% are provable
# (single-token option values, still auto-quoted) and 406 occ across 269 tools were
# unsound-before (a multi-flag `<option value="-b -h">` quoting fuses argv words);
# macro-fmt-idempotence backs fmt §D16:
uv run python -m scripts.measure command-iuc-heuristics
uv run python -m scripts.measure command-lone-amp
uv run python -m scripts.measure command-unquoted-var
uv run python -m scripts.measure iuc011-fixability
uv run python -m scripts.measure select-quoting-safety
uv run python -m scripts.measure shell-oracle-quoting
uv run python -m scripts.measure macro-fmt-idempotence

# Phase-3c sizing: clean @TOOL_VERSION@/@VERSION_SUFFIX@ extraction candidates
# (literal version="<base>+galaxy<suffix>" whose base == a package requirement
# version), split by whether a <macros> block exists or would need creating:
uv run python -m scripts.measure version-tokenization

# Shared-macros tokenization sizing (tokenize-version --macros-file, registry D20):
# for every macros file imported by >=2 tools, do the importers agree on one
# tokenizable version (the consensus case) or diverge. Tiny payoff today (built for
# the construction, not the corpus). ALSO exercises plan_shared_tokenization on every
# tokenizable corpus tool and retains any crash as a regression corpus
# (docs/corpus_data/version_token_sharing_errors.json). Needs the corpus, not in CI:
uv run python -m scripts.measure version-token-sharing

# Per-Galaxy-upgrade-code blast radius: how many tools `upgrade`-to-latest would
# cross each profile-behaviour code (backs codemod decisions §23 + the §22
# soundness boundary; data = the vendored PROFILE_UPGRADE_CODES):
uv run python -m scripts.measure semantic-upgrade-boundaries

# How much per-tool detection narrows that warning: per code, range-crossed vs
# actually-applicable counts across the corpus (backs codemod decisions §25;
# needs the corpus, so not run in CI):
uv run python -m scripts.measure upgrade-codes-applicability

# The TRUE 24.2 test-case-validation blocker population AND the parity oracle for our
# own shipped 24.2 checker (galaxy_tool_codemod.test_case_check, codemod §47): runs
# Galaxy's REAL strict validator (validate_test_cases_for_tool_source, the exact
# ProfileMigration24_2.advise call; needs the galaxy-tool-util dev dep) over every
# test-shipping tool, reporting clean / invalid (error-kind histogram) / validator-error
# (retained to docs/corpus_data/test_case_validation_errors.json) AND the confusion
# matrix of our provably-clean checker vs Galaxy's verdict, gated on ZERO unsound
# suppressions. Right-sizes + verifies the behavior gate's dominant stop
# (codemod §45/§46/§47); the Galaxy advantage is docs/galaxy_reimplementations.md.
# Needs the corpus, not in CI:
uv run python -m scripts.measure test-case-validation-truth

# Parity oracle for the GTR098/GTR099 datatypes pair (galaxy-tool-lint checks/datatypes.py,
# lint D36): runs Galaxy's REAL datatype linters (galaxy.tool_util.linters.datatypes
# ValidDatatypes/DatatypesCustomConf) over the corpus beside ours and asserts soundness —
# on MACRO-FREE tools (raw tree == expanded tree) ours matches Galaxy's verdict EXACTLY,
# on macro tools ours may only UNDER-report (it skips @…@ / macro-injected formats), never
# OVER-report (a false positive, which MUST be 0). Complements the drift guard (which pins
# our vendored datatype set == the installed galaxy-tool-util's) by proving the rule LOGIC
# matches. Retains every over-report to docs/corpus_data/datatype_validation_divergences.json.
# Backs docs/galaxy_reimplementations.md. Needs galaxy-tool-util + corpus, not in CI:
uv run python -m scripts.measure datatype-validation-truth

# Size + prove sound the GTR096 fix (FixTestParamQualification, codemod §48): for
# every tool the 24.2 checker blocks, apply the unique-leaf test-param qualification
# and report how many become provably clean, then validate each QUALIFIED tree with
# Galaxy's REAL validator (gated on zero unsound verdicts). The fix's corpus
# soundness proof; backs docs/proofs/GTR096.md. Needs galaxy-tool-util + corpus:
uv run python -m scripts.measure test-param-qualification

# Detector-precision sizing: how many tools the always-firing 20_09_consider_set_e
# detector (any <command> w/o strict=) would SOUNDLY stop flagging if tightened to
# "provably single simple command" — set -e cannot change a lone command (backs
# codemod decisions §28; needs the corpus, so not run in CI):
uv run python -m scripts.measure set-e-tightening

# Raw-tree vs post-macro-expansion detector divergence: per consider/must_fix code,
# over-flag (raw fires, a macro supplies the construct -> Galaxy would not) vs
# under-report (macro supplies the trigger -> the §25 gap) vs agree. Sizes the
# detection gap behind the macro-expansion detector port (backs codemod decisions
# §25; needs the corpus, so not run in CI):
uv run python -m scripts.measure macro-expansion-detection-gap

# Declared/defaulted profile vs the profile reached after `upgrade` (runs
# UpgradeToLatest per tool): before/after distributions + shift summary. Writes
# docs/upgrade_profile_shift_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure upgrade-profile-shift

# Where a *behavior-preserving* auto-upgrade would stall: walk each tool's
# profile toward latest, stopping at the first applicable Galaxy behaviour code
# (PROFILE_UPGRADE_CODES) the toolchain cannot auto-fix. Distribution of stuck
# tools by blocking profile/code, under must_fix-only and must_fix+consider
# policies. Writes docs/upgrade_behavior_block_stats.md (needs the corpus, so
# not run in CI):
uv run python -m scripts.measure upgrade-behavior-blocks

# Sizes the SHIPPED minimal-bump `upgrade` default (don't bump profile= unless
# strictly needed for validity; the behavior-gate walk is the opt-in --modernize):
# classify every tool as kept (validates at its baseline after repair) / bump-direct
# / bump-step-assisted / unreachable / unplaceable, split by the declared vs
# no-profile cohort, plus where the minimal bumps land vs the deployment ceiling.
# Writes docs/upgrade_minimal_need_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure upgrade-minimal-need

# Sizing for the format="input" runtime-gated fix (GTR015, codemod decisions §24):
# output <data format="input"> tools split by data-input cardinality (the single
# top-level data input subset is auto-fixable), plus the format_source-guard and
# crossing-gate skip counts (§24):
uv run python -m scripts.measure output-format-input

# <help> markup-format distribution: per-tool implicit-RST vs explicit
# format="markdown"/other (backs docs/galaxy_processing_model.md — RST renders
# server-side, markdown renders client-side; both supported):
uv run python -m scripts.measure help-formats

# Blank-line adoption: do tool authors already put a blank line between top-level
# <tool> sections in the SOURCE? Sizes the parked GTR003 convention for the IUC
# conversation (docs/iuc_conference_questions.md §4). Corpus: only 13.3% of section
# boundaries / 30% of tools use it. Print-only; needs the corpus:
uv run python -m scripts.measure blank-line-adoption

# Attribute-wrapping adoption: how often do tools wrap attributes across lines in the
# SOURCE (the multi-line layout our one-line serializer policy D8 collapses, which the
# IUC SHOULD allows for label/help)? Source-text scan (CDATA/comments stripped); backs
# iuc_conference_questions.md §5. Corpus: 20.8% of tools use a multi-line tag, 19.6%
# wrap label/help. Print-only; needs the corpus:
uv run python -m scripts.measure attribute-wrapping

# reStructuredText <help> codemod feasibility (backs
# docs/upgrade_research/restructuredtext_codemods.md; docutils-dependent, not in CI).
# help-rst-errors buckets docutils validity errors + sizes the deterministically-fixable
# subset (the GTR089.1 auto-fix target: ~62 tools / 32% of invalid); help-rst-features
# inventories RST node types + the non-CommonMark blockers; help-rst-to-markdown reports
# the RST->Markdown convertibility 2x2 (valid+convertible 74.5%, a node-type shape
# heuristic); help-rst-md-convert runs the REAL doctree->CommonMark converter + the
# render-equivalence gate (docutils html4css1 vs markdown-it-py "js-default", html:false
# — each side rendered exactly as Galaxy does; semantic-skeleton equality) and reports
# the true behaviour-equivalent convertible population: 73.4% PASS / 21.2% bail / 5.4%
# gate-fail (needs markdown-it-py, a galaxy-tool-source dev dep). Markdown target =
# markdown-it ^14 default preset (CommonMark+tables+strikethrough, html:false):
uv run python -m scripts.measure help-rst-errors
uv run python -m scripts.measure help-rst-features
uv run python -m scripts.measure help-rst-to-markdown
uv run python -m scripts.measure help-rst-md-convert

# Cheetah complexity of <command> + inline <configfile> (directive/variable-shape/
# hazard distribution; heuristic regex, not a Cheetah parse). Backs
# docs/upgrade_research/cheetah_variable_rewriting.md. Writes
# docs/cheetah_command_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure cheetah-command-complexity

# Parity + scope sizing for the SHIPPED faithful CDM lexer (galaxy_tool_source.cheetah_cdm,
# M5.1): run cheetah_spans() over every pure-text <command> body; report the parse-clean
# rate (vs the ~0.4% bail-to-regex) and the rename scope-shadowing population (clean
# bodies whose directive spans carry a #set/#for/#def local). Reproduces the Phase-0
# spike with shipped code. Needs the corpus (CT3 is now a base dep), print-only,
# not run in CI. Backs galaxy-tool-source/docs/decisions.md §19:
uv run python -m scripts.measure cheetah-cdm-coverage

# Save the ~0.4% of pure-text <command> bodies CT3 cannot compile (cheetah_spans -> None,
# where command_text/cheetah_refs fall back to the regex) as a retained corpus for later
# CT3-bail work. Writes docs/corpus_data/cheetah_cdm_bail_cases.json. Needs the corpus;
# not run in CI. Backs galaxy-tool-source/docs/decisions.md §19:
uv run python -m scripts.measure cheetah-cdm-bails

# Coverage of the first Cheetah MUTATOR (M5.3): attempt to rename every input definition
# of every tool via the shipped tier-1 cheetah_rename.rename_param, tallying clean apply
# vs each atomic bail (shadowed / mixed-content / lexer-bail / filter-bare-ref /
# cross-ref-residual). 96.3% apply cleanly (the tokenize-based <filter> rewrite, §22, took
# it from 93.1%; filter-bare-ref is now a 2.4% residual of ambiguous cases). Also checks
# Tier-B parity: rename_param_plan (offset-returning) must reach the same verdict as the
# tree mutator (96.8% same-verdict, 0 mismatches; the rest soundly decline). Needs the
# corpus (CT3 is now a base dep), print-only, not run in CI. Backs
# galaxy-tool-source/docs/decisions.md §20:
uv run python -m scripts.measure rename-coverage

# Cross-file rename sizing (tool bundle + sole-owned gate): rename every input definition
# across the tool AND its imported macros; classify tool-only / spills-to-macro (sole-owned
# vs shared) / bailed, plus the silent-break-today count (the bug the bundle fixes: 1.7% of
# renames). Reuses the shipped build_importer_map / rename_param_in_bundle. Writes
# docs/rename_macro_spread_stats.md. Needs the corpus (CT3 is now a base dep); not in CI. Backs
# galaxy-tool-source/docs/decisions.md §21:
uv run python -m scripts.measure rename-macro-spread

# The per-release XSD tightening ladder behind the Upgrade_vN gap audit
# (docs/deferred_fix_opportunities.md): diff every adjacent vendored schema pair and
# report only tool-stranding deltas — attr sites typed builtin->restricted, attrs
# newly use="required", changed patterns, REMOVED enum members (enum additions are
# widenings, ignored). Schema-only: no corpus, fixture-tested in CI:
uv run python -m scripts.measure xsd-tightenings

# Auto-fixable population for a 16_04_fix_interpreter codemod (GTR016): tools with a
# deprecated <command interpreter=…> split into bucket A (rewritable — any non-empty
# interpreter incl. flags/java -jar, the legacy composition being verbatim
# concatenation) / A-missing / B (leading-Cheetah) / empty-attribute, reusing the
# codemod's own eligibility predicate. Backs
# docs/upgrade_research/16_04_fix_interpreter.md. Writes
# docs/interpreter_bucket_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure interpreter-bucket-split

# Macro-file format/ftype residual (macro epic Phase 2a): tools stuck below latest
# that reach a newer profile once the literal format/ftype in their imported macro
# files are lowercased (the value Upgrade24_1 can't reach) — sound (temp-copy +
# re-validate, strict increase), split shared vs sole-owned defining file. Backs
# galaxy-tool-codemod/docs/macro-aware-normalization.md. Writes
# docs/macro_format_residual_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure macro-format-residual

# Phase-2b sizing: of the tools still stuck after 2a, how many reach a newer profile
# when token-supplied datatype values (format="@FMT@" whose <token> value is coercible)
# are also normalized — split inline vs imported token. 0 across the corpus => the
# heavyweight expansion-provenance layer is unjustified for datatypes (2a is complete).
# Writes docs/macro_token_residual_stats.md (needs the corpus, so not run in CI):
uv run python -m scripts.measure macro-token-datatype-residual

# Provable subset of text-param quoting (the GTR020.2 residual): of the bare
# $text_param <command> refs GTR020.1 leaves unquoted, how many resolve to a text
# param whose value a regex validator proves is one shell-inert, non-empty token
# (end-anchored, inert charset, non-optional) — i.e. provably safe to auto-quote.
# Corpus: 26 of 2,202 (1.2%); 91% have no validator. Backs the decision to keep
# text-param quoting advisory (GTR020.2), not auto-fixed. Print-only; needs corpus:
uv run python -m scripts.measure text-param-quotable

# GTR020.1 quoting scope vs the IUC "text/input/output files must be quoted" rule:
# classify the <command> vars GTR020.1 auto-quotes today by Galaxy param KIND
# (input-file / numeric / select / boolean / attr / builtin), so a proposed
# restriction to the IUC scope shows KEEP (input files) vs DROP (the safe no-op
# quoting of non-file single-token vars), plus the text-param / output-file refs
# the IUC rule wants but GTR020.1 can't behavior-preservingly quote (GTR020.2's
# advisory residual). Print-only; needs the corpus:
uv run python -m scripts.measure command-quoting-kinds

# Sizes the IUC "Booleans" anti-pattern in <command>: a Cheetah #if/#elif/#unless
# whose condition tests a type="boolean" param (GTR069 catches it for <conditional>
# elements; this is the command-side manifestation). Bare `#if $bool` is fine, so it
# splits each boolean #if block by what the body does — gates-other-params (references
# a DIFFERENT input param = the genuine "boolean used as a conditional for other
# options" anti-pattern), constant-only (literal-flag block; the idiom is
# truevalue/falsevalue + a bare $bool), other (refs only the bool / builtins) — to
# tell a sound advisory from noise. Uses the CT3 lexer; print-only; needs the corpus.
# Corpus: of 9,302 command tools, 1,207 use a boolean #if; gates-other-params 342
# tools / constant-only 593 tools:
uv run python -m scripts.measure command-boolean-if

# `.lint_skip` reconciliation sizing (the `lint-skip` command, cli D19 / registry
# D24): classify every planemo `.lint_skip` name-line, mirroring the shipped
# removability gate, into auto-removable (fixed-removable + already-stale),
# coverage-partial (covered only incidentally, kept), located (fires, kept), and
# out-of-coverage (kept). Print-only; needs the corpus. Corpus: auto-removable
# 160 / 640 lines (25.0%):
uv run python -m scripts.measure lint-skip-corpus

# GTR013 macro-`<expand>` placement: sizes whether the future faithful-resolution
# layer earns its plumbing over the shipped pinning fix (codemod §53). Per tool
# with a top-level `<expand>`, shallow-resolve the macro to its element tags, then
# compare PINNING (every expand pinned) vs RESOLUTION (a single-known-IUC-tag
# expand scored by its resolved tag) layouts. Decision number = tools the two
# disagree on (an `<expand>` the author placed out of its IUC slot). Corpus:
# 4,081/9,373 have a top-level <expand>, 452 differ. Print-only; needs the corpus:
uv run python -m scripts.measure expand-reorder-resolution

# version= attribute shape distribution + two-token provenance (backs
# docs/iuc_conference_questions.md #1, the suite-wide version-suffix question).
# Per tool with a version=, classify the shape, and for the
# @TOOL_VERSION@+galaxy@VERSION_SUFFIX@ two-token form resolve whether both tokens
# are imported from a macros file vs defined inline (tier-1 token_definitions).
# Corpus: 2,248/8,903 two-token, 73.9% of those import both tokens. Print-only;
# needs the corpus:
uv run python -m scripts.measure version-suffix-shape
```

**Note:** invoke as `python -m scripts.X`, not `python scripts/X.py` — the
scripts import from `scripts._shared`, which requires `scripts` to be
importable as a package (i.e. the workspace root on `sys.path`).

**Corpus-completeness guard:** a full (stats-regenerating) `corpus_check`
sweep over the toolshed source aborts up front if the toolshed corpus looks
partial — no `galaxy-toolshed/manifest.json` (`fetch_toolshed` writes it only on
completion) or far fewer clones on disk than the manifest records (a `.local`
clobbered by a merge checkout). Regenerating a `docs/*_stats.md` page from a
partial corpus silently corrupts every number, so the sweep refuses; re-run
`fetch_toolshed` (additive) or pass `--no-stats`. Partial sweeps (`--limit` /
`--repo`) don't regenerate stats and so aren't gated.

## Coding standards

All hand-written code follows **dignified-python** (governs), with
**optimized-python** as a secondary reference. Both skills are vendored at
`.claude/skills/dignified-python/` and `.claude/skills/optimized-python/`.
`make check-skills` (= `scripts/check_vendored_skills.py`) reports when either
vendored skill has drifted from its upstream (a weekly `vendored-skills.yml` job
also opens a tracking issue); re-vendor deliberately, since upstream can change
the governing standard.

Key rules:
- Prefer LBYL for routine branching; use exceptions at the CLI error boundary
  (chained `from e`), at third-party API boundaries, and where the operation
  itself is the authoritative test (dignified-python's softened stance).
- `pathlib.Path` with explicit `encoding="utf-8"` on all text I/O.
- Keyword-only arguments after the first.
- Absolute imports, no re-exports, no `__all__`.
- No import-time side effects (`@cache` for module state).
- TDD for codemod-tier work — failing test first, then minimum code to pass.

## Architecture

Tiers, each independently installable:

| Tier | Layer | Package | Owns |
|---|---|---|---|
| 0.5 | **rule metadata** | `galaxy-tool-refactor-rules` | `RuleMeta` descriptor + `render_rule_reference_table`. Dependency-free; shared by tiers 2 & 3 so the GTR registry spans both. |
| 1 | **parsing & validation** | `galaxy-tool-source` | `load_tool` / `parse_tool` / `validate_tool`, typed xsdata views. **No serializer.** |
| 2 | **structure** | `galaxy-tool-codemod` | `CodemodCommand` visitor framework + bundled structural codemods (each carries a `RuleMeta` GTR code; see `catalog.coded_codemods()`) + `canonical_codemods()` contract. |
| 3 | **formatting** | `galaxy-tool-fmt` | Cosmetic rules (indent / empty-element shorthand; the blank-line rule GTR003 is parked pending IUC input, fmt §D4) + the shared `cli_support` CLI engine. The only tier that serialises canonical output XML. |
| 3.5 | **advisory checks** | `galaxy-tool-lint` | Detect-only IUC best-practice checks (`GTR` codes, `RuleMeta.detect_only`); read-only LBYL queries over tier 1 yielding `Violation`. Depends only on tiers 1 + 0.5. |
| 3.6 | **rule registry / rulesets** | `galaxy-tool-refactor-registry` | Unified, code-addressable `RuleHandle` over all three families + named rulesets (`cosmetic`/`default`/`iuc`/`strict`) + `run`/`upgrade`/`detect`. **Library-first** (no click/exit; structured I/O; introspectable). Depends on 0.5/1/2/3/3.5; lower tiers don't depend on it. |
| 4 | **app / CLI** | `galaxy-tool-refactor-cli` | The user-facing `galaxy-tool-refactor` CLI. Consumes the registry facade (tier 3.6); owns `format`, `upgrade`, `check`, `find-references`, `rename-param`, `rulesets`, `rules`, `normalize-macros`, `convert-help`, `tokenize-version`, `lint-skip`. |
| 4 | **MCP server** | `galaxy-tool-refactor-mcp` | An agent-facing MCP server over the registry facade (a sibling of the CLI). A thin FastMCP binding (`server.py`) over a protocol-agnostic adapter (`service.py`, facade → JSON). Tools (9): `format_tool`/`upgrade_tool`/`check_tool`/`convert_help_tool`/`tokenize_version_tool`/`find_references_tool`/`rename_param_tool`/`list_rulesets`/`list_rules` — every single-document facade op (repo-scoped `normalize-macros`/`lint-skip` stay CLI-only; mcp D7). Goal 1 of `docs/vision.md`; agent-authored rules (Goal 2) remain future. |

**Orchestration lives in the registry facade (tier 3.6); the CLI is a thin
front-end.** Each lower tier is consumable standalone; the facade composes them
into one code-addressable rule set with rulesets and a library-first
`run`/`upgrade`/`detect` API. The CLI (`galaxy-tool-refactor-cli`) depends on the
facade (plus fmt's `cli_support` engine and tier-1 parsing) and owns eleven
commands:

- `galaxy-tool-refactor format` — apply a ruleset's fixable rules (the default
  ruleset = `canonical_codemods()` + cosmetic) then serialise. Safe, idempotent; never changes
  `profile=`. Advisory rules in a selection (`--ruleset strict`) are reported as
  notes, never applied. (No longer byte-identical to the pre-partition historical
  output: GTR020.1 — `SingleQuoteCommandVars` — now also single-quotes the
  *provably*-single-valued Cheetah vars in `<command>`, a behaviour-preserving fix;
  codemod `docs/decisions.md` §30.)
- `galaxy-tool-refactor upgrade` — repair, then profile placement, then
  format. Opt-in, semantic. **Minimal-bump by default**: `profile=` moves only
  when strictly needed for validity — kept when the repaired tool validates at
  its baseline, undeclared stays undeclared, else the minimum valid profile at
  or above the baseline (`UpgradeToValid`, GTR097). `--modernize` opts into
  the **behavior-preserving walk**, capped at the lower of two ceilings: the
  behaviour ceiling (the newest vendored profile reachable without crossing
  a Galaxy `must_fix` change that applies to the tool and that no
  runtime-gated fix provably clears; the auto-fix probe is
  proof-by-execution per tool) and the deployment ceiling (the newest
  profile every major public Galaxy server runs; vendored in registry
  `deployment.py`, drift-guarded against `docs/galaxy_server_versions.json`).
  Stop reports name the blocking code(s) and link to
  `docs/profile_boundaries.md`, or name the deployment cap; applicable
  `consider` changes warn but never stop.
  `--allow-behavior-change` lifts the walk's behaviour gate only (an error
  without a walk mode); `--target-profile` walks to an explicit vendored
  profile, implies the walk, and may exceed the deployment ceiling. The
  shared imported-`@PROFILE@` bump honors the same mode per importer. No
  `--ruleset` (rulesets are a format/check concept); `--select`/`--ignore`
  adjust its fixable rule set. (Codemod `docs/decisions.md` §45/§50,
  registry D21/D22/D23, cli D16/D17/D18; proof:
  `docs/proofs/behavior-gate.md`.)
- `galaxy-tool-refactor check` — report-only over the selected rules' detect
  phases. Fixable findings exit non-zero; advisory findings appear only
  under `--ruleset strict` and are informational unless `--strict`.
- `galaxy-tool-refactor find-references NAME PATHS` — read-only query (not a rule):
  every Cheetah `$NAME` reference site across a tool **and its imported macro files**
  (cli `docs/decisions.md` §D8/§D10; tier-1 Cheetah reference model §18).
- `galaxy-tool-refactor rename-param OLD NEW PATHS [--repo-root DIR] [--across-importers]`
  — the mutating sibling of `find-references`: rename a parameter across every Cheetah
  section, by-name cross-ref attribute, and `<tests>` mirror, plus the definition —
  across the tool **and its imported macros** (the bundle), atomically. `--repo-root`
  proves a touched macro is sole-owned before editing it (a shared macro is skipped +
  reported, or — with `--across-importers` — renamed across every importer in lockstep
  when they all agree). Fixes a silent bug: a param referenced only in an imported macro
  is no longer left dangling (1.7% of corpus renames; `scripts.measure
  rename-macro-spread`). First Cheetah mutator (M5.3); tier-1 `cheetah_rename` §20 +
  `bundle` §21, cli `docs/decisions.md` §D9/§D10/§D11, registry D14.
- `galaxy-tool-refactor rulesets` / `rules` — introspection of the baked-in
  rulesets and rules.
- `galaxy-tool-refactor normalize-macros` — opt-in, repo-scoped: lowercase literal
  `format`/`ftype` in `<macros>`-root files (the macro-library analog of 24.2
  normalization the per-tool `upgrade` can't reach). Writes files other than the one
  named, so it is never folded into `format`/`upgrade` (cli `docs/decisions.md` §D7).
- `galaxy-tool-refactor convert-help` — opt-in: convert an RST `<help>` to Markdown
  (`format="markdown"`, GTR092) when *provable* — profile ≥ 24.2 (the XSD gate; run
  `upgrade` first) and the markdown-it rendering semantically equals the docutils
  rendering (tier-1 `rst_markdown`, the `[markdown]` extra). Swaps Galaxy's rendering
  engine, so never part of `format`/`upgrade` (cli §D12, codemod §38, xml §24).
- `galaxy-tool-refactor tokenize-version` — opt-in: factor a literal
  `version="<base>+galaxy<suffix>"` into `@TOOL_VERSION@`/`@VERSION_SUFFIX@` tokens
  shared with the matching package requirement, kept only when the expansion-equality
  gate proves the macro expansion byte-identical. A multi-element style restructure,
  so never part of `format`/`upgrade` (cli §D13, codemod §43, registry D19).
  `--macros-file NAME` puts the tokens in a macros file the tool imports instead of an
  inline block: created when absent, merged into an existing file when proven inert for
  its other importers, or a same-version directory group tokenized together (consensus).
  Shared-macros edits are proof-by-execution gated (cli §D14, registry D20).
  `--adopt-suffix` is the **identity-changing** opt-in: for a bare version equal to a
  package requirement, ADD `+galaxy0` and tokenize (`1.20` becomes `1.20+galaxy0`).
  Not behaviour-preserving (the published version changes), so it is gated on the
  controlled-change gate (expansion differs solely in the version), inline only, and
  never in `format`/`upgrade` or MCP (cli §D15).
- `galaxy-tool-refactor lint-skip PATHS` — opt-in convenience: clean up planemo
  `.lint_skip` sidecars. For each tool directory with a `.lint_skip`, apply the
  toolchain's fixes and delete a suppression line **only when it can prove the line
  is resolved** — the planemo linter must be completely covered (every covering GTR
  code is a faithful check-tier port or a canonical codemod; derived, not
  hand-curated) and clean on every tool in the directory after the fix. Everything
  else is left untouched and unmentioned (`check` reports the full picture). Rewrites
  files other than the one named (the tool XML + its `.lint_skip`), so never part of
  `format`/`upgrade` (cli §D19, registry D24; `docs/lint_skip.md`).

Selection is shared across `format`/`upgrade`/`check`: `--ruleset NAME`
(repeatable / comma-separated — the union of the named sets), `--select CODE…`,
`--ignore CODE…` (ruff-style precedence `--ignore` ▸ `--select`
▸ `--ruleset`; `--select` replaces the ruleset's set). Rules and rulesets are
developer-defined — no user-defined rules.

`galaxy-tool-fmt`'s own CLI is **cosmetic-only** and has no codemod
dependency (the former `[canonical]` extra is gone). The library
(`format_tool_document`) is likewise cosmetic-only.

See `galaxy-tool-source/docs/decisions.md` §9 for the three-tier
rationale; `galaxy-tool-refactor-cli/docs/decisions.md` §D1,
`galaxy-tool-fmt/docs/decisions.md` §D12, and
`galaxy-tool-codemod/docs/decisions.md` §16 for the app tier, the
fmt-CLI-cosmetic-only reversal, and the `canonical_codemods()` /
`AUTO_UPGRADE_CODEMODS` split; and
`galaxy-tool-refactor-rules/docs/decisions.md` §D1 (+ codemod §15,
fmt §D11) for the shared `RuleMeta` extraction and the cross-tier
GTR registry; and `docs/iuc_best_practices.md` (+ codemod §17) for the
IUC best-practices coverage map and the `<tool>` element-order codemod
(GTR013); and `galaxy-tool-refactor-registry/docs/decisions.md` D1–D4
(+ cli `docs/decisions.md` D4, fmt §D15) for the rule-registry facade,
rulesets, per-rule selection, and the move of orchestration below the CLI.
For the per-profile upgrade map (what each profile bump requires, the
structural-vs-semantic split, and the validity-as-oracle soundness boundary)
see `docs/profile_upgrades.md` (+ codemod `docs/decisions.md` §22).
`galaxy-tool-refactor-mcp` is the agent-facing MCP server over the facade (Goal 1
of its `docs/vision.md`, shipped — see `galaxy-tool-refactor-mcp/docs/decisions.md`
D1); the agent-authored-rules direction (Goal 2) is still future.
