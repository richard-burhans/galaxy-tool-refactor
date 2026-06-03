"""Codemod: reorder the root ``<tool>``'s child elements to the IUC convention.

Implements IUC best-practice #52 (element order under ``<tool>``). The Galaxy
schema's ``<tool>`` content model is ``xs:all`` (order-free), so reordering
children never affects validity — the IUC order is a pure convention this
codemod normalises toward. Tags outside the convention keep their relative
position after the known ones; a tool whose children carry a free-floating
comment is left untouched (see ``Cursor.reorder_children``). The codemod
performs the structural move only; the cosmetic formatter re-normalises the
inter-element whitespace afterward.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.cursor import Cursor

_IUC_ELEMENT_ORDER: tuple[str, ...] = (
    "description",
    "macros",
    "edam_topics",
    "edam_operations",
    "xrefs",
    "parallelism",
    "requirements",
    "code",
    "stdio",
    "version_command",
    "command",
    "environment_variables",
    "configfiles",
    "inputs",
    "request_param_translation",
    "outputs",
    "tests",
    "help",
    "citations",
)


class ReorderToolChildren(CodemodCommand):
    """Reorder the root ``<tool>`` element's children to the IUC convention."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR013",
        summary="Reorder <tool> child elements to the IUC convention.",
        since="0.0.1",
        cite="https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html",
    )

    def detect_Tool(self, cursor: Cursor) -> Iterable[Change]:
        if cursor.would_reorder_children(_IUC_ELEMENT_ORDER):
            yield Change(
                code=self.meta.code,
                sourceline=cursor.sourceline,
                xpath=cursor.xpath,
                message="<tool> child elements are not in IUC convention order",
                mutate=lambda: cursor.reorder_children(_IUC_ELEMENT_ORDER),
            )
