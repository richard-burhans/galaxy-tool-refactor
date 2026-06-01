"""Runtime-gated fixes: corrections for profile changes the XSD does NOT enforce.

The ``upgrade_vN`` codemods (``upgrades.py``) are **validity-gated** — each makes a
tool valid at the next vendored profile, and ``UpgradeToLatest`` advances only when
``newest_valid_profile`` improves. But some Galaxy profile changes are *runtime*
behaviours that leave the XSD happy: e.g. from 21.09 ``from_work_dir`` filenames are
quoted, so surrounding whitespace becomes literal. Applying the fix (strip it) does
**not** change validity, so it cannot ride the ``UpgradeToLatest`` loop.

A ``RuntimeGatedFix`` is a normal detect-primitive ``CodemodCommand`` plus an
``introduced_profile`` marker. The ``upgrade`` path applies each fix whose
``introduced_profile`` is at or below the profile the tool actually reached — so a
tool that stalls below it is untouched (Galaxy ran it under the old behaviour). Each
fix mirrors a Galaxy ``must_fix`` upgrade code (see
``profile_semantics.PROFILE_UPGRADE_CODES`` and ``docs/decisions.md`` §24). These are
**upgrade-only**: in ``coded_codemods()`` but not ``CANONICAL_CODEMODS``, so they
never run under ``format`` / the ``iuc`` preset and never change ``profile=``.
"""

from __future__ import annotations

from packaging.version import Version

from galaxy_tool_xml_codemod.codemods._runtime_gated import RuntimeGatedFix
from galaxy_tool_xml_codemod.codemods.fix_from_work_dir_whitespace import (
    FixFromWorkDirWhitespace,
)
from galaxy_tool_xml_codemod.codemods.fix_output_format_input import (
    FixOutputFormatInput,
)

# Every runtime-gated fix, in application order.
RUNTIME_GATED_FIXES: tuple[type[RuntimeGatedFix], ...] = (
    FixOutputFormatInput,
    FixFromWorkDirWhitespace,
)


def runtime_fixes_for(profile: str, /) -> tuple[type[RuntimeGatedFix], ...]:
    """Return the runtime-gated fixes that apply at a reached *profile*.

    A fix applies when its ``introduced_profile`` is at or below *profile* — i.e.
    the tool will run under the new behaviour. *profile* is a vendored version
    string (the upgrade target); callers pass a resolved profile, never ``None``.
    """
    reached = Version(profile)
    return tuple(
        fix for fix in RUNTIME_GATED_FIXES if Version(fix.introduced_profile) <= reached
    )
