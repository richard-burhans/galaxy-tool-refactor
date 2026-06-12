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

import copy
import logging
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_source.binding import newest_valid_profile, oldest_valid_profile
from galaxy_tool_source.profiles import latest_profile

from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.codemods._coarse_detect import coarse_detect
from galaxy_tool_codemod.codemods._validation_repair import restore_root
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
    """Iteratively upgrade a tool toward the latest profile (or a ceiling).

    Each round re-declares the newest valid profile and, if that is below the
    target, applies the registered single-step upgrade for it. The target is
    the latest vendored profile, or the *ceiling* when one is given; the
    behavior gate (``behavior_gate``) passes the newest profile reachable
    without crossing an applicable, unfixable behaviour change. Stops at the
    target, at a sticking version with no registered upgrade, or if a round
    makes no progress (the same version twice); the last two leave the tool
    validating at the best version reached, which ``UpdateProfile`` has
    already declared. A stall *at the ceiling* is deliberate and not reported.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR012",
        summary="Iteratively upgrade a tool toward the latest profile.",
        since="0.0.1",
    )

    def __init__(self, *, ceiling: str | None = None) -> None:
        # The newest profile the walk may reach (a behaviour boundary from the
        # behavior gate, or an explicit user target); ``None`` walks to the
        # latest vendored profile. Stalling AT the ceiling is a deliberate cap,
        # not a missing ``upgrade_vN``, so it is never warned about.
        self._ceiling = ceiling
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
        target = self._ceiling if self._ceiling is not None else latest_profile()
        seen: set[str] = set()
        # One stateless instance, re-declared each round (matches the sweep's
        # "reuse a single codemod instance" rationale).
        update_profile = UpdateProfile(ceiling=self._ceiling)
        update_profile.apply(module)
        version = newest_valid_profile(module.document, ceiling=self._ceiling)
        # Each productive round advances to a strictly newer version; the
        # ``seen`` guard halts a non-advancing round so the loop terminates.
        while version is not None and version != target and version not in seen:
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
                    "there but the target profile is %s; an upgrade for %s "
                    "needs to be implemented",
                    version,
                    target,
                    version,
                )
                return
            upgrade().apply(module)
            update_profile.apply(module)
            new_version = newest_valid_profile(module.document, ceiling=self._ceiling)
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


class UpgradeToValid(CodemodCommand):
    """Declare the *minimum* profile at or above a floor the tool validates at.

    The minimal-bump counterpart of ``UpgradeToLatest``: where that walks a
    tool as far toward the latest profile as the behaviour gate allows, this
    moves ``profile=`` no further than validity strictly requires. It backs the
    ``upgrade`` default of not bumping a profile unless the tool is invalid
    where it sits (registry facade policy; the modernize path keeps using
    ``UpgradeToLatest``).

    *floor* is the tool's resolved baseline (its declared ``profile=``, or
    Galaxy's ``16.01`` legacy default when undeclared). Behaviour:

    - The (already-repaired) tool validates at some profile at or above the
      floor as-is → declare exactly the **oldest** such profile via
      ``UpdateProfile`` and stop. When that profile equals an existing
      declaration the apply is a byte no-op; an undeclared tool gains the floor.
    - Nothing at or above the floor validates as-is → step through
      ``UPGRADE_CODEMODS`` (the same single-step structural upgrades
      ``UpgradeToLatest`` uses), re-probing after each step, and declare the
      first profile at or above the floor that a step unblocks. The declaration
      lands once, at the minimum — no intermediate ``UpdateProfile``.
    - A stall (a sticking version with no registered upgrade, or a step that
      cannot advance the tool) reverts any structural steps it tried and leaves
      the tool byte-untouched, reporting the floor via ``unreachable_floor``
      (the caller fails the tool closed).

    This never lowers a profile: ``oldest_valid_profile`` only considers
    profiles at or above the floor, so the declaration is always >= the
    baseline.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR097",
        summary=(
            "Declare the minimum profile at or above the baseline the tool"
            " validates at."
        ),
        since="0.0.1",
    )

    def __init__(self, *, floor: str) -> None:
        # The tool's resolved baseline; the declaration never falls below it.
        self._floor = floor
        # From-versions a structural step advanced the tool past, in order.
        self._applied_upgrades: list[str] = []
        # The floor, when no profile at or above it could be reached, else
        # ``None``. Read via ``unreachable_floor``.
        self._unreachable_floor: str | None = None

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self,
            module,
            message="profile= would be set to the minimum validating profile",
        )

    def apply(self, module: Module, /) -> None:
        self._applied_upgrades = []
        self._unreachable_floor = None
        document = module.document
        needed = oldest_valid_profile(document, floor=self._floor)
        if needed is not None:
            UpdateProfile(ceiling=needed).apply(module)
            return
        # Nothing at or above the floor validates as-is; step structurally,
        # re-probing for the minimum after each advancing step. Snapshot first so
        # a walk that advances partway but stalls below the floor is fully
        # reverted — "unreachable" leaves the tool byte-untouched by construction,
        # never half-upgraded with the profile undeclared.
        snapshot = copy.deepcopy(document.root)
        seen: set[str] = set()
        version = newest_valid_profile(document)
        while version is not None and version not in seen:
            seen.add(version)
            upgrade = UPGRADE_CODEMODS.get(version)
            if upgrade is None:
                break
            upgrade().apply(module)
            new_version = newest_valid_profile(document)
            if new_version != version:
                self._applied_upgrades.append(version)
            needed = oldest_valid_profile(document, floor=self._floor)
            if needed is not None:
                UpdateProfile(ceiling=needed).apply(module)
                return
            version = new_version
        restore_root(document.root, snapshot)
        self._applied_upgrades = []
        self._unreachable_floor = self._floor

    def upgrade_steps_applied(self) -> tuple[str, ...]:
        return tuple(self._applied_upgrades)

    def unreachable_floor(self) -> str | None:
        """The floor when no profile at or above it could be reached, else ``None``.

        A non-``None`` value means the tool validates nowhere at or above its
        baseline, even after the structural steps — a pre-existing breakage a
        profile bump cannot fix. The apply reverts any steps it tried and leaves
        such a tool byte-untouched.
        """
        return self._unreachable_floor
