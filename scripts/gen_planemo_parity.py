"""Regenerate the GTR coverage table in ``docs/planemo_linter_parity.md``.

Run from the workspace root::

    uv run python -m scripts.gen_planemo_parity

Replaces the table between the ``BEGIN``/``END`` markers with the registry-derived
table (``galaxy_tool_refactor_registry.parity.render_parity_table``). The prose
preamble and the HAVE/SKIP/n-a accounting are left untouched. A freshness test
(``test_planemo_parity_table.py``) keeps the committed block in sync.
"""

from __future__ import annotations

import pathlib

from galaxy_tool_refactor_registry.parity import (
    BEGIN_MARKER,
    END_MARKER,
    render_parity_table,
)

_DOC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "planemo_linter_parity.md"


def regenerate() -> None:
    """Rewrite the generated table block in the parity doc from rule metadata."""
    text = _DOC.read_text(encoding="utf-8")
    before, begin, rest = text.partition(BEGIN_MARKER)
    if not begin:
        raise SystemExit(f"BEGIN marker not found in {_DOC}")
    _, end, after = rest.partition(END_MARKER)
    if not end:
        raise SystemExit(f"END marker not found in {_DOC}")
    block = f"{BEGIN_MARKER}\n{render_parity_table()}\n{END_MARKER}"
    _DOC.write_text(f"{before}{block}{after}", encoding="utf-8")


if __name__ == "__main__":
    regenerate()
    print(f"regenerated {_DOC}")
