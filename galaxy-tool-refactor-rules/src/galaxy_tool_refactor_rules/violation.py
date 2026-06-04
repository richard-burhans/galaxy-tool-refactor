"""The ``Violation`` diagnostic descriptor shared across the refactor tiers.

A ``Violation`` is the per-occurrence report a detect (lint) phase produces:
which rule fired (``code``), where (``sourceline`` + ``xpath``), and a
human-readable ``message``. It is the read-only counterpart to the mutating
``Edit`` (tier 3) / ``Change`` (tier 2) types — those carry the fix; this carries
the finding. Both the formatter (tier 3) and codemod (tier 2) detect phases, the
``check`` CLI (tier 4), and the advisory check library surface diagnostics as
``Violation``s, so the type lives here next to ``RuleMeta`` where every tier can
reach it without depending on one another.

Like ``RuleMeta`` this is pure data — the location is a plain ``int`` line plus a
``str`` xpath, never an lxml handle — which keeps this package dependency-free
(no lxml, no tier 1/2/3 imports). See ``docs/decisions.md`` § D1 for the
shared-vocabulary rationale.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    """A single detected rule occurrence in a tool XML document.

    Attributes:
        code: The rule's identifier (e.g. ``"GTR002"``); matches ``RuleMeta.code``.
        sourceline: 1-based line of the offending element, or ``0`` when the
            element was synthesised and has no source position.
        xpath: Absolute xpath to the offending element (e.g.
            ``"/tool/inputs/param[1]"``).
        message: One-line human-readable description of the finding.
    """

    code: str
    sourceline: int
    xpath: str
    message: str
