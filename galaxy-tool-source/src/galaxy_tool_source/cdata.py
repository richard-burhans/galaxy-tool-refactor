"""Shared predicates for the CDATA best practice (the GTR018/GTR019 substrate).

Galaxy ``<command>`` and ``<help>`` bodies are best written inside a
``<![CDATA[…]]>`` section so shell operators (``&&``, ``<``, ``|``) and markup stay
literal. Two callers need to agree on the *same* notion of "can a pure-text body be
losslessly wrapped":

- the **fix** sub-rules (tier 2 ``WrapCommandCdata`` / ``WrapHelpCdata``, codes
  ``GTR018.1`` / ``GTR019.1``) wrap exactly the bodies ``cdata_wrappable`` accepts;
- the **advisory** sub-rules (tier 3.5, codes ``GTR018.2`` / ``GTR019.2``) flag the
  *residual* — a body that needs CDATA (``needs_cdata``) but is **not**
  ``cdata_wrappable`` (mixed-content, carries a ``]]>`` terminator, or contains a
  carriage return that a CDATA section cannot preserve).

Living in tier 1 keeps that one predicate shared so the fix/advisory partition is
sound by construction (no drift), without the check tier (3.5) importing the codemod
tier (2). Operates on a raw ``etree._Element``; pure (element in, bool out).
"""

from __future__ import annotations

from lxml import etree


def is_cdata_wrapped(element: etree._Element, /) -> bool:
    """Whether *element*'s own leading text body is a ``<![CDATA[…]]>`` section.

    lxml exposes CDATA as plain ``.text`` with no marker, so this re-serialises (the
    tier-1 parser keeps CDATA, ``strip_cdata=False``, so a section round-trips) and
    inspects the body. Leading whitespace before the section still counts as wrapped;
    a partly-wrapped body (``echo <![CDATA[…]]>``) or a CDATA-bearing *child* does
    not count as the element itself being wrapped.
    """
    serialised: str = etree.tostring(element, encoding="unicode", with_tail=False)
    body = serialised[serialised.index(">") + 1 :]
    return bool(body.lstrip().startswith("<![CDATA["))


def needs_cdata(element: etree._Element, /) -> bool:
    """Whether *element* has a non-whitespace text body not already CDATA-wrapped.

    The population the CDATA best practice applies to — the union of what the fix
    handles and what its advisory residual flags.
    """
    return bool((element.text or "").strip()) and not is_cdata_wrapped(element)


def cdata_wrappable(element: etree._Element, /) -> bool:
    """Whether *element*'s body can be losslessly wrapped in **one** CDATA section.

    True iff the body is non-whitespace text, has **no child nodes** (a mixed-content
    body can't be one section), is **not already** wrapped, contains no ``]]>``
    terminator (which cannot live inside a section), and contains no carriage return
    (``\r`` / U+000D). A CDATA section cannot carry ``&#13;`` — entity/char references
    are not recognised inside a section, and a raw CR is normalised to LF on the next
    parse — so wrapping a CR-bearing body would silently rewrite it (and is
    non-idempotent); ``docs/behavior_preservation.md`` GTR018.1/GTR019.1. This is
    exactly the fix's eligibility; the advisory residual is
    ``needs_cdata and not cdata_wrappable``.
    """
    text = element.text
    if text is None or not text.strip():
        return False
    if len(element) != 0:  # any child node — element, comment, or PI
        return False
    if is_cdata_wrapped(element):
        return False
    if "\r" in text:  # a CR has no in-CDATA form (&#13; is not recognised there)
        return False
    return "]]>" not in text
