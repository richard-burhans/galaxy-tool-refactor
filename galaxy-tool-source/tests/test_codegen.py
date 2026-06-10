"""Slow codegen sweep: xsdata must regenerate a model from every vendored XSD.

Deselected by default (``-m 'not slow'``); run with ``uv run pytest -m slow``.
Each version is generated in its own subprocess via the production codegen path
(``galaxy_tool_source._codegen``), into a throwaway directory.
"""

import py_compile
from pathlib import Path

import pytest

from galaxy_tool_source._codegen import generate_one
from galaxy_tool_source.models.registry import version_to_module
from galaxy_tool_source.profiles import available_profiles


@pytest.mark.slow
@pytest.mark.parametrize("version", available_profiles())
def test_codegen_succeeds_for_every_vendored_xsd(version: str, tmp_path: Path) -> None:
    generate_one(version, models_dir=tmp_path)
    package = tmp_path / version_to_module(version)
    assert (package / "galaxy.py").is_file()
    assert (package / "__init__.py").is_file()
    for module in package.glob("*.py"):
        py_compile.compile(str(module), doraise=True)
