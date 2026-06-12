"""Freshness guard: the committed boundary-reference block == the generated output.

If the vendored behaviour-code catalogue or the auto-fix registry changes,
``docs/profile_boundaries.md`` must be regenerated
(``uv run python -m scripts.gen_profile_boundaries``) or this fails, naming
the command — the stop note points users at this doc, so it must always match
the shipped gate.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_codemod.boundaries import (
    BEGIN_MARKER,
    END_MARKER,
    render_boundary_reference,
)

_DOC = Path(__file__).resolve().parents[2] / "docs" / "profile_boundaries.md"


def test_boundary_reference_block_is_fresh() -> None:
    text = _DOC.read_text(encoding="utf-8")
    assert BEGIN_MARKER in text and END_MARKER in text, "boundary markers missing"
    begin = text.index(BEGIN_MARKER)
    end = text.index(END_MARKER) + len(END_MARKER)
    committed = text[begin:end]
    expected = f"{BEGIN_MARKER}\n{render_boundary_reference()}\n{END_MARKER}"
    assert committed == expected, (
        "docs/profile_boundaries.md reference is stale — regenerate with "
        "`uv run python -m scripts.gen_profile_boundaries`"
    )
