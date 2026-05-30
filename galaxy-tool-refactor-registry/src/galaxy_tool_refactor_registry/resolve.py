"""Resolve a preset + ``--select`` / ``--ignore`` into a concrete code set.

Precedence is ruff-style: ``--ignore`` ▸ ``--select`` ▸ ``--preset``. Concretely,
``--select`` *replaces* the preset's set (an explicit selection resets the base,
not adds to it), then ``--ignore`` subtracts. With neither flag the result is the
preset's set (default ``iuc``). Unknown preset names / rule codes raise the typed
``UnknownPreset`` / ``UnknownRuleCode`` (LBYL: validated before any work).
"""

from __future__ import annotations

from collections.abc import Iterable

from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos

from galaxy_tool_refactor_registry.adapters import fmt_rules
from galaxy_tool_refactor_registry.errors import UnknownPreset, UnknownRuleCode
from galaxy_tool_refactor_registry.presets import DEFAULT_PRESET, presets
from galaxy_tool_refactor_registry.registry import known_codes


def _validate_codes(codes: Iterable[str], /) -> None:
    known = known_codes()
    for code in codes:
        if code not in known:
            raise UnknownRuleCode(code)


def resolve_codes(
    *,
    preset: str | None = None,
    select: Iterable[str] = (),
    ignore: Iterable[str] = (),
) -> frozenset[str]:
    """Resolve a selection to the concrete set of rule codes to run.

    Args:
        preset: A preset name, or ``None`` for the default (``iuc``).
        select: Rule codes that *replace* the preset's set when non-empty.
        ignore: Rule codes to subtract from the resulting set.

    Returns:
        The frozenset of selected rule codes.

    Raises:
        UnknownPreset: *preset* is not a known preset.
        UnknownRuleCode: a *select* / *ignore* code is not a known rule.
    """
    select = tuple(select)
    ignore = tuple(ignore)
    name = preset if preset is not None else DEFAULT_PRESET
    if name not in presets():
        raise UnknownPreset(name)
    _validate_codes((*select, *ignore))
    base = frozenset(select) if select else presets()[name]
    return base - frozenset(ignore)


def upgrade_base_codes() -> frozenset[str]:
    """The fixable rules ``upgrade`` runs by default, besides the profile bump.

    Today's ``upgrade`` repairs typos (``FixTypos``) and cosmetically formats; the
    profile upgrade itself (``UpgradeToLatest``) is intrinsic to the command and
    always runs, so it is not a member of this set. Presets do not apply to
    ``upgrade`` (its rule set is fixed); only ``--select`` / ``--ignore`` adjust it.
    """
    return frozenset({FixTypos.meta.code}) | frozenset(
        cls.meta.code for cls in fmt_rules()
    )


def resolve_upgrade_codes(
    *, select: Iterable[str] = (), ignore: Iterable[str] = ()
) -> frozenset[str]:
    """Resolve ``--select`` / ``--ignore`` for ``upgrade`` over its base set.

    Like ``resolve_codes`` but with no preset: the base is
    ``upgrade_base_codes()``. ``--select`` replaces it, ``--ignore`` subtracts.
    """
    select = tuple(select)
    ignore = tuple(ignore)
    _validate_codes((*select, *ignore))
    base = frozenset(select) if select else upgrade_base_codes()
    return base - frozenset(ignore)
