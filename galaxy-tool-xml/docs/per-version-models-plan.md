# Per-version xsdata models for galaxy-tool-xml

> **Status: IMPLEMENTED — historical design plan.** This describes the
> per-version model refactor as proposed; it has since shipped. The
> "Context" below is the *pre-refactor* state (a single model from the
> then-latest XSD, `galaxy-26.0`); the latest vendored profile is now
> `26.1` (28 XSDs). For the current state see `CLAUDE.md`, `README.md`,
> and `docs/decisions.md` §4 / §10. Retained for design rationale.

## Context

`galaxy-tool-xml` generates one xsdata typed-model package
(`galaxy_tool_xml.models`, file `models/galaxy.py`, ~11.7k lines) from **only the
latest** vendored XSD (`galaxy-26.0`). A tool of any profile is bound leniently
against that single latest-XSD model.

We want a **separate generated model package per vendored XSD version** (28,
Galaxy 16.10 → 26.1) so a future downstream project can **convert a tool XML
from one XSD version to the next** — it needs a faithful typed view of *each*
schema release. The library keeps **no serializer**: the converter mutates the
lxml tree; the per-version models are read-only views for understanding each
version.

## Approach

Generate a complete xsdata model package for **every** vendored XSD version
instead of only the latest. The 28 packages are **generated at build time and
not committed** — the build backend moves from `uv_build` to **hatchling** with a
custom build hook that runs the codegen for both wheel builds and editable
installs.

`ToolDocument.model()` becomes **profile-aware**: it resolves the tool's
`profile` to a vendored version and binds against that version's model, with an
optional `version=` override. Two registry helpers — `tool_class(version)` and
`model_module(version)` — give the downstream converter direct access to any
version's typed classes. `model()`'s return type is a generated `AnyTool` union
over all 28 `Tool` classes. `corrections.py` likewise checks a tool against its
own release's vocabulary.

A new `newest_valid_profile(tool)` reports the newest vendored profile a tool
still validates against — a primitive for the downstream converter.

Real-world confidence comes from a corpus sweep: a maintainer script runs the
full API over every tool in `galaxyproject/tools-iuc` and retains any tool that
crashes the library as a permanent regression fixture.

> **Public-API change.** With per-version models there is no single `Tool`, so
> the bare `from galaxy_tool_xml.models import Tool` is **removed** from the
> public API; the latest model class is `tool_class(latest_profile())`. The
> library is at 0.1.0 with no released consumers, so the API is corrected now
> rather than carried.

## Target layout

```
src/galaxy_tool_xml/
├── _codegen.py            NEW, hand-written — the codegen engine (no hatchling dep)
└── models/
    ├── __init__.py        REWRITE — package docstring only (matches the repo's
    │                      "__init__ exposes no re-exports" convention)
    ├── registry.py        NEW, hand-written, PUBLIC — version→model lookups
    ├── any_tool.py        GENERATED, gitignored — `AnyTool` union (type-only use)
    └── v16_10/ … v26_1/   GENERATED, gitignored — xsdata output, one pkg/version
hatch_build.py             NEW, repo root — thin hatchling hook (~20 lines)
scripts/corpus_check.py    NEW — real-world tools-iuc corpus sweep
tests/data/regressions/    NEW dir — real-world tools retained as regression fixtures
```

Version → package slug: `"v" + version.replace(".", "_")` (`26.1`→`v26_1`),
defined once as `version_to_module()` in `registry.py`.

## Implementation

### 1. Codegen engine — `src/galaxy_tool_xml/_codegen.py`

A package module, hand-written, importing only stdlib and `registry` at module
scope — **no hatchling, and no xsdata until the `__main__` path** — so
`regenerate.py` and the tests import it freely. It self-locates `schema/` and
`models/` via `__file__`.

