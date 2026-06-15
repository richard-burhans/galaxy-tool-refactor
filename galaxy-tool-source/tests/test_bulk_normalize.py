"""Tests for the bulk normalizer (scripts/bulk_normalize.py, Half A).

Synthetic only. A valid-but-ragged-indentation tool is non-canonical (GTR001);
the normalizer should report it in a dry run without writing, and in --write mode
rewrite it to canonical form while holding the validity-preservation and
idempotence invariants. Macros files are not counted.
"""

from __future__ import annotations

from pathlib import Path

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


def test_macros_only_repo_counts_no_tools(tmp_path: Path) -> None:
    macros_dir = tmp_path / "tools" / "bar"
    macros_dir.mkdir(parents=True)
    (macros_dir / "macros.xml").write_bytes(_MACROS)

    result = normalize_repo(tmp_path, codes=bulk_codes(), write=False)

    assert result.total_tools == 0
