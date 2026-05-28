# Plan: galaxy-tool-xml-codemod

## Status

**Pre-alpha scaffold.** The full design lives in `docs/architecture.md`
(forked from `galaxy-tool-xml/docs/codemod-architecture.md`); this file
tracks the current milestone plan and the open questions, not the whole
vision.

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

### M1 — `Module` type and `parse_module`

- `Module` wraps a `ToolDocument` and exposes both the lxml tree and the
  typed model.
- `parse_module(source)` accepts a path, bytes, or an existing
  `ToolDocument` (signature TBD).
- Tests: parse one tool from the corpus and verify the wrapper carries
  both views and survives unchanged.

### M2 — Cursor primitives

- `Cursor` wraps an `lxml._Element` plus its typed-model class.
- Typed mutation primitives (see `docs/architecture.md` §Cursor API):
  - `set_attribute(name, value)` / `delete_attribute(name)`
  - `replace_with(other_cursor)`
  - `remove()` (mark element for deletion)
  - `add_child(other_cursor, *, index=None)`
- Mutations write the underlying lxml tree; the typed-model view
  regenerates on demand. The lxml tree remains the source of truth.

### M3 — Visitor base classes

- `Visitor` (read-only) and `Transformer` (mutating).
- Dispatch by typed-model class name: `visit_Param`, `visit_Conditional`, ...
- Watch the *per-XSD-type class names* issue (`docs/architecture.md`
  §Risks) — `When`-becomes-many-classes is intrinsic to the XSD.

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

### Step 1: `Module` dataclass (`src/galaxy_tool_xml_codemod/module.py`)

```python
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml.models.any_tool import AnyTool

from galaxy_tool_xml_codemod.cursor import Cursor


@dataclass
class Module:
    """A parsed Galaxy tool XML unit: lxml tree + typed model + cursor root."""

    _document: ToolDocument = field(repr=False)

    @property
    def document(self) -> ToolDocument:
        return self._document

    @cached_property
    def model(self) -> AnyTool:
        return self._document.model()

    @property
    def cursor(self) -> Cursor:
        return Cursor(self._document.root)
```

Notes:
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
- M2 adds mutation methods (`set_attribute`, `remove`, etc.).

### Step 3: `parse_module` function (`src/galaxy_tool_xml_codemod/parse.py`)

```python
from __future__ import annotations

from pathlib import Path

from galaxy_tool_xml.binding import load_tool, parse_tool
from galaxy_tool_xml.document import ToolDocument

from galaxy_tool_xml_codemod.module import Module


def parse_module(source: Path | bytes | ToolDocument, /) -> Module:
    """Parse a Galaxy tool XML source into a Module.

    Args:
        source: A filesystem path, raw XML bytes, or an existing ToolDocument.

    Returns:
        A Module wrapping the parsed tool.
    """
    if isinstance(source, Path):
        document = load_tool(source)
    elif isinstance(source, bytes):
        result = parse_tool(source)
        if result.document is None:
            raise ValueError("bytes did not parse as well-formed XML")
        document = result.document
    else:
        document = source
    return Module(document)
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
3. `parse_module(ToolDocument)` — pass an existing document, verify identity
   (`module.document is the_document`).
4. `module.model` is computed once — access twice, compare `id()`.
5. `module.cursor` is a fresh `Cursor` each time (not cached).

### M1 acceptance criteria

1. `uv sync` clean.
2. All three test suites green.
3. `ruff check galaxy-tool-xml-codemod/src` clean.
4. `mypy --config-file galaxy-tool-xml-codemod/pyproject.toml galaxy-tool-xml-codemod/src` clean.
5. M1 tests green per Step 5.
6. `parse_module` re-exported (importable) from `galaxy_tool_xml_codemod.parse`.

## Verification (M0 acceptance)

Run from the workspace root (`galaxy-tool-refactor/`):

1. `uv sync` succeeds; `galaxy-tool-xml` resolves via the workspace reference.
2. `uv run pytest galaxy-tool-xml-codemod/tests/` runs the smoke test green.
3. `uv run ruff check galaxy-tool-xml-codemod/src` is clean.
4. `uv run mypy --config-file galaxy-tool-xml-codemod/pyproject.toml galaxy-tool-xml-codemod/src` reports no issues.
5. The package imports without side effects; `__init__.py` exposes nothing yet.
