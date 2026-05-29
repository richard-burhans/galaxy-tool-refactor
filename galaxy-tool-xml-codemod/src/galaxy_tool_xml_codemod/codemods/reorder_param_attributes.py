"""Codemod: rewrite ``<param>`` attribute order to the IUC convention.

Port of the fmt package's GTX002 rule, restated as a structural codemod.
Mutually-exclusive pairs (``min`` / ``truevalue``, ``max`` / ``falsevalue``,
``value`` / ``checked``) share a priority slot; in practice only one of
each pair appears on a given ``<param>``. Attributes outside the IUC
list sort alphabetically after the known ones — matches
``galaxy-language-server``'s ``IUCToolParamAttributeSorter``.
"""

from __future__ import annotations

from typing import ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods._attribute_ordering import canonical_order
from galaxy_tool_xml_codemod.cursor import Cursor

_IUC_PRIORITY: dict[str, int] = {
    "name": 0,
    "argument": 1,
    "type": 2,
    "format": 3,
    "min": 4,
    "truevalue": 4,
    "max": 5,
    "falsevalue": 5,
    "value": 6,
    "checked": 6,
    "optional": 7,
    "label": 8,
    "help": 9,
}


class ReorderParamAttributes(CodemodCommand):
    """Reorder every ``<param>`` element's attributes to the IUC convention."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX002",
        summary="Reorder every <param> element's attributes to the IUC convention.",
        since="0.0.1",
        cite="https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html",
    )

    def visit_Param(self, cursor: Cursor) -> None:
        cursor.reorder_attributes(
            canonical_order(cursor.attribute_names(), _IUC_PRIORITY)
        )
