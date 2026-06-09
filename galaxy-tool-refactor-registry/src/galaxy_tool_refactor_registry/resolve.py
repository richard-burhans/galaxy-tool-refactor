"""Resolve ruleset names + ``--select`` / ``--ignore`` into a concrete code set.

Precedence is ruff-style: ``--ignore`` ▸ ``--select`` ▸ ``--ruleset``. Concretely,
the base is the **union** of the named rulesets (or the default ruleset when none
are named); ``--select`` *replaces* that base (an explicit selection resets it, not
adds to it); then ``--ignore`` subtracts. Unknown ruleset names / rule codes raise
the typed ``UnknownRuleset`` / ``UnknownRuleCode`` (LBYL: validated before any work).
"""

from __future__ import annotations

from collections.abc import Iterable

from galaxy_tool_refactor_rules.rulesets import DEFAULT_RULESET
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos

from galaxy_tool_refactor_registry.adapters import fmt_rules
from galaxy_tool_refactor_registry.errors import UnknownRuleCode, UnknownRuleset
from galaxy_tool_refactor_registry.registry import expand_codes, known_codes
from galaxy_tool_refactor_registry.rulesets import ruleset_codes


def _validate_codes(codes: Iterable[str], /) -> None:
    known = known_codes()
    for code in codes:
        if code not in known:
            raise UnknownRuleCode(code)


def resolve_codes(
    *,
    rulesets: Iterable[str] = (),
    select: Iterable[str] = (),
    ignore: Iterable[str] = (),
) -> frozenset[str]:
    """Resolve a selection to the concrete set of rule codes to run.

    Args:
        rulesets: Ruleset names whose **union** forms the base set; empty means
            just the default ruleset (``DEFAULT_RULESET``).
        select: Rule codes that *replace* the ruleset base when non-empty.
        ignore: Rule codes to subtract from the resulting set.

    Returns:
        The frozenset of selected rule codes.

    Raises:
        UnknownRuleset: a name in *rulesets* is not a known ruleset.
        UnknownRuleCode: a *select* / *ignore* code is not a known rule.
    """
    names = tuple(rulesets) or (DEFAULT_RULESET,)
    select = tuple(select)
    ignore = tuple(ignore)
    code_map = ruleset_codes()
    for name in names:
        if name not in code_map:
            raise UnknownRuleset(name)
    _validate_codes((*select, *ignore))
    # A partition-parent code (e.g. GTR020) selects/ignores the whole practice; a
    # dotted child (GTR020.2) targets just that half. Ruleset sets already hold the
    # child codes, so only the user-supplied select/ignore need expanding.
    base = (
        expand_codes(frozenset(select))
        if select
        else frozenset().union(*(code_map[name] for name in names))
    )
    return base - expand_codes(frozenset(ignore))


def upgrade_base_codes() -> frozenset[str]:
    """The fixable rules ``upgrade`` runs by default, besides the profile bump.

    Today's ``upgrade`` repairs typos (``FixTypos``) and cosmetically formats; the
    profile upgrade itself (``UpgradeToLatest``) is intrinsic to the command and
    always runs, so it is not a member of this set. Rulesets do not apply to
    ``upgrade`` (its rule set is fixed); only ``--select`` / ``--ignore`` adjust it.
    """
    return frozenset({FixTypos.meta.code}) | frozenset(
        cls.meta.code for cls in fmt_rules()
    )


def resolve_upgrade_codes(
    *, select: Iterable[str] = (), ignore: Iterable[str] = ()
) -> frozenset[str]:
    """Resolve ``--select`` / ``--ignore`` for ``upgrade`` over its base set.

    Like ``resolve_codes`` but with no ruleset: the base is
    ``upgrade_base_codes()``. ``--select`` replaces it, ``--ignore`` subtracts.
    """
    select = tuple(select)
    ignore = tuple(ignore)
    _validate_codes((*select, *ignore))
    base = expand_codes(frozenset(select)) if select else upgrade_base_codes()
    return base - expand_codes(frozenset(ignore))
