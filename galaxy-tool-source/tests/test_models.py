"""Tests for the per-version generated models and profile-aware binding."""

import types
from pathlib import Path

import pytest

from galaxy_tool_source.binding import load_tool
from galaxy_tool_source.models.any_tool import AnyTool
from galaxy_tool_source.models.registry import (
    model_module,
    tool_class,
    version_to_module,
)
from galaxy_tool_source.profiles import available_profiles, latest_profile


@pytest.mark.parametrize("version", available_profiles())
def test_every_version_package_exposes_a_tool(version: str) -> None:
    assert model_module(version).__name__.endswith(version_to_module(version))
    assert isinstance(tool_class(version), type)


def test_model_resolves_the_declared_profile(data_dir: Path) -> None:
    document = load_tool(data_dir / "minimal_tool.xml")  # profile 24.0
    assert ".v24_0." in type(document.model()).__module__


def test_model_version_override(data_dir: Path) -> None:
    document = load_tool(data_dir / "minimal_tool.xml")
    assert ".v26_0." in type(document.model(version="26.0")).__module__


def test_model_without_profile_uses_galaxy_default(data_dir: Path) -> None:
    # No profile= -> Galaxy's 16.01 default -> nearest vendored model (oldest, 16.10).
    document = load_tool(data_dir / "tool_no_profile.xml")
    oldest = version_to_module(available_profiles()[0])
    assert f".{oldest}." in type(document.model()).__module__


def test_tool_class_latest_matches_its_module() -> None:
    latest = latest_profile()
    assert tool_class(latest) is model_module(latest).Tool


def test_any_tool_is_a_union() -> None:
    assert isinstance(AnyTool, types.UnionType)
