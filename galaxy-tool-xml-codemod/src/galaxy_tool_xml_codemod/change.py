"""``Change`` — one detected structural mutation, applied via a thunk.

A codemod's **detect** phase yields ``Change``s without touching the tree: each
carries the diagnostic data (``code``, ``sourceline``, ``xpath``, ``message`` —
the same fields as a tier-0.5 ``Violation``) plus a zero-argument ``mutate``
thunk that performs the mutation through the existing ``Cursor`` primitives. The
detect list *is* the report; running ``apply_changes`` over it is the fix. One
mutation site (the thunk body), one source of truth — the change a codemod
reports is exactly the change it applies, with no risk of the two drifting.

See ``galaxy-tool-xml-fmt``'s ``edits.py`` for the cosmetic-tier analogue; the
difference is that an ``Edit`` is a pure-data union dispatched by ``match/case``
whereas a ``Change`` carries its mutation as a closure over a ``Cursor`` call
(``docs/decisions.md`` § on the detect/fix split records why the structural tier
reuses the cursor rather than re-enumerating every mutation kind).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from galaxy_tool_refactor_rules.violation import Violation


@dataclass(frozen=True)
class Change:
    """One structural mutation a codemod detected, with the thunk that applies it.

    Attributes:
        code: The codemod's ``RuleMeta.code`` (e.g. ``"GTX002"``).
        sourceline: 1-based source line of the affected element, or ``0``.
        xpath: Absolute xpath of the affected element.
        message: One-line human-readable description of the change.
        mutate: Zero-argument thunk that performs the mutation when called.
            Excluded from equality and ``repr`` — two changes are equal when
            their diagnostic data matches, independent of closure identity.
    """

    code: str
    sourceline: int
    xpath: str
    message: str
    mutate: Callable[[], None] = field(compare=False, repr=False)

    def to_violation(self) -> Violation:
        """Project the change's diagnostic data onto a tier-0.5 ``Violation``."""
        return Violation(
            code=self.code,
            sourceline=self.sourceline,
            xpath=self.xpath,
            message=self.message,
        )


def apply_changes(changes: Iterable[Change], /) -> None:
    """Apply every change by invoking its ``mutate`` thunk, in iteration order.

    The single dispatch site for structural mutation: callers that only want
    the report iterate ``detect`` directly and never reach here.
    """
    for change in changes:
        change.mutate()
