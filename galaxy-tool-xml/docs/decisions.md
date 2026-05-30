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
| 1.5 | A missing `profile` attribute defaults to `"16.01"` *inside Galaxy*. **This project deliberately diverges**: a no-profile tool validates against the latest XSD (user choice). | Galaxy source + planning decision in `PLAN.md`. |
| 1.6 | A tool's set of valid profiles is **not guaranteed to be contiguous** across vendored XSDs. | Corpus sweep observation — see §10. `newest_valid_profile` does a linear newest→oldest scan rather than a binary search, on the strength of this. |
| 1.7 | `galaxy.util.xml_macros.load_with_references(path) -> (ElementTree, imported_paths)` is the canonical macro expander; it handles `<import>`, nested `<token>`, `<expand>` / `<macro>` / `<xml>`, and parameterised `<yield>` macros. Path-based, not in-memory. | Mirrored 1:1 in `macros.py`'s `expand_from_path` / `expand_from_tree`. |
| 1.8 | `galaxy.util` is Galaxy's **internal** API — not a stability-guaranteed surface. The `galaxy-util` PyPI package is CalVer (currently `26.0`). | Confirmed against the project's own docs / release cadence. Drives the range pin (§2.4) and the macros.py isolation rule. |
| 1.9 | The Galaxy ToolShed exposes content only over the **Mercurial wire protocol** — no tarball or raw-file endpoint on the public API. The API itself is HTTP/JSON, but file fetches require `hg clone`. | `scripts/fetch_toolshed.py` necessarily uses `hg`. |
| 1.10 | A ToolShed repository's "version" is its tip changeset; the API does **not** list it on the repository envelope. It must be captured client-side via `hg id -i` after cloning. | Necessitated the manifest in `corpus/galaxy-toolshed/manifest.json`. |

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
| **No-profile tools validate against the latest XSD.** | Deliberate divergence from Galaxy's `"16.01"` default — explicit user choice in `PLAN.md`. |
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
| **Toolshed `version` = tip changeset captured via `hg id -i` before `.hg/` is removed.** Recorded in a top-level manifest `corpus/galaxy-toolshed/manifest.json`; missing entries default to `"unknown"`. | The ToolShed API doesn't expose tip changesets (Assumption 1.10); `.hg/` is removed to save ~80% disk. The manifest is the single source of truth and is gitignored (the corpus itself is). |
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
| `.gitignore` excludes `src/galaxy_tool_xml/models/v*/`, `…/any_tool.py`, and the whole `corpus/` tree. Committed-but-generated: nothing in models; the `schema/` XSDs are committed. | Generated code regenerates deterministically from the committed XSDs + pinned xsdata; the corpus is reproducible from `corpus_sources.json` + the toolshed manifest. |

---

## 8. Coding standards

**`dignified-python` governs** (vendored at `.claude/skills/dignified-python/`); `optimized-python` is installed
as a reference. On conflict, dignified-python wins. Key applications in
this repo:

- LBYL over `try/except`. Exceptions only at the click error boundary
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
  **every** GTX rule *in isolation* (no other rules) across the corpus and
  writes `docs/corpus_rule_stats.md`. fmt rules (GTX001/003/004) are gated on
  validation and checked for **idempotence + no-crash only** — a rule like
  GTX003 run without GTX001 emits valid-but-non-canonical output, which is
  expected; we only assert it is stable and does not raise. Codemods
  (GTX002, GTX005–GTX012) reuse the existing `codemod` exercise (idempotence +
  post-codemod validity + eligibility), and `UpgradeToLatest` (GTX012)
  additionally surfaces its reach / sticking-point / per-step-advance discovery
  as upgrade QA. Failures retain to the owning tier's regression fixtures.
- **Why:** the `fmt` sweep runs all fmt rules together and the `codemod` sweep
  runs one codemod at a time; neither gave a single, persisted per-rule QA view
  across both tiers. Isolating each rule pinpoints which rule owns a regression
  and keeps the GTX registry honest. The upgrade characterization lives here as
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
