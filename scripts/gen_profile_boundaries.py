"""Regenerate the per-boundary reference in ``docs/profile_boundaries.md``.

Run from the workspace root::

    uv run python -m scripts.gen_profile_boundaries

Replaces the block between the ``BEGIN``/``END`` markers with the
catalogue-derived reference (``galaxy_tool_codemod.boundaries``), one section
per profile boundary and one entry per Galaxy behaviour code: what changes,
what the toolchain does about it (auto-fix, stop, or warn), Galaxy's verbatim
description, and the release link. The prose preamble is hand-written. A
freshness test (``test_profile_boundaries_doc.py``) keeps the committed block
in sync with the shipped gate.
"""

from __future__ import annotations

import pathlib

from galaxy_tool_codemod.boundaries import (
    BEGIN_MARKER,
    END_MARKER,
    render_boundary_reference,
)

_DOC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "profile_boundaries.md"


def regenerate() -> None:
    """Rewrite the generated reference block from the behaviour-code catalogue."""
    text = _DOC.read_text(encoding="utf-8")
    before, begin, rest = text.partition(BEGIN_MARKER)
    if not begin:
        raise SystemExit(f"BEGIN marker not found in {_DOC}")
    _, end, after = rest.partition(END_MARKER)
    if not end:
        raise SystemExit(f"END marker not found in {_DOC}")
    block = f"{BEGIN_MARKER}\n{render_boundary_reference()}\n{END_MARKER}"
    _DOC.write_text(f"{before}{block}{after}", encoding="utf-8")


if __name__ == "__main__":
    regenerate()
    print(f"regenerated {_DOC}")
