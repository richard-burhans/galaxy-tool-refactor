"""Shared ``format`` / ``ftype`` datatype-attribute normalization (the 24.2 pattern).

Galaxy 24.2 pattern-restricts ``format`` (``<param>`` ``FormatList`` / ``<data>``
``Format``) and ``ftype`` (test ``<param>`` / ``<output>`` / collection ``<element>``
datatypes) to lowercase, comma-separated, whitespace-free tokens. Normalization
lowercases each comma-separated token, strips its whitespace, and drops empties.

This is pure and element-level (no I/O, no ``Cursor`` framework), so it is shared by
two callers: ``Upgrade24_1`` (GTX010, the tool's own tree) and the imported-macro-file
normalization pass (tier 3.6). The macro pass passes ``skip_tokens=True`` to leave a
``@TOKEN@`` placeholder (e.g. ``format="@FORMAT@"``) untouched — lowercasing a token
reference would break it, and a macro's literal there is a placeholder, not a datatype.
``Upgrade24_1`` keeps its historical behaviour (``skip_tokens=False``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lxml import etree

# Attributes 24.2 newly pattern-restricts to lowercase datatype tokens.
DATATYPE_ATTRIBUTES = ("format", "ftype")


def normalize_datatype_value(value: str, /) -> str:
    """Lowercase and strip whitespace from each comma-separated token, dropping empties.

    ``"BAM"`` → ``"bam"``, ``"fa, fasta"`` → ``"fa,fasta"``. A value with no non-empty
    token (``""``, all-whitespace, or only commas) returns ``""`` — the caller drops
    the attribute. A ``<data>`` comma-list round-trips unchanged here (it is not
    coerced into the single-token ``Format`` pattern).
    """
    tokens = [token.strip().lower() for token in value.split(",")]
    return ",".join(token for token in tokens if token)


def normalize_datatype_attributes(
    element: etree._Element, /, *, skip_tokens: bool = False
) -> bool:
    """Normalize ``format`` / ``ftype`` on *element* in place; return whether changed.

    A value that normalizes to empty has its attribute *dropped* (an empty datatype
    restriction is no restriction, and ``""`` violates the 24.2 pattern). When
    *skip_tokens* is true, a value containing ``@`` (a macro ``@TOKEN@`` placeholder)
    is left untouched.
    """
    changed = False
    for attribute in DATATYPE_ATTRIBUTES:
        value = element.get(attribute)
        if value is None:
            continue
        if skip_tokens and "@" in value:
            continue
        normalized = normalize_datatype_value(value)
        if not normalized:
            del element.attrib[attribute]
            changed = True
        elif normalized != value:
            element.set(attribute, normalized)
            changed = True
    return changed
