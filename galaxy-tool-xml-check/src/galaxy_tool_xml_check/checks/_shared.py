"""Cross-module helpers shared by the themed check submodules."""


from __future__ import annotations

import re
from typing import TYPE_CHECKING

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from lxml import etree

if TYPE_CHECKING:
    from galaxy_tool_source.document import ToolDocument


_IUC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"


def _violation(
    document: ToolDocument,
    element: etree._Element,
    meta: RuleMeta,
    message: str,
    /,
) -> Violation:
    """Build a ``Violation`` for *meta* located on *element*."""
    line = element.sourceline
    return Violation(
        code=meta.code,
        sourceline=line if line is not None else 0,
        xpath=str(document.tree.getpath(element)),
        message=message,
    )


# A valid Cheetah placeholder name (Galaxy `is_valid_cheetah_placeholder`): a leading
# letter/underscore then word characters. An output name must be one to be addressable.
_CHEETAH_PLACEHOLDER = re.compile(r"^[a-zA-Z_]\w*$")


def _is_valid_regex(pattern: str, /) -> bool:
    """Whether *pattern* compiles as a regular expression (``re.error`` boundary)."""
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def _param_name(param: etree._Element, /) -> str | None:
    """Galaxy's resolved parameter name: ``name``, else derived from ``argument``.

    Mirrors ``galaxy.tool_util.parser.util._parse_name``: when ``name`` is absent the
    name is derived from ``argument`` (leading dashes stripped, the rest ``-``→``_``).
    Returns ``None`` when the param declares neither (the GTR054 case).
    """
    name = param.get("name")
    if name is not None:
        return str(name)
    argument = param.get("argument")
    if argument is None:
        return None
    return str(argument).lstrip("-").replace("-", "_")


def _string_as_bool(value: object, /) -> bool:
    """Galaxy's ``string_as_bool``: truthy for ``true``/``yes``/``on``/``1`` (any case).

    Case-insensitive, mirroring ``galaxy.util.string_as_bool``.
    """
    return str(value).lower() in ("true", "yes", "on", "1")
