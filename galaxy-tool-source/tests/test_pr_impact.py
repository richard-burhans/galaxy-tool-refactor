"""Unit tests for the PR-impact matching algorithm (scripts/pr_impact.py).

Synthetic only — no network, no PR corpus. The fixture exploits GTR002
(``ReorderParamAttributes``): a structural, always-applicable codemod whose
effect survives the cosmetic canonicalizer, so it is a clean probe for both the
detect ("would-have-flagged") and fix ("would-have-auto-fixed") metrics and for
the noise-cancellation guarantee.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.pr_impact import (
    _canonical_bytes,
    _detect_coincidences,
    _fix_coincidences,
    _iuc_fixable_codes,
    _measure_pr_impact,
    _pr_set_composition,
    _strict_codes,
)

# A param with attributes in non-canonical order (type/label/name) plus
# deliberately ragged indentation — both a structural defect (GTR002) and
# whitespace noise to prove the noise-cancellation property.
_BEFORE = b"""<tool id="foo" name="Foo" version="1.0" profile="22.01">
  <inputs>
        <param type="text" label="A label" name="bar"/>
  </inputs>
</tool>
"""

# The human "fix": the same tool with the param attributes in canonical order
# (name first). Indentation differs again, to show formatting is cancelled.
_HEAD_FIXED = b"""<tool id="foo" name="Foo" version="1.0" profile="22.01">
    <inputs>
      <param name="bar" type="text" label="A label"/>
    </inputs>
</tool>
"""

# A head that fixes nothing structural — only reindents (param order unchanged).
_HEAD_WHITESPACE_ONLY = b"""<tool id="foo" name="Foo" version="1.0" profile="22.01">
    <inputs>
        <param type="text" label="A label" name="bar"/>
    </inputs>
