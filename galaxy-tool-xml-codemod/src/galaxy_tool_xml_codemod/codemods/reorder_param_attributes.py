"""Codemod: rewrite ``<param>`` attribute order to the IUC convention.

Port of the fmt package's GTR002 rule, restated as a structural codemod.
Mutually-exclusive pairs (``min`` / ``truevalue``, ``max`` / ``falsevalue``,
``value`` / ``checked``) share a priority slot; in practice only one of
each pair appears on a given ``<param>``. Attributes outside the IUC
list sort alphabetically after the known ones — matches
``galaxy-language-server``'s ``IUCToolParamAttributeSorter``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.change import Change
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
        code="GTR002",
        summary="Reorder every <param> element's attributes to the IUC convention.",
        since="0.0.1",
        cite="https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html",
        order=60,
        rulesets=frozenset({"default", "iuc", "strict"}),
    )

    def detect_Param(self, cursor: Cursor) -> Iterable[Change]:
        desired = canonical_order(cursor.attribute_names(), _IUC_PRIORITY)
        if cursor.would_reorder_attributes(desired):
            yield Change(
                code=self.meta.code,
                sourceline=cursor.sourceline,
                xpath=cursor.xpath,
                message="<param> attributes are not in IUC convention order",
                mutate=lambda: cursor.reorder_attributes(desired),
            )
