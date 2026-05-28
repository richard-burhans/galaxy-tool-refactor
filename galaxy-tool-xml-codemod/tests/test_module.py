"""Tests for the ``Module`` wrapper dataclass."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from galaxy_tool_xml.binding import load_tool
from galaxy_tool_xml.models.any_tool import AnyTool

from galaxy_tool_xml_codemod.cursor import Cursor
from galaxy_tool_xml_codemod.module import Module


def test_module_exposes_underlying_document(minimal_tool_path: Path) -> None:
    """``module.document`` returns the wrapped ``ToolDocument`` by reference."""
    document = load_tool(minimal_tool_path)
    module = Module(document)
    assert module.document is document


def test_module_model_reflects_current_tree(minimal_tool_path: Path) -> None:
    """``module.model`` re-binds against the live tree on every access.

    A previous design cached the model with ``@cached_property``, which
    silently returned stale data after mutations. The cache was dropped
    to avoid the footgun; this test pins the no-cache contract.
    """
    module = Module(load_tool(minimal_tool_path))
    initial_id = module.model.id
    assert isinstance(module.model, AnyTool)
    module.cursor.set_attribute("id", "renamed")
    assert module.model.id == "renamed"
    assert module.model.id != initial_id


def test_module_cursor_points_at_root(minimal_tool_path: Path) -> None:
    """Two ``module.cursor`` accesses yield cursors at the same root element."""
    module = Module(load_tool(minimal_tool_path))
    first = module.cursor
    second = module.cursor
    assert isinstance(first, Cursor)
    assert first._element is second._element
    assert first.tag == "tool"


def test_module_is_frozen(minimal_tool_path: Path) -> None:
    """``Module`` is a frozen dataclass — reassigning ``document`` raises."""
    module = Module(load_tool(minimal_tool_path))
    with pytest.raises(FrozenInstanceError):
        module.document = load_tool(minimal_tool_path)  # type: ignore[misc]
