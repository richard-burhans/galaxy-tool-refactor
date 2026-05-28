# Plan: galaxy-tool-xml-codemod

## Status

**M1–M3.5 shipped** (2026-05-28). M4 (matcher language) and M5
(Cheetah reference resolver) remain. fmt's CLI now consumes this
package's `CANONICAL_CODEMODS` tuple via an optional `[canonical]`
extra; fmt's library is cosmetic-only and does not depend on codemod.

The original architecture lives in `docs/architecture.md` (a working
copy forked from `galaxy-tool-xml/docs/codemod-architecture.md`); it
predates the M1–M3.5 implementation. Decisions adopted during
implementation are recorded in `docs/decisions.md`; this file tracks
milestone status and the open architectural questions still to be
answered.

## Foundation needed from galaxy-tool-xml

Per `docs/architecture.md` §"What galaxy-tool-xml should add":

1. **Macro file resolution** — given a `ToolDocument`, return every
   `Path` involved (tool + transitively-imported macros). Lets codemods
   touch the right files. **Not yet shipped.**
2. **Trivia contract documented** in `galaxy-tool-xml/README.md`
   (structure / attrs / order / comments / CDATA / text / encoding /
   `sourceline` survive; indentation / blank lines / quote style /
   empty-element shorthand / attribute spacing do not). **Partial.**
3. **Trivia contract pinned in tests** via
   `galaxy-tool-xml/scripts/corpus_check.py::check_roundtrip`. **Done.**
4. **Macro provenance per element** (which file / which macro defined
   it). Side table keyed by a stable locator. **Later — wait for a
   codemod that needs it.**

Items 1-2 are tracked in the parent repo. Until they land, this repo's
M1+ milestones use ad-hoc parent-repo internals.

## Milestone plan

### M0 — scaffold *(done)*

- `pyproject.toml`, `src/galaxy_tool_xml_codemod/`, `tests/`
- `galaxy-tool-xml` as a workspace dependency (all three tiers share a
  single uv workspace under `galaxy-tool-refactor/`)
- ruff / mypy / pytest configured the same as the other packages
- Smoke test importing the package — passing

### M1 — `Module` type and `parse_module` *(done — 2026-05-28)*

- `Module` (frozen dataclass) exposes the `ToolDocument`, a typed
  `model` (plain `@property` — re-binds on every access; see
  decisions.md §5), and a fresh `cursor`.
- `parse_module(Path | bytes | ToolDocument)` — strict on Path/bytes
  via `load_tool`; shares ToolDocument by reference.
- 14 tests under `tests/test_parse.py`, `tests/test_module.py`,
  `tests/test_cursor.py` (read-only navigation slice).

### M2 — Cursor primitives *(partial — 2026-05-28)*

Shipped:
- `set_attribute(name, value)`, `delete_attribute(name)`,
  `reorder_attributes(names)` (raises on non-permutation),
  `attribute_names()`.
- Read-only navigation: `tag`, `get_attribute`, `children` (filters
  Comment/PI nodes), `parent`.

Deferred to a later milestone (no current consumer):
- `replace_with(other_cursor)`, `remove()`,
  `add_child(other_cursor, *, index=None)`. Per decisions.md §6,
  Cursor still carries only the lxml element, not a typed-model class
  — per-context dispatch is deferred.

### M3 — Visitor base classes *(minimal slice done — 2026-05-28)*

Shipped:
- One `CodemodCommand` base class (no `Visitor`/`Transformer` split —
  decisions.md §6).
- Tag-PascalCase dispatch: `<param>` → `visit_Param`, `<change_format>`
  → `visit_ChangeFormat`. Per decisions.md §6, dispatch is by XML tag,
  not typed-model class.
- `apply(module)` walks the tree pre-order; `visit_X` returning
  `False` halts descent.
- Mutations apply immediately to the lxml tree.

Deferred (no current consumer):
- Atomicity via deep-copy snapshot. The CLI orchestrator and the
  corpus sweep apply codemods directly without a snapshot;
  introduce a Harness type when a real use case appears.
- Per-codemod macro-mode handling — the `MACRO_MODE` ClassVar was
  removed (decisions.md §8); re-introduce when a codemod that needs
  macro expansion / stripping lands together with a harness that
  honours it.
- Profile-drift warning — not implemented in the apply loop.

### M3.5 — Port structural fmt rules + canonical-set wiring *(done — 2026-05-28)*

The two structural rules previously in `galaxy-tool-xml-fmt` have
been ported as proper codemods (verb-noun naming, TDD):

- `codemods/reorder_param_attributes.py::ReorderParamAttributes`
  (was fmt GTX002). Lifts `_IUC_PRIORITY` verbatim.
- `codemods/reorder_tool_attributes.py::ReorderToolAttributes`
  (was fmt GTX005). Lifts `_TOOL_PRIORITY` verbatim.
- `canonical.py` exposes `CANONICAL_CODEMODS: tuple[type[CodemodCommand], ...]`.
  fmt's CLI consumes it as an **optional** dependency via the
  `[canonical]` extra; fmt's library is unaffected (see decisions.md
  §§9–10).
