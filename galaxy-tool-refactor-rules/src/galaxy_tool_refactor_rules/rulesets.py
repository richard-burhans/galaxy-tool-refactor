"""The named rule-sets — the maintainer-facing vocabulary for grouping rules.

A *ruleset* is a named, described bucket of rules. **Membership is declared per
rule** (``RuleMeta.rulesets``): a maintainer marks a rule's set(s) right on the
rule. This module is the authoritative catalog of the ruleset *names and
descriptions* — the one property that belongs to the set itself, not to any
member. The registry tier (3.6) derives ``name -> {codes}`` by grouping rules by
their declared membership, and the CLI ``--ruleset`` flag selects the **union** of
the named sets.

Dependency-free, like the rest of tier 0.5 — ruleset names are plain strings, so a
rule in any tier can declare membership (``RuleMeta(..., rulesets=frozenset({...}))``)
without importing anything heavier. Adding a ruleset is a developer task (a new
``Ruleset`` here + tagging the member rules); there are no user-defined rulesets.

The catalog also defines the subset relationships informally via the seeded
membership: ``cosmetic`` ⊆ ``default`` == ``iuc`` ⊆ ``strict`` today. ``default``
is the set applied when the user names no ruleset; it reproduces the historical
default ``format`` behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ruleset:
    """A named rule-set: a selectable bucket of rules.

    Attributes:
        name: The selection key (e.g. ``"default"``) — exactly as it appears in
            ``RuleMeta.rulesets`` and on the CLI ``--ruleset`` flag.
        description: A one-line human-readable summary.
    """

    name: str
    description: str


DEFAULT_RULESET = "default"
"""The ruleset selected when the user names none (the no-argument ``format`` set)."""


_CATALOG: tuple[Ruleset, ...] = (
    Ruleset(
        name="cosmetic",
        description="Cosmetic whitespace only (indent, blank lines, shorthand).",
    ),
    Ruleset(name="default", description="default"),
    Ruleset(name="iuc", description="iuc"),
    Ruleset(
        name="strict",
        description="Everything in 'default' plus the advisory best-practice "
        "checks (report-only).",
    ),
)


def rulesets_catalog() -> tuple[Ruleset, ...]:
    """Return every defined ruleset, in display order."""
    return _CATALOG


def ruleset_names() -> tuple[str, ...]:
    """Return the defined ruleset names, in display order."""
    return tuple(ruleset.name for ruleset in _CATALOG)


def ruleset_description(name: str, /) -> str | None:
    """Return the one-line description for *name*, or ``None`` if undefined."""
    for ruleset in _CATALOG:
        if ruleset.name == name:
            return ruleset.description
    return None
