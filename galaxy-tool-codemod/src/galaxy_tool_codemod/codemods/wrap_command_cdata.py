"""Codemod: wrap a pure-text ``<command>`` body in CDATA (GTR018, IUC #34).

Galaxy runs the ``<command>`` body through Cheetah then a shell, so shell operators
(``&&``, ``<``, ``|``) are common; the IUC best practice is to wrap the body in a
``<![CDATA[…]]>`` section so those stay literal without XML-escaping. This codemod
performs the lexical wrap for the *pure-text* subset (see ``_cdata.cdata_wrap_change``
for the eligibility predicate); it is behaviour-preserving (only the serialised bytes
change, not the value Galaxy runs) and so rides the canonical/``format`` pipeline.
The advisory ``GTR018.2`` check remains the detector for the mixed-content residual
this codemod skips. See ``docs/decisions.md`` §29.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.codemods._cdata import cdata_wrap_change
from galaxy_tool_codemod.cursor import Cursor


class WrapCommandCdata(CodemodCommand):
    """Wrap a pure-text ``<command>`` body in a ``<![CDATA[…]]>`` section."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR018.1",
        parent="GTR018",
        summary="Wrap a pure-text <command> body in CDATA (IUC #34).",
        since="0.0.1",
        cite="https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html",
        order=90,
        rulesets=frozenset({"default", "iuc", "strict"}),
    )

    def detect_Command(self, cursor: Cursor) -> Iterable[Change]:
        change = cdata_wrap_change(cursor, code=self.meta.code, element="command")
        if change is not None:
            yield change
