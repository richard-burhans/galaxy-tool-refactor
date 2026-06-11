"""Codemod: drop a `<param>` ``name`` that its ``argument`` already implies (GTR037).

Reimplements planemo's `InputsNameRedundantArgument` linter
(`galaxy.tool_util.linters.inputs`) — report-only — as a fixer.

Galaxy derives a parameter's name from ``argument`` when ``name`` is absent:
``_parse_name(None, argument) = argument.lstrip("-").replace("-", "_")``
(`tool_util/parser/util.py`). So when a ``<param>`` declares **both** and the declared
``name`` *equals* that derived name, the ``name`` is redundant — dropping it leaves
Galaxy computing the identical name, and every Cheetah ``$name`` reference / by-name
cross-reference keeps resolving unchanged.

**Validity-safe across every profile.** ``param/@name`` is optional in all 28 vendored
XSDs that allow ``argument`` (verified: none require ``name`` while permitting
``argument`` — the two were coupled in Galaxy's schema evolution), so dropping it never
invalidates a tool that currently validates — including novel tool XML, not just the
corpus.

Acts only on a ``<param>`` under ``<inputs>`` (an input *definition*): a
``<test><param>`` is matched by name and must keep it. Idempotent (after the drop there
is no ``name`` to match). Joins ``canonical_codemods()``. See ``docs/decisions.md`` §35
and ``../../docs/planemo_linter_parity.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemod import CodemodCommand

if TYPE_CHECKING:
    from collections.abc import Iterable

    from galaxy_tool_codemod.cursor import Cursor

_IUC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"


def _derived_name(argument: str, /) -> str:
    """Galaxy's name-from-argument derivation (`_parse_name(None, argument)`)."""
    return argument.lstrip("-").replace("-", "_")


def _under_inputs(cursor: Cursor, /) -> bool:
    """Whether *cursor* sits anywhere under an ``<inputs>`` (an input definition)."""
    node = cursor.parent()
    while node is not None:
        if node.tag == "inputs":
            return True
        node = node.parent()
    return False


class DropRedundantParamName(CodemodCommand):
    """Drop a `<param>` ``name`` equal to the name its ``argument`` already implies."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR037",
        summary=(
            "Drop a <param> 'name' that equals the name Galaxy derives from its "
            "'argument' (redundant; argument implies the same name)."
        ),
        since="0.0.1",
        cite=_IUC,
        order=50,
        rulesets=frozenset({"default", "iuc", "strict"}),
        planemo_linters=frozenset({"InputsNameRedundantArgument"}),
    )

    def detect_Param(self, cursor: Cursor) -> Iterable[Change]:
        argument = cursor.get_attribute("argument")
        name = cursor.get_attribute("name")
        if argument is None or name is None:
            return
        if name != _derived_name(argument):
            return  # name carries info the argument doesn't imply — keep it
        if not _under_inputs(cursor):
            return  # a <test><param> is matched by name, never argument-derived
        yield Change(
            code=self.meta.code,
            sourceline=cursor.sourceline,
            xpath=cursor.xpath,
            message=f"drop redundant name='{name}' (argument '{argument}' implies it)",
            mutate=lambda: cursor.delete_attribute("name"),
        )
