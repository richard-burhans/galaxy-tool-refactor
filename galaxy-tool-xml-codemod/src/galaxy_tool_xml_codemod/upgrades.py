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
from galaxy_tool_xml.profiles import latest_profile

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

    def __init__(self) -> None:
        # From-versions the most recent ``apply`` advanced the tool past, in
        # order. Read via ``upgrade_steps_applied`` for per-step sweep stats.
        self._applied_upgrades: list[str] = []

    def apply(self, module: Module, /) -> None:
        self._applied_upgrades = []
        latest = latest_profile()
        seen: set[str] = set()
        UpdateProfile().apply(module)
        version = newest_valid_profile(module.document)
        # Each productive round advances to a strictly newer version; the
        # ``seen`` guard halts a non-advancing round so the loop terminates.
        while version is not None and version != latest and version not in seen:
            seen.add(version)
            upgrade = UPGRADE_CODEMODS.get(version)
            if upgrade is None:
                return  # unhandled sticking point — the discovery sweep reports it
            upgrade().apply(module)
            UpdateProfile().apply(module)
            new_version = newest_valid_profile(module.document)
            if new_version != version:
                # The step advanced the tool — credit it to this from-version.
                self._applied_upgrades.append(version)
            version = new_version

    def upgrade_steps_applied(self) -> tuple[str, ...]:
        return tuple(self._applied_upgrades)
