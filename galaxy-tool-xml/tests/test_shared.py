"""Unit tests for ``scripts/_shared.py`` corpus-discovery helpers.

``is_deprecated_path`` and ``iter_tool_xmls`` are the single choke point
through which every corpus sweep (validate / fmt / codemod) and the
``measure`` queries discover tool XML, so the deprecated-directory
exclusion rule is worth covering in isolation rather than only through a
multi-minute full sweep.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts._shared import is_deprecated_path, iter_tool_xmls


@pytest.mark.parametrize(
    "path",
    [
        Path("corpus/tools-iuc/deprecated/tools/gatk2/base_recalibrator.xml"),
        Path("corpus/galaxy-toolshed/thanhlv/galru_deprecated/tool.xml"),
        Path("corpus/galaxy-toolshed/rayane_elm/deprecated_tool_p/x.xml"),
        Path("corpus/galaxy-toolshed/x/neat_genreads/utilities/deprecated/x.xml"),
        Path("deprecated/tools/x.xml"),  # repo-rooted (corpus_check) relative case
        Path("corpus/x/DEPRECATED/tool.xml"),  # case-insensitive
        Path("corpus/x/Deprecated_Tool/tool.xml"),  # case-insensitive variant
        Path("corpus/x/mydeprecation_notes/x.xml"),  # substring rule: 'deprecation'
    ],
)
def test_is_deprecated_path_excludes(path: Path) -> None:
    assert is_deprecated_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        Path("corpus/tools-iuc/tools/gatk2/base_recalibrator.xml"),
        Path("corpus/tools-iuc/tools/old/x.xml"),  # 'old' must not match
        Path("corpus/tools-iuc/tools/archive/x.xml"),  # 'archive' must not match
        # filename-only guard: file named *deprecated* under a live dir is kept
        Path("corpus/tools-iuc/tools/foo/deprecated_helper.xml"),
    ],
)
def test_is_deprecated_path_keeps(path: Path) -> None:
    assert is_deprecated_path(path) is False


def test_iter_tool_xmls_skips_deprecated_and_hg(tmp_path: Path) -> None:
    """Only the live tool is yielded; deprecated dirs and .hg/ are skipped."""
    live = tmp_path / "tools" / "foo" / "tool.xml"
    deprecated = tmp_path / "deprecated" / "tools" / "old_tool.xml"
    hg = tmp_path / ".hg" / "store" / "leftover.xml"
    for path in (live, deprecated, hg):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<tool/>", encoding="utf-8")

    found = sorted(iter_tool_xmls(tmp_path))

    assert found == [live]
