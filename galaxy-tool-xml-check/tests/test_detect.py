"""Tests for the advisory-check registry and runner."""

from __future__ import annotations

from galaxy_tool_xml.binding import load_tool

from galaxy_tool_xml_check.detect import all_checks, detect_violations


def test_registry_has_twelve_checks_with_unique_codes() -> None:
    checks = all_checks()
    assert len(checks) == 12
    codes = [cls.meta.code for cls in checks]
    assert len(set(codes)) == 12
    assert all(code.startswith("IUC") for code in codes)


def test_registry_is_sorted_by_code() -> None:
    codes = [cls.meta.code for cls in all_checks()]
    assert codes == sorted(codes)


def test_every_check_is_detect_only() -> None:
    assert all(cls.meta.detect_only for cls in all_checks())


def test_detect_violations_sorted_by_line() -> None:
    # A near-empty tool trips many checks; results come back line-ordered.
    tool = b'<tool id="X" name="N" version="bad!"><inputs/></tool>'
    violations = detect_violations(load_tool(tool))
    lines = [violation.sourceline for violation in violations]
    assert lines == sorted(lines)
    assert violations  # several findings on a bare tool
