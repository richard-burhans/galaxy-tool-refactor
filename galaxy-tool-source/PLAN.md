# galaxy-tool-source — Implementation Plan

> **Status: SUPERSEDED — historical document, retained for reference.**
>
> The plan below was the initial design from 2026-05-22, before implementation began. The
> project has since been fully implemented and has evolved beyond this plan in several
> material ways (per-version typed models replacing the single-latest model, `hatchling`
> build backend replacing `uv_build`, the corpus stats system, and the `valid_<profile>`
> validity columns, among others). **Do not implement against this file.** For the current
> state and the reasoning behind every divergence, see:
>
> - `CLAUDE.md` — current architecture and conventions
> - `README.md` — current public API
> - `docs/decisions.md` — assumptions, design decisions, and testing-derived data
> - `docs/per-version-models-plan.md` — the post-PLAN refactor that introduced per-version models
> - `docs/codemod-architecture.md` — the planned tier-2 codemod package this library feeds

---

## Context

The working directory `/home/rcb112/project/claude/galaxy-tool-source` is **empty** — no code,
not a git repo (it already carries the correct name; the earlier rename is done). There is
nothing to analyze, so the user chose to **plan a new project from scratch**.

**What it is.** A Python library + small CLI that is the **foundation for a separate,
`black`-like program** for Galaxy tool definition XML — the `<tool>` wrapper XML files that
define Galaxy bioinformatics tools. That downstream project will check a tool for conformance
to a rule set, autofix it, and reformat it. **This repository is the foundation only** — no
rules, no formatter/serializer, no downstream tool. It provides:

1. **Parse** Galaxy tool XML into a **mutable representation** that faithfully preserves
   everything a formatter needs — CDATA section contents, comments, attribute data and order,
   and the significant text inside elements like `<command>`/`<help>`.
2. A **typed read-only view** of a parsed tool, for convenient rule-checking.
3. **Profile-aware XSD validation**, with configurable **macro handling** so validation is
   accurate on real-world tools that use Galaxy macros.
4. **Near-miss typo suggestions** against the schema vocabulary (suggest only, no mutation).

### Design decisions confirmed with the user

| Decision | Choice |
|---|---|
| Naming | Repo directory + distribution + CLI command all **`galaxy-tool-source`**; import package **`galaxy_tool_source`** (standard hyphen→underscore convention) |
| Data-binding | **xsdata** — typed dataclasses generated from an XSD |
| Schema source | **Vendor Galaxy's official tool XSD** — one copy per Galaxy release |
| Profile-aware validation | XSD picked by the tool's `profile`; `on_missing` = `nearest` (default) / `exact` / `latest` |
| Profile scope | **Validation only** — typed models generated once from the latest XSD |
| Internal representation | **lxml tree = mutable source of truth; xsdata model = derived read-only view** |
| XML output | **None** — the library exposes the tree; callers serialize it themselves |
| **Macro handling** | `validate_tool(macro_handling=…)` spectrum **`off` → `skip` → `strip` → `expand`**, default **`expand`** (matches Galaxy: validate the post-expansion tool) |
| **Macro expansion** | Galaxy's own `galaxy.util.xml_macros` — `galaxy-util` is a **runtime dependency**, isolated behind one adapter module (`macros.py`) |
| **Version comparison** | **`packaging.version.Version`** — no hand-rolled version parser |
| Typo handling | `corrections.py` — `suggest_corrections()` returns near-miss name suggestions; **suggest only, no mutation** |
| Scope | **Library + CLI, foundation only** — no rules, no serializer, no downstream tool. `corrections.py` **is in v0.1.** |
| Coding standards | **dignified-python** (governs) + **optimized-python** (reference) — both vendored as skills |
| Packaging | **uv** project manager + **uv_build** build backend |

### Architecture

Parsing produces a **`ToolDocument`** wrapping a mutable **lxml tree** — the source of truth.
lxml preserves CDATA, comments, attribute order, and text exactly; xsdata dataclasses cannot
hold comments, so they cannot be the faithful representation. `ToolDocument.model()` returns a
derived **read-only** xsdata typed view, re-bound from the tree on demand. Preserving the
tree's fidelity is the **contract** owed to the downstream formatter project, which consumes a
`ToolDocument`, mutates the tree, and serializes it itself.

**Macro flow.** The Galaxy XSD is, by design, a **post-macro-expansion** schema — it does not
define `<expand>` and Galaxy validates only *after* expanding macros. So `validate_tool`
transforms the tool per its `macro_handling` mode (default `expand`) into a **throwaway copy**
and validates *that*. The `ToolDocument`'s tree is **never** mutated by validation — the
formatter's contract holds. Expansion reuses Galaxy's canonical implementation
(`galaxy.util.xml_macros`); all macro logic and the only `galaxy-util` import live in one
module, `macros.py`, so the coupling to Galaxy's internal API is localised.

Module map (representation → operations → schema → CLI → generated):
- `document.py` — the `ToolDocument` representation (records its `source_path`).
- `profiles.py` — resolves a tool's `profile` to one of the ~30 vendored per-release XSDs.
- `macros.py` — macro detection, stripping, and expansion; the sole `galaxy-util` adapter.
- `binding.py` — parse and validate entry points + result/error types.
- `corrections.py` — near-miss typo suggestions against the schema vocabulary.
- `cli.py` — the click CLI.
- `models/` — xsdata-generated typed classes.

