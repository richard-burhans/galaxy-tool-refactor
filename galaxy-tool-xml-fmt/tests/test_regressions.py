"""Replay retained regression fixtures through the formatter pipeline.

Every subdirectory under ``tests/data/regressions/`` is a tool that
``scripts/corpus_check.py`` found non-idempotent (or crashing) in a
corpus sweep. This test parametrises one case per fixture and asserts
``format(format(x)) == format(x)`` — the same invariant the sweep
script checks, replayed in the fast test suite so any future
regression catches at ``pytest`` time, not at the next corpus run.

A new fixture lands automatically when ``scripts/corpus_check.py``
retains it; no test edits required. Fixture provenance is recorded in
``tests/data/regressions/PROVENANCE.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from galaxy_tool_xml.binding import load_tool

from galaxy_tool_xml_fmt.format import format_tool_document

_REGRESSIONS_DIR = Path(__file__).parent / "data" / "regressions"


def _fixture_paths() -> list[Path]:
    """Return every fixture's ``tool.xml`` path, sorted for stable ids."""
    if not _REGRESSIONS_DIR.exists():
        return []
    return sorted(
        subdir / "tool.xml"
        for subdir in _REGRESSIONS_DIR.iterdir()
        if subdir.is_dir() and (subdir / "tool.xml").is_file()
    )


@pytest.mark.parametrize(
    "tool_path",
    _fixture_paths(),
    ids=lambda path: path.parent.name,
)
def test_regression_fixture_is_idempotent(tool_path: Path) -> None:
    """Formatting twice must yield identical bytes."""
    once = format_tool_document(load_tool(tool_path))
    twice = format_tool_document(load_tool(once))
    assert once == twice
