"""The unified, code-addressable rule registry across all three families.

``registry()`` is the **selectable** set — the codemod canonical rules, the fmt
cosmetic rules, and the advisory IUC checks — keyed by ``RuleMeta.code``. The
upgrade-only codemods (GTX007–GTX012) are not selectable; they are kept in the
internal index purely so the duplicate-code guard sees the whole GTX namespace
and so ``list_rules(include_upgrade=True)`` can enumerate them.

The GTX/IUC code namespace is collision-free by construction (fmt 001/003/004;
canonical codemods 002/005/006/013; upgrade codemods 007–012; checks IUC001–012),
and ``_index`` asserts it — a future rule that reuses a code fails loudly here
rather than silently shadowing another.
"""

from __future__ import annotations

from functools import cache

from galaxy_tool_refactor_registry.adapters import (
    advisory_checks,
    check_handle,
    codemod_handle,
    fmt_handle,
    fmt_rules,
    selectable_codemods,
    upgrade_only_codemods,
)
from galaxy_tool_refactor_registry.errors import UnknownRuleCode
from galaxy_tool_refactor_registry.handle import RuleHandle


def _build_index(
    entries: list[tuple[RuleHandle, bool]],
) -> dict[str, tuple[RuleHandle, bool]]:
    """Index *entries* by ``RuleHandle.meta.code``; raise on any duplicate.

    Pure and uncached so the collision guard is testable in isolation (feed it
    two entries that share a code) without touching the real rule registrations
    or the ``@cache``d ``_index`` table.
    """
    index: dict[str, tuple[RuleHandle, bool]] = {}
    for handle, selectable in entries:
        code = handle.meta.code
        if code in index:
            raise ValueError(
                f"duplicate rule code {code!r}: two rules share one code"
            )
        index[code] = (handle, selectable)
    return index


@cache
def _index() -> dict[str, tuple[RuleHandle, bool]]:
    """Build ``code -> (handle, selectable)`` for every baked-in rule.

    Raises ``ValueError`` on any duplicate code across the families.
    """
    entries: list[tuple[RuleHandle, bool]] = []
    entries.extend((codemod_handle(cls), True) for cls in selectable_codemods())
    entries.extend((codemod_handle(cls), False) for cls in upgrade_only_codemods())
    entries.extend((fmt_handle(cls), True) for cls in fmt_rules())
    entries.extend((check_handle(cls), True) for cls in advisory_checks())
    return _build_index(entries)


def registry() -> dict[str, RuleHandle]:
    """The selectable ``code -> RuleHandle`` map (excludes upgrade-only codes)."""
    return {code: handle for code, (handle, sel) in _index().items() if sel}


def all_handles() -> dict[str, RuleHandle]:
    """Every ``code -> RuleHandle``, including the upgrade-only codemods."""
    return {code: handle for code, (handle, _sel) in _index().items()}


def by_code(code: str, /) -> RuleHandle:
    """Return the selectable rule for *code*, or raise ``UnknownRuleCode``."""
    handle = registry().get(code)
    if handle is None:
        raise UnknownRuleCode(code)
    return handle


def known_codes() -> frozenset[str]:
    """Every selectable rule code (what ``--select`` / ``--ignore`` accept)."""
    return frozenset(registry())


def advisory_codes() -> frozenset[str]:
    """The selectable codes that are advisory (report-only, ``detect_only``)."""
    return frozenset(
        code for code, handle in registry().items() if not handle.fixable
    )
