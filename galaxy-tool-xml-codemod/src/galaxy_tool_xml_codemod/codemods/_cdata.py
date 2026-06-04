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
already-wrapped bodies are left untouched; the advisory sub-rules GTR018.2 / GTR019.2
flag the rare residual these fix sub-rules deliberately skip.
"""

from __future__ import annotations

from galaxy_tool_xml.cdata import cdata_wrappable

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.cursor import Cursor


def cdata_wrap_change(cursor: Cursor, /, *, code: str, element: str) -> Change | None:
    """Return a Change wrapping *cursor*'s body in CDATA, or ``None`` if unwrappable.

    Eligibility is the shared tier-1 ``cdata_wrappable`` predicate (so the advisory
    GTR018.2 / GTR019.2 residual — ``needs_cdata and not cdata_wrappable`` — can never
    drift from what this fix accepts). Unwrappable cases each left for the advisory
    sub-rule: a whitespace-only body, a mixed-content body (any child node), an
    already-wrapped body, or a body containing ``]]>`` (which cannot be expressed in
    one CDATA section).
    """
    if not cdata_wrappable(cursor.element):
        return None
    text = cursor.text
    if text is None:  # cdata_wrappable guarantees non-None; keeps mypy + LBYL happy
        return None
    return Change(
        code=code,
        sourceline=cursor.sourceline,
        xpath=cursor.xpath,
        message=f"<{element}> body is not wrapped in CDATA",
        mutate=lambda: cursor.set_text(text, cdata=True),
    )
