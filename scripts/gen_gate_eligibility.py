"""Regenerate the per-rule eligibility table in ``docs/gate_eligibility.md``.

Run from the workspace root::

    uv run python -m scripts.gen_gate_eligibility

Replaces the table between the ``BEGIN``/``END`` markers with the registry-derived
classification (``galaxy_tool_refactor_registry.gate_eligibility``). The prose
preamble is left untouched. A freshness test (registry
``tests/test_gate_eligibility.py``) keeps the committed block in sync. Backs the
auto-fix-system plan §5 and ``docs/iuc_conference_questions.md`` §7.
"""

from __future__ import annotations

import pathlib

from galaxy_tool_refactor_registry.gate_eligibility import (
    BEGIN_MARKER,
    END_MARKER,
    render_eligibility_table,
)

_DOC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "gate_eligibility.md"


def regenerate() -> None:
    """Rewrite the generated table block from the gate-eligibility classification.

    The classification (``gate_eligibility._FIXABLE_BUCKETS``, a per-code dict) is
    keyed by ``RuleMeta.code``; the rule roster supplies the codes and the advisory
    set, not the bucket assignment.
    """
    text = _DOC.read_text(encoding="utf-8")
    before, begin, rest = text.partition(BEGIN_MARKER)
    if not begin:
        raise SystemExit(f"BEGIN marker not found in {_DOC}")
    _, end, after = rest.partition(END_MARKER)
    if not end:
        raise SystemExit(f"END marker not found in {_DOC}")
    block = f"{BEGIN_MARKER}\n{render_eligibility_table()}\n{END_MARKER}"
    _DOC.write_text(f"{before}{block}{after}", encoding="utf-8")


if __name__ == "__main__":
    regenerate()
    print(f"regenerated {_DOC}")
