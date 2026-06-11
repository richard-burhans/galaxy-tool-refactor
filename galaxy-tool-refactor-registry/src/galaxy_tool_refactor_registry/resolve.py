"""Resolve ruleset names + ``--select`` / ``--ignore`` into a concrete code set.

Precedence is ruff-style: ``--ignore`` ▸ ``--select`` ▸ ``--ruleset``. Concretely,
the base is the **union** of the named rulesets (or the default ruleset when none
are named); ``--select`` *replaces* that base (an explicit selection resets it, not
adds to it); then ``--ignore`` subtracts. A ``--select`` / ``--ignore`` token may be
a GTR code, a partition-parent code, or a **planemo linter name** (case-insensitive,
resolved to the covering GTR code(s)). Unknown ruleset names / tokens raise the typed
``UnknownRuleset`` / ``UnknownRuleCode`` (LBYL: validated before any work).
"""

from __future__ import annotations

from collections.abc import Iterable

from galaxy_tool_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_refactor_rules.rulesets import DEFAULT_RULESET

from galaxy_tool_refactor_registry.adapters import OPT_IN_COMMAND_BY_CODE, fmt_rules
from galaxy_tool_refactor_registry.errors import UnknownRuleCode, UnknownRuleset
from galaxy_tool_refactor_registry.planemo import planemo_index
from galaxy_tool_refactor_registry.registry import (
    all_handles,
    expand_codes,
    known_codes,
)
from galaxy_tool_refactor_registry.rulesets import ruleset_codes


def _non_selectable_hint(token: str, /) -> str | None:
    """A hint when *token* names a real rule that is deliberately not selectable.

    ``None`` for a genuinely unknown token. For a non-selectable codemod the hint
    names where the rule actually lives: its dedicated command
    (``OPT_IN_COMMAND_BY_CODE`` — ``convert-help`` for GTR092, ``tokenize-version``
    for GTR094) or the
    ``upgrade`` pipeline.
    """
    code = token.upper()
    if code not in all_handles():
        return None
    command = OPT_IN_COMMAND_BY_CODE.get(code)
    if command is not None:
        return f"{code} is applied only by the dedicated `{command}` command"
    return f"{code} is internal to the `upgrade` pipeline, not selectable"


def _expand_selection(tokens: Iterable[str], /) -> frozenset[str]:
    """Expand ``--select`` / ``--ignore`` *tokens* to concrete GTR codes.

    Each token is a real GTR code, a partition-parent code (expands to its
    sub-rules), or a planemo linter name (case-insensitive → the covering GTR
    code(s); a bundled rule is reached by any of its names). Unknown tokens raise
    ``UnknownRuleCode``.
    """
    known = known_codes()
    index = planemo_index()
    out: set[str] = set()
    for token in tokens:
        # GTR codes match case-insensitively (canonical form is upper); planemo
        # linter names match case-insensitively (index keyed lower-cased). The
        # original token is preserved for the error message.
        if token.upper() in known:
            out |= expand_codes(frozenset({token.upper()}))
        elif token.lower() in index:
            out |= index[token.lower()]
        else:
            raise UnknownRuleCode(token, hint=_non_selectable_hint(token))
    return frozenset(out)


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
    # A partition-parent code (e.g. GTR020) selects/ignores the whole practice; a
    # dotted child (GTR020.2) targets just that half; a planemo name resolves to the
    # covering GTR code(s). Ruleset sets already hold the concrete child codes.
    base = (
        _expand_selection(select)
        if select
        else frozenset().union(*(code_map[name] for name in names))
    )
    return base - _expand_selection(ignore)


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
    base = _expand_selection(select) if select else upgrade_base_codes()
    return base - _expand_selection(ignore)
