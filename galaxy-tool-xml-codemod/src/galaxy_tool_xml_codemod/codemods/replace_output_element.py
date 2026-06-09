"""Codemod: replace a deprecated ``<output type="data">`` with ``<data>`` (GTR036).

Reimplements planemo's `OutputsOutput` linter (`galaxy.tool_util.linters.output`,
*"Avoid the use of 'output' and replace by 'data' or 'collection'"*) — which only
reports — as a fixer, for the **behaviour-preserving** case.

Galaxy routes a `<outputs>` child by tag (`tool_util/parser/xml.py`): an
``<output type="data">`` is parsed by the *same* ``_parse`` as a ``<data>``, so renaming
the element to ``<data>`` and dropping the now-redundant ``type="data"`` is a pure
no-op for Galaxy.

**Scope — ``type="data"`` only.** Two siblings are deliberately left flagged (advisory),
not rewritten:

- ``<output type="collection">`` — Galaxy remaps ``collection_type`` → ``type`` and
  ``collection_type_source`` → ``type_source`` and fills ``type_source`` via
  ``unicodify(None)`` when the source attribute is absent, so a literal rename is not
  provably equivalent. Deferred.
- ``<output>`` with no ``type`` — an *expression* output (`_parse_expression`), a
  different output kind, not a data rename.

Only acts on ``<output>`` whose parent is ``<outputs>`` — an ``<output>`` under
``<test>`` is a test assertion, not an output definition. Idempotent (after the rename
there is no ``<output>`` left to match). See ``docs/decisions.md`` §34 and
``../../docs/planemo_linter_parity.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.codemod import CodemodCommand

if TYPE_CHECKING:
    from collections.abc import Iterable

    from galaxy_tool_xml_codemod.cursor import Cursor

_IUC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"


def _to_data(cursor: Cursor, /) -> None:
    """Rename ``<output type="data">`` to ``<data>`` and drop the redundant ``type``."""
    cursor.delete_attribute("type")
    cursor.rename_tag("data")


class ReplaceOutputElement(CodemodCommand):
    """Replace a deprecated ``<outputs><output type="data">`` with ``<data>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR036",
        summary=(
            'Replace a deprecated <outputs><output type="data"> with <data> '
            "(collection / expression outputs are left for the advisory check)."
        ),
        since="0.0.1",
        cite=_IUC,
        order=40,
        rulesets=frozenset({"default", "iuc", "strict"}),
        planemo_linters=frozenset({"OutputsOutput"}),
    )

    def detect_Output(self, cursor: Cursor) -> Iterable[Change]:
        parent = cursor.parent()
        if parent is None or parent.tag != "outputs":
            return  # a <test><output> is a test assertion, not an output definition
        if cursor.get_attribute("type") != "data":
            return  # collection / expression outputs are out of scope (see module doc)
        yield Change(
            code=self.meta.code,
            sourceline=cursor.sourceline,
            xpath=cursor.xpath,
            message='replace deprecated <output type="data"> with <data>',
            mutate=lambda: _to_data(cursor),
        )
