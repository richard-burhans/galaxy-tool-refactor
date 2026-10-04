"""Cross-module helpers shared by the themed check submodules."""


from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from galaxy_tool_source.macros import expand_from_tree, has_macros
from galaxy_tool_source.param_names import resolved_param_name
from lxml import etree

if TYPE_CHECKING:
    from pathlib import Path

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


@lru_cache(maxsize=1)
def _expand(root: etree._Element, source_dir: Path | None, /) -> etree._Element | None:
    """Cached expansion of *root*. ``maxsize=1`` because rules run per document."""
    expanded, errors = expand_from_tree(root, source_dir=source_dir)
    if expanded is None or errors:
        return None
    return expanded.getroot()


def expanded_root(document: ToolDocument, /) -> etree._Element | None:
    """The macro-expanded root, or ``None`` when a macro-using tool fails to expand.

    A presence check that reads the raw tree reports every tool declaring the element
    through ``<expand macro="..."/>`` as declaring nothing. Measured on one 55-wrapper
    repository: 40 of 42 GTR025 findings and 44 of 50 GTR038 findings were that, which
    buries the real ones.

    ⚠ ELEMENTS OF THE RETURNED TREE ARE NOT IN ``document.tree``, so
    ``document.tree.getpath()`` cannot locate them and ``_violation`` must never anchor
    on one. Decide with this tree; anchor on the original.

    Returning ``None`` on a failed expansion keeps the no-false-positive contract: the
    caller reports nothing rather than guessing, exactly as GTR034 does.
    """
    root = document.root
    if not has_macros(root):
        return root
    source_dir = document.source_path.parent if document.source_path else None
    return _expand(root, source_dir)


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
    return resolved_param_name(param)


def _string_as_bool(value: object, /) -> bool:
    """Galaxy's ``string_as_bool``: truthy for ``true``/``yes``/``on``/``1`` (any case).

    Case-insensitive, mirroring ``galaxy.util.string_as_bool``.
    """
    return str(value).lower() in ("true", "yes", "on", "1")
