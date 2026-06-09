"""Freshness guard: the committed parity-table block == the generated output.

If a rule's ``planemo_linters`` / ``rulesets`` / ``summary`` / ``detect_only`` changes,
``docs/planemo_linter_parity.md`` must be regenerated
(``uv run python -m scripts.gen_planemo_parity``) or this fails, naming the command.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_refactor_registry.parity import (
    BEGIN_MARKER,
    END_MARKER,
    render_parity_table,
)

_DOC = Path(__file__).resolve().parents[2] / "docs" / "planemo_linter_parity.md"


def test_parity_table_block_is_fresh() -> None:
    text = _DOC.read_text(encoding="utf-8")
    assert BEGIN_MARKER in text and END_MARKER in text, "parity-table markers missing"
    begin = text.index(BEGIN_MARKER)
    end = text.index(END_MARKER) + len(END_MARKER)
    committed = text[begin:end]
    expected = f"{BEGIN_MARKER}\n{render_parity_table()}\n{END_MARKER}"
    assert committed == expected, (
        "docs/planemo_linter_parity.md GTR table is stale — regenerate with "
        "`uv run python -m scripts.gen_planemo_parity`"
    )
