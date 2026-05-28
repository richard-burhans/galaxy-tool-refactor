"""Regression tests over real-world tools retained from the corpus sweep.

``scripts/corpus_check.py`` copies any tool from the public Galaxy tool corpus
that crashes the library or violates a checked invariant into
``tests/data/regressions/<name>/tool.xml`` (with any macro files it imports).
Each retained tool is replayed here through the very same invariant battery —
every check must pass. This sweep is empty until the corpus check finds
something.
"""

from pathlib import Path

import pytest
from scripts.corpus_check import (
    check_immutable,
    check_macro_handling,
    check_model,
    check_newest_valid_profile,
    check_parse_load_agree,
    check_roundtrip,
    validity_vector,
)

from galaxy_tool_xml.binding import parse_tool

_RETAINED = sorted((Path(__file__).parent / "data" / "regressions").glob("*/tool.xml"))


@pytest.mark.parametrize("tool", _RETAINED, ids=lambda path: path.parent.name)
def test_retained_tool_holds_every_invariant(tool: Path) -> None:
    document = parse_tool(tool).document
    assert document is not None and document.root.tag == "tool"
    for category, detail in (
        check_immutable(document),
        check_roundtrip(document),
        check_model(document),
        check_parse_load_agree(tool),
        check_macro_handling(tool, document),
        check_newest_valid_profile(tool, validity_vector(tool)),
    ):
        assert category == "ok", f"{tool.parent.name}: {category} — {detail}"
