"""Codemod: replace a deprecated ``<output type="data">`` with ``<data>`` (GTR036).

Reimplements planemo's `OutputsOutput` linter (`galaxy.tool_util.linters.output`,
*"Avoid the use of 'output' and replace by 'data' or 'collection'"*) — which only
reports — as a fixer, for the **behaviour-preserving** case.

Galaxy routes a `<outputs>` child by tag (`tool_util/parser/xml.py`): an
``<output type="data">`` is parsed by the *same* ``_parse`` as a ``<data>``, so renaming
the element to ``<data>`` and dropping the now-redundant ``type="data"`` is a pure
no-op for Galaxy.

**Scope — ``type="data"`` and ``type="collection"`` (when provable).** Galaxy's
deprecated-collection path (`parser/xml.py:548-563`) remaps in place —
``attrib["type"] = unicodify(collection_type)``, ``attrib["type_source"] =
unicodify(collection_type_source)`` — then parses via the *same*
``_parse_collection`` as a ``<collection>``. ``unicodify(None)`` is ``None``
(the typed overload, ``util/__init__.py:1190-1196``), and ``None`` reads
identically to an absent attribute, so when ``collection_type`` is **present**
the rewrite mirrors the remap exactly: rename the tag to ``<collection>``,
``collection_type`` → ``type``, ``collection_type_source`` → ``type_source``
(when present), drop the old ``type`` discriminator. Two cases stay flagged
(advisory), not rewritten:

- ``<output type="collection">`` with **no** ``collection_type`` — the
  deprecated path stores ``type=None`` (degenerate); no provable rewrite.
- ``<output>`` with no ``type`` — an *expression* output (`_parse_expression`),
  a different output kind, not a data rename.
- ``<output … from="…">`` — also an *expression* output (routed by ``from``, which
  may carry ``type="data"`` too). ``from`` is not valid on ``<data>``/``<collection>``,
  so converting it breaks validity; any output with a ``from`` attribute is skipped
  (found by the corpus fork proof on ``tools/pick_value``).

Only acts on ``<output>`` whose parent is ``<outputs>`` — an ``<output>`` under
``<test>`` is a test assertion, not an output definition. Idempotent (after the rename
there is no ``<output>`` left to match). See ``docs/decisions.md`` §34 and
``../../docs/planemo_linter_parity.md``.
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


def _to_data(cursor: Cursor, /) -> None:
    """Rename ``<output type="data">`` to ``<data>`` and drop the redundant ``type``."""
    cursor.delete_attribute("type")
    cursor.rename_tag("data")


def _to_collection(cursor: Cursor, /) -> None:
    """Mirror Galaxy's deprecated-collection remap (module docstring) statically."""
    cursor.delete_attribute("type")  # the "collection" discriminator, now the tag
    cursor.rename_attribute("collection_type", "type")
    if cursor.get_attribute("collection_type_source") is not None:
        cursor.rename_attribute("collection_type_source", "type_source")
    cursor.rename_tag("collection")


class ReplaceOutputElement(CodemodCommand):
    """Replace a deprecated ``<outputs><output type="data">`` with ``<data>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR036",
        summary=(
            'Replace a deprecated <outputs><output type="data"> with <data>, and'
            ' <output type="collection"> with <collection> via Galaxy\'s own'
            " attribute remap (expression / degenerate outputs are left for the"
            " advisory check)."
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
        if cursor.get_attribute("from") is not None:
            # An expression tool's output (`<output type="data" … from="output">`) is
            # routed by `from`, not the deprecated-output path, and `from` is not a
            # valid attribute on <data>/<collection>, so a rename would break
            # validity. Leave it for the advisory check. (Found by the corpus fork
            # proof on tools/pick_value; docs/decisions.md §34.)
            return
        output_type = cursor.get_attribute("type")
        if output_type == "data":
            yield Change(
                code=self.meta.code,
                sourceline=cursor.sourceline,
                xpath=cursor.xpath,
                message='replace deprecated <output type="data"> with <data>',
                mutate=lambda: _to_data(cursor),
            )
            return
        if (
            output_type == "collection"
            and cursor.get_attribute("collection_type") is not None
        ):
            yield Change(
                code=self.meta.code,
                sourceline=cursor.sourceline,
                xpath=cursor.xpath,
                message=(
                    'replace deprecated <output type="collection"> with'
                    " <collection> (Galaxy's own attribute remap)"
                ),
                mutate=lambda: _to_collection(cursor),
            )
        # else: expression output / degenerate collection — advisory territory
