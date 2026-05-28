"""Smoke test: the package imports without side effects."""

from __future__ import annotations


def test_package_imports() -> None:
    """The package import succeeds and exposes its docstring."""
    import galaxy_tool_xml_codemod

    assert galaxy_tool_xml_codemod.__doc__
