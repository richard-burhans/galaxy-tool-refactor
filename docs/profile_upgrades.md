# Profile-upgrade ledger

A living map of every vendored Galaxy tool-XSD profile and **what is required to
carry a tool from each profile to the next**. Its purpose is to make the
automate-or-not decision for each `upgrade_vN` codemod legible: which steps are a
safe, mechanical, behaviour-preserving transform, and which need human judgement.

> **Update this doc as discovery continues.** Rows marked `TBD` are not yet
> analysed; the Corpus column is refreshed from the discovery sweep.

Related: the soundness boundary this ledger rests on is recorded in
[`galaxy-tool-codemod/docs/decisions.md` §22](../galaxy-tool-codemod/docs/decisions.md);
the upgrade machinery itself is §13 (`UpdateProfile`) and §14 (`UpgradeToLatest`).

---

## The soundness boundary (why this ledger is structured the way it is)

The upgrade machinery rests on one claim:

> A tool that **validates** under profile *X* needs no XML modification to *be* a
> valid profile-*X* tool — `UpdateProfile` simply declares `profile="X"`.

This is **sound for *structural* (XSD) acceptability** and is exactly why most
transitions need no codemod (see below). It is **NOT sufficient for *behavioural*
equivalence**: Galaxy's `profile` is a *runtime-compatibility contract*, not only
a schema selector. Some profile bumps change runtime defaults (error/exit-code
detection, `set -e` / Cheetah strictness, output-metadata inference, command-line
quoting) that the XSD does **not** encode. A tool can validate under both the old
and new profile yet *behave* differently once bumped.

Consequences for this ledger:

- **Structural** column = what the XSD changed (what *could* break validation).
- **Semantic** column = runtime behaviour the bump changes that the XSD is silent
  on (the risk validation cannot see). This is the column that gates `auto`.
- A transition is **`auto`** only when the structural delta is mechanically and
  behaviour-safely resolvable *and* the semantic column carries no
  behaviour-changing risk for the affected construct. Otherwise `needs-thought`.

## Why most transitions need no codemod

A **purely additive** schema change — new elements / attributes / assertion kinds,
removing and restricting nothing — cannot invalidate a tool that was valid under
the older profile: everything it used is still allowed. So for additive
transitions, "validates at the newer profile" holds for every previously-valid
tool, and `UpdateProfile` carries it forward with no content change. Only
transitions that **remove** a construct or **add a restriction** (a `pattern`
facet, a new `required`, a forbidden nesting) can strand a tool — those are the
only candidates for an `upgrade_vN`.

## Methodology — how these conclusions were reached (and how to refute them)

Every safety claim here rests on **three independent evidence sources**, each
reproducible. The verdict for a transition is their synthesis; any one of them
failing is grounds to revise a row.

### 1. Structural delta — what *could* break validity (XSD diff)

The committed per-release XSDs are the source of truth. For any transition:

```bash
diff galaxy-tool-source/src/galaxy_tool_source/schema/galaxy-<from>.xsd \
     galaxy-tool-source/src/galaxy_tool_source/schema/galaxy-<to>.xsd
```

Vendored set + commit/branch provenance: `…/schema/manifest.json` (28 XSDs,
16.10→26.1, each pinned to a Galaxy release-branch commit). The per-transition
signal used to classify each row (net-new / net-gone element & attribute
declarations, plus `pattern`/`use="required"`/`enumeration` churn) is produced by:

```bash
# from galaxy-tool-source/src/galaxy_tool_source/schema/
for adjacent pair (a,b): diff a b | grep -E '^[<>]' \
  | grep -oE '<xs:(element|attribute|group|attributeGroup) name="[^"]+"'   # added vs removed decls
  ; diff a b | grep -cE 'pattern value|use="required"|xs:enumeration'      # restriction churn
```

**The logical core:** a **purely additive** schema step — one that *adds* element
/ attribute / assertion declarations and *removes or restricts nothing* — cannot
invalidate a tool that was valid under the older profile, because every construct
the tool used is still permitted. So for additive steps, "validates at the newer
profile" holds for **every** previously-valid tool, with no content change. Only
**removals** and **new restrictions** (a `pattern` facet, a new `required`, a
newly-forbidden nesting) can strand a tool — those are the only `upgrade_vN`
candidates, and in this corpus they are exactly four steps.