The Galaxy tool XSD has evolved across releases, so validating an old tool against the newest
schema is misleading — hence per-release vendored XSDs and profile-based selection.

**Logging.** Library modules use `logging.getLogger(__name__)` and add no handler (silent by
default). `profiles.resolve_profile` logs at INFO when it falls back; `macros.py` logs
expansion problems; `scripts/fetch_schemas.py` logs skipped/failed branches. The CLI installs
a handler.

### Coding standards

Hand-written code follows **dignified-python** (vendored as a skill — step 2): LBYL over
`try/except`; exceptions only at the click error boundary (chained `from e`); `pathlib` with
explicit `encoding` for text I/O; no import-time side effects (`@cache` for module state);
absolute imports, **no re-exports, no `__all__`**; keyword-only args after the first.
minimaxir's **optimized-python** is also installed as a reference skill — on any conflict
**dignified-python governs**. The xsdata-generated `models/` is exempt (not hand-written); its
generated re-exporting `models/__init__.py` is the deliberate, sanctioned exception to the
no-re-exports rule.

### Key external facts (verified during planning)

- **xsdata** latest is **26.2** (Python 3.10+). Codegen is driven via
  `ResourceTransformer(config=GeneratorConfig()).process([uri])` — the constructor takes only
  `config` (no `print` argument) and `.process()` takes a list of `file://` URIs (no package
  argument); the package is set via `config.output.package`.
- Galaxy's tool XSD is at `lib/galaxy/tool_util/xsd/galaxy.xsd`; **releases before ~`20.09`**
  used `lib/galaxy/tools/xsd/galaxy.xsd` (the old path is gone by `release_21.05`) — the fetch
  script tries the new path then the old.
- The XSD is self-contained (no `xs:import`/`xs:include`), has **no `targetNamespace`** (so
  Galaxy tool XML is namespace-free), root element **`tool`**, and uses **strict content
  models** (`xs:all`/`xs:choice` of named elements, no wildcards). It **does not define
  `<expand>`**; it defines `<macros>`/`<import>`/`<token>`/`<xml>`/`<macro>` (the *definition*
  side only). It is a **post-expansion** schema.
- Galaxy ships **`release_*` branches** (`release_13.01` … **`release_26.0`**, the current
  newest); the suffix matches the `profile` attribute value. Not every branch ships the XSD —
  `fetch_schemas.py` downloads whichever do.
- The GitHub REST endpoint `git/matching-refs/heads/release_` is current and not deprecated.
- Galaxy validates tools against the XSD **only after macro expansion**; the XSD is consumed
  solely by the linter (`tool_util/linters/xsd.py`) and the docs generator — never at tool
  runtime.
- **Macro expansion**: `galaxy.util.xml_macros.load_with_references(path) -> (ElementTree,
  imported_paths)` handles `<import>`, nested `<token>`, `<expand>`/`<macro>`/`<xml>`, and
  parameterised `<yield>` macros. It ships in the **`galaxy-util`** PyPI package (CalVer,
  currently `26.0`; light deps; **internal API**, not a stability-guaranteed surface). It is
  **path-based** — expanding an in-memory or mutated tree requires serialising it to a temp
  directory first.
- `galaxy-util` needs `lxml` for its XML code path but **does not declare it**, and `packaging`
  is only a transitive dependency — so this project declares **both `lxml` and `packaging`
  explicitly**.
- `uv init --lib --build-backend uv` writes a correct `[build-system]` `uv_build` pin and a
  `src/` layout. In-package data files under `src/<pkg>/` are included in the wheel by
  default — to be verified empirically (step 14 / Verification).

## Project structure

```
galaxy-tool-source/                         (repo root)
├── PLAN.md                              this file — the implementation plan
├── pyproject.toml  uv.lock  .python-version  .gitignore  README.md  CLAUDE.md  LICENSE
├── .claude/skills/
│   ├── dignified-python/                vendored coding-standard skill (step 2)
│   └── optimized-python/                minimaxir's conventions, wrapped as a skill (step 2)
├── scripts/
│   ├── fetch_schemas.py                 downloads release XSDs + writes manifest & PROVENANCE.md
│   └── regenerate.py                    re-runs xsdata against the latest vendored XSD
├── src/galaxy_tool_source/
│   ├── __init__.py                      minimal — no re-exports (dignified-python)
│   ├── py.typed
│   ├── schema/                          vendored XSDs — internal, downloaded once
│   │   ├── manifest.json                machine-readable registry, consumed by profiles.py
│   │   ├── PROVENANCE.md                human-readable: where each XSD came from and why
│   │   └── galaxy-<version>.xsd         one file per Galaxy release that ships the XSD (~30)
│   ├── models/                          GENERATED by xsdata from the LATEST XSD — never hand-edit
│   ├── profiles.py                      profile/version registry + XSD resolution
│   ├── document.py                      ToolDocument — the mutable representation
│   ├── macros.py                        macro detect/strip/expand; sole galaxy-util adapter
│   ├── binding.py                       parse + validate entry points + result/error types
│   ├── corrections.py                   near-miss typo suggestions (suggest only)
│   └── cli.py                           click CLI
└── tests/
    ├── conftest.py  data/               fixtures (see step 13)
    ├── test_profiles.py  test_binding.py  test_macros.py  test_validate.py
    ├── test_corrections.py  test_cli.py
    └── test_codegen.py                  slow: xsdata codegen sweep over every vendored XSD
```

