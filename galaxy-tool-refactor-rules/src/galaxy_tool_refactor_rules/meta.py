"""The ``RuleMeta`` descriptor shared across the refactor tiers.

Both a tier-3 formatter rule (``galaxy_tool_xml_fmt.rules.Rule``) and a tier-2
codemod (``galaxy_tool_xml_codemod.codemod.CodemodCommand``) carry a
``meta: ClassVar[RuleMeta]`` so the two tiers expose one uniform vocabulary for
the GTX rule registry. The descriptor is pure data — it deliberately knows
nothing about lxml, edits, or the cursor walk, which keeps this package
dependency-free and the tiers independent.

Versioning convention: stability for consumers comes from pinning the owning
tier's package version in their lockfile, not from this metadata. ``since`` /
``until`` are documentary only — ``until`` stays ``None`` while a rule is active
and is stamped (for the changelog) in the same commit that retires the rule.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleMeta:
    """Metadata descriptor for a refactor rule (a fmt rule or a codemod).

    Attributes:
        code: Short unique rule identifier (e.g. ``"GTX001"``).
        summary: One-line human-readable description.
        since: Version in which this rule was introduced.
        until: Version in which this rule was removed, or ``None`` if active.
        cite: Optional reference URL or citation.
        order: Application order; lower values run first. Used by the formatter
            tier to sequence its rules; the codemod tier orders by its own
            pipeline tuple and leaves this at the default.
    """

    code: str
    summary: str
    since: str
    until: str | None = None
    cite: str | None = None
    order: int = 100
