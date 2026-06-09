"""The ``RuleMeta`` descriptor shared across the refactor tiers.

Both a tier-3 formatter rule (``galaxy_tool_xml_fmt.rules.Rule``) and a tier-2
codemod (``galaxy_tool_xml_codemod.codemod.CodemodCommand``) carry a
``meta: ClassVar[RuleMeta]`` so the two tiers expose one uniform vocabulary for
the GTR rule registry. The descriptor is pure data — it deliberately knows
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
        code: Short unique rule identifier (e.g. ``"GTR001"``).
        summary: One-line human-readable description.
        since: Version in which this rule was introduced.
        until: Version in which this rule was removed, or ``None`` if active.
        cite: Optional reference URL or citation.
        order: Application order; lower values run first. Each family is ordered
            independently by this value — the formatter tier sequences its
            cosmetic rules, and the codemod tier sequences its canonical codemods
            (the registry's apply phase sorts each family by ``order``). An
            upgrade-only or report-only rule leaves it at the default.
        detect_only: Whether the rule only *reports* (a lint with no automatic
            fix), as opposed to the fixable fmt rules and codemods. The advisory
            check tier (``galaxy-tool-xml-check``) sets this ``True``; a
            report-only consumer like the ``check`` CLI uses it to treat such
            findings as informational rather than as a failing gate.
        applies_to: The document kinds the rule operates on — a subset of
            ``{"tool", "macro"}``. A generic XML rule (canonical indentation,
            empty-element shorthand) applies to both; a tool-structural rule
            (``<tool>`` child order, a blank line between ``<tool>`` sections,
            attribute order, profile upgrades) applies only to ``"tool"``; a
            macro-library rule applies only to ``"macro"``. The default
            ``{"tool"}`` is the conservative choice — a rule runs on a macro
            file only when it explicitly opts in. Consumers run a rule against a
            document only when the document's kind is in this set.
        parent: The code of the **partition parent** this rule is a sub-rule of,
            or ``None`` for a standalone rule. A best-practice that splits into a
            provably-fixable part and an advisory residual is modelled as a parent
            practice code (e.g. ``"GTR020"``) with two sub-rules whose own ``code``
            is dotted: ``"GTR020.1"`` (fixable) and ``"GTR020.2"`` (advisory). The
            parent is a registry-level grouping (selectable, expands to its
            children), not itself a rule; this field is what the registry derives
            the groups from. See registry ``docs/decisions.md`` D10.
        rulesets: The names of the rule-sets this rule belongs to (the catalog
            lives in ``rulesets.py``). This is the maintainer-facing "mark which
            rules belong to which set" mechanism: the registry groups rules by
            these names into selectable sets, and the CLI ``--ruleset`` flag
            selects the **union** of the named sets. The default empty set means
            the rule is never independently selectable — e.g. an upgrade-only
            codemod driven internally by ``UpgradeToLatest``. Every name used
            here must appear in the ``rulesets.py`` catalog (guarded by a test).
    """

    code: str
    summary: str
    since: str
    until: str | None = None
    cite: str | None = None
    order: int = 100
    detect_only: bool = False
    applies_to: frozenset[str] = frozenset({"tool"})
    parent: str | None = None
    rulesets: frozenset[str] = frozenset()