**Limitation (and why source 2 is needed):** the name-diff heuristic is coarse —
a *relocated* or *renamed* declaration shows up as net-gone even though no tool is
actually stranded (marked `additive*`). The XSD diff tells you what is *possible*,
not what *happens*. The corpus sweep is the empirical arbiter.

### 2. Corpus evidence — what *actually* breaks (combined sweep)

```bash
uv run python -m scripts.corpus_check codemod \
    galaxy_tool_codemod.upgrades:UpgradeToLatest --source combined
```

This runs the full upgrade pipeline over **both** corpora — GitHub
(`corpus_sources.json`, 21 repos) and the Galaxy ToolShed
(`scripts/fetch_toolshed.py`), sha256-deduplicated — and reports, for every tool:
whether it reached the latest profile, and if not, the version it **stuck** at
(`STICKING POINT … need upgrade codemod for <version>`), plus per-`upgrade_vN`
advance counts. A tool is "stuck at V" when, after the pipeline, its
`newest_valid_profile` is V < latest. Eligibility = "validates at some vendored
profile" (`eligibility.py`).

The sweep is also the **soundness gate**: it re-parses and re-applies to assert
**idempotence**, and re-validates every output to assert **post-validity**. The
2026-06-01 run: 8,607 eligible, **0 non-idempotent / 0 post-validate-failed /
0 crashed**, 8,566 reach latest, only the four breaking steps advance any tool,
residual = the 24.1 macro-reachability/uncoercible cases + 2 tool-bugs.

**How to refute the structural-soundness claim with this:** re-run the sweep. If
any tool comes back **non-idempotent** or **post-validate-failed**, or a *new*
`STICKING POINT` appears at a step we call additive, the "additive ⇒ safe" /
"validity is the right structural oracle" claim is broken for that step — open it
as a row to scope. New corpus repos or a new vendored XSD are the likely triggers.

### 3. Semantic delta — what validity *cannot* see (Galaxy docs)

