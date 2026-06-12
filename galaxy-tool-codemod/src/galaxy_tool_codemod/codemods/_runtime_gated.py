"""Base class for runtime-gated fixes (see ``runtime_fixes.py`` for the rationale).

A ``RuntimeGatedFix`` is an ordinary detect-primitive ``CodemodCommand`` that also
declares ``introduced_profile`` — the vendored profile version at which the Galaxy
behaviour change it corrects takes effect. The ``upgrade`` path applies the fix only
when the tool reaches a profile at or above that version. Lives in its own leaf
module so concrete fixes can subclass it without a cycle through the
``runtime_fixes`` registry.
"""

from __future__ import annotations

from typing import ClassVar

from galaxy_tool_codemod.codemod import CodemodCommand


class RuntimeGatedFix(CodemodCommand):
    """A codemod for a runtime (non-XSD) profile change, gated on its profile."""

    introduced_profile: ClassVar[str]
    # The Galaxy behaviour code this fix clears: a ``PROFILE_UPGRADE_CODES``
    # name whose ``profile`` equals ``introduced_profile`` (pinned by
    # ``test_every_fix_declares_its_galaxy_upgrade_code``). The behavior gate
    # maps blockers to their auto-fixes through this.
    upgrade_code: ClassVar[str]
