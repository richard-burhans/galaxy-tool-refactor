# Decisions and Assumptions

A maintainer-facing record of every non-obvious assumption this project
relies on and every design decision driven by data, by an upstream
constraint, or by an explicit user preference. Live document — extend
when new evidence arrives or an assumption changes.

The narrative architecture lives elsewhere: `CLAUDE.md` (current state),
`README.md` (public API), `docs/per-version-models-plan.md` (the
per-version model refactor), `docs/codemod-architecture.md` (tier-2
design). This file is the **why** for the choices those docs reflect.

Each entry should answer: *what we assume / chose · what the alternative
was · what evidence or constraint settled it*.

---

## 1. Galaxy ecosystem (verified during planning)

These are external facts about the Galaxy project that the library
treats as given. Any change here is a real-world ecosystem change, not a
refactor.

| # | Assumption | Verified |
|---|---|---|
| 1.1 | The Galaxy tool XSD lives at `lib/galaxy/tool_util/xsd/galaxy.xsd`; releases before ~`20.09` shipped it at `lib/galaxy/tools/xsd/galaxy.xsd`. The old path is gone by `release_21.05`. | `scripts/fetch_schemas.py` tries the new path then the old; see `docs/per-version-models-plan.md` and `schema/PROVENANCE.md`. |
| 1.2 | The XSD is self-contained (no `xs:import` / `xs:include`), declares **no** `targetNamespace`, root element `tool`, strict content models (`xs:all` / `xs:choice` of named elements, no wildcards). | Inspected at planning time; the namespace-free property is exposed to consumers via the no-namespace lxml tree. |
| 1.3 | The XSD is **post-macro-expansion**: it does not define `<expand>`; it defines `<macros>` / `<import>` / `<token>` / `<xml>` / `<macro>` (the definition side only). Galaxy validates tools against the XSD **only after expanding macros**. | Confirmed against `tool_util/linters/xsd.py` in galaxyproject/galaxy. Drives the `macro_handling="expand"` default for `validate_tool`. |
| 1.4 | Galaxy ships `release_*` branches (`release_13.01` … `release_26.1` as of 2026-05-27 — 28 of those branches ship the XSD); the suffix matches the `profile` attribute value. Not every branch ships the XSD. | `git/matching-refs/heads/release_` API call inside `scripts/fetch_schemas.py`. |
| 1.5 | A missing `profile` attribute defaults to `"16.01"` inside Galaxy (`parse_profile`: `self.root.get("profile", "16.01")`). **We match Galaxy** (revised 2026-06-01): `resolve_profile(None)` resolves that `16.01` default to the nearest vendored XSD — `16.10`, our oldest — so a no-profile tool validates against `16.10`, not the latest. (Earlier we diverged to "latest"; reversed for behaviour fidelity now that the upgrade-soundness work models Galaxy's actual runtime. 16.10 is a faithful proxy: vs the pre-16.10 standalone Galaxy-XSD it adds only 3 attributes and removes nothing, and Galaxy's `upgrade_codes.json` shows the only behaviour gate in the 16.01→16.10 window is 16.04.) | Galaxy `parse_profile` (`tool_util/parser/xml.py`); deprecated Galaxy-XSD repo diff; Galaxy `tool_util/upgrade/upgrade_codes.json`. |
| 1.6 | A tool's set of valid profiles is **not guaranteed to be contiguous** across vendored XSDs. | Corpus sweep observation — see §10. `newest_valid_profile` does a linear newest→oldest scan rather than a binary search, on the strength of this. |
| 1.7 | `galaxy.util.xml_macros.load_with_references(path) -> (ElementTree, imported_paths)` is the canonical macro expander; it handles `<import>`, nested `<token>`, `<expand>` / `<macro>` / `<xml>`, and parameterised `<yield>` macros. Path-based, not in-memory. | Mirrored 1:1 in `macros.py`'s `expand_from_path` / `expand_from_tree`. |
| 1.8 | `galaxy.util` is Galaxy's **internal** API — not a stability-guaranteed surface. The `galaxy-util` PyPI package is CalVer (currently `26.0`). | Confirmed against the project's own docs / release cadence. Drives the range pin (§2.4) and the macros.py isolation rule. |
| 1.9 | The Galaxy ToolShed exposes content only over the **Mercurial wire protocol** — no tarball or raw-file endpoint on the public API. The API itself is HTTP/JSON, but file fetches require `hg clone`. | `scripts/fetch_toolshed.py` necessarily uses `hg`. |
| 1.10 | A ToolShed repository's "version" is its tip changeset; the API does **not** list it on the repository envelope. It must be captured client-side via `hg id -i` after cloning. | Necessitated the manifest in `.local/corpus/galaxy-toolshed/manifest.json`. |

---

## 2. Python ecosystem dependencies

For each runtime dependency: pin, why, and what would break if a
maintainer "tightened it up" naively.

### 2.1 `xsdata[lxml] >= 26.2` — typed-model codegen + runtime parser

- Build-time and runtime dependency.
- 26.2 is the floor because the project drives codegen via the **API**
  (`ResourceTransformer(config=GeneratorConfig()).process([uri])`) — the
  signature settled at 26.2 (no `print` argument; positional list of
  `file://` URIs).
- See §5 for the codegen workarounds.

### 2.2 `lxml >= 5` — declared explicitly

- `galaxy-util` needs lxml for its XML code path but **does not
  declare** it. Without our explicit declaration, `pip install
  galaxy-tool-xml` could break on a fresh env where neither dep pulled
  lxml in transitively.

### 2.3 `click >= 8` — CLI

- Standard pin. No workarounds.

### 2.4 `galaxy-util >= 24, < 27` — macro expansion, range-pinned

- Range, not floor, because `galaxy.util` is Galaxy's internal API
  (Assumption 1.8). A wider open range would let a new Galaxy release
  silently change the macro semantics underneath us.
- All `galaxy.util` use is confined to `src/galaxy_tool_xml/macros.py`,
  so the blast radius of a future incompatibility is one module.
- Widen the upper bound only after `test_macros.py` runs green against
  the candidate version.

### 2.5 `packaging >= 23` — declared explicitly

- `packaging` is only a *transitive* dep of `galaxy-util`. Our use of
  `packaging.version.Version` in `profiles.py` is a direct dependency
  and must be declared as such, so a `galaxy-util` minor release that
  drops the transitive doesn't break us.

### 2.6 Dev: `xsdata[cli]`, `pytest`, `ruff`, `mypy`, `mercurial`

- `xsdata[cli]` brings the codegen toolchain (`ResourceTransformer` and
  its deps, e.g. `toposort`) — required at build time too (see
  `[build-system].requires`).
- `mercurial` is invoked only by `scripts/fetch_toolshed.py`; the
  pip-installed package brings its own `hg` binary, so the script does
  **not** rely on a system Mercurial install.

---

## 3. Representation: lxml tree is the source of truth

| Decision | Alternative | Why |
|---|---|---|
| **Mutable lxml tree** = source of truth; xsdata model = derived read-only view via `ToolDocument.model()`. | An xsdata-only representation, mutated through typed setters. | xsdata dataclasses cannot hold XML comments or preserve attribute order, so they cannot be the faithful representation. The downstream formatter (tier 3) needs that fidelity. |
| **No serializer in the library.** Callers serialise the tree themselves. | Provide a default `ToolDocument.write()`. | Tier 3 (`galaxy-tool-fmt`) is the only thing that writes Galaxy XML to disk in the planned three-tier architecture; baking a formatter into tier 1 would prejudge that. |
| **Parsing uses `strip_cdata=False` and reads `bytes`, never `str`.** | Decode to `str` first, or let CDATA collapse to text. | CDATA inside `<command>` / `<help>` carries shell scripting; collapsing it would silently change tool behaviour. Reading bytes lets lxml honour the XML encoding declaration. |
| **Library modules never call `logging.basicConfig`.** Each uses `logging.getLogger(__name__)`; the CLI installs the handler. | Configure at import time. | Library import must have no side effects (dignified-python). |

---

## 4. Profile-aware validation and binding

