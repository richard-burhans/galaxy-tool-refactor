"""GTX005: canonical attribute order on the root ``<tool>`` element.

Order per the Galaxy schema documentation examples: ``id``, ``name``,
``version``, ``profile``, then remaining attributes alphabetical. The
XSD itself imposes no display order; the order comes from convention
in the docs.

The Galaxy 26.1 XSD declares these ``<tool>`` attributes (required
first): ``id``, ``name``, ``version``, ``hidden``, ``display_interface``,
``tool_type``, ``profile``, ``license``, ``python_template_version``,
``workflow_compatible``, ``URL_method``, ``require_login``. Only the
documented prefix (``id``, ``name``, ``version``, ``profile``) is
explicitly ordered; the rest sort alphabetically.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_xml_fmt.attribute_ordering import reorder_attribute_edits
from galaxy_tool_xml_fmt.edits import Edit
from galaxy_tool_xml_fmt.rules import Rule, RuleMeta

if TYPE_CHECKING:
    from lxml import etree


_TOOL_PRIORITY: dict[str, int] = {
    "id": 0,
    "name": 1,
    "version": 2,
    "profile": 3,
}


class ToolAttributeOrder(Rule):
    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX005",
        summary="Canonical attribute order on the root <tool> element.",
        since="0.1.0",
        cite="https://docs.galaxyproject.org/en/latest/dev/schema.html",
        order=55,
    )

    def apply(self, tree: etree._ElementTree) -> Iterable[Edit]:
        """Yield attribute-reorder edits for the root ``<tool>`` element."""
        root = tree.getroot()
        if root.tag != "tool":
            return []
        return list(reorder_attribute_edits([root], _TOOL_PRIORITY))
