"""Profile-version upgrade registry and the ``UpgradeToLatest`` orchestrator.

Each entry in ``UPGRADE_CODEMODS`` is a single-step upgrade: a codemod that
makes the structural changes a tool stuck at version ``N`` needs to validate at
the next vendored version. ``UpgradeToLatest`` drives them in a loop, declaring
the newest valid profile (``UpdateProfile``) between steps, until the tool
reaches the latest profile or hits a sticking version with no registered
upgrade.

The registry is grown empirically: a corpus discovery sweep reports tools that
do not reach the latest profile and the version they stick at; each distinct
sticking version that real tools hit gets a new single-step codemod here. See
``docs/decisions.md`` §14.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from galaxy_tool_xml.binding import newest_valid_profile
from galaxy_tool_xml.profiles import available_profiles, latest_profile

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.update_profile import UpdateProfile
from galaxy_tool_xml_codemod.codemods.upgrade_24_1 import Upgrade24_1

if TYPE_CHECKING:
    from galaxy_tool_xml_codemod.module import Module

# Sticking version -> the codemod that upgrades a tool one step past it.
UPGRADE_CODEMODS: dict[str, type[CodemodCommand]] = {
    "24.1": Upgrade24_1,
}


class UpgradeToLatest(CodemodCommand):
    """Iteratively upgrade a tool toward the latest profile.

    Each round re-declares the newest valid profile and, if that is below the
    latest, applies the registered single-step upgrade for it. Stops at the
    latest profile, at a sticking version with no registered upgrade, or if a
    round makes no progress (the same version twice) — the last two leave the
    tool validating at the best version reached, which ``UpdateProfile`` has
    already declared.
    """

    def apply(self, module: Module, /) -> None:
        latest = latest_profile()
        seen: set[str] = set()
        # Bounded by the version count: each productive round advances to a
        # strictly newer version, and the ``seen`` guard halts non-advancing
        # ones — the range is a belt-and-braces termination backstop.
        for _ in range(len(available_profiles()) + 1):
            UpdateProfile().apply(module)
            version = newest_valid_profile(module.document)
            if version is None or version == latest or version in seen:
                return
            seen.add(version)
            upgrade = UPGRADE_CODEMODS.get(version)
            if upgrade is None:
                return  # unhandled sticking point — the discovery sweep reports it
            upgrade().apply(module)
