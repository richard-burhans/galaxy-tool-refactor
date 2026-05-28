"""GTX002: canonical attribute order on ``<param>`` elements.

Order, per the IUC tool-XML style guide:

  name, argument, type, format,
  min | truevalue, max | falsevalue, value | checked,
  optional, label, help

Mutually-exclusive pairs (e.g. ``min`` vs ``truevalue``) share a
priority slot — in practice only one of each pair appears on a given
``<param>``, so the shared slot keeps the canonical order stable
across param types. Attributes not in the IUC list sort alphabetically
after the known ones, matching galaxy-language-server's
``IUCToolParamAttributeSorter``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_xml_fmt.attribute_ordering import reorder_attribute_edits
from galaxy_tool_xml_fmt.edits import Edit
from galaxy_tool_xml_fmt.rules import Rule, RuleMeta

if TYPE_CHECKING:
    from lxml import etree


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


class ParamAttributeOrder(Rule):
    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX002",
        summary="Canonical IUC attribute order on <param> elements.",
        since="0.1.0",
        cite="https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html",
        order=50,
    )

    def apply(self, tree: etree._ElementTree) -> Iterable[Edit]:
        """Yield attribute-reorder edits for every ``<param>`` element in *tree*."""
        return list(reorder_attribute_edits(tree.iter("param"), _IUC_PRIORITY))
