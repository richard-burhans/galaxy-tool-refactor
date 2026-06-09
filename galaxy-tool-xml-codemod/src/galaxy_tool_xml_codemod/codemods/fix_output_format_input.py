"""Codemod: replace output ``format="input"`` with ``format_source`` (GTR015).

From profile 16.04 Galaxy disables ``format="input"`` on a tool output — the
behaviour was ill-defined (Galaxy's ``16_04_fix_output_format`` *must-fix* code).
The fix is to inherit the format from a specific input via
``format_source="<input name>"``.

Choosing *which* input is author intent in general, but it is unambiguous when the
tool has **exactly one data input addressable by an unqualified name** — a single
top-level ``<param type="data">``. This codemod auto-fixes only that case (109 of
the ~150 corpus tools with a ``format="input"`` output; see ``scripts/measure.py
output-format-input``); tools with zero, two-or-more, or a nested single data input
are left for the §23 upgrade warning to report. An output that already carries a
``format_source`` is also left alone — ``format="input"`` is inert there (Galaxy's
format_source branch wins at runtime), so the author's source must not be overwritten.

A runtime-gated fix (``runtime_fixes.py``): ``format="input"`` is XSD-valid, so this
does not change ``newest_valid_profile`` and cannot ride the ``UpgradeToLatest``
loop. ``detect`` is overridden (not the per-tag walk) because the fix needs
whole-tool context — the single data input — to choose ``format_source``; ``apply``
is still derived from ``detect``. See ``docs/decisions.md`` §24.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.codemods._runtime_gated import RuntimeGatedFix
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from lxml import etree

    from galaxy_tool_xml_codemod.module import Module


def _sole_top_level_data_input_name(root: etree._Element, /) -> str | None:
    """Return the name of the tool's single top-level ``<param type="data">``.

    ``None`` unless there is exactly one ``<param type="data">`` anywhere under
    ``<inputs>`` and it is a direct child of ``<inputs>`` (so an unqualified
    ``format_source`` reference resolves) with a non-empty ``name``.
    """
    inputs = root.find("inputs")
    if inputs is None:
        return None
    data_params = [p for p in inputs.iter("param") if p.get("type") == "data"]
    if len(data_params) != 1:
        return None
    sole = data_params[0]
    parent = sole.getparent()
    if parent is None or parent.tag != "inputs":
        return None
    name = sole.get("name")
    return name or None


def _swap_format_for_source(cursor: Cursor, source_name: str) -> Callable[[], None]:
    """Return a thunk that sets ``format_source`` and drops ``format`` on *cursor*."""

    def mutate() -> None:
        cursor.set_attribute("format_source", source_name)
        cursor.delete_attribute("format")

    return mutate


class FixOutputFormatInput(RuntimeGatedFix):
    """Rewrite output ``<data format="input">`` to ``format_source`` (single input)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR015",
        summary=(
            'Replace output <data format="input"> with format_source for a tool'
            " with a single top-level data input."
        ),
        since="0.0.1",
        cite="https://github.com/galaxyproject/galaxy/pull/1688",
        planemo_linters=frozenset({"OutputsFormatInput"}),
    )

    introduced_profile: ClassVar[str] = "16.04"

    def detect(self, module: Module, /) -> Iterator[Change]:
        root = module.document.root
        source_name = _sole_top_level_data_input_name(root)
        if source_name is None:
            return  # 0, 2+, or a nested single data input — needs author intent
        outputs = root.find("outputs")
        if outputs is None:
            return
        for data in outputs.iter("data"):
            if data.get("format") != "input":
                continue
            if data.get("format_source") is not None:
                # ``format="input"`` is already inert when a ``format_source`` is
                # present — Galaxy's format_source branch overrides it
                # (actions/__init__.py). Leave the author's existing source (which may
                # point at a collection or a different input) for the §23 warning.
                continue
            cursor = Cursor(data)
            yield Change(
                code=self.meta.code,
                sourceline=cursor.sourceline,
                xpath=cursor.xpath,
                message=(
                    'output format="input" replaced with'
                    f' format_source="{source_name}"'
                ),
                mutate=_swap_format_for_source(cursor, source_name),
            )
