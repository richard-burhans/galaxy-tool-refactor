"""Tests for the advisory-check registry and runner."""

from __future__ import annotations

from galaxy_tool_source.binding import load_tool
from lxml import etree

from galaxy_tool_xml_check.detect import all_checks, detect_violations


def test_registry_has_sixty_six_checks_with_unique_codes() -> None:
    checks = all_checks()
    assert len(checks) == 69
    codes = [cls.meta.code for cls in checks]
    assert len(set(codes)) == 69
    assert all(code.startswith("GTR") for code in codes)


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


def test_detect_violations_does_not_mutate_the_input() -> None:
    """The advisory tier is read-only: the document tree is untouched.

    The cross-tier facade test exercises this path, but the contract belongs to
    this tier — pin it here too (audit ``§N5``, mirroring fmt's purity test).
    """
    document = load_tool(b'<tool id="X" name="N" version="bad!"><inputs/></tool>')
    before = etree.tostring(document.root)
    detect_violations(document)
    assert etree.tostring(document.root) == before