- `scripts/corpus_check.py` has a `codemod` subcommand that drives one
  codemod across the corpus, asserts idempotence (re-parsing bytes
  between passes) + post-codemod `validate_tool`, and retains
  failures as regression fixtures under
  `tests/data/regressions/<id>/tool.xml`. `tests/test_regressions.py`
  parametrises over those fixtures.

### M4 — Matcher language

- Predicate combinators on cursors: `Attr(name="format", value="bam")`,
  `HasChild(...)`, `MatchesXPath(...)`, etc.
- LibCST-matcher-shaped but not a drop-in.

### M5 — Cheetah reference resolver

- **Long pole** (`docs/architecture.md` §Risks: "Most interesting
  refactors cross the XML→Cheetah boundary"). Treat as a first-class
  subsystem of this repo, not an afterthought.
- M5 is gated on M1-M4 being usable end-to-end; first ship of v1 can
  cover XML-only refactors and grow into Cheetah later.

### Future — profile-upgrade codemods (deferred)

A second class of baked-in codemods will rewrite tool XML to conform to
a newer Galaxy profile (e.g. migrate constructs deprecated between
profile `21.05` and `26.01`). Opt-in (not part of `MANDATORY_CODEMODS`),
target-version-aware, likely grouped in `upgrades.py` alongside
`mandatory.py`. No implementation planned in M1–M5; mentioned here so
the package layout leaves room.

## Open questions — resolved

The following were open questions in the original design; decisions below.

### 1. `parse_module` signature

**Decision:** `parse_module(source: Path | bytes | ToolDocument) -> Module` — a
single positional argument with a union type. LBYL form: `isinstance` dispatch,
not overloading. Path → `load_tool`; bytes → `parse_tool`; `ToolDocument` → wrap
directly. This matches dignified-python (one clear call site per input form, no
overloads, no sentinel kwargs).

### 2. Macro mode contract

**Decision:** Class attribute on `CodemodCommand`, mirroring LibCST's
`DESCRIPTION`:

```python
class MyCodemod(CodemodCommand):
    MACRO_MODE: ClassVar[Literal["expand", "skip", "strip", "off"]] = "expand"
```

The harness reads `MACRO_MODE` before running the visitor and calls the
appropriate `macros.py` primitive. Authoring guide must document each mode
and which codemods need which. `"expand"` is the safe default for codemods
that need to see structure added by macros.

### 3. Cursor mutation API

**Decision:** Typed setter methods (honest about in-place mutation), not
`with_changes`. No return value sentinels — a visitor that removes its node
calls `cursor.remove()` and returns `False` to stop descent. Methods:

- `cursor.set_attribute(name, value)` / `cursor.delete_attribute(name)`
- `cursor.remove()` — removes from parent, returns `False` implicitly
- `cursor.replace_with_siblings(others)` — replaces this element with a sequence
- `cursor.add_child(other, *, index=None)` — inserts a child cursor

These ship in M2. M1 Cursor is read-only navigation only.

### 4. Profile-bump policy

**Decision:** After a codemod run, call `validate_tool(document)` at the tool's
declared profile. Failure emits a `logging.WARNING`, not an exception. Mode is
`warn` by default; CLI exposes `--on-profile-drift {warn,error,ignore}`. Surface
prominently in CLI `--help` and authoring guide.

### 5. Decisions log

Create `docs/decisions.md` when the first architectural decision lands (M1).
Mirror tier-1's §-numbering and date + reproducible-command conventions.

---

## M1 implementation plan — `Module` and `parse_module`

**Scope:** `Module` wrapper, `parse_module` entry point, read-only `Cursor`
navigation. No mutations — those are M2.

### Signature scope decision

`parse_module(source: Path | bytes | ToolDocument)` is intentionally
**narrower** than Tier 1's `Source = str | Path | bytes | BinaryIO`.
Reasons: dignified-python prefers one clear call site per input form;
mypy strict catches misuse; `BinaryIO` is unused — codemods don't
stream; `str`-as-path is awkward because the LBYL `isinstance` ladder
would have to disambiguate `str` (a path? raw XML?) from `bytes`.
Callers with a string path wrap it: `parse_module(Path(s))`.

### Step 1: `Module` dataclass (`src/galaxy_tool_xml_codemod/module.py`)

```python
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml.models.any_tool import AnyTool

from galaxy_tool_xml_codemod.cursor import Cursor


@dataclass(frozen=True)
class Module:
    """A parsed Galaxy tool XML unit: lxml tree + typed model + cursor root."""

    document: ToolDocument

    @cached_property
    def model(self) -> AnyTool:
        return self.document.model()

    @property
    def cursor(self) -> Cursor:
        return Cursor(self.document.root)
```

Notes:
- `document` is a public field — `Module` has no invariant to defend, so
  the getter-only `@property` indirection adds nothing.
- `frozen=True` because `Module` identity is stable for the life of a
  codemod run (the underlying lxml tree mutates; the wrapper does not
  get reassigned). Frozen also makes the dataclass hashable, useful for
  caches later.
- `model` is `@cached_property` (not `@property`) — xsdata binding is not free.
  This satisfies the dignified-python no-import-time-side-effects rule via
  `@cache`/`@cached_property` for module-level state, applied here at instance
  level.
- `cursor` is a plain `@property` — `Cursor` construction is O(1).
- No `tree` or `root` shortcut — callers go through `module.document.root`. YAGNI.

### Step 2: `Cursor` class (`src/galaxy_tool_xml_codemod/cursor.py`)

M1 scope: read-only navigation only.

```python
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree


@dataclass
class Cursor:
    """A position in the lxml element tree, with typed navigation."""

    _element: etree._Element = field(repr=False)

    @property
    def tag(self) -> str:
        return str(self._element.tag)

    def get_attribute(self, name: str, /) -> str | None:
        return self._element.get(name)

    def children(self) -> list[Cursor]:
        return [Cursor(child) for child in self._element]

    def parent(self) -> Cursor | None:
        parent = self._element.getparent()
        return Cursor(parent) if parent is not None else None
```

Notes:
- `_element` is private — callers use cursor methods, not raw lxml.
- M2 adds mutation methods (`set_attribute`, `remove`, etc.) and a
  second field carrying the typed-model class for the element
  (resolved via `tool_class(version)` from Tier 1 plus the parent
  profile). M1 callers never see typed-class info, so adding the field
  later does not break M1's API.

### Step 3: `parse_module` function (`src/galaxy_tool_xml_codemod/parse.py`)

```python
from __future__ import annotations

from pathlib import Path

from galaxy_tool_xml.binding import load_tool
from galaxy_tool_xml.document import ToolDocument

from galaxy_tool_xml_codemod.module import Module


def parse_module(source: Path | bytes | ToolDocument, /) -> Module:
    """Parse a Galaxy tool XML source into a Module.

    Args:
        source: A filesystem path, raw XML bytes, or an existing ToolDocument.

    Returns:
        A Module wrapping the parsed tool. For Path / bytes input, raises
        ``ToolXmlSyntaxError`` on any well-formedness error (delegates to
        ``load_tool`` — symmetric strict semantics across input forms). For
        ``ToolDocument`` input, wraps **by reference** — deep-copy atomicity
        is the harness's job (M2+), not the parser's.
    """
    if isinstance(source, ToolDocument):
        return Module(source)
    return Module(load_tool(source))
```

### Step 4: Public re-exports (`src/galaxy_tool_xml_codemod/__init__.py`)

Following dignified-python (no `__all__`, no re-exports), leave `__init__.py`
empty or with a module docstring only. Callers import directly:

```python
from galaxy_tool_xml_codemod.parse import parse_module
from galaxy_tool_xml_codemod.module import Module
from galaxy_tool_xml_codemod.cursor import Cursor
```

### Step 5: Tests (`tests/test_module.py`)

Minimal M1 acceptance tests:

1. `parse_module(path)` — load a tool from the corpus data dir, verify
   `module.cursor.tag == "tool"` and `module.model` is an `AnyTool`.
2. `parse_module(bytes)` — pass raw XML bytes, same assertions.
3. `parse_module(ToolDocument)` — pass an existing document, verify
   identity (`module.document is the_document`) — pins the
   share-not-copy contract.
4. `module.model` is computed once — `assert module.model is
   module.model` (identity, not `id()`).
5. `module.cursor` returns cursors that point at the same element:
   `c1._element is c2._element`. The cursor object identity itself is
   not part of the contract.
6. **Negative case:** `parse_module(b"<tool")` (malformed bytes) raises
   `ToolXmlSyntaxError`. Pins the strict-bytes decision.

### M1 acceptance criteria

1. `uv sync` clean.
2. All three test suites green.
3. `ruff check galaxy-tool-xml-codemod/src` clean.
4. `mypy --config-file galaxy-tool-xml-codemod/pyproject.toml galaxy-tool-xml-codemod/src` clean.
5. M1 tests green per Step 5 (six cases).
6. `parse_module` re-exported (importable) from `galaxy_tool_xml_codemod.parse`.
7. `docs/decisions.md` exists with four entries seeded (signature
   scope, strict bytes, share-not-copy, frozen Module with public
   `document` field).

## Verification (M0 acceptance)

Run from the workspace root (`galaxy-tool-refactor/`):

1. `uv sync` succeeds; `galaxy-tool-xml` resolves via the workspace reference.
2. `uv run pytest galaxy-tool-xml-codemod/tests/` runs the smoke test green.
3. `uv run ruff check galaxy-tool-xml-codemod/src` is clean.
4. `uv run mypy --config-file galaxy-tool-xml-codemod/pyproject.toml galaxy-tool-xml-codemod/src` reports no issues.
5. The package imports without side effects; `__init__.py` exposes nothing yet.
