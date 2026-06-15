"""Tests for the bulk normalizer (scripts/bulk_normalize.py, Half A).

Synthetic only. A valid-but-ragged-indentation tool is non-canonical (GTR001);
the normalizer should report it in a dry run without writing, and in --write mode
rewrite it to canonical form while holding the validity-preservation and
idempotence invariants. Macros files are not counted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.bulk_normalize import bulk_codes, normalize_repo

# Valid tool (validates at 24.0) with ragged 2-/8-space indentation, so GTR001 fires.
_DIRTY = b"""<tool id="t" name="T" version="1.0" profile="24.0">
  <description>desc</description>
        <command><![CDATA[echo x]]></command>
  <inputs>
    <param name="a" type="text"/>
  </inputs>
  <outputs>
        <data name="out" format="txt"/>
  </outputs>
</tool>
"""

_MACROS = b"""<macros>
    <token name="@TOOL_VERSION@">1.0</token>
</macros>
"""


def _tool_repo(tmp_path: Path, content: bytes = _DIRTY) -> Path:
    tool_dir = tmp_path / "tools" / "foo"
    tool_dir.mkdir(parents=True)
    (tool_dir / "foo.xml").write_bytes(content)
    return tmp_path


def test_bulk_codes_membership() -> None:
    codes = bulk_codes()
    assert "GTR001" in codes  # gate-eligible (indentation)
    assert "GTR004" in codes  # bulk-only (shorthand) is included in the bulk pass
    # The contested attribute-order rules are never in the bulk pass.
    assert "GTR002" not in codes
    assert "GTR005" not in codes


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    root = _tool_repo(tmp_path)
    tool = root / "tools" / "foo" / "foo.xml"
    before = tool.read_bytes()

    result = normalize_repo(root, codes=bulk_codes(), write=False)

    assert result.total_tools == 1
    assert result.normalized == 1
    assert result.written == 0
    assert tool.read_bytes() == before  # dry run wrote nothing


def test_write_normalizes_and_holds_invariants(tmp_path: Path) -> None:
    root = _tool_repo(tmp_path)
    tool = root / "tools" / "foo" / "foo.xml"
    before = tool.read_bytes()

    result = normalize_repo(root, codes=bulk_codes(), write=True)

    assert result.normalized == 1
    assert result.written == 1
    assert tool.read_bytes() != before  # rewritten to canonical
    assert result.validity_regressions == []
    assert result.idempotence_failures == []

    # Re-running over the now-canonical repo is a no-op.
    again = normalize_repo(root, codes=bulk_codes(), write=True)
    assert again.normalized == 0
    assert again.already_canonical == 1


def test_write_reverts_a_validity_regression(tmp_path: Path, monkeypatch) -> None:
    # Simulate a rule that would break validity (valid before, invalid after): the
    # tool must be reverted to its original, not left written. Guards the
    # safe-by-construction property the GTR036 fork-proof finding motivated.
    import scripts.bulk_normalize as bn

    root = _tool_repo(tmp_path)
    tool = root / "tools" / "foo" / "foo.xml"
    original = tool.read_bytes()

    calls = {"n": 0}

    class _FakeValidation:
        def __init__(self, valid: bool) -> None:
            self.valid = valid

    def _fake_validate(target, **kwargs):  # noqa: ANN001, ANN003 — test stub
        calls["n"] += 1
        return _FakeValidation(calls["n"] == 1)  # original valid, post-write invalid

    monkeypatch.setattr(bn, "validate_tool", _fake_validate)
    result = bn.normalize_repo(root, codes=bulk_codes(), write=True)

    assert result.validity_regressions == ["tools/foo/foo.xml"]
    assert result.reverted == 1
    assert result.written == 0
    assert tool.read_bytes() == original  # reverted, not left broken


def test_macros_only_repo_counts_no_tools(tmp_path: Path) -> None:
    macros_dir = tmp_path / "tools" / "bar"
    macros_dir.mkdir(parents=True)
    (macros_dir / "macros.xml").write_bytes(_MACROS)

    result = normalize_repo(tmp_path, codes=bulk_codes(), write=False)

    assert result.total_tools == 0


def test_write_reverts_when_the_post_write_recheck_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If the idempotence/validity re-check raises *after* the write, the unverified
    # bytes must never be left on disk (safe-by-construction): the original is
    # restored, the revert is counted, and the failure is retained for the report.
    import scripts.bulk_normalize as bn

    repo = _tool_repo(tmp_path)
    tool = repo / "tools" / "foo" / "foo.xml"
    original = tool.read_bytes()

    real_run = bn.facade_run
    calls = {"n": 0}

    def flaky_run(path: Path, *, codes: frozenset[str]):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] >= 2:  # the post-write idempotence re-check
            raise RuntimeError("boom")
        return real_run(path, codes=codes)

    monkeypatch.setattr(bn, "facade_run", flaky_run)

    result = bn.NormalizeResult()
    bn._normalize_one(
        tool, "tools/foo/foo.xml", result, codes=bn.bulk_codes(), write=True
    )

    assert tool.read_bytes() == original  # reverted, not left half-written
    assert result.reverted == 1
    assert result.errors  # the failure is retained, not silently swallowed
