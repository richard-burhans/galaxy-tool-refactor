"""Rule base class and metadata for the formatter.

Rules are stateless ABCs whose ``apply()`` method inspects an lxml tree and
yields ``Edit``s describing the canonical-form mutations to perform. The
pipeline (``format.format_tool_document``) instantiates each rule per format
call and feeds its edits to ``apply_edits``.

The complete set of active rules is declared in ``format.all_rules()``.

Versioning convention: stability for CI consumers comes from pinning
``galaxy-tool-xml-fmt==x.y.z`` in their lockfile (no ``--rules-version``
flag). ``RuleMeta.since`` / ``RuleMeta.until`` is documentary metadata
only — ``all_rules()`` returns every rule currently in source; retirement
is a code deletion that stamps ``until`` in the deletion commit for the
changelog.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from lxml import etree

    from galaxy_tool_xml_fmt.edits import Edit


@dataclass(frozen=True)
class RuleMeta:
    """Metadata descriptor for a formatter rule.

    Attributes:
        code: Short unique rule identifier (e.g. ``"GTX001"``).
        summary: One-line human-readable description.
        since: Version in which this rule was introduced.
        until: Version in which this rule was removed, or ``None`` if active.
        cite: Optional reference URL or citation.
        order: Application order; lower values run first.
    """

    code: str
    summary: str
    since: str
    until: str | None = None
    cite: str | None = None
    order: int = 100


class Rule(ABC):
    """Abstract base class for formatter rules."""

    meta: ClassVar[RuleMeta]

    @abstractmethod
    def apply(self, tree: etree._ElementTree) -> Iterable[Edit]:
        """Yield ``Edit``s that transform *tree* toward canonical form."""
        ...
