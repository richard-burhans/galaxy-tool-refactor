"""Version-to-model registry: locate the generated per-version typed model.

Every vendored XSD version has its own xsdata-generated model package under
``galaxy_tool_xml.models`` (``v16_10`` … ``v26_0``). This module resolves an
exact vendored version string to that package, or to its root ``Tool`` class.

Imports are lazy and cached, so importing this module performs no I/O and pulls
in no generated code; it depends only on the standard library, which also makes
it safe to import from the build hook before the package is installed.
"""

from __future__ import annotations

import importlib
from functools import cache
from types import ModuleType


def version_to_module(version: str) -> str:
    """Return the model sub-package name for an exact vendored ``version``.

    ``"26.0"`` becomes ``"v26_0"``. Every vendored version is ``MAJOR.MINOR``,
    so the mapping is unambiguous. The codegen engine derives the xsdata output
    package from this same rule.
    """
    return "v" + version.replace(".", "_")


@cache
def model_module(version: str) -> ModuleType:
    """Import and return the generated model package for a vendored ``version``."""
    return importlib.import_module(
        "galaxy_tool_xml.models." + version_to_module(version)
    )


@cache
def tool_class(version: str) -> type:
    """Return the root ``Tool`` dataclass of a vendored ``version``'s model."""
    tool = getattr(model_module(version), "Tool", None)
    if not isinstance(tool, type):
        raise TypeError(
            f"galaxy_tool_xml.models.{version_to_module(version)} "
            f"has no generated Tool class"
        )
    return tool
