"""Runtime-gated fixes: corrections for profile changes the XSD does NOT enforce.

The ``upgrade_vN`` codemods (``upgrades.py``) are **validity-gated** — each makes a
tool valid at the next vendored profile, and ``UpgradeToLatest`` advances only when
``newest_valid_profile`` improves. But some Galaxy profile changes are *runtime*
behaviours that leave the XSD happy: e.g. from 21.09 ``from_work_dir`` filenames are
quoted, so surrounding whitespace becomes literal. Applying the fix (strip it) does
**not** change validity, so it cannot ride the ``UpgradeToLatest`` loop.

A ``RuntimeGatedFix`` is a normal detect-primitive ``CodemodCommand`` plus an
``introduced_profile`` marker. The ``upgrade`` path applies each fix whose Galaxy
behaviour the tool actually **crosses** — its ``introduced_profile`` lies above the
tool's pre-upgrade baseline and at or below the profile it reached
(``baseline < introduced_profile <= reached``). A tool that stalls below a fix is
untouched (Galaxy ran it under the old behaviour); a tool **already** declaring a
profile at or above the fix's introduction is *also* untouched — Galaxy already
applied the new behaviour, so rewriting it would change current behaviour rather than
preserve it (codemod ``docs/decisions.md`` §24, the crossing-gate). Each fix mirrors
a Galaxy ``must_fix`` upgrade code (see ``profile_semantics.PROFILE_UPGRADE_CODES``).
These are **upgrade-only**: in ``coded_codemods()`` but not ``canonical_codemods()``, so
they never run under ``format`` / the ``default`` ruleset and never change ``profile=``.
"""

from __future__ import annotations

from packaging.version import Version

from galaxy_tool_codemod._version import version_or_none
from galaxy_tool_codemod.codemods._runtime_gated import RuntimeGatedFix
from galaxy_tool_codemod.codemods.fix_from_work_dir_whitespace import (
    FixFromWorkDirWhitespace,
)
from galaxy_tool_codemod.codemods.fix_interpreter import FixInterpreter
from galaxy_tool_codemod.codemods.fix_output_format_input import (
    FixOutputFormatInput,
)
from galaxy_tool_codemod.codemods.fix_test_param_qualification import (
    FixTestParamQualification,
)

# Every runtime-gated fix, ordered by ``introduced_profile`` ascending (16.04
# before 21.09 before 24.2). Order is cosmetic: the fixes touch disjoint
# constructs and the facade applies all whose introduction profile the tool
# reached (see §24).
RUNTIME_GATED_FIXES: tuple[type[RuntimeGatedFix], ...] = (
    FixInterpreter,
    FixOutputFormatInput,
    FixFromWorkDirWhitespace,
    FixTestParamQualification,
)


def runtime_fixes_for(
    reached_profile: str, /, *, baseline_profile: str | None
) -> tuple[type[RuntimeGatedFix], ...]:
    """Return the runtime-gated fixes the tool *crosses* on its way to *reached*.

    A fix applies only when the tool actually crosses its Galaxy behaviour boundary:
    ``baseline_profile < introduced_profile <= reached_profile``. *baseline_profile*
    is the tool's pre-upgrade runtime baseline (a missing ``profile=`` resolves to
    ``16.01``; see the facade's ``_semantic_baseline``); *reached_profile* is the
    profile the tool actually reached after upgrade.

    The lower bound is the crossing-gate: a tool that **already** declares a profile
    at or above a fix's ``introduced_profile`` is left untouched, because Galaxy
    already applies the new behaviour there — rewriting it would change current
    behaviour rather than preserve it. When *baseline_profile* is ``None`` or
    unparseable (e.g. a ``@PROFILE@`` macro token) we cannot place the crossing, so
    we conservatively apply **no** runtime fixes and let the §23 semantic warning
    report instead.
    """
    if baseline_profile is None:
        return ()
    baseline = version_or_none(baseline_profile)
    reached = version_or_none(reached_profile)
    if baseline is None or reached is None:
        return ()
    return tuple(
        fix
        for fix in RUNTIME_GATED_FIXES
        if baseline < Version(fix.introduced_profile) <= reached
    )
