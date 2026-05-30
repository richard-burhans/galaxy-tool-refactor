"""The ``CheckRule`` ABC for advisory (detect-only) IUC checks.

A check is the read-only analogue of a fmt rule / codemod: it carries a
``RuleMeta`` (with ``detect_only=True`` and a unique ``IUC`` code) and a
``detect`` method that performs a non-mutating LBYL query over a parsed
``ToolDocument`` and yields the shared tier-0.5 ``Violation``. The complete set
of active checks is declared in ``detect.all_checks()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

if TYPE_CHECKING:
    from galaxy_tool_refactor_rules.violation import Violation
    from galaxy_tool_xml.document import ToolDocument


class CheckRule(ABC):
    """Abstract base class for an advisory, detect-only IUC check."""

    meta: ClassVar[RuleMeta]

    @abstractmethod
    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        """Yield advisory ``Violation``s for *document*. Never mutates it."""
        ...
