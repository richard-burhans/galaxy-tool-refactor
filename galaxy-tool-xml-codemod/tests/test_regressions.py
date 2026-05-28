"""Replay retained regression fixtures through ``CANONICAL_CODEMODS``.

Every subdirectory under ``tests/data/regressions/`` is a tool that
``scripts/corpus_check.py codemod`` previously found non-idempotent,
post-validation-breaking, or crashing under a codemod sweep. This file
parametrises one case per fixture and asserts the same invariants the
sweep script checks — running every canonical codemod once must produce
the same byte-state as running them twice, and post-codemod validation
must still pass under the chosen profile (declared, else newest valid).

A new fixture lands automatically when ``corpus_check.py codemod``
retains it; no test edits required. Fixture provenance is recorded in
``tests/data/regressions/PROVENANCE.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from galaxy_tool_xml.binding import validate_tool
from lxml import etree

from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS
from galaxy_tool_xml_codemod.eligibility import corpus_test_profile
from galaxy_tool_xml_codemod.parse import parse_module

_REGRESSIONS_DIR = Path(__file__).parent / "data" / "regressions"


def _fixture_paths() -> list[Path]:
    """Return every fixture's ``tool.xml`` path, sorted for stable IDs."""
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
def test_canonical_codemods_are_idempotent_on_fixture(tool_path: Path) -> None:
    """Applying ``CANONICAL_CODEMODS`` twice must yield identical bytes."""
    module = parse_module(tool_path)
    for codemod_cls in CANONICAL_CODEMODS:
        codemod_cls().apply(module)
    once = etree.tostring(module.document.tree)
    for codemod_cls in CANONICAL_CODEMODS:
        codemod_cls().apply(module)
    twice = etree.tostring(module.document.tree)
    assert once == twice


@pytest.mark.parametrize(
    "tool_path",
    _fixture_paths(),
    ids=lambda path: path.parent.name,
)
def test_canonical_codemods_preserve_validity_on_fixture(tool_path: Path) -> None:
    """The canonical codemods do not break post-codemod validation on the fixture."""
    profile = corpus_test_profile(tool_path)
    if profile is None:
        pytest.skip("fixture is ineligible under the codemod-sweep policy")
    module = parse_module(tool_path)
    for codemod_cls in CANONICAL_CODEMODS:
        codemod_cls().apply(module)
    assert validate_tool(module.document, profile=profile).valid
