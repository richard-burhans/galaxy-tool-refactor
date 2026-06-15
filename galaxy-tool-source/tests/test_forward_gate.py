"""Tests for the forward-enforcement gate (scripts/forward_gate.py, Half B).

Synthetic only. The probe is canonical indentation (GTR001), a gate-eligible rule:
a tool with ragged indentation is non-canonical and fails the gate; running it
through the gate's own rule set produces a clean tool that passes. Also pins the
invariant that the gate never runs the blocked attribute-order rules.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_refactor_registry.facade import run as facade_run
from scripts.forward_gate import (
    _select_tool_documents,
    check_files,
    gate_codes,
    main,
)

# Ragged indentation (2- and 8-space mix) is non-canonical, so GTR001 fires.
_DIRTY = b"""<tool id="t" name="T" version="1.0" profile="24.0">
  <description>d</description>
        <command><![CDATA[echo x]]></command>
  <inputs/>
</tool>
"""

_MACROS = b"""<macros>
    <token name="@TOOL_VERSION@">1.0</token>
</macros>
"""


def _write(directory: Path, name: str, content: bytes) -> Path:
    path = directory / name
    path.write_bytes(content)
    return path


def test_gate_codes_exclude_blocked_attribute_order() -> None:
    codes = gate_codes()
    assert "GTR001" in codes  # canonical indentation is gate-eligible
    # The contested attribute-order rules must never run in the gate.
    assert "GTR002" not in codes
    assert "GTR005" not in codes


def test_dirty_tool_fails_clean_tool_passes(tmp_path: Path) -> None:
    dirty = _write(tmp_path, "dirty.xml", _DIRTY)
    canonical = facade_run(dirty, codes=gate_codes()).formatted
    clean = _write(tmp_path, "clean.xml", canonical)

    dirty_findings = check_files([dirty], codes=gate_codes())
    clean_findings = check_files([clean], codes=gate_codes())

    assert dirty in dirty_findings
    assert "GTR001" in dirty_findings[dirty]
    assert clean_findings == {}


def test_macros_and_missing_files_are_not_checked(tmp_path: Path) -> None:
    macros = _write(tmp_path, "macros.xml", _MACROS)
    missing = tmp_path / "gone.xml"
    # macros.xml is not a <tool>; a non-existent path is dropped.
    assert _select_tool_documents([macros, missing]) == []


def test_main_exit_codes(tmp_path: Path) -> None:
    dirty = _write(tmp_path, "dirty.xml", _DIRTY)
    canonical = facade_run(dirty, codes=gate_codes()).formatted
    clean = _write(tmp_path, "clean.xml", canonical)

    assert main([str(clean)]) == 0
    assert main([str(dirty)]) == 1
    # No paths is a pass (nothing changed).
    assert main([]) == 0