## Implementation steps

### 1. Initialize the project with uv

- The working directory is already named `galaxy-tool-source`; all steps run inside it.
- `uv init --lib --build-backend uv --name galaxy-tool-source` — scaffolds `pyproject.toml`,
  `src/` layout, `.python-version`, `.gitignore`, `README.md`, and a git repo with a correct
  `uv_build` pin. Distribution `galaxy-tool-source`; import package `galaxy_tool_source` at
  `src/galaxy_tool_source/`.
- Flesh out `README.md`: short description, a minimal usage example
  (`from galaxy_tool_source.binding import load_tool, validate_tool`), and an explicit
  **Public API** list (see step 12).
- Add an MIT `LICENSE`; extend `.gitignore` with `.pytest_cache/`, `.mypy_cache/`,
  `.ruff_cache/`. **Do not** gitignore `models/` or `schema/` — both are committed.

### 2. Install the coding-standard skills

Vendor both skills under `.claude/skills/` so they travel with the repo. Commit both.

- **dignified-python** — copy the whole directory from `dagster-io/erk` via a sparse clone:
  ```sh
  git clone --depth 1 --filter=blob:none --sparse https://github.com/dagster-io/erk "$tmp"
  git -C "$tmp" sparse-checkout set .agents/skills/dignified-python
  mkdir -p .claude/skills && cp -r "$tmp/.agents/skills/dignified-python" .claude/skills/
  ```
- **optimized-python** — minimaxir's gist is plain markdown with no skill frontmatter, so
  *wrap* it: download the body from
  `https://gist.githubusercontent.com/minimaxir/10b780671ee5d695b4369b987413b38f/raw/`, then
  author `.claude/skills/optimized-python/SKILL.md` = a YAML frontmatter block (`name`,
  `description`) + the gist content verbatim.
- For each skill, record provenance (source URL, commit/revision SHA, retrieval date,
  license) in a `VENDORED.md` beside its `SKILL.md`. Verify each `SKILL.md`'s frontmatter
  matches Claude Code's skill format.

### 3. Configure `pyproject.toml`

```toml
[project]
name = "galaxy-tool-source"
version = "0.1.0"
description = "Foundation library for parsing, profile-aware validation, and typed inspection of Galaxy tool XML"
authors = [{ name = "Richard Burhans", email = "richard.burhans@gmail.com" }]
license = "MIT"
requires-python = ">=3.10"
dependencies = [
    "xsdata[lxml]>=26.2",
    "lxml>=5",            # declared explicitly: galaxy-util needs lxml but does not declare it
    "click>=8",
    "galaxy-util>=24,<27",# macro expansion (galaxy.util.xml_macros); internal API -> ranged pin
    "packaging>=23",      # version comparison; only a transitive dep of galaxy-util otherwise
]

[project.scripts]
galaxy-tool-source = "galaxy_tool_source.cli:main"

[dependency-groups]
dev = ["xsdata[cli]>=26.2", "pytest>=8", "ruff", "mypy"]

[build-system]
requires = ["uv_build>=..."]      # left as uv init generated it
build-backend = "uv_build"

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["slow: xsdata codegen sweep over every vendored XSD"]
addopts = "-m 'not slow'"          # the codegen sweep is deselected by default

[tool.ruff]
src = ["src"]
target-version = "py310"
extend-exclude = ["src/galaxy_tool_source/models"]   # generated code — don't lint/format

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "PTH"]   # incl. bugbear (B904) and use-pathlib

[tool.mypy]
files = ["src"]
strict = true
exclude = "src/galaxy_tool_source/models/"   # generated code — still imported for types
```

`lxml` is the representation, validator, and `recover=True` syntax-error collector; `click` is
the CLI library; `galaxy-util` supplies macro expansion; `packaging` compares versions. The
`galaxy-util` pin is a **range** (`>=24,<27`) because `galaxy.util` is Galaxy's internal
utility API, not a stability-guaranteed surface — widen it deliberately, not by accident. The
`xsdata[cli]` **dev** extra supplies the code-generation machinery. The generated `models/` is
excluded from ruff and mypy. **Codegen reproducibility** (Verification step 3) depends on the
exact xsdata version — that is pinned by the committed `uv.lock`, so regeneration is a
maintainer task run via `uv run` on the locked toolchain.

### 4. `scripts/fetch_schemas.py` — download the XSDs and document provenance

A **standalone maintenance script** (Python stdlib only — `urllib`, `json`, `argparse`,
`pathlib`, `logging`; runnable before `uv sync`). The vendored XSDs are **internal, permanent
assets** — committed, each normally downloaded once.

- **Default run** — *additive*: downloads `galaxy.xsd` for every Galaxy release **not already
  in the collection**, leaving existing files/commits/dates untouched.