| Decision | Why |
|---|---|
| **Per-release vendored XSD** (~28 files, committed under `src/galaxy_tool_xml/schema/`). | The XSD evolves across releases; validating an old tool against the newest schema is misleading. |
| **`validate_tool` resolves the XSD from the tool's `profile`** with `on_missing="nearest"` as default. `exact` and `latest` are the other modes. | Real-world tools declare any profile in the release range; "nearest" mirrors what Galaxy itself accepts. |
| **`macro_handling` defaults to `"expand"`** (modes: `off` / `skip` / `strip` / `expand`). | Galaxy validates the post-expansion tool (Assumption 1.3); the default matches what Galaxy actually does. |
| **`expand` writes a throwaway temp copy** — the `ToolDocument.tree` is **never** mutated by validation. | The formatter contract requires the tree to be untouched after parse; loss of comments / whitespace in the expanded tree doesn't matter because the tree is discarded after the validation call. |
| **`newest_valid_profile` is a linear newest→oldest scan.** | Validity is not contiguous (Assumption 1.6); a valid/invalid probe at a single profile cannot distinguish "too old" from "too new", so binary search would be wrong. O(1) common case (modern tool validates at latest); worst case is one validation per vendored profile (28 at time of writing), and `compiled_schema` is `@cache`d. |
| **No-profile tools validate against `16.10`** (the nearest vendored XSD to Galaxy's `16.01` default). | Matches Galaxy's runtime default (revised 2026-06-01; see Assumption 1.5). |
| **Binding (`ToolDocument.model()`) is profile-aware too.** A tool's tree is bound against the model for its resolved profile, overridable via `model(version=...)`. | The downstream codemod tool needs faithful typed views of *each* release (see `docs/per-version-models-plan.md`). |
| **xsdata `ParserConfig` is lenient** (`fail_on_unknown_properties=False`, `fail_on_unknown_attributes=False`); schema-required fields the tree omits default to `None`. | Lets an un-expanded tool bind without raising; macro tokens absent from the post-expansion schema don't crash binding. |

---

## 5. Implementation workarounds (forced by upstream bugs)

These are **not** preferences — each is a specific upstream defect with
a recorded mitigation. Each should be revisited when the upstream
project releases a fix.

### 5.1 xsdata 26.2 circular-reference detector — `KeyError` on Galaxy 24.2+

- **Symptom:** xsdata's nested-class circular-reference detector raises
  `KeyError` on the Galaxy 24.2+ schema when inner classes are nested.
- **Mitigation:** `_codegen.py` sets
  `GeneratorConfig.output.unnest_classes = True`. Each XSD version is
  generated in its own subprocess because xsdata caches the resolved
  output path process-wide.
- **Where:** `src/galaxy_tool_xml/_codegen.py`; the flag is unconditional
  (harmless on older XSDs).
- **Side effect:** The generated class taxonomy is flat top-level
  (`Param`, `Conditional`, `ChangeFormatWhen`, etc.) — see `docs/codemod-architecture.md` §"Node taxonomy".

### 5.2 libxml2 — non-deterministic content model on Galaxy 19.05–23.0

- **Symptom:** Galaxy releases 19.05 through 23.0 shipped an XSD whose
  `Output` type has a non-deterministic content model; libxml2 refuses
  to compile it.
- **Mitigation:** `profiles.compiled_schema` retries after applying
  Galaxy's own release-23.1 fix (drop the redundant `Output` group) in
  memory. The vendored XSD files on disk remain verbatim.
- **Where:** `src/galaxy_tool_xml/profiles.py`.

---

## 6. Corpus stats system

The maintainer-facing corpus sweep
(`scripts/corpus_check.py`) and its supporting docs make several
non-obvious choices, several of them recently revisited.

| Decision | Why |
|---|---|
| **Two sources: `github` and `toolshed`; a `combined` sweep deduplicates by sha256 of file bytes.** | github captures the curated repositories; toolshed captures the long tail. Identical bytes is a stronger dedup signal than path or `@id` matching across repos. |
| **A "tool" is a file whose XML root element is literally `<tool>`.** Other XML files (tool_conf, repository_dependencies, etc.) are filtered out of stats and out of the fine-grained data file. | The library's domain is `<tool>` files; counting anything else would distort every distribution. |
| **`combined` mode dedup affects stats counters and invariant checks only; the fine-grained data file emits *all occurrences*.** | The Sources table in the markdown counts how many duplicates were *dropped from the aggregate stats*; the fine-grained data answers "which repo/path actually has this tool", and that's a per-occurrence question. |
| **Toolshed `version` = tip changeset captured via `hg id -i` before `.hg/` is removed.** Recorded in a manifest `.local/corpus/galaxy-toolshed/manifest.json`; missing entries default to `"unknown"`. | The ToolShed API doesn't expose tip changesets (Assumption 1.10); `.hg/` is removed to save ~80% disk. The manifest is the single source of truth and is gitignored (the corpus itself is). |
| **`tool_id` column = post-macro-expansion `@id`**, falling back to the raw `@id` (often a macro-token string) on expansion failure. | Driven by the 2000-tool survey (§10.1) — `@id` is present on 100% of tools and is the tool's logical identity, distinct from its file path. The expansion is free because `_expanded_attrs` already expands once and reads both `profile` and `id` from the result. |
| **Fine-grained schema = (`repo`, `version`, `path`, `tool_id`, `sha256`)** for per-source files; **plus** (`profile_raw`, `profile_expanded`, `newest_valid`) and one `valid_<profile>` 0/1 flag per vendored profile (28 columns at time of writing) for the combined file. | User choice: keep per-source files minimal and put the cross-source profile analysis in the combined view. The per-profile validity flags expose the full validity vector so downstream consumers can reason about non-contiguity (§10.3) without re-running validation. |
| **JSON + TSV, both formats every run.** JSON preserves schema column order via `dict` insertion order; TSV sanitises `\t` / `\n` / `\r` → space defensively. | Pandas / duckdb consume JSON; jq / awk / spreadsheets consume TSV. Both are tiny to write and worth shipping together. |
| **Fine-grained data and markdown stats share one gate** (skipped on `--no-stats`, `--limit`, `--repo`). | Partial sweeps must never produce a truncated artifact. |
| **Combined-mode duplicate rows reuse the first-seen `ToolStats` from a sha256→stats cache.** | Re-running `_exercise` on every duplicate would multiply the sweep time by ~2× without adding information (same bytes → same validity vector). |
| **Tooling: `hg` and `git` binaries via subprocess; `urllib` for the GitHub REST API.** | Each script makes 2–3 calls per repo and the network dominates everything. PyGithub / GitPython / python-hglib would be heavyweight imports with no measurable benefit; the Mercurial Python API is explicitly *not* a stable surface. |
| **Per-tool failure reasons categorized and surfaced in the combined stats markdown only.** Two new sections — *Macro-expansion failure reasons* (Group A) and *Tools with no valid vendored profile — reason breakdown* (Group A+B) — appear in `docs/combined_corpus_stats.md`. Tool-level reason fields (`expansion_failure_reason`, `no_valid_reason`) live on `ToolStats` but are not exposed in the fine-grained data files. | The aggregate breakdown answers "are these our bugs?" at a glance (the answer is *no* — see §10.4). The combined view is the right place because the breakdown is most informative when deduplicated across sources. Categorization runs only when needed (no-valid tools get one extra `validate_tool` call to pull the first error). |
| **External links in `docs/corpus_data/failures/*.md` are plain markdown — no HTML anchors with `target="_blank"`.** | github.com's markdown sanitizer strips the `target` attribute from committed `.md` files, so the HTML form renders the same as plain markdown on the public web view (verified 2026-05-27 — change pushed, behavior confirmed, then reverted). The HTML form would still pay off under any non-GitHub renderer (MkDocs / Pages / IDE preview), but the project does not currently ship one, so the noise is unjustified. Revisit if a static-site build is added. |
| **Combined-only `presence` column on every row** (`github_only` / `toolshed_only` / `both`), keyed by `tool_id`. Stamped post-sweep by `_stamp_presence`. Per-source artifacts do not carry the column (it would be constant). | Surfaces "is this tool also maintained on github?" as first-class data. Match key `tool_id` is what readers care about ("is the same logical tool present?") and is empirically near-equivalent to `(tool_id, basename)` at the corpus level (3,569 vs 3,568 cross-source matches in the 2026-05-29 sweep — see §10.11). The sha256-based "Sources" Unique/Duplicates table already captures byte-identical presence; `presence` adds the logical-identity view. |
| **No `[view]` link swap when only the `tool_id` matches.** A toolshed row with a github sibling keeps its `[view]` link pointed at the toolshed bytes; the sibling is surfaced as an *(also in github: …)* annotation on the `Repository` cell instead. | The recorded failure is a property of the toolshed bytes. The github sibling has *different* bytes and may not have the same failure (or may not fail at all); linking there would mislead the reader about what the row is reporting. Annotation gives the cross-reference without lying about provenance. |
| **Corpus discovery skips deprecated directories.** `scripts/_shared.py:iter_tool_xmls` — the single discovery walker shared by `corpus_check` and `measure` — drops `.hg/` metadata and any file under a directory component containing `"deprecat"` (case-insensitive, via `is_deprecated_path`). | Tools under `deprecated/` are obsolete and would distort every distribution; one choke point makes the exclusion durable across re-fetches. Added 2026-05-29; the refreshed post-exclusion measurements are in §10. |

---

## 7. Tooling and packaging

| Decision | Why |
|---|---|
| `uv` as project manager, `hatchling` as build backend with a custom build hook. | The build hook generates one per-version model package per vendored XSD (28 at time of writing) at wheel and editable-install time (`docs/per-version-models-plan.md`); `uv_build` had no hook surface, so the backend moved. |
| `ruff` lint + format; `mypy --strict`. Both exclude the generated `models/v*/` and `models/any_tool.py`. | Hand-written code is held to the standard; generated code isn't ours to fix. |
| No CI (`v0.1`, deliberate). | A single maintainer + a fast local `pytest`/`ruff`/`mypy` triad is sufficient at this scale; CI is a later add. |
| `.gitignore` excludes `src/galaxy_tool_xml/models/v*/`, `…/any_tool.py`, and the whole `.local/` scratch tree (the corpus lives at `.local/corpus/`). Committed-but-generated: nothing in models; the `schema/` XSDs are committed. | Generated code regenerates deterministically from the committed XSDs + pinned xsdata; the corpus is reproducible from `corpus_sources.json` + the toolshed manifest. |

---

## 8. Coding standards

**`dignified-python` governs** (vendored at `.claude/skills/dignified-python/`); `optimized-python` is installed
as a reference. On conflict, dignified-python wins. Key applications in
this repo:

- Prefer LBYL for routine branching. Exceptions at the click error boundary
  (chained `from e`) and where third-party APIs offer no LBYL form.
- `pathlib.Path` with explicit `encoding="utf-8"` on every `read_text` /
  `write_text`.
- No import-time I/O; `@functools.cache` for module-state accessors
  (`_corpus_sources`, `_toolshed_manifest`, `compiled_schema`, etc.).
- Absolute imports, no re-exports, no `__all__`. Exception (sanctioned):
  the xsdata-generated `models/v*/__init__.py` re-exports its module so
  `from galaxy_tool_xml.models.v26_0 import Tool` works.
- Keyword-only arguments after the first.
- Hand-written code is checked by ruff + mypy; the generated `models/`
  is excluded from both.

---

## 9. Three-tier vision (context)

`galaxy-tool-xml` is tier 1 (the **parsing & validation** layer) of a
three-package architecture:

| Tier | Layer | Package | Status | Job |
|---|---|---|---|---|
| 1 | parsing & validation | `galaxy-tool-xml` | this repo | parse · validate · typed view; no serializer |
| 2 | structure | `galaxy-tool-xml-codemod` | M1–M3.5 shipped (2026-05-28) | structural refactors via `CodemodCommand` + `CANONICAL_CODEMODS` |
| 3 | formatting | `galaxy-tool-xml-fmt` | shipped (2026-05-28) | cosmetic `black`-like formatter; the only tier that writes XML |

This split is *why* tier 1 has no serializer (Decision 3) and why it
ships full per-version typed models (Decision 4): the structural layer
in tier 2 needs a faithful view of *each* release to plan structural
edits, and tier 3 owns trivia preservation downstream.

**Tier 3 → tier 2 is an optional dependency.** fmt's library is
cosmetic-only and does not import codemod; the codemod package is
declared as fmt's `[canonical]` extra, and fmt's CLI orchestrates
both layers when the extra is installed. Minimal installs (xml + fmt)
still get a working cosmetic formatter. See
`galaxy-tool-xml-fmt/docs/decisions.md` §D10 and
`galaxy-tool-xml-codemod/docs/decisions.md` §9 (the split) + §10 (the
`MANDATORY_CODEMODS` → `CANONICAL_CODEMODS` rename) for the
optional-extra rationale.

> **Update 2026-05-29:** the `[canonical]` extra was later removed and
> all cross-tier orchestration moved to a new tier-4 app
> (`galaxy-tool-refactor-cli`); fmt's CLI is now cosmetic-only too. This
> added tier 0.5 `galaxy-tool-refactor-rules` and tier 4 (and, on
> 2026-05-30, tier 3.5 `galaxy-tool-xml-check`, and later tier 3.6
> `galaxy-tool-refactor-registry` — the rule-registry facade the app CLI
> now sits on — bringing the workspace to seven packages). The independence
> principle above still holds — fmt never depends on codemod. See
> `galaxy-tool-xml-fmt/docs/decisions.md` §D12,
> `galaxy-tool-xml-codemod/docs/decisions.md` §16,
> `galaxy-tool-refactor-cli/docs/decisions.md` §D1/§D4, and
> `galaxy-tool-refactor-registry/docs/decisions.md` D1–D4.

Full design: `docs/codemod-architecture.md` (the original architecture
note; per-decision rationale on the implementation lives in each
tier's own `docs/decisions.md`).

---

## 10. Testing-derived measurements

Each measurement records what was sampled, on what date, and what
decision it informed. Every entry cites the exact `scripts/measure.py`
subcommand that reproduces its numbers — re-run the cited command
after a corpus refresh and update the entry rather than parroting
older figures. Add new measurements here when a new question is asked.

Run all measurements at once: `uv run python -m scripts.measure --all
--jobs 4`. List them: `uv run python -m scripts.measure --list`.

### 10.1 Tool `@id` vs. path (2026-05-29)

Justifies emitting **both** `tool_id` and `path` columns in the
fine-grained corpus data (§6).

| Property | Result |
|---|---|
| Unique tools surveyed | 9,358 |
| `@id` present on `<tool>` | 100.0% (9,358 / 9,358) |
| `@id` contains a macro token (e.g. `@PROFILE@`) on the **expanded** tree | 0.0% — expansion resolves every macro `@id` before the column is recorded |
| `@id` matches the file stem | 53.0% |
| `@id` matches the parent directory name | 11.6% — much lower than the pre-toolshed 37.5% sample, since toolshed tools usually nest under `<owner>/<repo_name>/<tool>.xml` where the parent is the suite, not the tool |
| `<tool>` files with no `@id` | 0 |

**Conclusion:** path and `@id` agree on ~53% of tools by stem and only
~12% by parent directory, so they carry distinct information. Both
columns stay. The 2000-tool github-only sample reported in earlier
versions of this section overstated parent-directory agreement because
it predated the toolshed half of the corpus.

**Reproduced by:** `uv run python -m scripts.measure tool-id-vs-path`

### 10.2 Corpus size and source mix (2026-05-29 sweep)

Snapshot of the corpus as observed by a full `corpus_check.py
--source combined` run.

| Measure | github | toolshed | combined |
|---|---:|---:|---:|
| Distinct repos that contributed `<tool>` files | 20 | 6,107 | 6,127 |
| Repos swept (from `corpus_sources.json` / toolshed manifest) | 21 | 7,653 | 7,674 |
| Combined rows in `combined_corpus_data.json` | 4,095 | 8,677 | 12,772 |
| Unique tools after sha256 dedup (credited to first-seen source) | 4,080 | 5,278 | 9,358 |
| Duplicate rows dropped from unique-tool counts | — | — | 3,414 |

Empty repos (no `<tool>` files) account for the gap between "repos
swept" and "distinct repos that contributed". The "aggregate
duplicates dropped" figure quoted in the combined stats markdown
counts every duplicate XML file, including non-tool XMLs
(`tool_conf.xml`, `repository_dependencies.xml`, etc.) that the data
file never sees.

**Conclusion:** github is iterated first so a tool present in both
sources is credited to github (`(github=4,080, toolshed=5,278) =
9,358`). The 7,975 "duplicates dropped" in the Sources table of
`combined_corpus_stats.md` includes 3,414 duplicate tool rows plus
4,561 duplicate non-tool XMLs.

**Reproduced by:** `uv run python -m scripts.measure corpus-size-source-mix`

### 10.3 Validity-vector contiguity (2026-05-29 combined sweep)

A non-trivial fraction of tools have a **non-contiguous** validity
vector — they validate at some profile, fail at an intermediate one,
and validate again later. Originally observed in
`docs/per-version-models-plan.md` and confirmed by every sweep since.

| Combined-sweep snapshot | Non-contiguous | Total unique | % |
|---|---:|---:|---:|
| 2026-05-29 | 203 | 9,358 | 2.2% |

**Conclusion:** Assumption 1.6 holds. The `newest_valid_profile`
implementation stays a linear newest-first scan (§4) — a binary search
would be unsound on a non-monotonic vector. The figure is reported via
`combined_corpus_stats.md`'s *Validity-vector contiguity* table on
every full sweep.

**Reproduced by:** `uv run python -m scripts.measure validity-distribution`

### 10.4 No-valid-profile taxonomy (2026-05-29 combined sweep)

Of the 9,358 unique tools, **750** (8.0%) do not validate against any
of the 28 vendored XSDs. Every category traces to a genuine
schema-noncompliant property of the tool, not a library bug.

**Group A — macro expansion failed** (12 tools / 1.6% of the no-valid
set): the post-expansion tree never reaches the XSD.

| Reason | Count |
|---|---:|
| undefined macro reference in `<expand>` | 8 |
| imported `macros.xml` file not on disk | 1 |
| malformed XML in tool file (e.g. `--` inside a comment, unmatched tags) | 3 |

**Group B — expansion ok, XSD rejects everywhere** (738 tools / 98.4%):

| Reason | Count | % of no-valid |
|---|---:|---:|
| XSD does not declare attribute used by tool | 348 | 46.4% |
| XSD does not allow element under this parent | 217 | 28.9% |
| XSD does not allow element at all | 37 | 4.9% |
| attribute value outside XSD's enumeration | 35 | 4.7% |
| other XML syntax error (recovered tree, parser logged errors) | 35 | 4.7% |
| invalid boolean (`"True"`/`"False"` vs `"true"`/`"false"`) | 33 | 4.4% |
| other XSD type / pattern mismatch | 19 | 2.5% |
| XSD-required attribute missing | 10 | 1.3% |
| invalid character encoding (non-UTF-8 bytes) | 4 | 0.5% |

**Conclusion:** ~75% of all no-valid tools (B1 + B2 = 565) use
attributes or elements the public Galaxy XSD does not formally cover —
a long-standing gap between Galaxy's runtime parser (lenient) and its
public schema (strict). The rest split between minor type mismatches
(booleans, enums, regex facets) and outright malformed input. Each
category is surfaced in `combined_corpus_stats.md` so future drift is
visible.

**Reproduced by:** `uv run python -m scripts.measure no-valid-profile-taxonomy`

### 10.5 Newest-valid-at-latest distribution (2026-05-29 combined sweep)

Quantifies the "common case" referenced by `binding.py`'s
`newest_valid_profile` and the `per-version-models-plan.md` ceiling
discussion.

| Result | Count | % |
|---|---:|---:|
| Validates at the latest vendored profile (currently 26.1) | 8,440 | 90.2% |
| Validates at some older vendored profile | 168 | 1.8% |
| Validates at no vendored profile | 750 | 8.0% |

**Conclusion:** 90.2% of unique tools validate at the latest profile,
so the newest-first scan in `newest_valid_profile` is O(1) on nine out
of ten calls. The 1.8% that validate only at an older profile is the
population the per-release models exist to serve.

**Reproduced by:** `uv run python -m scripts.measure validity-distribution`

### 10.6 Macro usage (2026-05-29 combined sweep)

Justifies the prominence of macro handling in the API
(`validate_tool`'s `macro_handling=` parameter, `expand_from_path`, the
`macros.py` adapter) and the corresponding test fixtures.

| | Tools | % |
|---|---:|---:|
| Uses macros (`<macros>` / `<expand>` / `<import>` / `<token>`) | 5,125 | 54.8% |
| Macro-free | 4,233 | 45.2% |

**Conclusion:** the macro path is the majority case — there is no
"common case" without macro handling. The library's `macro_handling`
default of `"expand"` is the right one.

**Reproduced by:** `uv run python -m scripts.measure macro-usage`

### 10.7 Profile-as-macro-placeholder (2026-05-29 combined sweep)

How often a tool's literal `profile` attribute is a macro token (e.g.
`@PROFILE@`, `@TOOL_PROFILE@`) rather than a literal version string.
Drives the design choice in `corpus_check.py` to record **both**
`profile_raw` and `profile_expanded`; only the expanded value is
meaningful for distribution stats.

| | Count | % |
|---|---:|---:|
| `profile` attribute is a macro placeholder | 1,486 | 15.9% |
| `profile` attribute is a literal version or absent | 7,872 | 84.1% |

Distinct placeholder values observed: `@GALAXY_VERSION@`, `@PROFILE@`,
`@PROFILE_VERSION@`, `@TOOL_PROFILE@`, `@profile@`. `@PROFILE@`
dominates.

**Conclusion:** any stat keyed on `profile` without prior macro
expansion would mis-classify ~1 in 6 tools. The corpus check expands
before counting; the public abstract reports the expanded figure.

**Reproduced by:** `uv run python -m scripts.measure macro-placeholder-profile`

### 10.8 Expansion-failed `tool_id` fallback (2026-05-29 combined sweep)

Earlier docstrings in `corpus_check.py` described the
expansion-failure fallback as "typically a macro-token string like
`bcftools_@EXECUTABLE@`". The 12 tools whose expansion fails today
were checked against that claim.

| | Count | % |
|---|---:|---:|
| Expansion-failed tools whose `tool_id` contains `@` | 0 | 0.0% |
| Expansion-failed tools with a literal `tool_id` | 12 | 100.0% |

**Conclusion:** the macro-token fallback path exists in code but is
not currently exercised by any tool in the corpus. The fallback is
still correct (it returns the raw `@id` whatever it looks like), but
the docstring example overstated how often that raw `@id` is a macro
token. The example has been softened to "the raw `@id` literal, which
may or may not contain a macro token".

**Reproduced by:** `uv run python -m scripts.measure expansion-failed-ids`

### 10.9 Lenient-text-style field children (2026-05-29 combined sweep)

Justifies `_patch_xsdata_primitive_node_leniency` in
`src/galaxy_tool_xml/document.py`. The XSD declares fields like
`<help>`, `<command>`, `<description>` as primitive `xs:string`
content; without the patch, xsdata's `PrimitiveNode` raises on any
element child found inside. The question: how often is this actually
exercised?

| Field | Occurrences | With element children | Rate |
|---|---:|---:|---:|
| `<help>` | 13,286 | 7 | 0.053% |
| `<citation>` | 5,349 | 1 | 0.019% |
| **TOTAL** (across all xs:string-content fields) | 63,022 | **8** | **0.013%** |

Affected children include `<i>` (italics inside `<help>`), `<expand>`
(unexpanded macro inside `<help>`), and one nested `<citation>`. The
8 distinct affected tools are spread across toolshed only.

**Conclusion:** rare in absolute terms (8 of ~13,000 parseable
tools), but the failure mode is non-recoverable on the affected tool —
without the patch, `.model()` would raise `XmlContextError`. The patch
turns the crash into a silent skip (the lxml tree, which is the
source of truth, keeps the markup verbatim). The cost is one
class-method monkey-patch run at most once via `@cache`.

**Reproduced by:** `uv run python -m scripts.measure lenient-text-fields`

### 10.10 Corrections cutoff (2026-05-29 combined sweep)

Justifies `_CUTOFF = 0.8` in `src/galaxy_tool_xml/corrections.py`.
Sweeps the cutoff value over the 348 tools whose no-valid-profile
reason is "XSD does not declare attribute used by tool" — the
population most likely to harbour real attribute typos — and counts
how many produce at least one attribute correction at each cutoff.

| Cutoff | Tools with ≥1 attribute suggestion | Total attribute suggestions emitted |
|---:|---:|---:|
| 0.60 | 87 (25.0%) | 179 |
| 0.70 | 72 (20.7%) | 144 |
| 0.75 | 49 (14.1%) | 94 |
| 0.80 (current default) | 49 (14.1%) | 93 |
| 0.85 | 40 (11.5%) | 66 |
| 0.90 | 11 (3.2%) | 20 |

**Conclusion:** `0.80` sits on the conservative end of a small
plateau (`0.75` → `0.80` adds zero new tools, only loosens
suggestions). Dropping to `0.70` would catch 23 more tools but at the
cost of looser matches whose precision has not been hand-audited.
The current `0.80` is defensible; a deliberate audit would be needed
to support a change.

**Reproduced by:** `uv run python -m scripts.measure corrections-cutoff`

### 10.11 Cross-source presence (2026-05-29 combined sweep)

Justifies the `presence` column on every combined-data row and the
*"Failures by source presence"* section in
`docs/combined_corpus_stats.md`. Match key is `tool_id` (logical
identity) — see §6 row on the column.

**Overall presence**, keyed on `tool_id`, across 9,358 unique tools:

| Bucket | Tools | % |
|---|---:|---:|
| `github_only`    | 227   | 2.4%  |
| `toolshed_only`  | 4,465 | 47.7% |
| `both`           | 4,666 | 49.9% |

**Failing-tool presence**, across the 750 distinct failures:

| Bucket | Tools | % |
|---|---:|---:|
| `github_only`    | 38  | 5.1%  |
| `toolshed_only`  | 560 | 74.7% |
| `both`           | 152 | 20.3% |

**Failures × source cross-tab** — the same numbers the new stats
section reports, deduped by sha256 to reconcile with the
per-category index pages under `docs/corpus_data/failures/`:

| Source | Failures | With sibling in other source |
|---|---:|---:|
| github   | 123 | 85 |
| toolshed | 627 | 67 |

**Match-key choice (sanity check):** the corpus has 3,569 cross-source
matches under `tool_id` and essentially the same (3,568) under
`(tool_id, basename(path))`. Tightening the key gains nothing at the
corpus level and gives only 7 fewer matches on the failure subset
(124 vs 131); the simpler `tool_id` key wins. Byte-identical (`sha256`)
matching is much stricter — 3,118 across the whole corpus, 40 on the
failure subset — and is captured separately by the Sources Unique /
Duplicates table in `docs/combined_corpus_stats.md`. These match-key
counts are emitted by the *Match-key sanity check* block of the
`cross-source-presence` measurement below.

**Conclusion:** about half the unique-tool population lives in both
corpora by logical identity. Among the failing population, that share
drops to 20% — most failing toolshed tools (75%) have no github
sibling at all and are unlikely to be silently superseded by an
updated copy elsewhere. The 152 failures present in both sources are
exactly the population a future "is this maintained on
github?" triage workflow would surface first.

**Reproduced by:** `uv run python -m scripts.measure cross-source-presence`

### 10.12 Upgrade headroom (2026-05-29 combined sweep)

Sizes what the tier-4 `galaxy-tool-refactor upgrade` command does across the
9,358 unique tools (latest profile `26.1`):

- **3,632 (38.8%)** *understated* — declare a literal profile older than the one
  they validate at; `UpdateProfile` bumps the declaration up. This is the
  command's dominant effect.
- **4,975 (53.2%)** carry a *macro-placeholder* profile (`@PROFILE@`-style) that
  is left as-is.
- **750 (8.0%)** validate at no profile — repair (`FixTypos`) territory before
  any upgrade is meaningful.
- **1** overstated (declares newer than it validates; left as-is, bump-up-only).

Structural headroom: of the **8,608** tools that validate somewhere, **8,440
(98.0%)** already have their newest-valid profile at the latest; only **168
(2.0%)** sit below latest and are candidates for a structural `upgrade_vN`. So
the upgrade command is overwhelmingly a profile-declaration bump, with a small
structural-migration tail.

**Reproduced by:** `uv run python -m scripts.measure upgrade-headroom`

### 10.13 Element cardinality (2026-05-29 combined sweep)

Per-unique-tool occurrence of the structures codemods traverse: `<test>` in
**71.0%** (max 49 in one tool), `<requirement>` **39.7%**, `<conditional>`
**37.5%** (max **378** in one tool), `<collection>` **10.1%**,
`<output_collection>` **6.9%**. The deep `<conditional>` nesting (hundreds in a
single tool) is why the cursor walk is iterative rather than recursion-bounded.

**Reproduced by:** `uv run python -m scripts.measure element-cardinality`

### 10.14 Command interpreter mix (2026-05-29 combined sweep, heuristic)

Heuristic first-interpreter classification of each tool's `<command>` across
9,358 unique tools: **66.9%** wrap a binary directly (no recognised interpreter
token), **18.2%** python, **7.2%** Rscript, **5.7%** shell, **1.5%** perl; 40
tools carry no `<command>`. Most Galaxy tools shell out to a packaged binary
rather than embedding an interpreter. A first-token scan, not a parser — a tool
that merely mentions an interpreter in a comment is counted as that interpreter.

**Reproduced by:** `uv run python -m scripts.measure command-language`

---

## 11. `suggest_corrections` accepts a `profile` override

**Date:** 2026-05-28.

- **What we chose:** `suggest_corrections(target, *, profile=None)`. By
  default the tool's own declared profile drives the schema vocabulary
  (unchanged behaviour); an explicit `profile` selects a different
  release's vocabulary for the lockstep walk.
- **Alternative:** Keep the function profile-implicit and have a caller
  that wants a different vocabulary temporarily rewrite the tree's
  `profile` attribute before calling.
- **Why:** The Tier-2 `FixTypos` repair codemod probes each release
  newest-to-oldest, asking "which typos would *this* profile's vocabulary
  surface?" — it must drive the vocabulary without mutating the tool it is
  about to repair. A keyword override is a one-line, backward-compatible
  addition; the attribute-rewrite alternative is a mutation footgun.
  `profile=None` preserves the exact prior behaviour, so no existing
  caller changes.

---

## 12. Open items

- **`source` column in the combined corpus data file.** ✅ Added
  2026-05-29 — `combined_corpus_data.{json,tsv}` now carries an explicit
  `source` (`github` / `toolshed`) column, derived per-row via
  `_row_source`. Combined-only; per-source files omit it (it would be
  constant there).
- **CI** — ✅ added 2026-05-29: `.github/workflows/ci.yml` runs `uv sync`
  + ruff + mypy + the five package test suites on every PR/push (no
  corpus needed; the slow xsdata-codegen sweep stays `-m slow`).
- **Schema-error line numbers in `expand` / `strip` modes** point to
  the transformed tree, not the original source file. Only
  `macro_handling="off"` yields original-source line numbers. Inherent
  to validating a post-transformation tree.
- **Typo suggestions are now profile-bound** (via `corrections.py`'s
  profile-aware vocabulary, per `docs/per-version-models-plan.md` §7).
  A historical caveat in `PLAN.md` ("uses the latest schema's
  vocabulary") is no longer applicable.

## 13. `corpus_check rules` per-rule isolation sweep + deterministic stat ordering

**Date:** 2026-05-29.

- **What we chose:** a fourth `corpus_check` subcommand, `rules`, that runs
  **every** GTR rule *in isolation* (no other rules) across the corpus and
  writes `docs/corpus_rule_stats.md`. fmt rules (GTR001/003/004) are gated on
  validation and checked for **idempotence + no-crash only** — a rule like
  GTR003 run without GTR001 emits valid-but-non-canonical output, which is
  expected; we only assert it is stable and does not raise. Codemods
  (GTR002, GTR005–GTR012) reuse the existing `codemod` exercise (idempotence +
  post-codemod validity + eligibility), and `UpgradeToLatest` (GTR012)
  additionally surfaces its reach / sticking-point / per-step-advance discovery
  as upgrade QA. Failures retain to the owning tier's regression fixtures.
- **Why:** the `fmt` sweep runs all fmt rules together and the `codemod` sweep
  runs one codemod at a time; neither gave a single, persisted per-rule QA view
  across both tiers. Isolating each rule pinpoints which rule owns a regression
  and keeps the GTR registry honest. The upgrade characterization lives here as
  QA (the `UpgradeToLatest` row) rather than as a separate user-facing page,
  since `corpus_check codemod` already isolates it and `measure.py
  upgrade-headroom` (§10.12) sizes the addressable population.
- **Deterministic stat ordering:** `_profile_sort_key` previously gave
  version-equal but string-distinct labels (`20.5`/`20.05`, `24.0`/`24.00`,
  `24.1`/`24.01`) identical keys, so their rows reshuffled on every sweep
  (counts unchanged) and churned the committed artifact. The key is now total —
  a raw-string tiebreak after the numeric parts (nested so a numeric prefix like
  `24` vs `24.0` never compares an int against the string). Regeneration is now
  idempotent.
- **Reproduced by:** `uv run python -m scripts.corpus_check rules`;
  determinism pinned by `test_corpus_check.py`'s `_profile_sort_key` tests.

## 14. Macro-file resolution + token-definition lookup (`macros.py`)

**Date:** 2026-05-30. Phase 1 of the macro-aware refactoring effort (see
`galaxy-tool-xml-codemod/docs/macro-aware-normalization.md` and the workspace
plan). Reproduced-by: `uv run --package galaxy-tool-xml pytest
galaxy-tool-xml/tests/test_macros.py`.

- **What we chose.** Two public, read-only `macros.py` functions (the foundation
  the codemod tier's `PLAN.md` listed as "Macro file resolution — not yet
  shipped"):
  - `imported_macro_paths(target) -> list[Path]` — the macro files a tool
    imports, **transitively** (each file's own `<import>`s resolved against *its*
    directory, matching Galaxy), de-duplicated, in import order, existing-only.
  - `token_definitions(target) -> list[TokenDefinition]` — every `<token>`
    defined for a tool, inline (`source=None`) then per imported file
    (`source=<path>`). `TokenDefinition` carries `name` / `value` / `source` /
    `sourceline`. This is how a token-aware codemod will find where a
    `profile="@PROFILE@"` is actually defined (the corpus shows 1,384 of 1,486
    such tokens live in an imported file — `docs/macro_corpus_stats.md`).
- **`target` is `ToolDocument | Path`, not the full `Source`.** Resolution needs
  a location on disk, so raw `bytes`/streams are out of scope (an in-memory
  `ToolDocument` with no `source_path` returns `[]`). This is deliberately
  narrower than `validate_tool`'s `Source | ToolDocument`.
- **LBYL, and `macros.py` stays free of `binding`.** Imports are walked with
  plain lxml (`recover=True`) and resolved by `pathlib`; an `<import>` that is
  absolute, contains `..`, or is missing is skipped — no Galaxy exception
  surfaces, and no `binding` import is taken (avoiding a `binding`↔`macros`
  cycle; `macros.py` newly imports only the leaf `document.ToolDocument`).
- **Read-only for now.** A mutable `MacroDocument` for *editing* macro files is
  deferred to the next phase (running fmt/codemods on macro files); these two
  functions are the read foundation the bundle, the shared-import graph, and the
  token-aware profile upgrade all build on.

## 15. `MacroDocument` + `load_macros` (editing foundation)

**Date:** 2026-05-30. Phase 2 (first step) of the macro-aware effort — the
mutable macro-file document that §14 deferred. Reproduced-by: `uv run --package
galaxy-tool-xml pytest galaxy-tool-xml/tests/test_binding.py`.

- **What we chose.** `MacroDocument` (`document.py`) — the macro-file counterpart
  to `ToolDocument`: a mutable lxml tree (CDATA / comments / attribute order
  preserved) exposed via `tree` / `root` / `source_path`, **no serializer**
  (exposing the tree is the contract). `load_macros(source) -> MacroDocument`
  (`binding.py`) mirrors `load_tool` — same `_read_source` + `_parse_bytes`
  machinery, raising `ToolXmlSyntaxError` on malformed XML.
- **No `profile`, no `model`, no validation.** A macro library is a fragment the
  Galaxy XSD does not define as a standalone document, so `MacroDocument`
  deliberately omits `ToolDocument`'s `profile`/`model()` and there is no
  `validate_macros` — macro files are parsed and edited, and correctness is still
  checked by validating the *expanded tool* (`validate_tool`), unchanged.
- **Root tag not enforced.** `load_macros` parses and wraps whatever root it
  finds; a caller distinguishing a macro file from a tool inspects
  `root.tag` (a cheap `is_macros_root` byte pre-check for the CLI/bundle comes
  with the fmt/codemod-on-macros step).
- **Why a separate type, not reusing `ToolDocument`.** `ToolDocument.model()` /
  `.profile` are tool-specific and meaningless on a `<macros>` root; a dedicated
  type keeps the contract honest and lets fmt/codemod dispatch on document kind.

## 16. Command-text analysis utilities (`command_text` + `command_vars` + `cdata`)

**Date:** 2026-06-03 (`command_text`/`command_vars`); 2026-06-04 (`cdata`, with the
partition work). Reproduced-by: `uv run --package galaxy-tool-xml pytest
galaxy-tool-xml/tests/test_command_text.py galaxy-tool-xml/tests/test_command_vars.py
galaxy-tool-xml/tests/test_cdata.py`.

Three small, dependency-light modules analyse `<command>` / `<help>` body content:

- `command_text.unquoted_cheetah_vars(text)` — a read-only lexer yielding every
  fully-unquoted shell-line `$var` with its name, line offset, and absolute
  `start`/`end` character span (quote-state tracking across newlines, Cheetah
  directive skipping). It is *not* a parser — no Cheetah grammar, no shell AST. The
  conservative regex scan (`_scan_unquoted_cheetah_vars`) is then **filtered against the
  faithful CT3 span lexer** (§19; CT3 is a base dependency): a candidate survives only if
  its `$` is the start of a genuine `PLACEHOLDER` span, so a `$` inside a `#raw` block, a
  `#* … *#` block comment, or an escaped `\$` — invisible to the line-based regex — is
  dropped. The lexer only *narrows*; only on the ~0.4% CT3 bail is the raw regex result
  returned (2026-06-06: CT3 promoted from the `cheetah-cdm` extra to a base dep — §19).
- `command_vars` — resolves a `$var` against a tool's `<inputs>` and classifies it
  (`input_param_info` / `classify_var` / `provably_quotable`) into the
  quoting-safety buckets, exposing the provable subset `{safe, attr_safe,
  builtin_path}`. A `select` / `drill_down` is "safe" only when its option set is
  statically known and every `<option value>` is a single shell token
  (`_select_options_are_single_tokens`) — *not* by type alone: a multi-flag dropdown
  (`<option value="-b -h">`) word-splits, so quoting it would change behaviour. The
  unprovable residual (whitespace/glob value, a `<options from_*>` runtime source, or
  no static options) is demoted to `text` (advisory `GTR020.2`). Sized by
  `scripts.measure select-quoting-safety` (2026-06-06). A `boolean` is likewise *not*
  safe by type: it renders to its author-written `truevalue` / `falsevalue`, so it is
  "safe" only when both are non-empty single tokens (`_boolean_values_are_single_tokens`).
  The ubiquitous `falsevalue=""` flag idiom is demoted to `text` — quoting the empty
  false case emits a stray `''` argument (2026-06-11 soundness fix; codemod §44).
  `command_var_info` (2026-06-13) extends `input_param_info` with the tool's
  **output files**: each `<outputs>` direct-child `<data name=>` joins `kinds` as
  `safe`. An output `<data>` variable renders to the dataset file path Galaxy
  assigns — the same single-token, Galaxy-controlled value domain that already
  makes a `type="data"` *input* `safe`, and with no word-splitting idiom to break
  — so single-quoting it is behaviour-preserving, and the IUC rule's scope is
  verbatim "text parameters, input **and output files**". `<collection>` outputs
  are excluded (not a single file path) and an input wins on a name collision
  (`setdefault`). The GTR020.1 fixer and GTR020.2 advisory both moved to
  `command_var_info`, so the partition stays exact (outputs now fixed, not
  advised); text params remain the advisory residual (a free-form value may carry
  spaces, so quoting is not provably a no-op). Sized by `scripts.measure
  command-quoting-kinds`. `io_file_names` / `is_io_file_ref` (2026-06-13) then
  isolate the **file** subset of the rule — single `type="data"` inputs +
  `<outputs>` `<data>` — which is all GTR020.1 now quotes (codemod §52, from the
  PR #8090 review); selects / numbers / booleans / attrs / built-ins, though
  provably single-token, are out of the rule's scope and left unquoted.
- `cdata` — `cdata_wrappable` / `needs_cdata` / `is_cdata_wrapped`: predicates on an
  element deciding whether a pure-text body can be losslessly wrapped in one CDATA
  section (the GTR018/GTR019 substrate).

**Why tier 1.** Each is shared by a codemod fix sub-rule (tier 2) *and* its advisory
residual sub-rule (tier 3.5): `provably_quotable` by GTR020.1/GTR020.2,
`cdata_wrappable` by GTR018.1/GTR018.2 and GTR019.1/GTR019.2. Code shared below both
must sit in tier 1 (tier 0.5 is RuleMeta-only, no `etree`); the parsing foundation is
the natural home, and it keeps the codemod from depending upward on the check tier.
One shared predicate per practice is what makes the partition **sound** — the fix and
its advisory residual can't drift (registry `docs/decisions.md` D10). `scripts.measure`
imports the same `command_vars` classifier so the corpus sizing and the codemod never
diverge. These are *analysis* helpers (string/element in, data out) — the library
still emits no XML (the `cdata.is_cdata_wrapped` re-serialise is a read-only probe,
serializer-allowlisted).

## 17. Shell boundary oracle (`shell_oracle`) — bashlex behind the `[shell-oracle]` extra

**Date:** 2026-06-04.

`shell_oracle.py` is the permanent half of the deferred Cheetah/shell **M5** layer: a
read-only **boundary oracle** over a realized `<command>` line, parsed with **bashlex**
(bash's own grammar, ported to Python). It exposes `boundary_signature` (the argv word
partition + full fd→target redirection topology — the exact behaviour a single-quote
edit must preserve), a `quoting_context` classifier, and the composed policy
`quote_is_behavior_preserving`. Design + the Phase-0 spike that de-risked it:
`../../docs/upgrade_research/cheetah_bashlex_boundary_oracle.md`.

### Decisions

- **bashlex is isolated behind the optional `galaxy-tool-xml[shell-oracle]` extra**, not
  a hard dependency: bashlex is **GPL v3+** and this tier is MIT. `_bashlex()` guards on
  `importlib.util.find_spec`; every entry point degrades gracefully when the extra is
  absent (`boundary_signature`/`quoting_context` → `None`/`UNKNOWN`,
  `quote_is_behavior_preserving` → the value-domain `provably_quotable`). So the default
  output is unchanged and license-clean; installing the extra changes behaviour.
- **The quoting *policy* lives here, in tier 1**, beside `provably_quotable`, because the
  GTR020.1 fixer (tier 2) and the GTR020.2 advisory check (tier 3.5) both call it — same
  rationale as §16. One shared predicate keeps their fix/advisory partition exact.
- **Vars are kept as bash *expansions*, never value-substituted.** bash word-splits
  expansion *results*, not literal text (`foo=$x` with a space-bearing `$x` stays one
  value, but the literal `foo=a b` is assignment + command), so substituting a value
  would mis-model splitting. The classifier replaces each Cheetah var with a simple
  `$SENTINEL` expansion (so dotted `${x.y}` — invalid bash — never breaks the parse) and
  reads the target's *syntactic context* from the AST: assignment RHS → `NO_SPLIT`;
  `>&`/`<&` dup target → `DUP_TARGET`; bare word / redirect-file target / inside `$(…)`
  → `SPLIT`; parse failure (`[[ … ]]`, `$(( … ))`) or not-found → `UNKNOWN`.
- **`quote_is_behavior_preserving` = value-domain + a `DUP_TARGET` narrowing only.**
  `DUP_TARGET` → never quote (quoting a numeric fd in `>&`/`<&` flips a dup into a file
  redirect; conservatively vetoes file-valued dups too); `SPLIT` / `NO_SPLIT` / `UNKNOWN`
  → defer to `provably_quotable`.
- **No widening on `NO_SPLIT` (corrected 2026-06-04 — the original Phase-1 widening was
  reverted as unsound).** `VAR=$x` is a no-split context for a shell *expansion*, but
  Galaxy renders a Cheetah `$x` to its value as **literal text** before the shell runs, and
  a literal `VAR=foo bar` *does* split (assignment + command `bar`) — so single-quoting a
  space-bearing value there changes behaviour. The classifier still reports `NO_SPLIT`
  (correct about *shell* structure) but the policy must not act on it; the prominent
  docstring comment guards against re-adding the widening. Sound widening of Cheetah command
  values needs adversarial-shape render verification (deferred). Known tiny gap: a var used
  as a literal fd-number prefix `$intvar>file` is `SPLIT` and may be quoted — requires
  `$integer_param` immediately before `>`, essentially absent in real tools.

### Reproduction

```sh
uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_shell_oracle.py
```

## 18. Cheetah reference model (`cheetah_refs`)

**Date:** 2026-06-04. First read-only piece of the M5 Cheetah-section-editing work
(`../../docs/upgrade_research/cheetah_section_editing.md`).

`cheetah_refs.py` finds **every** Cheetah `$var` reference across a tool's
Cheetah-templated sections — the read-only substrate for `find-references` (and, later,
param refactors). `cheetah_references(text)` returns `CheetahRef`s (name, identifier
`segments`, section, `sourceline`, span); `tool_cheetah_references(root)` enumerates the
`fill_template` sections of the **raw** tree (`<command>`, inline `<configfile>`,
`<environment_variable>`, output `<data>`/`<collection>` `label`, dynamic
`<options>`/`<filter>`, `<entry_point>`, `data_source redirect_url_params` — see
`../../docs/galaxy_processing_model.md`).

### Decisions

- **Distinct from `command_text.unquoted_cheetah_vars`.** That reports only the
  fully-unquoted shell-line `$var`s in `<command>` for the GTR020 quoting practice; this
  reports *every* reference (quoted, in `#if`/`#set` directives, in every templated
  section) because find-references / a future unused-param consumer need them all.
- **Faithful by default (2026-06-06), regex only as a fallback.** `cheetah_references`
  resolves through the CT3 span lexer (§19; CT3 is a base dependency): a reference is a
  `PLACEHOLDER` span or a `$var` in a `#if`/`#set`/… `DIRECTIVE` head; `COMMENT` spans,
  `#raw` blocks (one verbatim directive span — `directive == "raw"`, skipped), and
  escaped `\$` are excluded, exactly as Cheetah resolves them. This makes
  `find-references` agree with the faithful `rename-param` mutator (so the query never
  shows a site rename would refuse). It falls back to the conservative `_CHEETAH_VAR`
  regex (the original superset) only on the ~0.4% of sections CT3 cannot compile — the
  safe direction for a read-only query. The goal is correctness for
  novel tool XML, not a corpus-fitted superset, so the faithful path is used whenever
  available. References from imported macros / `<expand>` are out of scope (macro files).
- **`segments` not just root.** A reference's identifier segments (`${adv.x}` → `(adv, x)`)
  let a consumer match a parameter name as the *leaf* of a `$cond.sub` access, not only the
  root — needed for find-references on a conditional sub-param.
- **`referenced_identifiers(root)` (added for GTR034 unused-param).** The set of every
  identifier that could name a param: the union of all `tool_cheetah_references` segments
  **and** the identifier tokens of every attribute value, *skipping the `name` attr of
  `<param>` definitions* (so a param isn't "used" by its own declaration). The
  attribute-token scan generically subsumes **every** by-name param cross-reference Galaxy
  has — `data_ref`, `format_source`, `metadata_source`, `change_format @input`, dynamic
  `<options>` `from_dataset` / `filter @ref`, output `<collection>` `structured_like` /
  `collection_type_source`, output-action `option @name` / `filter @ref`, … — because they
  are **all attributes** (there is no positional or free-text param linking in Galaxy tool
  XML), so no per-attribute allowlist is needed. Conservative (over-counts: a coincidental
  `format="fastq"` token only protects a like-named param). The check tier (3.5) consumes
  this on the macro-expanded tree; see check `docs/decisions.md` D11.
- **Why `referenced_identifiers` deliberately does *not* use the faithful lexer.** Unlike
  `cheetah_references`, it must also catch **bare-name** references the Cheetah lexer can't
  see — a param named in an output `<filter>` Python expression (`<filter>store_ext</filter>`,
  no `$`) or a cross-ref attribute — so it scans *all* identifier tokens, not just `$`
  placeholders. And it powers an *advisory* (GTR034 "this param looks unused, remove it"),
  where the costly error is a **false positive** (telling an author to delete a used param);
  over-counting references is therefore the *correct* conservative direction, for novel XML
  too. Narrowing it to the faithful `$var`-only scan would both miss bare-name refs and risk
  false "unused" reports — so the broad scan is intentional, not a missed faithful upgrade.

### Reproduction

```sh
uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_cheetah_refs.py
```

## 19. Faithful Cheetah lexer (`cheetah_cdm`) — CT3 (a base dependency)

**Date:** 2026-06-05 (shipped behind the optional `[cheetah-cdm]` extra); **made a base
dependency 2026-06-06** (see the update under Decisions). M5.1 of the
Cheetah-section-editing roadmap
(`../../docs/upgrade_research/cheetah_section_editing.md`) — the precision drop-in the
`cheetah_refs` regex (§18) reserved, shipped ahead of the first mutator (rename).

`cheetah_cdm.py` harvests the **exact source spans** of every `$placeholder` /
`#directive` / comment in a Cheetah section by subclassing CT3's own
`Cheetah.Parser.Parser` and recording each `eat*` hook's `[start, pos())` extent.
`cheetah_spans(text)` returns the ordered list of `CheetahSpan`s (`kind`, `start`,
`end`, `text`, `directive`), or `None` to bail. Because the real parser drives the
harvest, `##` comments, `#raw` blocks, escaped `\$`, and embedded strings are classified
exactly as Cheetah would — the fidelity a *mutator* needs and the regex cannot give
(it would rewrite bytes inside a `#raw` block).

### Decisions

- **CT3 is a base dependency (Update 2026-06-06).** Originally isolated behind the
  optional `galaxy-tool-xml[cheetah-cdm]` extra (mirroring `[shell-oracle]`, §17), CT3
  was promoted to a **base dependency** (`galaxy-util[template]` in `[project]`
  `dependencies`) once enough rules depend on faithful spans for *soundness*
  (`command_text`/GTR020, `cheetah_refs`/find-references, rename): a single sound code
  path beats a dual faithful/regex one, and the faithful result is correct for novel
  tool XML by default. **Unlike `[shell-oracle]` (bashlex is GPL), CT3 is MIT**, so it
  is a clean hard dependency. `cheetah_spans` still returns `None` on the ~0.4% of
  bodies CT3 cannot compile — callers fall back to the §18 regex *only there* (those
  bodies are retained as a corpus for later work: `scripts.measure cheetah-cdm-bails`
  writes `docs/corpus_data/cheetah_cdm_bail_cases.json`) — and defensively if CT3 were
  somehow absent. The `Parser` subclass is built once in a `@cache`d factory; CT3 is
  imported lazily.
- **Spans are disjoint, ordered, and round-trip-faithful.** The literal text between
  spans is the gap, so a section re-serialises by interleaving gaps with each
  `span.text` — the contract a byte-faithful mutator relies on.
- **A directive head swallows its own `$vars`.** `#if $paired` / `#set $tmp = $base` are
  single directive spans (no nested placeholder spans); a reference *inside* a directive
  must be recovered from that span's text by a scope-aware consumer, not read off the
  placeholder list. This is exactly what the future rename scope model needs (bindings
  live in `#set`/`#for`/`#def` heads).
- **Bail (`None`) on any CT3 compile failure**, never raise: ~0.4% of corpus bodies
  (py2-isms, `#import` of an absent module, an unbalanced `#end`). The caller degrades to
  the regex, so a faithful answer is a strict upgrade and a bail is never worse than
  today. SyntaxWarnings from CT3's generated code are silenced inside `cheetah_spans`.
- **Parity with the spike.** Over the corpus, `cheetah-cdm-coverage` reports **9,202 /
  9,236 = 99.6%** pure-text `<command>` bodies parse-clean, **0.4%** bail, and **22.6%**
  of clean bodies carry a `#set`/`#for`/`#def` local (the rename scope-shadowing
  population) — reproducing the read-only Phase-0 spike with shipped code.

### Reproduction

```sh
uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_cheetah_cdm.py
uv run python -m scripts.measure cheetah-cdm-coverage   # corpus parity + scope sizing
```

## 20. Parameter rename (`cheetah_rename`) — the first Cheetah mutator

**Date:** 2026-06-05. M5.3 of the Cheetah-section-editing roadmap
(`../../docs/upgrade_research/cheetah_section_editing.md`) — the mutating sibling of the
`cheetah_refs` reference model (§18), the first consumer of the faithful lexer (§19).

`cheetah_rename.rename_param(root, *, old, new)` rewrites every reference to a parameter
`old` so it reads `new`: `$old` in `<command>` / inline `<configfile>` (via `cheetah_cdm`,
so a `$old` inside `#raw` / `##` / an escaped `\$old` is left alone), `$old` in
attribute-Cheetah (output `label`, dynamic `<options>`, `<entry_point>`,
`<environment_variable>`, `data_source`), the by-name cross-reference attributes, the
`<tests>` elements that mirror the input tree, and the definition itself. Returns a
`RenameOutcome` (renamed-site count, or a bail reason).

### Decisions

- **Rename is atomic.** A half-applied rename (definition renamed, a reference left
  dangling) is a broken tool, so it rewrites *every* live occurrence or changes nothing.
  It bails — `shadowed` (a `#set`/`#for`/`#def` local shadows `old`), `mixed-content` (a
  body whose Cheetah text is split by child elements), `lexer-bail` (CT3 can't parse a
  body referencing `old`), `filter-bare-ref` (an output `<filter>` names `old` by bare
  Python word), `cross-ref-residual` (a non-literal attribute still equals `old` after
  rewriting — a by-name reference this version does not model), or `not-found` /
  `invalid-name` / `no-op`.
- **Faithful lexer for bodies, regex for the simple sites.** `<command>` / `<configfile>`
  go through `cheetah_cdm` (the `#raw`/comment fidelity a mutator needs); the short
  single-expression sites (attribute-Cheetah, env vars) use the segment regex directly —
  they carry no `#raw`/comments. Both rewrite only the matching identifier *segment*
  (`$cond.old` → `$cond.new`), so a different name (`$old_other`) is never touched.
- **The cross-reference model is explicit, and was sized by the corpus.** The first cut
  bailed 41.7% of renames on a coarse "any attribute still equals `old`" net. The
  `rename-coverage` sweep showed that residual was dominated by `<tests>` mirrors (a test
  references params by name) plus a few real cross-ref attributes (`when@input`,
  `filter@ref`, `from_dataset`, `split_inputs`), with the rest coincidental literals
  (`label`/`value`/`type`/`format`/…). Modelling the references and exempting the literals
  (`_LITERAL_ATTRS`) took clean coverage **51.5% → 93.1%** and the residual cross-ref bail
  to 0.1% (the later `<filter>` rewrite, §22, took clean coverage on to **96.3%**).
- **Completeness net, denylist-guarded.** After rewriting, a non-literal attribute still
  equal to `old` trips `cross-ref-residual` — catching an unmodelled by-name reference so
  rename bails rather than ship a dangling tool, while the `_LITERAL_ATTRS` denylist keeps
  a coincidental `label="old"` from a false bail.
- **No serialization here.** Tier 1 mutates the lxml tree (the source of truth); the
  facade deep-copies before calling (so a bail never mutates the caller's tree) and
  serialises through fmt. Corpus: of 72,247 input definitions across 8,928 tools, **96.3%
  rename cleanly** (322,859 sites); the residual bails are `filter-bare-ref` (2.4%, §22),
  `lexer-bail`/`mixed-content` (0.5% each), `shadowed` (0.3%), `cross-ref-residual` (0.1%).

### Tier-B offset API (`rename_param_plan`) — minimal diffs for the editor

**Date:** 2026-06-05. Step 1 of `../../docs/upgrade_research/lsp_rename_integration.md`:
bring rename into [galaxy-language-server](https://github.com/galaxyproject/galaxy-language-server)
as a real "Rename Symbol". An editor rename must touch **only** the renamed tokens, not
reflow the document — which `rename_param` + the fmt serializer would (the facade's
`RenameParamResult.formatted` reserialises the whole tree). So tier 1 grows a
TextEdit-oriented rendering alongside the tree mutator:
`rename_param_plan(source, *, old, new) -> RenamePlan`, a tuple of disjoint,
document-ordered `RenameEdit(start, end, replacement)` spans into the **original** source.

- **One planner, two renderings.** `rename_param` and `rename_param_plan` share
  `_plan_rename` (which sites, which bails) and differ only in how the plan is applied —
  tree mutation vs. resolving each site to source offsets. The two can never disagree on
  scope or bail reason; the existing §20 bail taxonomy is reused verbatim.
- **Raw-source locators (the new code), self-checked.** `_segment_edits` already gives
  spans *within* a section's decoded text; resolving them to the raw document needs three
  new pieces — a start-tag locator (`_start_tag_open`/`_start_tag_close`), an attribute-
  value locator (`_attr_value_base`), and the text-body walker below. These use a focused
  raw-source scan (option (a) of the LSP design note — chosen over coupling to galaxyls's
  `XmlAttribute` model so the engine stays editor-agnostic, reusable for a future CLI
  `--diff`). Every resolved span is verified against the source and the final edits checked
  disjoint, so a mis-anchored span bails (`locator-failed`) rather than corrupting the file.
- **Decoded→raw body walker, not a flat offset.** A `.text` offset equals a raw-source
  offset only for an entity-free, single-CDATA, no-leading-whitespace body — which is *not*
  the common case (many `<command>` bodies are plain text with `&amp;&amp;` for shell `&&`,
  or `<command>\n<![CDATA[…`). So `_text_body_offset_map` walks the raw body from just past
  the start tag, consuming `<![CDATA[` / `]]>` markers (content verbatim) and decoding
  entity references outside a section, and relocates each decoded span to the source. Only
  an entity it cannot decode (a non-predefined named entity, which DTD-less XML would not
  have parsed anyway) bails `entity-content`.
- **`sourceline` is the start tag's *closing* line.** lxml reports `sourceline` as the line
  of a start tag's `>`, which for a multi-line tag (`<param name="x"\n  type="data"/>`) is
  *later* than the opening `<`. `_start_tag_open` therefore anchors on the `<tag` whose
  start tag *closes* on `sourceline` (with a document-order ordinal for ties) — a flat
  forward-scan from that line grabbed the *next* element and renamed the wrong param.
- **Whole-source bails.** A non-recoverable source bails `parse-error`; non-UTF-8 `bytes`
  bail `encoding` (the LSP path passes an already-decoded `str`, so this is bytes-only).
- **Offsets are character offsets into the decoded `str`** (bytes decoded UTF-8), the unit
  an LSP server converts to a `Range` via its `position_at_offset`. The LSP path passes the
  editor's already-decoded `str`; the `bytes` convenience only supports UTF-8.

**Coverage (sized by `rename-coverage`, which now also checks Tier-B parity).** Across the
72,247 corpus rename attempts the offset path reaches the **same verdict as the tree
mutator for 96.8%** with **0 genuine mismatches** (the shared planner guarantees parity;
the sweep asserts it). The remaining 3.2% are *sound declines*, not edits gone wrong:
`locator-failed` 3.2% (exotic anchoring the raw scan can't reconcile — e.g. a literal
`<tag` inside a comment / CDATA / help example that shifts the document-order ordinal) and
`encoding` 0.0%. The two big early gaps were closed during sizing: entity/CDATA skew (the
body walker, which also covers attribute values) and multi-line start tags (the
`sourceline`-is-the-close-line fix) took parity 71.3% → 87.5% → 96.8%. An editor can fall
back to a whole-document `TextEdit` (the design note's Tier A) for the declined cases.

The galaxyls binding (deps, `prepareRename` / `rename`, offset→`Range`, bail→diagnostic)
is the separate step 2 of the design note, upstreamed there — not in this repo.

### Reproduction

```sh
uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_cheetah_rename.py
uv run python -m scripts.measure rename-coverage   # outcome distribution over the corpus
```

## 21. The tool bundle — cross-file parameter rename (`bundle`)

**Date:** 2026-06-05. Extends §20: rename a parameter across a tool **and its
transitively-imported macro files**, not just the single tool file.

A Galaxy tool routinely *defines* a `<param>` in its own `<inputs>` but only
*references* it (`$param`) — or mirrors it in `<tests>` — inside an imported macro
file. The real `tools-iuc/pal2nal` is the canonical case: `pal2nal.xml` defines
`<param name="protein_alignment">` and is just `<expand macro="command"/>`, while the
`$protein_alignment` references live in `macros.xml`'s `<xml name="command"><command>`
and six `<test>` mirrors in `tests.xml`. The §20 single-file rename renamed the
definition and **reported success while leaving the macro references dangling** — a
silent broken-tool bug, not merely missing coverage. Renaming
`protein_alignment` across the bundle rewrites **9 sites across 3 files**.

Corpus-wide (`rename-macro-spread`): of 71,935 input-definition renames, **1,243 (1.7%)
spill into an imported macro — every one a silent break today**; 1,039 (84%) touch only
sole-owned macros (v1 auto-applies with `--repo-root`), 204 touch a shared macro (v1
skips + reports). 94.4% are tool-internal (unaffected).

### Decisions

- **A `ToolBundle` is the unit; `load_bundle(path)` builds it** from the existing
  `imported_macro_paths` + `load_tool` + `load_macros`. Each member carries its own
  `source_path`, so edits write back to the right file ("locate-in-source" — the same
  strategy `normalize-macros` / the `@PROFILE@` bump already use; **not** the deferred
  expansion-provenance layer, which solves post-expansion node attribution — a problem
  this rename doesn't have, since references are literal text in the macro source).
- **One planner, three callers.** `rename_param` already took an arbitrary root; it now
  reads the **mode from the root tag** (`<tool>` vs `<macros>`) so `<command>` /
  `<configfile>` fragments nested under `<xml name="…">` are found by descendant scan,
  and a `name="old"` definition / output / `<test>` mirror anywhere in a macro is
  **rewritten** (not skipped — a skipped `name` is residual-exempt and would slip the
  completeness net). No parallel planner; the §20 "two renderings share one planner"
  invariant holds with `rename_param_in_bundle` as the third caller.
- **Whole-bundle atomicity with a `not-found` carve-out.** A member that simply doesn't
  mention `old` reports `not-found` and contributes nothing (the common outcome for an
  unrelated macro — it must **not** abort). *Any other* member bail (`shadowed`,
  `mixed-content`, `lexer-bail`, `filter-bare-ref`, `cross-ref-residual`) bails the
  whole bundle: renaming the tool's param while a macro reference survives would dangle.
- **No shared-file gate here.** This tier mutates in-memory trees and reports which
  members changed; whether an edited macro is safe to write (sole-owned vs shared by
  other tools) is a repo-wide question owned by the registry gate (registry D12). The
  caller passes a bundle it will discard on a bail, exactly as the facade deep-copies
  before the single-root `rename_param`.

### Reproduction

```sh
uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_bundle.py
uv run python -m scripts.measure rename-macro-spread   # spill % + silent-break count
```

## 22. Output `<filter>` rename — a tokeniser-precise rewrite

**Date:** 2026-06-05. Extends §20: rename a parameter referenced inside an output
`<filter>`, which §20 conservatively bailed (`filter-bare-ref`).

A Galaxy output `<filter>` is a **Python expression** over the input values
(`<filter>genome == 'hg19'</filter>`), so a top-level parameter is referenced by **bare
name**, not `$genome`. §20's first cut bailed whenever `old` appeared as a bare-ish token
in any filter — the single largest residual bail (~5.6% of corpus rename attempts), and a
*conservative over-bail* (it fired even when `old` only appeared inside a string literal).

### Decisions

- **`tokenize`, not `ast`/libCST.** The rename engine is offset-based (both the tree
  mutator and the offset/`WorkspaceEdit` path consume `(start, end)` spans over the
  original source). `tokenize` yields exactly that — every token with its precise
  `(row, col)` — and the discrimination needed here is token-level, not semantic: rewrite
  a bare `NAME` token equal to `old`, leave `STRING` tokens (`'old'`, dict keys, values)
  and attribute accesses (`x.old`, a `NAME` after `OP('.')`) alone. A CST library would
  add a heavyweight dependency and push toward regenerate-the-whole-expression, fighting
  the minimal-diff model; `tokenize` (+ `ast.literal_eval` for one string-equality check)
  is stdlib and offset-native.
- **Bail-on-doubt, narrowed.** `_filter_name_spans` returns the `NAME`-token spans plus an
  *ambiguous* flag, set when `old` also occurs as a **string literal** — a possible
  `cond['old']` sub-parameter dict-key that cannot be told from a coincidental value. The
  rename still bails `filter-bare-ref` then, and when a filter body won't tokenise at all
  (falling back to the conservative `_has_bare_reference` check). So the bail survives only
  for the genuinely-ambiguous residual.
- **Result.** Clean rename coverage **93.1% → 96.3%** (`rename-coverage`); `filter-bare-ref`
  dropped from the largest bail to a 2.4% residual. The offset path keeps full parity
  (0 mismatches), so the editor/`WorkspaceEdit` rename gains filters too. Showcase:
  `tools-iuc/pdfimages` (`output_format` → 9 sites incl. 3 `<filter>`s), previously
  un-renamable.

### Reproduction

```sh
uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_cheetah_rename.py -k filter
uv run python -m scripts.measure rename-coverage
```

## 23. `<help>` reStructuredText — validity + surgical repair (`rst`, docutils)

**Date:** 2026-06-09. New module `galaxy_tool_xml.rst` + a `docutils>=0.21` base
dependency. The shared predicate behind the **GTR089 fix/advisory partition** (codemod
§37, check D31): `rst_is_invalid` (the validity test) and `repair_help_rst` (the
deterministic, gated repair). This is the RST analogue of the Cheetah work (§19–§22) —
a hostile-format mutator for the *other* embedded language in a tool, `<help>`.

Galaxy renders a `<help>` body as reStructuredText to HTML **server-side**
(`galaxy.util.rst_to_html`); a body with `format="markdown"` renders client-side instead
and is out of scope. `rst_is_invalid` matches Galaxy's `rst_to_html(error=True)`: publish
through docutils with a `warning_stream` that raises on the first reporter message and
`halt_level` lifted so that stream is the trigger. (This predicate moved here verbatim
from the check tier, which now imports it — so the check tier no longer declares docutils
directly; it is transitive through tier 1.)

### Decisions

- **Surgical, line-anchored repair — never parse-and-reserialise.** docutils has **no
  faithful RST writer** (its writers target HTML/LaTeX/XML) and its nodes carry **no source
  offsets** (only a reporter `line`). So — exactly the constraint that forced the Cheetah
  lexer — repair edits the *source text* anchored on the reporter's line number, and is
  proven safe rather than reconstructed.
- **Class-keyed recipes, not corpus-keyed.** Each fixable error class maps to one
  deterministic recipe (title-underline-too-short → extend the underline run to the title
  width; "ends without a blank line" family → insert a blank line before the reported
  dedent). General by construction — it repairs any tool exhibiting the class, not just
  corpus instances (no overfit).
- **A strong behaviour-preservation gate is what makes it canonical-safe.** A repaired
  round is kept only if it (a) strictly reduces serious (level ≥ 2) messages, (b)
  introduces no new error class, **and** (c) leaves the docutils doctree structurally
  identical *modulo the removed system messages* (`_structural_signature`). Edits are
  vetted individually before the batch is re-gated, so one bad edit can't poison a fixable
  round. Anything failing the gate returns `None` (the codemod no-ops; the residual stays
  GTR089.2). This correctly **vetoes** the tempting "drop a trailing transition" fix:
  docutils renders a trailing `----` as an `<hr>`, so dropping it changes rendered output.
- **Macro-bearing help (`@TOKEN@`) is left alone** — the literal token is what docutils
  sees, not the expanded value, so no edit there is provably safe.

### Reproduction

```sh
uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_rst.py
uv run python -m scripts.measure help-rst-errors   # the fixable-class population
```

## 24. `<help>` RST → Markdown conversion + render-equivalence gate (`rst_markdown`)

**Date:** 2026-06-10

The converter + gate behind the GTR092 opt-in conversion (codemod §38) and the
`help-rst-md-convert` standing measure — promoted here from `scripts/measure.py`
when the conversion capability shipped, so the measure and the codemod run the
same code paths.

- **Rendering model (verified in the Galaxy clone):** RST renders **server-side**
  (`galaxy.util.rst_to_html` = docutils html4css1; `ToolHelpRst.vue` just
  `v-html`s it); `format="markdown"` renders **client-side** (`ToolHelpMarkdown.vue`
  → `MarkdownIt({html:false}).render`, markdown-it ^14 default preset). Conversion
  **swaps the engine** — behaviour-changing by construction — hence the gate.
- **`rst_to_commonmark(text)`** — a whitelist doctree visitor (sections→ATX,
  paragraphs, em/strong/literal, fenced literal blocks, bullet/enum lists,
  block quotes, transitions, links, images; **GFM pipe tables** for a *simple*
  table — one tgroup, a single-row `thead` (GFM needs a header), span-free,
  inline-only cells — and **hard breaks** for a *flat* line block) that **bails
  on the first node with no CommonMark form** (incl. a header-less/spanning/
  block-content table → `"table"`, a nested line block → `"line_block"`);
  returns `(markdown, None)` or `(None, bail_class)`.
- **`conversion_is_render_equivalent(rst, md)`** — renders both sides exactly as
  Galaxy does (docutils html4css1 vs markdown-it-py `js-default`, `html:false`),
  reduces each to a normalized semantic skeleton (canonical tag names,
  `<tt>`→`<code>`, fenced `<pre><code>`→`<pre>`, loose-vs-tight list `<p>`
  unwrapped, whitespace insignificant at block boundaries only; **drop the
  docutils-only `<colgroup>`/`<col>` table artifacts, and map both markdown-it
  `<br>` and docutils `div.line` to one shared line-boundary marker** so a
  faithful table / line-block conversion compares equal), and accepts iff equal.
  Negative-controlled (corruptions — incl. swapped cells, dropped rows, reordered
  lines — are rejected; pinned by tests).
- **`convert_help_rst(text)`** — the composed pipeline: invalid RST goes through
  the §23 surgical repair first (itself gated), then convert, then gate (against
  the repaired text — what Galaxy would render). `None` unless *provably*
  convertible.
- **Dependency:** markdown-it-py rides the **`[markdown]` extra**
  (`markdown_renderer_available()` is the LBYL check) — the gate is mandatory,
  so an absent extra means refusal, never a blind conversion. MIT, but the
  capability is opt-in, so it follows the bashlex extra pattern, not the CT3
  base-dep pattern. It stays a dev dep so the tests run in CI.
- **Corpus:** 73.4 % of RST `<help>` bodies convert + pass the gate
  (`scripts.measure help-rst-md-convert`, R4 — the measure imports this module).
  The GFM table/line-block support lifted this from 72.2 % (+88 tools); the gate
  rejected the 139 non-simple tables/line-blocks that convert but don't render
  equivalently — far below the spike's ungated ~78–80 % guess.

### Reproduced by

```sh
uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_rst_markdown.py
uv run python -m scripts.measure help-rst-md-convert   # needs the corpus
```

## 25. `schema_content.text_bearing_tags` — the schema as the payload-guard source of truth

**Date:** 2026-06-10. Reproduced-by: `uv run --package galaxy-tool-xml pytest
galaxy-tool-xml/tests/test_schema_content.py`. The fmt tier's whitespace guards
(GTR004 collapse denylist, GTR001 payload-subtree skip) had hand-maintained tag
lists; this module derives the set from the vendored XSDs instead — an element
is **text-bearing** iff its content model admits character data
(`xs:simpleContent` / `mixed="true"` / a builtin / a named simpleType), unioned
across all 28 schemas (conservative for a guard; unknown type references also
resolve conservatively). The derivation is honest about name collisions
(`<inputs>` is element-only under `<tool>` but `simpleContent` under
`<configfiles>`; legacy `<macros>` is `xs:anyType`) — context handling and
proof-carried exceptions live in the consumer (fmt `payload.py`, fmt §D20),
not here. Tier direction is clean: tier 1 owns the schemas, fmt consumes the
derived fact.

## 26. Renamed: `galaxy-tool-xml` → `galaxy-tool-source` (2026-06-10)

The package (dist `galaxy-tool-xml`, import `galaxy_tool_xml`) is now
**`galaxy-tool-source`** / **`galaxy_tool_source`** — aligned with Galaxy's own
`ToolSource` vocabulary (`galaxy.tool_util.parser`) and with what the tier
actually owns: the *tool source* (parsing, validation, profile resolution,
Cheetah views), not XML cosmetics. Renamed before the first PyPI publish so
the old name is never published. The three sibling dists
(`galaxy-tool-xml-codemod`/`-fmt`/`-check`) keep their names — "xml" describes
their own domain (they codemod/format/check the tool XML), which stays true.

**Historical entries in this file (and every dated record — audit records,
research notes, the deferral ledger) keep the old name verbatim**; only
current-state docs were rewritten. Execution record:
`~/.claude/plans/rename-galaxy-tool-source-plan.md`; two sed traps found and
guarded — the sibling *dist* names need `[^-]`, and the sibling *import*
names (`galaxy_tool_xml_codemod` et al.) equally need `[^_]`.

## 27. Renamed the three `-xml-` sibling dists (drop "xml"); §26's "keep their names" reversed (2026-06-11)

§26 renamed tier 1 to `galaxy-tool-source` but argued the three sibling dists
should **keep** their `galaxy-tool-xml-*` names ("xml describes their domain").
That call is reversed here, driven by the decision to publish the whole tooling
to PyPI: publishing the front-door `-cli`/`-mcp` forces publishing their entire
dependency tree (all eight packages), so every package gets a public name — and
relative to the already-published `galaxy-tool-source`, the `-xml-` packages were
the inconsistent ones. Settled **before** their first publish (post-publish
renames mean a tombstone + deprecation shim).

| Tier | Old dist / import | New dist / import |
|---|---|---|
| 2 | `galaxy-tool-xml-codemod` / `galaxy_tool_xml_codemod` | `galaxy-tool-codemod` / `galaxy_tool_codemod` |
| 3 | `galaxy-tool-xml-fmt` / `galaxy_tool_xml_fmt` | `galaxy-tool-fmt` / `galaxy_tool_fmt` |
| 3.5 | `galaxy-tool-xml-check` / `galaxy_tool_xml_check` | `galaxy-tool-lint` / `galaxy_tool_lint` |

Tier 3.5 also dropped "check" → **`lint`**: on PyPI "check" reads as planemo's
"run the tool to check it"; `lint` unambiguously names the planemo-parity linter
tier (the CLI verb stays `check`). Tier 1 (`galaxy-tool-source`, published),
the product family (`galaxy-tool-refactor-{rules,registry,cli,mcp}`), and the
`check` CLI subcommand are unchanged. The result is two deliberate families:
`galaxy-tool-*` reusable libraries (`source`/`codemod`/`fmt`/`lint`) and
`galaxy-tool-refactor-*` the product built on them. A `galaxy-tool-refactor`
front-door metapackage was deferred to a follow-up — now shipped, §28.

**Historical entries keep the old names verbatim** (as §26 established — this
file's §9/§26 still show `galaxy-tool-xml-*`); only current-state docs and all
code/config were rewritten, via a full-token sed (`galaxy-tool-xml-{codemod,fmt,check}`
and the `_`-form) that never touches the bare `galaxy-tool-xml` tier-1 historical
name. Rationale + the building-block-vs-product analysis:
`../docs/package_naming_plan.md`.

## 28. Added the `galaxy-tool-refactor` front-door metapackage (2026-06-11)

The follow-up §27 deferred: a ninth workspace distribution, dist name
**`galaxy-tool-refactor`** (directory `galaxy-tool-refactor-meta/`), so
`pip install galaxy-tool-refactor` gives end users the product without knowing the
package layout. It depends on `galaxy-tool-refactor-cli==<version>` (which provides
the `galaxy-tool-refactor` command) and offers an **`[mcp]` extra** pulling
`galaxy-tool-refactor-mcp` for the agent-facing server. Pure metapackage — no
modules (hatchling `bypass-selection`), a metadata-only wheel.

It is a full **lockstep** member: `scripts/bump_version.py` sets its version and
pins both intra-deps (it was extended to also pin `[project.optional-dependencies]`
extras, so the `[mcp]` pin can't drift), and `test_workspace_versions` (now nine
members) enforces it. It is **not** in the qa-gate roster (no `src/`/`tests/`) and
not a tier — it carries no abstraction. `release.yml` builds and publishes it with
the other eight; it needs its own PyPI trusted publisher.

Rationale (front-door metapackage as the install convenience, libraries stay
separately installable): the ecosystem analysis in `../docs/package_naming_plan.md`.

## 29. Version-tokenization moved to tier 1 + the offset planner (`version_tokens`, 2026-06-11)

GTR094 (`tokenize-version`) factors a literal `version="<base>+galaxy<suffix>"`
into `@TOOL_VERSION@`/`@VERSION_SUFFIX@`. Its *decision* (`tokenization_skip_reason`),
its *soundness gate* (`expansion_equality_holds`, proof by execution: tokenizing must
not change the macro expansion), and its *tree mutation* (`tokenize_tree`) previously
lived in the tier-2 codemod (`galaxy-tool-codemod` §43). This release moves them down
to tier 1 (`version_tokens.py`) and adds an **offset planner**,
`tokenize_version_plan`, alongside. The codemod is now the tree-rendering of the
shared tier-1 decision (a thin `Module` adapter); the planner is the
editor-and-CLI-shared rendering.

This is the version-tokenization counterpart of the `cheetah_rename` /
`rename_param_plan` dual-rendering discipline (§20): tier 1 has no serializer, so the
planner returns minimal `(start, end, replacement)` edits over the *original* tool
source plus, in separate-file mode, the full content of a new `macros.xml`
(`NewMacroFile`). The CLI applies the plan and writes the file; the
galaxy-language-server turns it into an LSP `WorkspaceEdit` (the tool edits as
`TextEdit`s, the new file as a `CreateFile` resource operation). The planner emits
only text edits and one fixed four-line `macros.xml` template, never a general
document serialization (the serializer-allowlist guard scopes its single
expansion-gate `etree.tostring` as throwaway, like the codemod's was).

**Proof by execution over the rendered bytes.** Every successful plan applies its own
edits, re-parses, macro-expands, and bails unless that expansion is byte-identical to
the original's, so an imperfect offset anchor yields a *bail*, never wrong output.
Two anchoring subtleties a development-time corpus parity spot-check surfaced (the
106 tools the proven codemod would tokenize): (a) libxml2 reports `sourceline` as the
start tag's closing `>` line, so a multi-line `<tool …>` whose `<tool` is on an
earlier line is anchored by scanning *backward* from that line; (b) the inserted
`<macros>` block reuses the *original* leading whitespace as its prefix, so the gate's
`remove(<macros>)` leaves the surrounding inter-element whitespace byte-identical (a
naive insertion swallowed a blank line into the new element's tail and failed the
gate). Both are pinned by regression tests in `test_version_tokens.py`. With them
fixed the planner reaches **100% inline parity** with the codemod (106/106);
separate-file mode declines (safe bail) on the 2 tools that already carry a `<macros>`
block, where inline placement is the natural choice.

Phase 1 of `~/.claude/plans/version-token-macros.md` (the offset-planner foundation);
the CLI `--macros-file` wiring and the galaxyls Code Action follow, the latter with a
committed CLI-vs-plan parity test (mirroring `rename_param` vs `rename_param_plan`).

## 30. Adopt-suffix: the controlled-change gate (`version_tokens`, 2026-06-11)

`adopt_suffix_skip_reason` / `adopt_suffix_equality_holds` back the opt-in,
identity-changing `tokenize-version --adopt-suffix` (cli §D15): a tool whose *bare*
version equals a package `<requirement>` gets `+galaxy0` added and is tokenized. Unlike
plain tokenization this *changes* the published version, so the expansion-equality gate
(§29) does not apply. Instead `adopt_suffix_equality_holds` is a **controlled-change
gate**: it expands the original and the adopted tree, sets the original expansion's root
`version` to `base+galaxy0`, and requires byte-equality. This proves by execution that
the only effect is the intended version bump (no requirement that should not have moved,
no token leaking elsewhere); anything else fails closed. The mutation reuses
`tokenize_tree(base=version, suffix="0")` (the adopted state is just a tokenized
`base+galaxy0` tool); only the precondition (bare version, no `+`/`@`, equal to a
package requirement) and the gate differ. Inline only; the bare-version population is
sized by `scripts.measure version-tokenization` (`n_version_equals_req_no_suffix`).

## 31. `newest_valid_profile` gains a `ceiling` (2026-06-12)

Reproduced-by: `uv run --package galaxy-tool-source pytest
galaxy-tool-source/tests/test_validate.py -k ceiling`.

The newest-first scan accepts a keyword-only `ceiling`: profiles newer than it
are skipped, so the result never exceeds it (and is `None` when no vendored
profile lies at or below it). Motivation: the codemod tier's behavior gate
(codemod decisions §45) must be able to ask "the newest profile this tool
validates at *without crossing a behaviour boundary*"; capping the scan here
keeps every declaration site (`UpdateProfile`, `UpgradeToLatest`, the
registry's shared-token targets) on one primitive instead of post-filtering in
each caller. Backward compatible; the default scans everything as before.