- **Entry point** — `python -m galaxy_tool_xml._codegen <version> <output_root>`
  runs xsdata for one version *in that fresh process*: stages
  `galaxy-{version}.xsd` as `galaxy.xsd` in a tempdir, sets
  `GeneratorConfig.output.package = "galaxy_tool_xml.models." +
  version_to_module(version)` and `output.unnest_classes = True` (unconditional —
  required for Galaxy 24.2+, harmless older), `chdir`s to `output_root`, runs
  `ResourceTransformer`. xsdata is imported only here.
- `generate_one(version, *, output_root)` — runs that entry point in a fresh
  subprocess, with `PYTHONPATH` set to `src/` so it imports `galaxy_tool_xml`
  even at build time, before the package is installed. A fresh process per
  version is mandatory — xsdata caches its resolved output path within a process.
  `check=True`; stderr is surfaced on failure.
- `regenerate_all_models(*, force=False)` — **existence skip**: if every
  `models/v*/` package and `any_tool.py` exist and not `force`, return at once (a
  new vendored XSD → its dir missing → full rebuild; a clean CI checkout → all
  missing → full rebuild). Otherwise `rmtree` stale `models/v*/`, run
  `generate_one(v, output_root=src)` for all 28 versions in parallel via a
  `ThreadPoolExecutor` (threads block on subprocesses), then write
  `models/any_tool.py` (`AnyTool = v16_10…Tool | … | v26_1…Tool`).
- `clean_generated()` — `rmtree` `models/v*/` and remove `any_tool.py`.

`output_root` is `src/` for builds and `regenerate.py`; the codegen test points
it at a tempdir. The build hook, `regenerate.py`, and `test_codegen.py` all drive
this one module.

### 2. Build hook — `hatch_build.py` (repo root)

A ~20-line `CustomBuildHook(BuildHookInterface)`: `initialize` inserts
`<root>/src` on `sys.path`, imports `regenerate_all_models`, calls it; `clean`
calls `clean_generated`. Configured globally so it fires for the standard wheel
**and** editable installs — an editable `uv sync` then populates `models/` for
development (tests, mypy, IDE all need the generated files present).

### 3. `pyproject.toml`

- `[build-system]`: `requires = ["hatchling>=1.27", "xsdata[lxml]>=26.2"]`,
  `build-backend = "hatchling.build"`. `xsdata[lxml]` is now also a build
  dependency; it stays in `[project] dependencies` (the runtime parser needs it).
- `[tool.hatch.build.targets.wheel]`: `packages = ["src/galaxy_tool_xml"]`;
  `artifacts = ["src/galaxy_tool_xml/models/v*/", "src/galaxy_tool_xml/models/any_tool.py"]`
  (whitelists the gitignored generated files into the wheel). Default sdist
  inclusion suffices — `hatch_build.py`, `scripts/`, `schema/` are VCS-tracked;
  the hook regenerates models when a wheel is built from the sdist.
- `[tool.hatch.build.hooks.custom]` `path = "hatch_build.py"`.
- `xsdata[cli]` supplies the codegen toolchain (`ResourceTransformer` and its
  dependencies, e.g. `toposort`); it is required at build time (`[build-system]`)
  and kept in the dev group for `regenerate.py` and the codegen test.
- Narrow the lint excludes so hand-written code is checked, generated code exempt:
  ruff `extend-exclude = ["src/galaxy_tool_xml/models/v*", "src/galaxy_tool_xml/models/any_tool.py"]`;
  mypy `exclude = "src/galaxy_tool_xml/models/(v[0-9].*|any_tool\\.py)"`.

### 4. `models/registry.py` (new, hand-written, public)

dignified-python compliant; no import-time I/O; lazy + `@cache`d:

- `version_to_module(version) -> str` — the version→slug rule (single definition;
  `_codegen.py` imports it from here).
- `model_module(version) -> ModuleType` — `importlib.import_module(...)`.
- `tool_class(version) -> type` — fetches `Tool` from that module; an LBYL
  `isinstance(obj, type)` check (raising on failure) keeps the return a real
  `type` and satisfies strict mypy's `warn_return_any`.

Imports only `importlib`; independent of `profiles.py` and of any generated
module, so it is safe to import at build time.

### 5. `models/__init__.py` (rewrite)