- **`--force`** — re-downloads all release XSDs, refreshing every file, commit SHA, date, and
  the provenance document.

Each run:

1. List Galaxy release branches via `GET
   https://api.github.com/repos/galaxyproject/galaxy/git/matching-refs/heads/release_`
   (`?per_page=100`, following `Link: rel="next"`). Send a `User-Agent` header; honor
   `GITHUB_TOKEN` if set. **If the branch list cannot be retrieved** — network failure,
   non-200 response, or rate-limit exhaustion — **log a warning and fall back to the XSDs
   already vendored in `schema/`**: the run then downloads nothing, leaves `manifest.json`
   and `PROVENANCE.md` untouched, reports the existing collection, and exits **0**. **If the
   API is unreachable *and* `schema/` holds no XSDs** (a true first run with no network),
   exit with a **non-zero error** instead. This fallback applies to `--force` runs too — an
   unreachable API can never re-download, so it warns and keeps the existing collection.
2. Keep branches whose `<version>` matches `^\d+\.\d+$`; without `--force`, skip versions
   already in `manifest.json`.
3. Download `galaxy.xsd` from `raw.githubusercontent.com/galaxyproject/galaxy/<branch>/<path>`,
   trying `lib/galaxy/tool_util/xsd/galaxy.xsd` then `lib/galaxy/tools/xsd/galaxy.xsd`;
   releases with neither (predating the XSD) are skipped (logged).
4. Write each XSD to `src/galaxy_tool_source/schema/galaxy-<version>.xsd`, and update **both**:
   - `schema/manifest.json` — per-version `{version, release_branch, commit, path_in_repo,
     file, retrieved}` + a `latest` key.
   - `schema/PROVENANCE.md` — regenerated: a methodology preamble, a per-XSD table (version,
     branch, commit, repo path, source URL, retrieval date), and a **third-party attribution**
     note that the XSDs come from `galaxyproject/galaxy` under that project's license.

**Commit the XSDs, the manifest, and PROVENANCE.md.**

### 5. `scripts/regenerate.py` — generate the typed models (from the latest XSD)

A Python script driving **xsdata's code-generation API directly** (no subprocess/CLI). It
reads `latest` from `manifest.json`, copies that XSD into a temp dir as `galaxy.xsd` (a stable
name → the generated module is always `models/galaxy.py`, even when `latest` bumps), and runs
the generator. xsdata writes the package relative to cwd, so the script `chdir`s to `src/`.

