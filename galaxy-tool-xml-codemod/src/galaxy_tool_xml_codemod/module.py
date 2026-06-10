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

from galaxy_tool_source.document import MacroDocument, ToolDocument
from galaxy_tool_source.models.any_tool import AnyTool

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
        """A fresh root ``Cursor``, re-derived from the live document each access.

        Not cached, for the same reason as ``model``: a codemod that mutated the
        tree must always see the current root, never a stale cursor.
        """
        return Cursor(self.document.root)


@dataclass(frozen=True)
class MacroModule:
    """A parsed Galaxy macro-library file: lxml tree + root ``Cursor``.

    The macro-file counterpart to ``Module``. A macro library has no typed
    ``model`` or ``profile`` (see ``MacroDocument``), so this wraps just the
    document and a fresh root ``Cursor`` over its ``<macros>`` element; codemod
    primitives (the ``Cursor`` mutators) work on it unchanged, since ``Cursor``
    is generic over any lxml element. Used to navigate and edit a macro file —
    e.g. the macro-library normaliser and the token-aware profile upgrade.
    """

    document: MacroDocument

    @property
    def cursor(self) -> Cursor:
        """A fresh root ``Cursor`` over ``<macros>``, re-derived on each access."""
        return Cursor(self.document.root)
