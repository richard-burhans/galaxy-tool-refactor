"""Shared pytest fixtures and configuration."""

from pathlib import Path

import pytest


@pytest.fixture
def data_dir() -> Path:
    """The directory holding the tool-XML test fixtures."""
    return Path(__file__).parent / "data"
