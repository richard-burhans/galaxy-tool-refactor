"""Profile-version upgrade registry and the ``UpgradeToLatest`` orchestrator.

Each entry in ``UPGRADE_CODEMODS`` is a single-step upgrade: a codemod that
makes the structural changes a tool stuck at version ``N`` needs to validate at
the next vendored version. ``UpgradeToLatest`` drives them in a loop, declaring
the newest valid profile (``UpdateProfile``) between steps, until the tool
reaches the latest profile or hits a sticking version with no registered
upgrade.

The registry is grown empirically: a corpus discovery sweep reports tools that
do not reach the latest profile and the version they stick at; each distinct
sticking version that real tools hit gets a new single-step codemod here.
Beyond the corpus, ``UpgradeToLatest`` reports at *runtime* whenever it stalls
at a sub-latest profile with no registered upgrade — it logs a warning and
exposes ``missing_upgrade()`` — so a tool that needs an as-yet-unwritten
``upgrade_vN`` (e.g. one not represented in the corpus, run through fmt's
canonical pipeline) is surfaced rather than silently left behind. See
``docs/decisions.md`` §14.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_source.binding import newest_valid_profile
from galaxy_tool_source.profiles import latest_profile

from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.codemods._coarse_detect import coarse_detect
from galaxy_tool_codemod.codemods.update_profile import UpdateProfile
from galaxy_tool_codemod.codemods.upgrade_19_01 import Upgrade19_01
from galaxy_tool_codemod.codemods.upgrade_21_09 import Upgrade21_09
from galaxy_tool_codemod.codemods.upgrade_24_0 import Upgrade24_0
from galaxy_tool_codemod.codemods.upgrade_24_1 import Upgrade24_1
from galaxy_tool_codemod.codemods.upgrade_25_1 import Upgrade25_1

if TYPE_CHECKING:
    from collections.abc import Iterator

    from galaxy_tool_codemod.change import Change
    from galaxy_tool_codemod.module import Module

logger = logging.getLogger(__name__)

# Sticking version -> the codemod that upgrades a tool one step past it.
UPGRADE_CODEMODS: dict[str, type[CodemodCommand]] = {
    "19.01": Upgrade19_01,
    "21.09": Upgrade21_09,
    "24.0": Upgrade24_0,
    "24.1": Upgrade24_1,
    "25.1": Upgrade25_1,
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

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR012",
        summary="Iteratively upgrade a tool toward the latest profile.",
        since="0.0.1",
    )

    def __init__(self) -> None:
        # From-versions the most recent ``apply`` advanced the tool past, in
        # order. Read via ``upgrade_steps_applied`` for per-step sweep stats.
        self._applied_upgrades: list[str] = []
        # Sub-latest version the most recent ``apply`` stalled at with no
        # registered upgrade codemod, or ``None``. Read via ``missing_upgrade``.
        self._missing_upgrade: str | None = None

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self, module, message="tool would be upgraded toward the latest profile"
        )

    def apply(self, module: Module, /) -> None:
        self._applied_upgrades = []
        self._missing_upgrade = None
        latest = latest_profile()
        seen: set[str] = set()
        # One stateless instance, re-declared each round (matches the sweep's
        # "reuse a single codemod instance" rationale).
        update_profile = UpdateProfile()
        update_profile.apply(module)
        version = newest_valid_profile(module.document)
        # Each productive round advances to a strictly newer version; the
        # ``seen`` guard halts a non-advancing round so the loop terminates.
        while version is not None and version != latest and version not in seen:
            seen.add(version)
            upgrade = UPGRADE_CODEMODS.get(version)
            if upgrade is None:
                # A profile real tools validate at, below the latest, with no
                # upgrade codemod yet. Report it (the corpus discovery sweep
                # only sees corpus tools; this catches everything else — e.g.
                # a user's tool run through fmt's canonical pipeline) so the
                # missing upgrade_vN gets written.
                self._missing_upgrade = version
                logger.warning(
                    "no upgrade codemod for profile %s: the tool validates "
                    "there but the latest profile is %s — an upgrade for %s "
                    "needs to be implemented",
                    version,
                    latest,
                    version,
                )
                return
            upgrade().apply(module)
            update_profile.apply(module)
            new_version = newest_valid_profile(module.document)
            if new_version != version:
                # The step advanced the tool — credit it to this from-version.
                self._applied_upgrades.append(version)
            version = new_version

    def upgrade_steps_applied(self) -> tuple[str, ...]:
        return tuple(self._applied_upgrades)

    def missing_upgrade(self) -> str | None:
        """The sub-latest version the last ``apply`` lacked an upgrade for.

        ``None`` when the tool reached the latest profile, or stalled at a
        version that *does* have an upgrade codemod (one that simply could not
        advance this particular tool). A non-``None`` value names a profile for
        which an ``upgrade_vN`` codemod still needs to be written.
        """
        return self._missing_upgrade
