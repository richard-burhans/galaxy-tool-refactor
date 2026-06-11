"""Shared pytest fixtures for the codemod test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def data_dir() -> Path:
    """Directory holding tool-XML test fixtures."""
    return Path(__file__).parent / "data"


@pytest.fixture
def minimal_tool_path(data_dir: Path) -> Path:
    """Path to a minimal well-formed Galaxy tool XML fixture."""
    return data_dir / "minimal_tool.xml"


@pytest.fixture
def minimal_tool_bytes(minimal_tool_path: Path) -> bytes:
    """Raw bytes of the minimal tool XML fixture."""
    return minimal_tool_path.read_bytes()


@pytest.fixture
def tool_with_params_path(data_dir: Path) -> Path:
    """Path to a fixture containing three ``<param>`` elements at various depths."""
    return data_dir / "tool_with_params.xml"
