"""Hatchling build hook: generate the per-version xsdata models before packaging.

Runs for both standard wheel builds and editable installs, so a fresh
``uv sync`` populates ``src/galaxy_tool_xml/models/`` for development. The codegen
itself lives in ``galaxy_tool_xml._codegen`` (which never imports hatchling);
this hook only wires it into the build.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Generate the per-version model packages before the build collects files."""

    def _ensure_src_on_path(self) -> None:
        """Put ``src/`` on ``sys.path`` — the package is not yet installed."""
        src = str(Path(self.root) / "src")
        if src not in sys.path:
            sys.path.insert(0, src)

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Run the per-version codegen before the wheel collects its files."""
        self._ensure_src_on_path()
        from galaxy_tool_xml._codegen import regenerate_all_models

        regenerate_all_models()

    def clean(self, versions: list[str]) -> None:
        """Remove the generated model packages on ``hatch build --clean``."""
        self._ensure_src_on_path()
        from galaxy_tool_xml._codegen import clean_generated

        clean_generated()
