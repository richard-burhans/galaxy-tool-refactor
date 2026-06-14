"""Codemod: reorder the root ``<tool>``'s child elements to the IUC convention.

Implements IUC best-practice #52 (element order under ``<tool>``). The Galaxy
schema's ``<tool>`` content model is ``xs:all`` (order-free), so reordering
children never affects validity — the IUC order is a pure convention this
codemod normalises toward. Tags outside the convention (notably an opaque
``<expand macro="…"/>``, whose expanded tag the codemod cannot see) are pinned
to their original position, never floated to the end (``docs/decisions.md``
§53); a tool whose children carry a free-floating comment is left untouched
(see ``Cursor.reorder_children``). The codemod performs the structural move
only; the cosmetic formatter re-normalises the inter-element whitespace
afterward.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.cursor import Cursor

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

_IUC_RANK: dict[str, int] = {tag: index for index, tag in enumerate(_IUC_ELEMENT_ORDER)}


class ReorderToolChildren(CodemodCommand):
    """Reorder the root ``<tool>`` element's children to the IUC convention.

    By default an opaque top-level ``<expand>`` is **pinned** to its position
    (§53), since the codemod cannot see the tag it expands to. When the registry
    facade resolves an ``<expand>`` to the single IUC tag it produces, it passes
    ``expand_ranks`` (child index → resolved IUC tag) so that ``<expand>`` is
    actively placed in its slot rather than pinned (the resolution layer). The
    canonical pipeline constructs this codemod with no arguments (pure pinning);
    only the facade, which can run macro expansion, supplies the per-document map.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR013",
        summary="Reorder <tool> child elements to the IUC convention.",
        since="0.0.1",
        cite="https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html",
        order=80,
        rulesets=frozenset({"default", "iuc", "strict"}),
        planemo_linters=frozenset({"XMLOrder"}),
    )

    def __init__(self, *, expand_ranks: dict[int, str] | None = None) -> None:
        """*expand_ranks* maps a top-level child index to the IUC tag it resolves
        to (facade-supplied); absent => pure pinning (the standalone default)."""
        self._expand_ranks = expand_ranks or {}

    def detect_Tool(self, cursor: Cursor) -> Iterable[Change]:
        override = {
            index: _IUC_RANK[tag]
            for index, tag in self._expand_ranks.items()
            if tag in _IUC_RANK
        }
        if cursor.would_reorder_children(_IUC_ELEMENT_ORDER, rank_override=override):
            yield Change(
                code=self.meta.code,
                sourceline=cursor.sourceline,
                xpath=cursor.xpath,
                message="<tool> child elements are not in IUC convention order",
                mutate=lambda: cursor.reorder_children(
                    _IUC_ELEMENT_ORDER, rank_override=override
                ),
            )
