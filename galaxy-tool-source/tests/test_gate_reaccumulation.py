"""Unit tests for the gate re-accumulation measure (scripts/gate_reaccumulation.py).

Synthetic only — no network, no PR corpus. Like ``test_pr_impact``, the probe is
GTR002 (``ReorderParamAttributes``): a tool with misordered ``<param>``
attributes is non-canonical, and running it through the ``default`` formatter
produces a canonical sibling that the gate passes. That gives one "merged result
the gate would flag" and one "merged result the gate accepts" without depending
on any one rule's wording.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_refactor_registry.facade import run as facade_run
from galaxy_tool_refactor_registry.resolve import resolve_codes
from scripts._shared import is_tool_document
from scripts.gate_reaccumulation import (
    _ATTRIBUTE_ORDER_CODE,
    _attribute_order_only,
    _gate_candidate_codes,
    _measure_gate_reaccumulation,
    _variant_shares,
)

# A merged tool left non-canonical: <param> attributes in type/label/name order
# (the documented order is name first), so GTR002 still fires on the merged bytes.
_DIRTY = b"""<tool id="foo" name="Foo" version="1.0" profile="22.01">
    <inputs>
        <param type="text" label="A label" name="bar"/>
    </inputs>
</tool>
"""

# A macros file (not a <tool>): must be excluded from the denominator.
_MACROS = b"""<macros>
    <token name="@TOOL_VERSION@">1.0</token>
</macros>
"""


def _canonical(content: bytes, tmp_path: Path) -> bytes:
    """Return *content* run through the default formatter — the gate-clean form."""
    src = tmp_path / "_canon_src.xml"
    src.write_bytes(content)
    return facade_run(src, codes=resolve_codes(rulesets=["default"])).formatted


def _make_pr(repo_root: Path, number: int, relpath: str, content: bytes) -> None:
    """Write *content* as PR *number*'s merged (head) snapshot at *relpath*."""
    head_path = repo_root / f"pr-{number}" / "head" / relpath
    head_path.parent.mkdir(parents=True, exist_ok=True)
    head_path.write_bytes(content)


def _manifest_entry(number: int, relpath: str) -> dict[str, object]:
    return {
        "status": "ok",
        "number": number,
        "changed_xml_files": [relpath],
        "snapshot": {"head": {"present": True}},
    }


def test_is_tool_document_distinguishes_tool_from_macros(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_DIRTY)
    macros = tmp_path / "macros.xml"
    macros.write_bytes(_MACROS)

    assert is_tool_document(tool) is True
    assert is_tool_document(macros) is False


def test_dirty_merged_pr_is_flagged_clean_is_not(tmp_path: Path) -> None:
    _make_pr(tmp_path, 1, "tools/foo/foo.xml", _DIRTY)
    _make_pr(tmp_path, 2, "tools/bar/bar.xml", _canonical(_DIRTY, tmp_path))

    manifest = {
        "1": _manifest_entry(1, "tools/foo/foo.xml"),
        "2": _manifest_entry(2, "tools/bar/bar.xml"),
    }

    result = _measure_gate_reaccumulation(
        tmp_path, manifest, candidate_codes=_gate_candidate_codes()
    )

    assert result.pr_count == 2
    assert result.prs_with_tool == {1, 2}
    # PR 1 (dirty) is flagged by attribute order; PR 2 (canonical) is clean.
    assert _ATTRIBUTE_ORDER_CODE in result.per_pr_codes[1]
    assert result.per_pr_codes[2] == set()
    assert result.per_code_prs[_ATTRIBUTE_ORDER_CODE] == 1


def test_macros_only_pr_excluded_from_denominator(tmp_path: Path) -> None:
    _make_pr(tmp_path, 3, "tools/baz/macros.xml", _MACROS)

    manifest = {"3": _manifest_entry(3, "tools/baz/macros.xml")}

    result = _measure_gate_reaccumulation(
        tmp_path, manifest, candidate_codes=_gate_candidate_codes()
    )

    # The PR is swept but contributes no evaluable tool, so it is not in the
    # flagged/total denominator.
    assert result.pr_count == 1
    assert result.prs_with_tool == set()


def test_variant_shares_and_attribute_order_only(tmp_path: Path) -> None:
    _make_pr(tmp_path, 1, "tools/foo/foo.xml", _DIRTY)
    _make_pr(tmp_path, 2, "tools/bar/bar.xml", _canonical(_DIRTY, tmp_path))

    manifest = {
        "1": _manifest_entry(1, "tools/foo/foo.xml"),
        "2": _manifest_entry(2, "tools/bar/bar.xml"),
    }
    result = _measure_gate_reaccumulation(
        tmp_path, manifest, candidate_codes=_gate_candidate_codes()
    )

    shares = {share.name: share for share in _variant_shares(result)}
    full = next(s for name, s in shares.items() if name.startswith("full ("))
    minus = next(s for name, s in shares.items() if "minus attribute" in name)

    assert full.total == 2
    assert full.flagged == 1  # the dirty PR
    # Dropping GTR002 leaves the dirty PR clean, so the gate-minus-attr flags none.
    assert minus.flagged == 0
    # And that PR is flagged ONLY by attribute order.
    assert _attribute_order_only(result) == 1
