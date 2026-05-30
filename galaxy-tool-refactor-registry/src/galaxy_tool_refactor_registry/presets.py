"""Named presets — curated, behind-the-scenes rule subsets.

A preset is the black-like opinionated unit a user picks by name; the code↔preset
mapping is the single source of truth here (derived from the family registries so
it never drifts from the rules that actually exist):

- ``cosmetic`` — the fmt cosmetic rules only (whitespace / indent / shorthand).
- ``iuc`` — the canonical codemods (typo repair + attribute / element order) plus
  the cosmetic rules. This is exactly today's ``format`` behaviour, the
  "black-like opinionated formatter", and the **default** preset.
- ``strict`` — ``iuc`` plus every advisory IUC check (report-only). "Format me,
  and flag everything the IUC standard cares about." (The two reserved advisory
  stubs IUC011/IUC012 are members but never fire until implemented.)

Adding or changing a preset is a developer task — there are no user-defined
presets, by design.
"""

from __future__ import annotations

from functools import cache

from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS

from galaxy_tool_refactor_registry.adapters import advisory_checks, fmt_rules

DEFAULT_PRESET = "iuc"

_DESCRIPTIONS: dict[str, str] = {
    "cosmetic": "Cosmetic whitespace only (indent, blank lines, shorthand).",
    "iuc": "The opinionated canonical formatter: typo repair + attribute/element "
    "order + cosmetic formatting (the default).",
    "strict": "Everything in 'iuc' plus the advisory IUC best-practice checks "
    "(report-only).",
}


@cache
def presets() -> dict[str, frozenset[str]]:
    """Return ``preset name -> frozenset of rule codes`` (the single source)."""
    cosmetic = frozenset(cls.meta.code for cls in fmt_rules())
    canonical = frozenset(cls.meta.code for cls in CANONICAL_CODEMODS)
    advisory = frozenset(cls.meta.code for cls in advisory_checks())
    iuc = cosmetic | canonical
    return {
        "cosmetic": cosmetic,
        "iuc": iuc,
        "strict": iuc | advisory,
    }


def preset_names() -> tuple[str, ...]:
    """Preset names in display order (cosmetic, iuc, strict)."""
    return ("cosmetic", "iuc", "strict")


def preset_description(name: str, /) -> str:
    """A one-line human description for *name* (empty string if unknown)."""
    return _DESCRIPTIONS.get(name, "")
