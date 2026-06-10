"""Codemod: trim leading/trailing whitespace from safe-to-trim attributes (GTR035).

Reimplements planemo's `ToolNameWhitespace` / `RequirementVersionWhitespace` linters
(`galaxy.tool_util.linters.general`) — which only *report* — as a fixer, but **only for
the subset where trimming is behaviour-preserving**:

- ``<tool name="…">`` — a **display-contract** claim: ``parse_name`` reads the
  attribute raw (``tool_util/parser/xml.py:220-221``) but the name is a
  display/metadata string, not an addressing key (tools are addressed by ``id``),
  and HTML rendering collapses edge whitespace — the rendered display is
  identical.
- ``<requirement version="…">`` — Galaxy composes the conda spec **verbatim**:
  ``package_specifier = f"{self.package}={self.version}"``
  (``tool_util/deps/conda_util.py:461-465``), passed as a conda CLI argument — a
  whitespace-bearing value never resolved, so a *working* tool never has one;
  trimming only ever repairs an already-broken requirement.

A ``<tool>``'s ``id`` and ``version`` are **deliberately excluded** even though planemo
flags whitespace on them too (`ToolIDWhitespace` / `ToolVersionWhitespace`): Galaxy uses
both **raw** as the tool's identity / version key (`tool_util/parser/xml.py`
``parse_id`` / ``parse_version`` do not strip; ``Tool.id`` / ``Tool.version`` are the
registration and version-comparison keys), so trimming would change a *working* tool's
identity — not behaviour-preserving. Those stay for an advisory check (the ``.2`` style
residual), reported but not auto-fixed. See ``docs/decisions.md`` §33 and
``../../docs/planemo_linter_parity.md``.

Idempotent by construction: after a trim the value equals its ``strip()``, so a re-run
finds nothing. Validity-preserving (the attributes stay strings). Joins
``canonical_codemods()`` — safe, ``profile=``-preserving, runs under ``format``.
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


class TrimAttributeWhitespace(CodemodCommand):
    """Trim whitespace from a tool's ``name`` and a requirement's ``version``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR035",
        summary=(
            "Trim accidental leading/trailing whitespace from a <tool> 'name' and a "
            "<requirement> 'version' (the behaviour-preserving subset; a <tool> 'id'/"
            "'version' are identity-significant and left for the advisory check)."
        ),
        since="0.0.1",
        cite=_IUC,
        order=30,
        rulesets=frozenset({"default", "iuc", "strict"}),
        planemo_linters=frozenset(
            {
                "RequirementVersionWhitespace",
                "ToolNameWhitespace",
            }
        ),
    )

    def detect_Tool(self, cursor: Cursor) -> Iterable[Change]:
        yield from self._trim(cursor, "name")

    def detect_Requirement(self, cursor: Cursor) -> Iterable[Change]:
        yield from self._trim(cursor, "version")

    def _trim(self, cursor: Cursor, attr: str, /) -> Iterable[Change]:
        value = cursor.get_attribute(attr)
        if value is None or value == value.strip():
            return
        stripped = value.strip()
        yield Change(
            code=self.meta.code,
            sourceline=cursor.sourceline,
            xpath=cursor.xpath,
            message=f"<{cursor.tag}> {attr!r} has leading/trailing whitespace",
            mutate=lambda: cursor.set_attribute(attr, stripped),
        )
