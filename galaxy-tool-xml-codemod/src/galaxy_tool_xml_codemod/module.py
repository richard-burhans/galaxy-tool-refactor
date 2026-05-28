"""``Module`` — the wrapper a codemod operates on.

A ``Module`` holds a parsed Galaxy tool: the lxml-backed ``ToolDocument``
(source of truth), the typed xsdata-bound model (derived view), and a
root ``Cursor`` for traversal. Both ``model`` and ``cursor`` re-derive
from the live document on every access — the wrapper carries no cached
state, so codemods that mutate the tree always see fresh derived views.
See ``docs/decisions.md`` § 4 for the frozen-dataclass / public-field
rationale and § 5 for the no-cache decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml.models.any_tool import AnyTool

from galaxy_tool_xml_codemod.cursor import Cursor


@dataclass(frozen=True)
class Module:
    """A parsed Galaxy tool XML unit: lxml tree + typed model + cursor root."""

    document: ToolDocument

    @property
    def model(self) -> AnyTool:
        """Re-bind the typed model against the current tree on every access.

        Not cached: mutations propagate. xsdata binding is cheap enough
        for tool-sized trees that the no-staleness contract wins over
        the small CPU saving.
        """
        return self.document.model()

    @property
    def cursor(self) -> Cursor:
        return Cursor(self.document.root)
