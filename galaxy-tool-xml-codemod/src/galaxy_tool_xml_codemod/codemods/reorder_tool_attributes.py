"""Codemod: rewrite the root ``<tool>``'s attributes to the documented prefix order.

Port of the fmt package's GTR005 rule. Order per the Galaxy schema
documentation: ``id``, ``name``, ``version``, ``profile``, then any
remaining attributes alphabetical. The XSD itself imposes no display
order — the prefix comes from convention in the docs.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods._attribute_ordering import canonical_order
from galaxy_tool_xml_codemod.cursor import Cursor

_TOOL_PRIORITY: dict[str, int] = {
    "id": 0,
    "name": 1,
    "version": 2,
    "profile": 3,
}


class ReorderToolAttributes(CodemodCommand):
    """Reorder the root ``<tool>`` element's attributes to the documented prefix."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR005",
        summary=(
            "Reorder the root <tool> element's attributes to the documented"
            " prefix."
        ),
        since="0.0.1",
    )

    def detect_Tool(self, cursor: Cursor) -> Iterable[Change]:
        desired = canonical_order(cursor.attribute_names(), _TOOL_PRIORITY)
        if cursor.would_reorder_attributes(desired):
            yield Change(
                code=self.meta.code,
                sourceline=cursor.sourceline,
                xpath=cursor.xpath,
                message="<tool> attributes are not in the documented prefix order",
                mutate=lambda: cursor.reorder_attributes(desired),
            )