Package docstring only — no re-exports, no `__all__` — matching
`galaxy_tool_xml/__init__.py`'s existing "exposes no re-exports" convention. The
sanctioned re-export exception is now the xsdata-generated `v*/__init__.py` files.

### 6. `document.py` — profile-aware `model()`

Drop `from galaxy_tool_xml.models import Tool`. Import `resolve_profile`
(`profiles.py`) and `tool_class` (`registry.py`); import `AnyTool` **only** under
`if TYPE_CHECKING:` from `models.any_tool` — `document.py` has `from __future__
import annotations`, so the annotation is a string and no generated module is
imported at runtime (binding stays lazy: one version's package, never all 28).

```python
def model(self, *, version: str | None = None) -> AnyTool:
    resolved = resolve_profile(version if version is not None else self.profile)
    return _xml_parser().from_bytes(etree.tostring(self.root), tool_class(resolved))
```

`resolve_profile` (default `on_missing="nearest"`) maps `None` → latest, matching
`validate_tool`. The keyword-only `version` override lets the converter bind a
tool against an arbitrary target version. The cached lenient `_xml_parser()` is
unchanged.

### 7. `corrections.py` — profile-aware

`_walk` already takes a model class. In `suggest_corrections`, resolve
`resolve_profile(document.profile)` and walk against `tool_class(resolved)`
instead of the latest `Tool` — an old tool is then checked against its own
release's vocabulary. `_vocabulary` is `@cache`d per class, so distinct
per-version classes cache correctly.

### 8. `binding.py` — `newest_valid_profile()` (new public function)

Lives in `binding.py` (it needs `validate_tool`; placing it in `profiles.py`
would create an import cycle).

```python
def newest_valid_profile(target: Source | ToolDocument) -> str | None:
    """Return the newest vendored profile whose XSD the tool satisfies, or None."""
```

Parse `target` once into a `ToolDocument`, then scan `available_profiles()`
newest→oldest, calling `validate_tool(document, profile=candidate)` per step and
returning the first (newest) profile that passes; `None` when no vendored profile
validates.

A linear scan, **not a binary search**: a tool's valid profiles are *not*
guaranteed contiguous — the corpus sweep finds real tools with gaps — so a
newest-first scan that stops at the first pass is the only correct approach (a
valid/invalid probe cannot tell "too old" from "too new", and binary search
would need that). The scan is O(1) when the tool validates at the latest profile
— the common case (90.2% of unique tools in the 2026-05-29 combined sweep;
see `docs/decisions.md` §10.5). The worst case is 28 validations, and
`compiled_schema` is `@cache`d so repeated calls across tools never recompile.

### 9. `scripts/regenerate.py`

Thin wrapper: `from galaxy_tool_xml._codegen import regenerate_all_models`; call
it with `force=True`. No `sys.path` manipulation — it runs in the project venv
where the package is installed editable.

### 10. Tests

- `tests/test_codegen.py` — keep the `slow` per-version sweep; call
  `_codegen.generate_one(version, output_root=tmp_path)` so each version is
  generated in its own subprocess into a tempdir, then `py_compile` the output —
  the real production path, with no pollution of `src/`.
- `tests/test_models.py` (new, default suite) — over `available_profiles()`:
  every `v*` package imports and exposes `Tool`; `model()` picks the right
  version (`profile="19.05"` → class `__module__` ends `v19_05`; no profile →
  latest); `model(version="24.0")` override works; `tool_class(latest_profile())`
  resolves; `AnyTool` is importable.
- `tests/test_corrections.py` — add a profile-aware case (an attribute new in
  24.x flags as unknown on a `profile="19.05"` tool, not on `profile="26.0"`).
- `tests/test_validate.py` — add `newest_valid_profile` cases (returns the
  expected ceiling; a tool valid nowhere returns `None`) and a `slow`
  per-fixture test asserting `newest_valid_profile` equals the newest `True` in
  the full validity vector. (Contiguity is *not* asserted — the corpus sweep
  showed real tools whose valid profiles have gaps.)
- `tests/test_regressions.py` (new) — replays every retained real-world tool in
  `tests/data/regressions/*/` through the shared invariant battery from
  `corpus_check.py`. Starts empty; the §11 corpus sweep populates it.

No `conftest.py` change needed — `_codegen` is a normal package module.

### 11. Real-world corpus testing — `scripts/corpus_check.py` (new)

A maintainer/QA script (not a CI test — the corpus is thousands of files and
needs network). It shallow-clones `galaxyproject/tools-iuc` (cached in a
gitignored `.local/corpus/`; `--corpus-dir` can point at an existing checkout), walks
`tools/**/*.xml`, keeps files whose root element is `<tool>`, and for each
exercises the public API end-to-end — `parse_tool` → `model()` → `validate_tool`
→ `newest_valid_profile` → `suggest_corrections` — catching any **unexpected
exception** (a library crash, as opposed to a properly *reported* syntax / macro
/ validation error). The cloned directory structure is preserved so macro
`<import>`s resolve against each tool's sibling `macros.xml`.

It prints a summary (tools scanned; crashes grouped by failure signature) and,
for each distinct failure, copies the offending tool plus the sibling macro files
it imports into `tests/data/regressions/<name>/` as a permanent, self-contained
fixture, recording provenance (tools-iuc path + commit) in
`tests/data/regressions/PROVENANCE.md`.

Broad exception catching is confined to this diagnostic script — its job is to
*surface* crashes — and does not relax the library's LBYL rules. The sweep runs
during development (Verification step 8): triage each crash, fix the library bug,
keep the fixture so the bug can never silently return.

### 12. Docs

- `README.md` — Public API block: remove `from galaxy_tool_xml.models import
  Tool`; add `from galaxy_tool_xml.models.any_tool import AnyTool`,
  `from galaxy_tool_xml.models.registry import model_module, tool_class`, and
  `newest_valid_profile` to the `binding` line; note `model()` is profile-aware
  with a `version=` override. Refresh the Architecture paragraph.
- `CLAUDE.md` — `models/` is now 28 per-version generated packages plus
  hand-written `__init__.py`/`registry.py`, generated at build time, not
  committed; binding is now profile-aware (today's "binding is not
  [profile-aware]" sentence becomes wrong); `corrections.py` is profile-aware;
  the sanctioned re-export exception is now the generated `v*/__init__.py` files;
  Commands/`regenerate.py` regenerates all 28; note the hatchling backend,
  `_codegen.py`, and the `corpus_check.py` QA script.

### 13. Git hygiene

`git rm` the committed `models/galaxy.py` and old generated `models/__init__.py`.
Add to `.gitignore`: `src/galaxy_tool_xml/models/v*/`,
`src/galaxy_tool_xml/models/any_tool.py`, and `.local/corpus/` (the cached tools-iuc
clone). Committed under `models/` afterward: only `__init__.py` and `registry.py`.

## Public API: before → after

| Before | After |
|--------|-------|
| `from galaxy_tool_xml.models import Tool` | *removed* |
| — | `from galaxy_tool_xml.models.any_tool import AnyTool` |
| — | `from galaxy_tool_xml.models.registry import model_module, tool_class` |
| — | `from galaxy_tool_xml.binding import newest_valid_profile` |
| `ToolDocument.model()` | `ToolDocument.model(*, version=None)` (profile-aware) |

## Files

| File | Change |
|------|--------|
| `hatch_build.py` | **New** — thin hatchling build hook |
| `src/galaxy_tool_xml/_codegen.py` | **New** — codegen engine (no hatchling dep) |
| `src/galaxy_tool_xml/models/registry.py` | **New** — `version_to_module`, `model_module`, `tool_class` |
| `src/galaxy_tool_xml/models/__init__.py` | **Rewrite** — docstring-only |
| `src/galaxy_tool_xml/models/galaxy.py` | **Delete** (`git rm`) |
| `src/galaxy_tool_xml/document.py` | Profile-aware `model(*, version=None) -> AnyTool` |
| `src/galaxy_tool_xml/corrections.py` | Profile-aware `_walk` |
| `src/galaxy_tool_xml/binding.py` | Add `newest_valid_profile()` |
| `scripts/regenerate.py` | Thin wrapper over `regenerate_all_models` |
| `scripts/corpus_check.py` | **New** — real-world tools-iuc corpus sweep (§11) |
| `pyproject.toml` | Backend → hatchling; hook/artifacts config; narrowed excludes |
| `tests/test_codegen.py` | Call `_codegen.generate_one` |
| `tests/test_models.py` | **New** — per-version import + `model()` selection |
| `tests/test_corrections.py` | Profile-aware vocabulary case |
| `tests/test_validate.py` | `newest_valid_profile` cases + validity-matrix test |
| `tests/test_regressions.py` | **New** — sweeps retained corpus failures |
| `tests/data/regressions/` | **New** dir — retained failing tools + `PROVENANCE.md` |
| `.gitignore`, `README.md`, `CLAUDE.md` | Update as in §12–§13 |

## Risks & assumptions

- **Fresh-clone dev depends on the build hook.** `uv sync` builds an editable
  wheel, runs the hook, generates all 28 packages — first run is slow (parallel,
  but still ~minutes). The existence-skip makes later syncs instant; if a sync
  ever leaves models missing, `uv run python scripts/regenerate.py` regenerates
  them.
- **CI must `uv sync` (or run `regenerate.py`) before lint/type/test** — `mypy`,
  `ruff`, `pytest` need `models/v*/` + `any_tool.py` present.
- **`xsdata[lxml]` must be in `[build-system] requires`** — the build env is
  isolated; omitting it breaks the hook.
- **`AnyTool` requires narrowing** — a union of 28 distinct `Tool` classes only
  exposes their common attribute subset until a caller narrows by version. This
  is the precise type the converter wants.
- **`newest_valid_profile` is a linear scan** — assumption-free. The corpus
  sweep confirmed validity is *not* contiguous (2.58% of real tools have gaps
  in the 2026-05-27 combined sweep; see `docs/decisions.md` §10.3), so a
  binary search would be wrong; the newest-first scan is correct regardless.
- **Footprint** — ~28 × ~300 KB ≈ 8–9 MB of generated Python; repo unaffected
  (gitignored), wheel roughly triples.
- Each xsdata run is its own subprocess (`python -m galaxy_tool_xml._codegen`) —
  sharing a process reintroduces xsdata's output-path caching bug. The subprocess
  gets `PYTHONPATH=src/` so it works at build time, before the package is
  installed.
- `corpus_check.py` needs network access to `github.com`.

## Verification

1. `rm -rf src/galaxy_tool_xml/models/v* src/galaxy_tool_xml/models/any_tool.py`,
   then `uv sync` → all 28 `models/v*/` packages + `any_tool.py` reappear.
2. `uv run pytest` → `test_models.py`, `test_corrections.py`, `test_validate.py`,
   `test_binding.py`, `test_regressions.py` pass.
3. `uv run pytest -m slow` → codegen sweep + validity-matrix test pass.
4. `uv run mypy src` (strict) and `uv run ruff check . && uv run ruff format
   --check .` → clean, including the now-checked `registry.py` / `_codegen.py`.
5. Manual REPL check: a tool with `profile="19.05"` →
   `type(doc.model()).__module__` ends `v19_05`; `doc.model(version="24.0")` →
   `v24_0`; `newest_valid_profile(tool)` returns the expected ceiling.
6. `uv run galaxy-tool-xml validate tests/data/representative_tool.xml` and
   `suggest …` → CLI still works.
7. `uv build` → `unzip -l dist/*.whl` shows all 28 `models/v*/` packages,
   `any_tool.py`, and the `schema/` XSDs; build a wheel from the sdist to confirm
   the hook runs there too.
8. `uv run python scripts/corpus_check.py` → sweep galaxyproject/tools-iuc;
   triage every crash, fix the library bug, and confirm the retained
   `tests/data/regressions/` fixtures then pass under `uv run pytest`.
