"""Shared CDATA-wrapping detect logic for ``WrapCommandCdata`` / ``WrapHelpCdata``.

Galaxy ``<command>`` and ``<help>`` bodies are best written inside a
``<![CDATA[…]]>`` section so shell operators (``&&``, ``<``, ``|``) and markup
stay literal — the IUC ``tool_xml`` best practices (#34 for ``<command>``, #42 for
``<help>``). When a body is *pure text* — non-whitespace, no child nodes, not
already CDATA-wrapped, and free of the ``]]>`` terminator that can't live inside a
single section — wrapping it is **behaviour-preserving**: lxml already exposes the
entity-unescaped text, so only the serialised bytes change (entities become literal
inside CDATA), not the value Galaxy ultimately runs or renders.

Mixed-content bodies (text interleaved with child elements or comments) and
already-wrapped bodies are left untouched; the advisory IUC002/IUC010 checks remain
to flag the rare residual these codemods deliberately skip.
"""

from __future__ import annotations

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.cursor import Cursor


def cdata_wrap_change(cursor: Cursor, /, *, code: str, element: str) -> Change | None:
    """Return a Change wrapping *cursor*'s body in CDATA, or ``None`` if unwrappable.

    Unwrappable cases (each left for the advisory checks): a whitespace-only body,
    a mixed-content body (any child node), an already-wrapped body, or a body
    containing ``]]>`` (which cannot be expressed in one CDATA section).
    """
    text = cursor.text
    if text is None or not text.strip():
        return None
    if cursor.child_node_count() != 0:
        return None
    if cursor.is_cdata_wrapped():
        return None
    if "]]>" in text:
        return None
    return Change(
        code=code,
        sourceline=cursor.sourceline,
        xpath=cursor.xpath,
        message=f"<{element}> body is not wrapped in CDATA",
        mutate=lambda: cursor.set_text(text, cdata=True),
    )
