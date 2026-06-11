"""Architecture guard: no SyntaxWarnings (invalid escape sequences, etc.) in src/.

A non-raw string/docstring containing a regex escape like ``\\s`` emits a
``SyntaxWarning: invalid escape sequence`` at import time. It is harmless at runtime
but noisy (it surfaced on the first clean ``pip install`` of the published packages),
and the fix is trivial (raw-string the literal). This guard compiles every package's
``src/`` with ``SyntaxWarning`` promoted to an error, so a reintroduced escape fails CI
instead of leaking into a release.

The cross-package ``*/src`` sweep mirrors ``test_serializer_allowlist.py``.
"""

from __future__ import annotations

import warnings
from pathlib import Path

# The workspace root is two levels up (<root>/galaxy-tool-refactor-registry/tests/).
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _source_files() -> list[Path]:
    """Every hand-written ``src/`` module across the workspace packages.

    The generated per-version xsdata models (``models/v*/``, ``models/any_tool.py``)
    are excluded — they are not hand-written and not on the import path here.
    """
    files: list[Path] = []
    for src_dir in sorted(_WORKSPACE_ROOT.glob("*/src")):
        for module in sorted(src_dir.rglob("*.py")):
            parts = module.parts
            if "models" in parts and any(
                part.startswith("v") or part == "any_tool.py" for part in parts
            ):
                continue
            files.append(module)
    return files


def test_no_syntax_warnings_in_src() -> None:
    """Compiling every src/ module raises on any SyntaxWarning (e.g. ``\\s``).

    With ``SyntaxWarning`` promoted to an error, ``compile`` surfaces an invalid escape
    as a ``SyntaxError`` at the parse stage, so both are caught (a genuine SyntaxError
    in committed source should fail this guard too).
    """
    offenders: list[str] = []
    for module in _source_files():
        source = module.read_text(encoding="utf-8")
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            try:
                compile(source, str(module), "exec")
            except (SyntaxWarning, SyntaxError) as problem:
                rel = module.relative_to(_WORKSPACE_ROOT).as_posix()
                offenders.append(f"{rel}: {type(problem).__name__}: {problem}")

    assert not offenders, (
        "SyntaxWarning/SyntaxError in src/ (raw-string the literal, e.g. r\"\\s\"):\n  "
        + "\n  ".join(offenders)
    )
