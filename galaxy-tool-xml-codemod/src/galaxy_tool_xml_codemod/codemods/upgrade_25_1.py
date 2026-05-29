"""Single-step profile upgrade: 25.1 -> 26.0.

Empirically (a 25.1-stuck corpus sweep), the 26.0 delta tools trip on is the
removal of the obsolete top-level ``<trackster_conf>`` element — the Trackster
visualization config, dropped from the 26.0 schema. ``Upgrade25_1`` removes
every ``<trackster_conf>`` element: the feature no longer exists, so the only
way to validate at 26.0 is to drop it. Like the other upgrade codemods it does
structure only; ``UpdateProfile`` (run by ``UpgradeToLatest``) re-declares
``profile=`` afterwards. See ``docs/decisions.md`` §14.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from galaxy_tool_xml_codemod.module import Module


class Upgrade25_1(CodemodCommand):
    """Upgrade a tool stuck at profile 25.1 toward 26.0 (drop ``<trackster_conf>``)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX011",
        summary=(
            "Upgrade a tool stuck at profile 25.1 toward 26.0"
            " (drop <trackster_conf>)."
        ),
        since="0.0.1",
    )

    def apply(self, module: Module, /) -> None:
        for element in list(module.document.root.iter("trackster_conf")):
            Cursor(element).remove()
