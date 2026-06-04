"""Codemod: wrap a pure-text ``<help>`` body in CDATA (GTR019, IUC #42).

The IUC best practice wraps the ``<help>`` body in a ``<![CDATA[…]]>`` section so
reStructuredText markup (``<``, ``&``, backslashes, directive blocks) stays literal
without XML-escaping. This codemod performs the lexical wrap for the *pure-text*
subset (shared eligibility predicate in ``_cdata.cdata_wrap_change``); it is
behaviour-preserving — lxml already exposes the entity-unescaped help text, so only
the serialised bytes change, not the text Galaxy renders. The advisory ``GTR030``
check remains the detector for the mixed-content residual this codemod skips. See
``docs/decisions.md`` §29.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods._cdata import cdata_wrap_change
from galaxy_tool_xml_codemod.cursor import Cursor


class WrapHelpCdata(CodemodCommand):
    """Wrap a pure-text ``<help>`` body in a ``<![CDATA[…]]>`` section."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR019",
        summary="Wrap a pure-text <help> body in CDATA (IUC #42).",
        since="0.0.1",
        cite="https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html",
    )

    def detect_Help(self, cursor: Cursor) -> Iterable[Change]:
        change = cdata_wrap_change(cursor, code=self.meta.code, element="help")
        if change is not None:
            yield change