</tool>
"""


def _write(directory: Path, name: str, content: bytes) -> Path:
    path = directory / name
    path.write_bytes(content)
    return path


def test_detect_coincidence_attributes_the_fixed_code(tmp_path: Path) -> None:
    before = _write(tmp_path, "before.xml", _BEFORE)
    head = _write(tmp_path, "head.xml", _HEAD_FIXED)

    coincidences = _detect_coincidences(before, head, codes=_strict_codes())
    codes = {code for code, _msg in coincidences}

    # GTR002 fires on the misordered before and is gone once head reorders it.
    assert "GTR002" in codes
    # Advisory codes that fire on /tool in BOTH before and head (e.g. missing
    # <tests>/<help>) are present in both, so they are not "fixed" coincidences.
    assert "GTR025" not in codes


def test_fix_coincidence_attributes_exactly_one_code(tmp_path: Path) -> None:
    before = _write(tmp_path, "before.xml", _BEFORE)
    head = _write(tmp_path, "head.xml", _HEAD_FIXED)

    coincidences = _fix_coincidences(
        before, head, candidate_codes=list(_iuc_fixable_codes())
    )
    codes = {code for code, _kind, _b, _a in coincidences}

    # Only the attribute reorder coincides — cosmetic-only rules produce no hunk
    # in canonical space, so they never spuriously attribute.
    assert codes == {"GTR002"}
    code, kind, before_snippet, after_snippet = coincidences[0]
    assert kind in {"full_reproduce", "hunk_subset"}
    assert "bar" in after_snippet  # the reordered <param> line


def test_whitespace_only_change_yields_no_coincidence(tmp_path: Path) -> None:
    before = _write(tmp_path, "before.xml", _BEFORE)
    head = _write(tmp_path, "head.xml", _HEAD_WHITESPACE_ONLY)

    # Both canonicalize identically: the only difference was indentation.
    assert _canonical_bytes(before) == _canonical_bytes(head)
    assert (
        _fix_coincidences(before, head, candidate_codes=list(_iuc_fixable_codes()))
        == []
    )
    # And GTR002 still fires on both, so it is not a detect coincidence either.
    detected = _detect_coincidences(before, head, codes=_strict_codes())
    assert "GTR002" not in {code for code, _msg in detected}


def test_measure_pr_impact_over_synthetic_corpus(tmp_path: Path) -> None:
    relpath = "tools/foo/foo.xml"
    for ref, content in (("base", _BEFORE), ("first", _BEFORE), ("head", _HEAD_FIXED)):
        ref_dir = tmp_path / "pr-1" / ref / "tools" / "foo"
        ref_dir.mkdir(parents=True)
        (ref_dir / "foo.xml").write_bytes(content)

    manifest = {
        "1": {
            "status": "ok",
            "number": 1,
            "new_tool": False,
            "single_commit": False,
            "changed_xml_files": [relpath],
            "snapshot": {
                "base": {"present": True},
                "first": {"present": True},
                "head": {"present": True},
            },
        }
    }

    result = _measure_pr_impact(
        tmp_path,
        manifest,
        detect_codes=_strict_codes(),
        fix_codes=_iuc_fixable_codes(),
    )

    assert result.pr_count == 1
    assert result.prs_with_before["base"] == {1}
    assert result.prs_with_before["first"] == {1}
    # The fix coincidence is found from BOTH baselines (before == first here).
    assert result.prs_with_fix["base"] == {1}
    assert result.prs_with_fix["first"] == {1}
    assert result.per_code_fix[("base", "GTR002")] == 1
    assert result.per_code_fix[("first", "GTR002")] == 1


def test_single_commit_pr_skips_first_baseline(tmp_path: Path) -> None:
    relpath = "tools/foo/foo.xml"
    for ref, content in (("base", _BEFORE), ("head", _HEAD_FIXED)):
        ref_dir = tmp_path / "pr-2" / ref / "tools" / "foo"
        ref_dir.mkdir(parents=True)
        (ref_dir / "foo.xml").write_bytes(content)

    manifest = {
        "2": {
            "status": "ok",
            "number": 2,
            "new_tool": False,
            "single_commit": True,
            "changed_xml_files": [relpath],
            "snapshot": {
                "base": {"present": True},
                "first": {"present": True},
                "head": {"present": True},
            },
        }
    }

    result = _measure_pr_impact(
        tmp_path,
        manifest,
        detect_codes=_strict_codes(),
        fix_codes=_iuc_fixable_codes(),
    )

    assert result.prs_with_before["base"] == {2}
    # first == head on a single-commit PR → the first baseline is skipped.
    assert result.prs_with_before["first"] == set()


def test_pr_set_composition_tallies_qualifying_and_drops() -> None:
    manifest = {
        "1": {"status": "ok", "new_tool": False, "single_commit": False},
        "2": {"status": "ok", "new_tool": True, "single_commit": True},
        "3": {"status": "dropped", "drop_reason": "draft"},
        "4": {"status": "dropped", "drop_reason": "bot:planemo-autoupdate"},
        "5": {"status": "dropped", "drop_reason": "version_bump_only"},
        "6": {"status": "deferred"},
    }

    comp = _pr_set_composition(manifest)

    assert comp.scanned == 6
    assert comp.qualifying == 2
    assert comp.new_tool == 1
    assert comp.modify == 1
    assert comp.single_commit == 1
    # Bot drops are bucketed by the reason prefix (login stripped).
    assert comp.drop_reasons["bot"] == 1
    assert comp.drop_reasons["draft"] == 1
    assert comp.drop_reasons["version_bump_only"] == 1
    assert comp.other_status["deferred"] == 1


@pytest.mark.parametrize("missing_ref", ["base"])
def test_new_tool_pr_has_no_base_baseline(tmp_path: Path, missing_ref: str) -> None:
    relpath = "tools/foo/foo.xml"
    for ref, content in (("first", _BEFORE), ("head", _HEAD_FIXED)):
        ref_dir = tmp_path / "pr-3" / ref / "tools" / "foo"
        ref_dir.mkdir(parents=True)
        (ref_dir / "foo.xml").write_bytes(content)

    manifest = {
        "3": {
            "status": "ok",
            "number": 3,
            "new_tool": True,
            "single_commit": False,
            "changed_xml_files": [relpath],
            "snapshot": {
                missing_ref: {"present": False},
                "first": {"present": True},
                "head": {"present": True},
            },
        }
    }

    result = _measure_pr_impact(
        tmp_path,
        manifest,
        detect_codes=_strict_codes(),
        fix_codes=_iuc_fixable_codes(),
    )

    assert result.prs_with_before["base"] == set()
    assert result.prs_with_before["first"] == {3}
    assert result.per_code_fix[("first", "GTR002")] == 1
