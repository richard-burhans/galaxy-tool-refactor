"""The unified, code-addressable rule registry across all three families.

``registry()`` is the **selectable** set — the codemod canonical rules, the fmt
cosmetic rules, and the advisory checks — keyed by ``RuleMeta.code``. The
non-selectable codemods (GTR007–GTR012 + GTR093 validity-gated; GTR014–GTR016
runtime-gated; the opt-in-command-only GTR092) are kept in the internal index
purely so the duplicate-code guard sees the whole GTR namespace and so
``list_rules(include_upgrade=True)`` can enumerate them.

Every rule carries a single ``GTR###`` code; fixability is a rule property
(``RuleHandle.fixable``), not a prefix (registry ``docs/decisions.md`` D9). The
namespace is collision-free by construction (fmt GTR001/003/004; canonical codemods
GTR002/005/006/013/017/018/019/020; upgrade codemods GTR007–012; runtime-gated fixes
GTR014–016; advisory checks GTR021–033), and ``_index`` asserts it — a future rule
that reuses a code fails loudly here rather than silently shadowing another.
"""

from __future__ import annotations

from functools import cache

from galaxy_tool_refactor_registry.adapters import (
    advisory_checks,
    check_handle,
    codemod_handle,
    fmt_handle,
    fmt_rules,
    non_selectable_codemods,
    selectable_codemods,
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


def _validate_partitions(index: dict[str, tuple[RuleHandle, bool]], /) -> None:
    """Assert the partition sub-rule invariants (registry ``docs/decisions.md`` D10).

    For every rule carrying a ``meta.parent`` (a partition sub-rule):
    - its ``code`` is dotted as ``<parent>.<suffix>`` (so ``display_code`` /
      ``expand_codes`` and the dotted-code scheme stay coherent);
    - the parent code is **not** itself a registered rule code — a parent is a
      selectable group key, not a rule handle;
    - the parent groups **at least one fixable and one advisory** child — the whole
      point of a partition is the fix/advisory split.

    Pure and uncached (like ``_build_index``) so the guard is testable on a synthetic
    index. Raises ``ValueError`` loudly at registry-build time on any violation, so a
    future partition added without following the scheme fails fast rather than
    silently mis-rendering.
    """
    fixable_kids: dict[str, list[str]] = {}
    advisory_kids: dict[str, list[str]] = {}
    for code, (handle, _selectable) in index.items():
        parent = handle.meta.parent
        if parent is None:
            continue
        if not code.startswith(f"{parent}."):
            raise ValueError(
                f"partition sub-rule {code!r} must be coded '<parent>.<suffix>' "
                f"under its parent {parent!r}"
            )
        if parent in index:
            raise ValueError(
                f"partition parent {parent!r} collides with a real rule code — "
                "a parent is a selectable group key, not a rule"
            )
        (fixable_kids if handle.fixable else advisory_kids).setdefault(
            parent, []
        ).append(code)
    for parent in fixable_kids.keys() | advisory_kids.keys():
        if not fixable_kids.get(parent):
            raise ValueError(f"partition parent {parent!r} has no fixable sub-rule")
        if not advisory_kids.get(parent):
            raise ValueError(f"partition parent {parent!r} has no advisory sub-rule")


@cache
def _index() -> dict[str, tuple[RuleHandle, bool]]:
    """Build ``code -> (handle, selectable)`` for every baked-in rule.

    Raises ``ValueError`` on any duplicate code across the families, or on a
    malformed partition (``_validate_partitions``).
    """
    entries: list[tuple[RuleHandle, bool]] = []
    entries.extend((codemod_handle(cls), True) for cls in selectable_codemods())
    entries.extend((codemod_handle(cls), False) for cls in non_selectable_codemods())
    entries.extend((fmt_handle(cls), True) for cls in fmt_rules())
    entries.extend((check_handle(cls), True) for cls in advisory_checks())
    index = _build_index(entries)
    _validate_partitions(index)
    return index


def registry() -> dict[str, RuleHandle]:
    """The selectable ``code -> RuleHandle`` map (excludes non-selectable codes)."""
    return {code: handle for code, (handle, sel) in _index().items() if sel}


def all_handles() -> dict[str, RuleHandle]:
    """Every ``code -> RuleHandle``, including the non-selectable codemods."""
    return {code: handle for code, (handle, _sel) in _index().items()}


def by_code(code: str, /) -> RuleHandle:
    """Return the selectable rule for *code*, or raise ``UnknownRuleCode``."""
    handle = registry().get(code)
    if handle is None:
        raise UnknownRuleCode(code)
    return handle


def known_codes() -> frozenset[str]:
    """Every code ``--select`` / ``--ignore`` accept: selectable rules + the
    partition **parent** codes (which expand to their sub-rules, see
    ``resolve.resolve_codes``)."""
    return frozenset(registry()) | parent_codes()


def advisory_codes() -> frozenset[str]:
    """The selectable codes that are advisory (report-only, ``detect_only``).

    These are real rule codes (the ``.2`` sub-rules + the flat advisory checks);
    a partition *parent* is a group, not itself advisory, so it is not included.
    """
    return frozenset(
        code for code, handle in registry().items() if not handle.fixable
    )


@cache
def partition_groups() -> dict[str, tuple[str, ...]]:
    """``parent code -> its sub-rule codes`` (sorted) for every partition practice.

    A partition practice (e.g. ``GTR020``) is the parent of a fixable sub-rule
    (``GTR020.1``) and an advisory residual sub-rule (``GTR020.2``); the grouping is
    derived from each rule's ``RuleMeta.parent`` (registry ``docs/decisions.md`` D10).
    """
    groups: dict[str, list[str]] = {}
    for code, handle in all_handles().items():
        if handle.meta.parent is not None:
            groups.setdefault(handle.meta.parent, []).append(code)
    return {parent: tuple(sorted(children)) for parent, children in groups.items()}


@cache
def parent_codes() -> frozenset[str]:
    """The partition-parent group codes (selectable; not themselves rules)."""
    return frozenset(partition_groups())


def expand_codes(codes: frozenset[str], /) -> frozenset[str]:
    """Replace each partition-parent code with its sub-rule codes; others pass through.

    ``--select GTR020`` selects the whole practice (``GTR020.1`` + ``GTR020.2``);
    ``--ignore GTR020.2`` drops only the advisory residual.
    """
    groups = partition_groups()
    expanded: set[str] = set()
    for code in codes:
        expanded.update(groups.get(code, (code,)))
    return frozenset(expanded)


def display_code(code: str, /) -> str:
    """The code to show a user for a finding — the partition **parent** if *code* is
    a sub-rule, else *code* itself (so both halves of a practice read as one name)."""
    handle = all_handles().get(code)
    if handle is not None and handle.meta.parent is not None:
        return handle.meta.parent
    return code
