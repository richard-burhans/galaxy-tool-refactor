"""Codemod: strip surrounding whitespace from ``<data from_work_dir>`` (GTX014).

From profile 21.09 Galaxy quotes ``from_work_dir`` output filenames, so leading or
trailing whitespace in the attribute becomes a literal part of the path (Galaxy's
``21_09_fix_from_work_dir_whitespace`` *must-fix* upgrade code). Before 21.09 Galaxy
stripped the value itself, so stripping it is a no-op pre-21.09 and, for a tool
upgraded **across** the 21.09 boundary, behaviour-preserving (the stripped path is
what Galaxy ran pre-21.09); for a tool *already* at 21.09+ it is a correctness fix
to an already-broken path (0 such tools in the corpus).

This is a **runtime-gated fix**, not a validity-gated ``upgrade_vN``: a whitespace
``from_work_dir`` is XSD-valid at every profile, so stripping it does not change
``newest_valid_profile`` and cannot ride the ``UpgradeToLatest`` loop. The ``upgrade``
path applies it once a tool reaches profile ≥ 21.09 (``runtime_fixes.py``). It is a
plain detect-primitive codemod — detect reports each whitespace ``from_work_dir``;
``apply`` is derived. See ``docs/decisions.md`` §24.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.codemods._runtime_gated import RuntimeGatedFix
from galaxy_tool_xml_codemod.cursor import Cursor


class FixFromWorkDirWhitespace(RuntimeGatedFix):
    """Strip surrounding whitespace from every ``<data from_work_dir>`` value."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX014",
        summary=(
            "Strip surrounding whitespace from <data from_work_dir>"
            " (literal at profile >= 21.09)."
        ),
        since="0.0.1",
        cite="https://github.com/galaxyproject/galaxy/pull/12536",
    )

    introduced_profile: ClassVar[str] = "21.09"

    def detect_Data(self, cursor: Cursor) -> Iterable[Change]:
        value = cursor.get_attribute("from_work_dir")
        if value is None or value == value.strip():
            return
        stripped = value.strip()
        yield Change(
            code=self.meta.code,
            sourceline=cursor.sourceline,
            xpath=cursor.xpath,
            message="<data from_work_dir> has surrounding whitespace",
            mutate=lambda: cursor.set_attribute("from_work_dir", stripped),
        )