```python
#!/usr/bin/env python3
"""Regenerate the xsdata typed models from the latest vendored Galaxy XSD."""
import json, os, shutil, sys, tempfile
from pathlib import Path

from xsdata.codegen.transformer import ResourceTransformer
from xsdata.models.config import GeneratorConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "src" / "galaxy_tool_source" / "schema"

def main() -> int:
    latest = json.loads((SCHEMA_DIR / "manifest.json").read_text(encoding="utf-8"))["latest"]
    config = GeneratorConfig()
    config.output.package = "galaxy_tool_source.models"
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "galaxy.xsd"           # stable name -> stable models/galaxy.py
        shutil.copy(SCHEMA_DIR / f"galaxy-{latest}.xsd", staged)
        os.chdir(REPO_ROOT / "src")                 # xsdata writes the package relative to cwd
        ResourceTransformer(config=config).process([staged.as_uri()])
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

Invoke with `uv run python scripts/regenerate.py`. Run once; **commit the generated
`models/`**. xsdata's generated `models/__init__.py` re-exports every class, so
`from galaxy_tool_source.models import Tool` is stable.

### 6. `profiles.py` — profile/version registry and XSD resolution

Pure-Python (lxml + `packaging`). Per dignified-python, no module-level I/O — all state behind
`@functools.cache` accessors. Version handling uses **`packaging.version.Version`** directly.

- `_manifest() -> dict` — `@cache`; loads `manifest.json` via
  `importlib.resources.files("galaxy_tool_source")` (`encoding="utf-8"`).
- `available_profiles() -> list[str]` / `latest_profile() -> str`.
- `resolve_profile(profile: str | None, *, on_missing="nearest") -> str` — `None` →
  Galaxy's 16.01 default → nearest vendored (16.10; revised 2026-06-01, see decisions §1.5);
  exact match → it. Otherwise (no exact match, **including a `profile` that
  `packaging.version.Version` cannot parse** — caught `InvalidVersion`) apply `on_missing`:
  `nearest` (largest vendored `Version` not newer than the profile; latest if newer than all
  or unparseable, oldest if older than all) / `exact` (raise `UnknownProfileError`) /
  `latest`. Only `exact` raises. Logs at INFO on any fallback.
- `compiled_schema(version) -> lxml.etree.XMLSchema` — `@cache`; builds/caches per version.
- `UnknownProfileError(Exception)`.

### 7. `document.py` — `ToolDocument`, the representation

The central type; wraps the parsed mutable lxml tree. **No serialization method** — exposing
the tree is the contract.

- Constructed by the parse functions (step 9) from a tree parsed with
  `etree.XMLParser(recover=True, strip_cdata=False)` — CDATA and comments preserved.
- `.tree` / `.root` — the mutable lxml ElementTree / root `<tool>` element (the source of
  truth; the downstream project mutates these).
- `.source_path -> Path | None` — the file the document was loaded from, or `None` for
  `bytes`/stream input. Used by `validate_tool` to resolve macro `<import>`s **after** the
  tree has been mutated (the original file no longer reflects the in-memory tree).
- `.profile -> str | None` — the `profile` attribute (a property; O(1)).
- `.model() -> Tool` — a **method** (it does work): binds the *current* tree to the xsdata
  `Tool` model with a lenient `ParserConfig` (`fail_on_unknown_properties=False`,
  `fail_on_unknown_attributes=False`) so any-profile tool binds against the latest-XSD model.
  Re-derived each call; callers may cache.

### 8. `macros.py` — macro detection, stripping, and expansion

The **only** module that imports `galaxy.util.xml_macros`, isolating the coupling to Galaxy's
internal API behind one adapter. Pure functions; no module-level I/O.

- `MacroError` — a dataclass (`message: str`, `source: str | None`); `str()` renders a
  one-line message. Carries failures from expansion (cycles, missing macro, unresolved
  `<import>`).
- `has_macros(root) -> bool` — `True` if the tree contains any `<expand>` descendant or a
  `<macros>` child. Drives the `skip` mode and the `macros_present` result flag.
- `strip_macros(tree) -> ElementTree` — returns a **deep copy** with every `<expand>` element
  and the `<macros>` block removed; the input tree is untouched.
- `expand_from_path(path) -> tuple[ElementTree | None, list[MacroError]]` — direct
  `load_with_references(path)`; `<import>`s resolve against the file's own directory.
- `expand_from_tree(root, *, source_dir: Path | None) -> tuple[ElementTree | None,
  list[MacroError]]` — serialises `root` to a temp directory, copies each `<import>`ed macro
  file (located via `xml_macros.imported_macro_paths`, resolved against `source_dir`) into
  that temp directory, then runs `load_with_references` on the temp file. With
  `source_dir=None` (in-memory input, no origin) external `<import>`s cannot be resolved —
  inline macros still expand; a `MacroError` records the limitation.

All `galaxy.util.xml_macros` exceptions are caught here and converted to `MacroError`; macros.py
never lets a Galaxy exception escape. The expanded/stripped tree is a **throwaway** used only
for validation — its loss of comments/whitespace (Galaxy's parser strips them) does not matter.

### 9. `binding.py` — parse + validate entry points, result/error types

Parsing and validation live together because validation parses first and both share the
`XmlError` type. `binding.py` imports `document.py`, `profiles.py`, and `macros.py` one-way —
no cycle.

**Result / error types** (dataclasses):

- `XmlError` — `line`, `column`, `message`; `str()` → `"<source>:<line>:<col>: <msg>"` (the
  `<source>` placeholder is the file path, or `<string>` for `bytes`/stream input). Used for
  lxml well-formedness and lxml XSD-validation errors alike.
- `ParseResult` — `document: ToolDocument | None`, `syntax_errors: list[XmlError]`,
  `well_formed` property.
- `ValidationResult` — `valid: bool` (true iff `validated` and no syntax/schema/macro errors),
  `validated: bool` (false when XSD validation did not run — skipped, or expansion failed, or
  no usable tree), `schema_version: str`, `declared_profile: str | None`,
  `macro_handling: str`, `macros_present: bool`, `syntax_errors: list[XmlError]`,
  `errors: list[XmlError]` (schema errors), `macro_errors: list[MacroError]`.
- `ToolXmlSyntaxError(Exception)` — carries `errors: list[XmlError]`; raised only by `load_tool`.

**Functions** — LBYL: result-returning functions are the preferred API and never raise on
malformed XML; `load_tool` is the strict variant. Wrap third-party errors with `from e`.

- `load_tool(source) -> ToolDocument` — strict: raises `ToolXmlSyntaxError` on malformed XML.
- `parse_tool(source) -> ParseResult` — lenient: collects *every* well-formedness error; still
  builds a `ToolDocument` from the recovered tree when usable.
- `validate_tool(target, *, profile=None, on_missing="nearest", macro_handling="expand") ->
  ValidationResult` — profile-aware XSD validation. `target` is a source **or** a
  `ToolDocument`. Steps: resolve the profile (arg → the tool's `profile` → latest) and
  `profiles.compiled_schema(...)`; set `macros_present` via `macros.has_macros`; apply
  `macro_handling` — `off` validates the tree as-is; `skip` skips XSD validation when macros
  are present (`validated=False`); `strip` validates `macros.strip_macros(...)`; `expand`
  validates the expanded tree (`expand_from_path` for a path target, else
  `expand_from_tree` with `source_dir` from `ToolDocument.source_path`). When macros are
  absent every mode reduces to plain validation. Reports syntax errors and macro errors in the
  result; raises `UnknownProfileError` only with `on_missing="exact"`.

**Parsing rules.** `source` is a path (`str`/`Path`), an open binary stream, or `bytes`; read
into `bytes` **once** and parsed once — never decoded to `str` first, so lxml honours the XML
encoding declaration. (dignified-python's "explicit `encoding`" rule governs *text* file reads
— the manifest — not XML, which is bytes.) Immediately after a `recover=True` parse, snapshot
`parser.error_log` into `list[XmlError]` **before** the parser or any schema validator is
touched (the error log is overwritten on reuse). If recovery yields no usable root, return a
result with `document=None`/`validated=False` and only `syntax_errors`.

### 10. `corrections.py` — near-miss typo suggestions

A dedicated module — **independent of `validate_tool`** — that flags likely misspellings
against the schema vocabulary. **Suggestion only; no mutation.** Depends on `document.py`,
`models`, and `binding.py` (to parse a source `target`) — all one-way.

- `Correction` — a dataclass: `line: int`, `element: str` (containing element's tag), `kind`
  (`"attribute"` | `"element"` | `"enum_value"`), `found: str`, `suggested: str`,
  `attribute: str | None` (set for `enum_value`). `str()` renders a "did you mean?" line.
- `suggest_corrections(target) -> list[Correction]` — `target` is a source or a
  `ToolDocument`. Walks the **un-expanded** tree; for each element checks attribute names,
  child-element names, and enumerated attribute values against the schema vocabulary for that
  element. An invalid name/value with a close match (`difflib.get_close_matches`, cutoff
  ≈ 0.8) yields a `Correction`.

**Vocabulary & element resolution.** The vocabulary comes from introspecting the
xsdata-generated `models/` (no XSD re-parsing). The mechanism — to be confirmed against the
actual generated `models/galaxy.py` once step 5 has run — is:

- *Model resolution is contextual.* The same tag (`param`, `option`, `data`) has different
  content under different parents, so there is **no flat tag→class registry**. Instead the
  walk descends the tree and the model classes **in lockstep** from the `Tool` root:
  `_resolve_model(parent_cls, child_tag)` inspects `dataclasses.fields(parent_cls)`, reads each
  field's xsdata metadata (`metadata["type"]` ∈ `Element`/`Attribute`/`Elements`/…,
  `metadata["name"]` = the XML name), and returns the matching child field's model class
  (unwrapping `list[X]`/`Optional[X]`, and handling compound `Elements` fields whose
  `metadata["choices"]` lists several element/type pairs).
- *Enum values.* xsdata renders `xs:enumeration` as a generated `Enum` class. For an attribute
  field, if its type (after unwrapping `Optional`/`list`) is an `enum.Enum` subclass, the
  legal values are `{m.value for m in cls}`; otherwise no enum check. Union-typed and boolean
  attributes are out of scope for enum checks in v0.1.
- *Macro skip-set.* Elements `expand`, `macros`, `import`, `token`, `macro`, `xml` are
  **skipped** — never flagged, never recursed into — so an un-expanded tool does not produce
  false positives on its macro constructs.

### 11. `cli.py` — the click CLI

A `click` command group `galaxy-tool-source`; installs a logging handler. Per dignified-python
each command is an **error boundary**: catch, `click.echo(..., err=True)`,
`raise SystemExit(1) from e`.

- `validate FILE... [--profile V] [--on-missing nearest|exact|latest]
  [--macro-handling off|skip|strip|expand]` — `validate_tool` per file (default
  `macro_handling=expand`); prints syntax/macro/schema errors, the schema version used, and
  whether validation was skipped; non-zero exit on any error or `UnknownProfileError`.
- `suggest FILE...` — `suggest_corrections` per file; prints each "did you mean?" line; exits
  non-zero if any file has suggestions (usable as a check).
- `profiles` — list vendored XSD versions, latest marked.
- `main` is the click group, the `[project.scripts]` entry point.

### 12. `__init__.py` — minimal; declared public API

Per dignified-python `__init__.py` holds at most a module docstring (no re-exports, no
`__all__`, no module-level computation). Because there is no `__all__`, the **public API is
declared in prose** in `README.md` and `CLAUDE.md` — the exact symbols the downstream
formatter may rely on; everything else is private and may change. Non-public helpers are
underscore-prefixed. The supported surface:

```
from galaxy_tool_source.binding import load_tool, parse_tool, validate_tool
from galaxy_tool_source.binding import ParseResult, ValidationResult, XmlError, ToolXmlSyntaxError
from galaxy_tool_source.document import ToolDocument
from galaxy_tool_source.macros import MacroError
from galaxy_tool_source.corrections import suggest_corrections, Correction
from galaxy_tool_source.profiles import available_profiles, latest_profile, UnknownProfileError
from galaxy_tool_source.models import Tool
```

The version lives only in `pyproject.toml` (read via `importlib.metadata` if needed).

### 13. Tests

Fixtures in `tests/data/`: `minimal_tool.xml` (valid, recent profile); `representative_tool.xml`
(common constructs, `<command>` with **CDATA**, an **XML comment**, recent profile);
`tool_no_profile.xml`; `tool_old_profile.xml` (early profile, e.g. `16.04`); `invalid_tool.xml`
(well-formed, schema-invalid); `malformed_tool.xml` (multiple syntax errors); `tool_with_typos.xml`
(misspelled attribute e.g. `defualt`, a misspelled tag, a bad enum value — typos chosen so the
*correct* forms exist in the latest-XSD vocabulary); `tool_with_macros.xml` (uses
`<macros><import>macros.xml</import></macros>` and `<expand>`) plus its sibling `macros.xml`;
`tool_macro_error.xml` (references an undefined macro).

- `test_profiles.py` — `resolve_profile` exact / `nearest` / `exact` (raises) / `latest`,
  including an unparseable profile; `available_profiles` / `latest_profile`.
- `test_binding.py` — `load_tool` → `ToolDocument`; **faithful representation**: parsing
  `representative_tool.xml` leaves the CDATA section and comment node intact in
  `ToolDocument.tree`; `.source_path` set for path input, `None` for `bytes`; `.model()` typed
  field access; `parse_tool` on `malformed_tool.xml` → `document` recovered/`None` with
  **multiple** `syntax_errors`; `load_tool` on it raises.
- `test_macros.py` — `has_macros`; `strip_macros` removes `<expand>`/`<macros>` and leaves the
  input untouched; `expand_from_path` on `tool_with_macros.xml` resolves the `<import>` and
  the `<expand>`; `expand_from_tree` round-trips a mutated tree; `tool_macro_error.xml` yields
  a `MacroError`.
- `test_validate.py` — declared profile selects the matching XSD (`schema_version` reflects
  it); no-profile tool → latest; `profile=`/`on_missing` modes; `invalid_tool.xml` reports
  schema errors; `validate_tool` accepts a mutated `ToolDocument`; each `macro_handling` mode
  on `tool_with_macros.xml` (`expand` → valid, `off` → spurious `<expand>` errors, `skip` →
  `validated=False`, `strip` → validated); `macros_present`/`validated` flags correct.
- `test_corrections.py` — `suggest_corrections` on `tool_with_typos.xml` returns `Correction`s
  for the misspelled attribute / tag / enum value; a clean tool yields none; a
  genuinely-unknown name yields none; macro elements in `tool_with_macros.xml` yield none.
- `test_cli.py` — `click.testing.CliRunner`: `validate` (valid / schema-invalid / malformed /
  `--on-missing exact` / `--macro-handling` variants), `suggest`, `profiles`; assert exit
  codes/output.
- `test_codegen.py` — **`slow`-marked, deselected by default.** Parametrized over **every**
  vendored XSD in `manifest.json`: runs xsdata's codegen API into a temp dir
  (`monkeypatch.chdir(tmp_path)`) and asserts generation succeeds and the output
  byte-compiles. `xfail` any *historical* version that genuinely cannot be generated, with a
  recorded reason; the **latest** XSD must never `xfail` (it is what `models/` ships from).
  Run via `uv run pytest -m slow`.

### 14. `CLAUDE.md` (the `/init` deliverable)

Prefixed with the required header. Concise; only non-discoverable things:

- **Commands**: `uv sync`; `uv run pytest`; single test
  `uv run pytest tests/test_binding.py::test_name`; codegen sweep `uv run pytest -m slow`;
  `uv run ruff check .`; `uv run ruff format .`; `uv run mypy src`;
  `uv run python scripts/fetch_schemas.py` (`--force` re-downloads all);
  `uv run python scripts/regenerate.py`; `uv run galaxy-tool-source validate <file>`;
  `uv run galaxy-tool-source suggest <file>`; `uv build`.
- **Naming**: repo directory, distribution, and CLI command are all `galaxy-tool-source`; the
  import package is `galaxy_tool_source`.
- **Architecture**: foundation for a separate `black`-like Galaxy tool linter/formatter — it
  has **no serializer**. `ToolDocument` (`document.py`) wraps a mutable lxml tree = the source
  of truth; `binding.py` parses/validates; `profiles.py` resolves the per-release XSD;
  `macros.py` handles macros and is the sole `galaxy-util` adapter; `corrections.py` suggests
  near-miss typo fixes; `models/` is an xsdata-generated read-only typed view via
  `ToolDocument.model()`. Public API is the prose-declared list in step 12.
- **Coding standards**: hand-written code follows **dignified-python**, vendored at
  `.claude/skills/dignified-python/`; `optimized-python` is also installed as a reference,
  with dignified-python governing conflicts.
- **Non-obvious conventions**:
  - The lxml tree is the source of truth; the typed `Tool` model is a derived read-only view.
  - Parsing uses `strip_cdata=False`: the tree faithfully preserves CDATA, comments, and
    attribute order. XML is parsed from `bytes`, never a decoded `str`. The library does not
    emit XML.
  - The Galaxy XSD is a **post-macro-expansion** schema; `validate_tool` therefore transforms
    the tool per `macro_handling` (default `expand`) into a throwaway copy and validates that
    — the `ToolDocument` tree is never mutated.
  - `galaxy.util` is Galaxy's *internal* API; all use of it is confined to `macros.py`, and
    `galaxy-util` is pinned to a version range.
  - `models/` is xsdata-generated — never hand-edit; regenerate via `scripts/regenerate.py`
    (excluded from ruff and mypy; its `__init__.py` re-export is the one sanctioned exception
    to the no-re-exports rule).
  - `schema/` holds vendored XSDs — downloaded once by `scripts/fetch_schemas.py`; re-running
    is additive, `--force` re-downloads.
  - Validation is profile-aware (per-release XSD); binding is not — one `Tool` model from the
    latest XSD, xsdata parser lenient on unknown elements/attributes.
  - `corrections.py` is **suggest-only** and independent of `validate_tool`; its vocabulary
    comes from introspecting the generated `models/`, with a macro skip-set.
  - Failure modes: syntax errors (`load_tool` raises; others return them), macro-expansion
    errors, and XSD validation errors. The XSD has no `targetNamespace`.

## Caveats & known limitations (v0.1)

- **No serialization** — the library exposes the mutable tree but does not emit XML.
- **Macro expansion needs filesystem access.** `macro_handling="expand"` resolves `<import>`
  relative to the tool's source directory; an in-memory `bytes`/stream input with no origin
  directory cannot resolve external `<import>`s (inline macros still expand; a `MacroError`
  records it). Validating a mutated `ToolDocument` serialises it to a temp directory first.
- **Schema-error line numbers in `expand`/`strip` modes refer to the transformed (expanded or
  stripped) document, not the original source file.** Only `macro_handling="off"` yields
  original-source line numbers. This is inherent to validating a post-transformation tree.
- **`strip` mode does not substitute `@TOKEN@` values** — a token left in a strictly-typed
  attribute can mis-validate; `expand` is the only fully-accurate mode.
- **`galaxy.util` is Galaxy's internal API**, not a stability-guaranteed surface — the
  coupling is confined to `macros.py`, `galaxy-util` is range-pinned, and the usage is
  covered by `test_macros.py`.
- **The typed `.model()` view is read-only** and groups heterogeneous children into separate
  typed lists (xsdata default), not document order — use `.tree` when order or mutation matters.
- **One typed model across all profiles** — `.model()` uses the latest-XSD model; elements
  removed in newer XSDs still parse (lenient config) but are absent from the model.
- **Typo suggestions use the latest schema's vocabulary** — a name valid only in an *older*
  profile could rarely be mis-flagged. Profile-exact vocabulary is a later refinement.
- **No-profile tools validate against `16.10`** — the nearest vendored XSD to Galaxy's
  `"16.01"` legacy default for a missing `profile` (revised 2026-06-01 to match Galaxy;
  was previously "latest". See `docs/decisions.md` §1.5).
- **Vendored XSDs are a point-in-time snapshot** (~30 files, committed and shipped in the
  wheel; provenance in `PROVENANCE.md`). `fetch_schemas.py` is additive.
- **CI is out of scope for v0.1** — no `.github/workflows`.

## Verification

1. `uv sync` — resolves and installs runtime + dev deps cleanly (incl. `galaxy-util`, `lxml`).
2. `uv run python scripts/fetch_schemas.py` — populates `schema/` with one XSD per release,
   `manifest.json`, and `PROVENANCE.md`; spot-check the newest matches the current Galaxy
   release (`~26.0`) and `PROVENANCE.md` lists every XSD with source.
3. `uv run python scripts/regenerate.py` — regenerating produces **no git diff** (run on the
   `uv.lock`-pinned toolchain; this is a maintainer check).
4. `uv run pytest` — default tests pass; `uv run pytest -m slow` — the codegen sweep generates
   models from **every** vendored XSD with no errors.
5. `uv run ruff check .` and `uv run mypy src` (`--strict`) — clean.
6. `uv run galaxy-tool-source profiles` — lists every vendored version, latest marked.
7. `uv run galaxy-tool-source validate tests/data/minimal_tool.xml` — exits 0, reports the schema
   version; `... invalid_tool.xml` — non-zero with schema errors; `... malformed_tool.xml` —
   non-zero listing every syntax error; `... tool_with_macros.xml` — exits 0 under the default
   `expand`, and `--macro-handling off` on the same file reports spurious `<expand>` errors;
   `... --profile 99.9 --on-missing exact tests/data/minimal_tool.xml` — non-zero "unknown
   profile".
8. `uv run galaxy-tool-source suggest tests/data/tool_with_typos.xml` — reports the misspelled
   attribute / tag / enum value with "did you mean?" suggestions and exits non-zero.
9. `uv build` — produces a wheel; `unzip -l dist/*.whl` confirms `models/` **and** the whole
   `schema/` directory are included. If `uv_build` excludes the data files, add the needed
   `[tool.uv.build-backend]` config and rebuild.

## Sources

- [dignified-python skill (dagster/erk)](https://github.com/dagster-io/erk/blob/master/.agents/skills/dignified-python/SKILL.md)
- [minimaxir Python conventions gist](https://gist.github.com/minimaxir/10b780671ee5d695b4369b987413b38f)
- [galaxy.xsd in galaxyproject/galaxy](https://github.com/galaxyproject/galaxy/blob/dev/lib/galaxy/tool_util/xsd/galaxy.xsd)
- [galaxy.util.xml_macros](https://github.com/galaxyproject/galaxy/blob/dev/lib/galaxy/util/xml_macros.py) · [galaxy-util on PyPI](https://pypi.org/project/galaxy-util/)
- [Galaxy Tool XML File docs](https://docs.galaxyproject.org/en/latest/dev/schema.html)
- [The uv build backend](https://docs.astral.sh/uv/concepts/build-backend/) · [xsdata on PyPI](https://pypi.org/project/xsdata/)
