"""Rule base class for the formatter.

The ``RuleMeta`` descriptor each rule carries lives in the shared
``galaxy-tool-refactor-rules`` package (tier 0.5), so the formatter and the
codemod tier expose one uniform rule-metadata vocabulary.


Rules are stateless ABCs whose ``edits()`` method inspects an lxml tree and
yields ``Edit``s describing the canonical-form mutations to perform. The
pipeline (``format.format_tool_document``) instantiates each rule per format
call and feeds its edits to ``apply_edits``. (The method is ``edits``, not
``apply``, because — unlike codemod's ``CodemodCommand.apply`` and the registry's
``RuleHandle.apply`` — it *describes* edits rather than mutating; ``apply_edits``
performs them. See ``ARCHITECTURE.md`` §10.)

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
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

if TYPE_CHECKING:
    from lxml import etree

    from galaxy_tool_xml_fmt.edits import Edit


class Rule(ABC):
    """Abstract base class for formatter rules."""

    meta: ClassVar[RuleMeta]

    @abstractmethod
    def edits(self, tree: etree._ElementTree) -> Iterable[Edit]:
        """Yield ``Edit``s that transform *tree* toward canonical form."""
        ...
