#!/usr/bin/env python3
"""Regenerate every per-version xsdata typed model from the vendored XSDs.

A maintainer task: run on the ``uv.lock``-pinned toolchain via
``uv run python scripts/regenerate.py``. Each vendored XSD is regenerated into
its own package under ``src/galaxy_tool_xml/models/`` (``v16_10`` … ``v26_0``),
together with ``any_tool.py``.

The generated packages are not committed — the hatchling build hook regenerates
them on every build and editable install. Run this only to refresh them by hand,
for instance after vendoring a new schema with ``scripts/fetch_schemas.py``.
"""

from __future__ import annotations

from galaxy_tool_xml._codegen import regenerate_all_models


def main() -> int:
    """Regenerate every per-version model package and ``any_tool.py``."""
    regenerate_all_models(force=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
