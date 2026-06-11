"""``parse_module`` — entry point for the codemod framework.

See ``docs/decisions.md`` § 1 (narrow signature), § 2 (strict on bytes),
§ 3 (share-not-copy ToolDocument) for the design rationale.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_source.binding import load_macros, load_tool
from galaxy_tool_source.document import MacroDocument, ToolDocument

from galaxy_tool_codemod.module import MacroModule, Module


def parse_module(source: Path | bytes | ToolDocument, /) -> Module:
    """Parse a Galaxy tool XML source into a ``Module``.

    Args:
        source: A filesystem path, raw XML bytes, or an existing
            ``ToolDocument``.

    Returns:
        A ``Module`` wrapping the parsed tool.

    Raises:
        ToolXmlSyntaxError: For ``Path`` / ``bytes`` input, on any
            well-formedness error. Symmetric strict semantics across
            input forms (delegates to ``load_tool``).
    """
    if isinstance(source, ToolDocument):
        return Module(source)
    return Module(load_tool(source))


def parse_macro_module(source: Path | bytes | MacroDocument, /) -> MacroModule:
    """Parse a Galaxy macro-library file into a ``MacroModule``.

    The macro-file counterpart to ``parse_module``: strict on ``Path`` / ``bytes``
    (delegates to ``load_macros``, raising ``ToolXmlSyntaxError`` on malformed
    XML — symmetric with ``parse_module``); shares an existing ``MacroDocument``
    by reference.
    """
    if isinstance(source, MacroDocument):
        return MacroModule(source)
    return MacroModule(load_macros(source))
