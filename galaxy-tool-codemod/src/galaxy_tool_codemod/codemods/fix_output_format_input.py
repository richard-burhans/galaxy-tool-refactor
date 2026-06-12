"""Codemod: replace output ``format="input"`` with ``format_source`` (GTR015).

From profile 16.04 Galaxy disables ``format="input"`` on a tool output — the
behaviour was ill-defined (Galaxy's ``16_04_fix_output_format`` *must-fix* code).
The fix is to inherit the format from a specific input via
``format_source="<input name>"``.

Choosing *which* input is author intent in general, but it is unambiguous when the
tool has **exactly one data input** — top-level or nested. Galaxy keys the
``input_datasets`` map ``format_source`` is resolved against by the **prefixed
(qualified) name** (``actions/__init__.py``): a conditional or section ancestor
contributes ``name|`` (a ``<when>`` contributes nothing), so a sole nested input is
addressed as ``cond|input`` — an upstream-tested feature
(``test/functional/tools/format_source_in_conditional.xml``). A **repeat** ancestor
is the one nesting with no static address (its prefix is instance-indexed,
``r_0|``), so it still bails. Behaviour also matches when the input is *absent* at
runtime (an unselected branch / an empty optional): pre-16.04 ``format="input"``
resolved to ``"data"`` with no datasets in the form, and a missing
``format_source`` key falls through to the parsed format default — also ``"data"``
(``xml.py``; Galaxy's conditional test tool exercises exactly this fallthrough).
Tools with zero or two-or-more data inputs are left for the §23 upgrade warning
(with several inputs, pre-16.04 ``format="input"`` resolved to the *last* form
input's ext — under Galaxy's own ``TODO``-marked nondeterminism there is no
deterministic behaviour to preserve). An output that already carries a
``format_source`` is also left alone — ``format="input"`` is inert there (Galaxy's
format_source branch wins at runtime), so the author's source must not be
overwritten. (Originally top-level-only — 109 corpus tools; the 2026-06-10
widening to qualified nested names is ``docs/decisions.md`` §40.)

A runtime-gated fix (``runtime_fixes.py``): ``format="input"`` is XSD-valid, so this
does not change ``newest_valid_profile`` and cannot ride the ``UpgradeToLatest``
loop. ``detect`` is overridden (not the per-tag walk) because the fix needs
whole-tool context — the single data input — to choose ``format_source``; ``apply``
is still derived from ``detect``. See ``docs/decisions.md`` §24.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemods._runtime_gated import RuntimeGatedFix
from galaxy_tool_codemod.cursor import Cursor

if TYPE_CHECKING:
    from lxml import etree

    from galaxy_tool_codemod.module import Module


# Grouping ancestors that contribute a ``name|`` segment to the runtime prefixed
# name (visit_input_values: conditional + section); ``<when>`` is transparent. A
# ``<repeat>`` prefix is instance-indexed (``r_0|``) — no static address — so any
# other ancestor tag bails.
_QUALIFYING_TAGS = frozenset({"conditional", "section"})


def _sole_data_input_qualified_name(root: etree._Element, /) -> str | None:
    """The qualified ``format_source`` name of the tool's single data input.

    ``None`` unless there is exactly one ``<param type="data">`` under
    ``<inputs>``, it has a non-empty ``name``, and every grouping ancestor is a
    *statically addressable* one — a named ``<conditional>`` / ``<section>``
    (each contributing ``name|``, matching Galaxy's runtime prefixed name) or a
    transparent ``<when>``. A top-level input yields its bare name; a repeat
    ancestor (instance-indexed prefix) or an unnamed grouping yields ``None``.
    """
    inputs = root.find("inputs")
    if inputs is None:
        return None
    data_params = [p for p in inputs.iter("param") if p.get("type") == "data"]
    if len(data_params) != 1:
        return None
    sole = data_params[0]
    name = sole.get("name")
    if not name:
        return None
    segments = [name]
    node = sole.getparent()
    while node is not None and node is not inputs:
        if node.tag in _QUALIFYING_TAGS:
            segment = node.get("name")
            if not segment:
                return None
            segments.append(segment)
        elif node.tag != "when":
            return None  # repeat (indexed prefix) or unknown grouping
        node = node.getparent()
    if node is None:
        return None  # defensive: param not actually under <inputs>
    return "|".join(reversed(segments))


def _swap_format_for_source(cursor: Cursor, source_name: str) -> Callable[[], None]:
    """Return a thunk that sets ``format_source`` and drops ``format`` on *cursor*."""

    def mutate() -> None:
        cursor.set_attribute("format_source", source_name)
        cursor.delete_attribute("format")

    return mutate


class FixOutputFormatInput(RuntimeGatedFix):
    """Rewrite output ``<data format="input">`` to ``format_source`` (single input)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR015",
        summary=(
            'Replace output <data format="input"> with format_source for a tool'
            " with a sole data input (qualified name when nested)."
        ),
        since="0.0.1",
        cite="https://github.com/galaxyproject/galaxy/pull/1688",
        planemo_linters=frozenset({"OutputsFormatInput"}),
    )

    introduced_profile: ClassVar[str] = "16.04"
    upgrade_code: ClassVar[str] = "16_04_fix_output_format"

    def detect(self, module: Module, /) -> Iterator[Change]:
        root = module.document.root
        source_name = _sole_data_input_qualified_name(root)
        if source_name is None:
            return  # 0, 2+, or a repeat-nested single input — needs author intent
        outputs = root.find("outputs")
        if outputs is None:
            return
        for data in outputs.iter("data"):
            if data.get("format") != "input":
                continue
            if data.get("format_source") is not None:
                # ``format="input"`` is already inert when a ``format_source`` is
                # present — Galaxy's format_source branch overrides it
                # (actions/__init__.py). Leave the author's existing source (which may
                # point at a collection or a different input) for the §23 warning.
                continue
            cursor = Cursor(data)
            yield Change(
                code=self.meta.code,
                sourceline=cursor.sourceline,
                xpath=cursor.xpath,
                message=(
                    'output format="input" replaced with'
                    f' format_source="{source_name}"'
                ),
                mutate=_swap_format_for_source(cursor, source_name),
            )