Profile-gated **runtime** behaviour is **not derivable from the XSD**; it lives in
Galaxy's tool-execution code and is documented under the `<tool> profile`
attribute in the Galaxy schema docs:
[docs.galaxyproject.org/en/latest/dev/schema.html](https://docs.galaxyproject.org/en/latest/dev/schema.html)
(authoritative source = `lib/galaxy/tool_util/parser/` / the profile handling in
the Galaxy repo). The Semantic column transcribes those notes per version.

**How to refute / extend the semantic findings:** read the `profile` attribute
documentation for the version in question (or the Galaxy source that branches on
`profile`); if a profile bump changes a runtime default not listed in the Semantic
column, add it. A demonstrated case where a tool validates identically at X and
X+1 but *runs* differently after the bump **supports** the boundary in §22 (it is
the boundary); it does not refute the *structural* soundness, which is about
validity only.

### Synthesis → the `Automatable` verdict

`none` when the step is additive **and** strands no corpus tool (UpdateProfile
carries it; the Semantic cell flags any behaviour the bump opts into). `auto` when
a step is a **restrict** that strands tools **and** the fix is a mechanical,
behaviour-preserving transform verified idempotent + post-valid by the sweep.
`needs-thought` when the fix would be lossy or require a semantic judgement (left
stuck and reported, never guessed).

---

## Ledger

28 vendored profiles (`16.10` → `26.1`); `26.1` is latest. Structural class from
the XSD diff; Corpus from the combined discovery sweep. Automatable:
`none` = no codemod needed · `auto` = mechanical & behaviour-safe codemod ·
`needs-thought` = lossy/semantic, left stuck & reported.

> **Sweep run 2026-06-01** (`--source combined`): 8,607 eligible · 7,227 modified ·
> **8,607 idempotent · 0 non-idempotent · 0 post-validate-failed · 0 crashed** ·
> **8,566 reached latest (26.1), 41 below**. Per-step advances: 19.01→9, 24.0→1,
> 24.1→111, 25.1→5. Only sticking points: 24.1 (39), 21.05 (1, tool-bug), 21.09
> (1, tool-bug). No transition outside the four below strands a real tool — the
> empirical confirmation that every additive step needs no codemod.
>
> The **declared (or 16.01-defaulted) → reached** profile distribution this implies
> — what `upgrade` actually moves — is `docs/upgrade_profile_shift_stats.md`
> (`scripts/measure.py upgrade-profile-shift`): of all 9,358 unique tools (a wider
> population than the eligible-only sweep above), 60.9% declare no profile (run as
> 16.01), and **91.7% (8,582) reach 26.1** after `UpgradeToLatest`; 7.8% validate
> nowhere (need `FixTypos` repair first).

The **Semantic delta** column is keyed to Galaxy's own catalogue: each cell names
the `upgrade_codes.json` code(s) (mirrored as `PROFILE_UPGRADE_CODES` in
`galaxy-tool-codemod/.../profile_semantics.py`) whose profile == the *To*
version, with their `level` (`must_fix` / `consider`). "none documented" = no
upgrade code at that step. The behaviour takes effect for a tool **declaring** the
*To* profile (bumping `profile=` into that row opts in). Since 2026-06-12 the
default `galaxy-tool-refactor upgrade` **stops** at the behaviour ceiling: it
never crosses a `must_fix` code that applies to the tool (per-tool detection
ported from Galaxy's advisor; codemod `docs/decisions.md` §25 + §45) unless a
runtime-gated fix provably clears it on that tool; applicable `consider` codes
are warned about and do not stop the walk. `--allow-behavior-change` restores
the historical walk-to-latest with the §23 warning; the user-facing per-code
"what changed and what to do" reference is
[`profile_boundaries.md`](profile_boundaries.md) (generated, freshness-tested).
When a bump that advances the profile crosses **no** applicable code (or every
applicable `must_fix` was provably fixed), the inverse is surfaced
affirmatively: `UpgradeResult.behavior_preserving` is `True` and a clean-pass
note says so; proving the governed construct is absent (or fixed) lets the
tool move past the boundary behaviour-safely (codemod §23 + §45). The per-code
corpus blast radius is `scripts/measure.py
semantic-upgrade-boundaries`, crossed-vs-applicable is `scripts/measure.py
upgrade-codes-applicability`, and where the gated `--modernize` walk stops is
`docs/upgrade_behavior_block_stats.md` (`scripts/measure.py
upgrade-behavior-blocks`, computed with the shipped gate functions);
pinnability is in `galaxy-tool-codemod/docs/behavior-preserving-upgrade.md`.

> **Two scopes the catalogue doesn't cover, flagged inline:** (1) **16.04**'s four
> codes (interpreter/output-format/exit-code/extra-file) predate the oldest vendored
> XSD (16.10), so they have no transition row — they gate the *no-profile* baseline
> (a no-profile tool runs as 16.01; see the soundness §22). (2) A few real runtime
> changes the Galaxy **schema docs** describe are **not** in `upgrade_codes.json` —
> 19.01 `<stdio>`-prepend, 19.05 Python 2→3, 25.1 `<credentials>` — marked
> "(schema docs; not an upgrade code)" in the cell.

| From → To | Structural class | Structural delta (XSD) | Semantic delta (runtime, not in XSD) | Corpus stuck | Automatable | Codemod |
|---|---|---|---|---|---|---|
| 16.10 → 17.01 | additive | `+conversion`, EDAM `edam_operation(s)`/`edam_topic(s)`, `datatype_isinstance`, `shared_inputs` | none documented | 0 | none | — |
| 17.01 → 17.05 | additive | `+decompress`, `meta_ref`, `refresh_on_change`, `input_dataset` | none documented | 0 | none | — |
| 17.05 → 17.09 | additive* | metadata hooks (`+hook`, `provided_metadata_*`, `default_identifier_source`); `ftype` decl relocated (not dropped) | `17_09_consider_provided_metadata_style` (consider, niche): galaxy.json metadata format; restore via `provided_metadata_style="legacy"` | 0 | none | — |
| 17.09 → 18.01 | additive* | `+import`/`token`/`xml` (macro elems); `request_parameter_translation` → `request_param_translation` (rename) | `18_01_consider_structured_like` (consider): `structured_like` must be fully qualified; `18_01_consider_home_directory` (consider, niche): per-job `$HOME`, restore via `use_shared_home="true"` | 0 | none | — |
| 18.01 → 18.05 | additive | no tool-facing decl change | none documented | 0 | none | — |
| 18.05 → 18.09 | additive | `+data_style`, `tags` | `18_09_consider_python_environment` (consider): data-manager tools run without Galaxy's virtualenv (the fully-qualified-reference rule is **18.01**'s `structured_like`, not here) | 0 | none | — |
| 18.09 → 19.01 | additive | `+has_h5_attribute`/`has_h5_keys` assertions | `<stdio>` checks prepend to preset checks (schema docs; not an upgrade code) | 0 | none | — |
| **19.01 → 19.05** | **restrict** | output element restructure (`Output*` groups); **`name` required on output `<data>`** | default Python 2.7 → 3.5 (schema docs; not an upgrade code) | **9** | **auto** | **GTR008** |
| 19.05 → 19.09 | additive | `+entry_points`/`port`/`url`, `xrefs`, `has_n_lines` | none documented | 0 | none | — |
| 19.09 → 20.01 | additive | `+assert_command_version`, `has_size` | none documented | 0 | none | — |
| 20.01 → 20.05 | additive | `+delta_frac`, `sort_by` | `20_05_consider_inputs_as_json_changes` (consider): unselected optional select/data_column → JSON `null` (not `"None"`); multiples → lists | 0 | none | — |
| 20.05 → 20.09 | additive | `+file_sources`, `recurse`/`sort_by`/`filename` | `20_09_consider_set_e` (consider): `set -e`, restore via `strict="false"`; `20_09_consider_output_collection_order` (consider): collection-element sort order significant in tests | 0 | none | — |
| 20.09 → 21.01 | additive | `+creator`/`person`/`organization` (schema.org `Thing`) | none documented | 0 | none | — |
| 21.01 → 21.05 | additive | `+meta_file_key` | none documented | 0 | none | — |
| 21.05 → 21.09 | additive* | `+required_files`/`include`/`exclude`; (one tool strands here — `has_size/@delta_frac` tool-bug) | `21_09_fix_from_work_dir_whitespace` (must_fix → auto-fixed by **GTR014**): `from_work_dir` whitespace becomes literal; `21_09_consider_python_environment` (consider): `data_source` tools lose Galaxy's venv | 1 (tool-bug) | needs-thought | — |
| 21.09 → 22.01 | additive | test-assertion expansion (`TestAssertions*` groups, `xml_element`, …) | none documented | 1 (tool-bug) | needs-thought | — |
| 22.01 → 22.05 | additive | `+resource`; job `action` reorg | none documented | 0 | none | — |
| 22.05 → 23.0 | additive | `+sep`, `reverse_sort_order` | `23_0_consider_optional_text` (consider): inferred-optional text params template as `None` (was `""`) | 0 | none | — |
| 23.0 → 23.1 | additive | `+has_json_property_with_*` assertions | none documented | 0 | none | — |
| 23.1 → 23.2 | additive | `+collection`/`element`/`default` (in test output context) | none documented | 0 | none | — |
| 23.2 → 24.0 | additive | `+macro`/`param`/`request_body`/`request_headers` (HTTP data source) | `24_0_consider_python_environment` (consider): `data_source_async` loses Galaxy's venv; `24_0_request_cleaning` (consider): undeclared request params dropped | 0 | none | — |
| **24.0 → 24.1** | **restrict** | `<filter>` no longer allowed in a `<collection>`'s child `<data>`; discover-datasets attrs moved to `OutputDiscoverDatasetsCommon` | none documented | **1** | **auto** | **GTR009** |
| **24.1 → 24.2** | **restrict** | `format`/`ftype` gain a `pattern` facet (`FormatList`/`Format`, lowercase tokens); `TestAssertion` group consolidated | `24_2_fix_test_case_validation` (must_fix): stricter `<test>` validation — `data_column` params require a valid `data_ref` | **39** (residual; was 53) | **partial** | **GTR010** |
| 24.2 → 25.0 | additive | `+fields`/`icon`, data-table `src`/`table_name` | none documented | 0 | none | — |
| 25.0 → 25.1 | additive | `+credentials`/`secret`/`variable` | tool credentials via `<credentials>`, not user prefs (schema docs; not an upgrade code) | 0 | none | — |
| **25.1 → 26.0** | **restrict** | `<trackster_conf>` dropped; `<action>` + `name`/`output_name` attrs removed; `+min`/`max` | none documented | **5** | **auto** (trackster) | **GTR011** |
| 26.0 → 26.1 | additive | `+credentials`/`secret`/`variable` (top-level) | none documented | 0 | none (latest) | — |

\* "additive*" = the diff shows a relocation/rename rather than a true removal; no
corpus tool is stranded, so it behaves as additive in practice. Confirm per the
sweep before treating any such row as breaking.

> **The semantic column is the crux of the soundness boundary.** Rows like
> 19.01→19.05 (Python 3), 20.01→20.05 (JSON `None`/lists), 20.05→20.09 (`set -e`),
> 17.09→18.01 (`structured_like` must be qualified), and 22.05→23.0 (optional text
> → `None`) are
> **structurally additive yet behaviourally loaded**: a tool validates identically
> before and after, so `UpdateProfile` will bump it with no codemod — but the
> bumped tool *runs* under the new defaults. This is precisely why "validates at X"
> does not prove "behaves the same at X" (codemod decisions §22). Automatic
> `upgrade_vN` codemods address only the **restrict** rows; the semantic risk on a
> bump is the user's to review (upgrade is opt-in/semantic, §16).

---

## Detailed notes — the breaking transitions

### 19.01 → 19.05 — `name` required on output `<data>` (GTR008)
**Delta:** 19.05 restructured the output groups and made `name` **required** on
output `<data>`. **Stuck:** 9 tools (all `ucsb-phylogenetics/ucsb_phylogenetics`),
bare `<data from_work_dir="…"/>` with no `name`. **Auto rationale:** the 9 stuck
tools never *reference* the output name (not in `<command>`, not in a `<test>`), so
a synthesised, collision-free placeholder (`output`, `output2`, …) is
behaviour-neutral. This is a *synthesis* (placeholder identity), not recovery of
author intent — a judgement call on a one-repo signal. **Semantic check:** TBD —
confirm no 19.02–19.05 runtime default change interacts with unnamed outputs.

### 24.0 → 24.1 — `<filter>` forbidden inside a collection's `<data>` (GTR009)
**Delta:** a collection element now admits only `actions`/`change_format`; a
top-level output `<data><filter>` is still fine. **Stuck:** 1 (`phac-nml/kat_filter`),
whose paired collection's two `<data>` carried the *same* filter. **Auto
rationale:** an identical all-or-nothing filter on every child is equivalent to one
filter on the `<collection>`, so hoist + drop is semantics-preserving. Refuses
non-equivalent cases (differing/partial child filters, a collection that already
has its own filter) — those stay stuck and are reported. **Also in this delta:**
discover-datasets attributes (`directory`/`ext`/`pattern`/`recurse`/`sort_by`/
`visible`) were moved into a shared group; confirm via sweep that no tool strands
on that move (none observed).

### 24.1 → 24.2 — `format`/`ftype` pattern facet (GTR010) — **partial**
**Delta:** `format` (and `ftype`) gained a `pattern` facet: `FormatList`
(`<param>`, comma-separated `[a-z0-9._-]` tokens) / `Format` (`<data>`, one such
token). **Stuck:** 53 → 39 residual after the codemod. **Auto rationale:**
lowercase + whitespace-strip per comma token is semantics-preserving (Galaxy
datatype extensions are lowercase; whitespace was never significant); a value that
normalises to empty is dropped (empty restriction = no restriction). **`needs-thought`
residual (~39):** ~18 with a coercible value living in an **imported macro file**
the per-tool codemod can't reach (cross-file normalisation — see
`galaxy-tool-codemod/docs/macro-aware-normalization.md`); ~11 non-datatype junk
(`?`, `plain text`, `$var`); ~9 single-token-context comma-lists with no basis to
pick one datatype. These are reported, not guessed.

### 25.1 → 26.0 — `<trackster_conf>` dropped (GTR011)
**Delta:** the obsolete top-level `<trackster_conf>` (Trackster viz config) is
removed in 26.0; the diff also shows `<action>` and `name`/`output_name` attributes
removed and `min`/`max` added. **Stuck:** 5. **Auto rationale (trackster):** the
element is obsolete with no replacement, so removal is the only path and is
behaviour-neutral (Trackster is gone). **Resolved:** the 2026-06-01 combined sweep
strands no tool on the `<action>` / `name` / `output_name` removals — GTR011's
`<trackster_conf>`-only scope advances all 5 stuck tools to latest, so no extra
case to scope here.

### 21.05 / 21.09 residuals — tool bugs, not version deltas (no codemod)
1 tool each strands here on constructs that were removed with no equivalent
(`has_size/@delta_frac`; a semantically-invalid collection `type`). These are bad
tools, not a one-step migration; left stuck and reported (`needs-thought`).
