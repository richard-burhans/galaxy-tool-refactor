"""Codemod-sweep eligibility helpers.

The codemod subcommand of ``scripts/corpus_check.py`` and the
regression-replay tests in ``tests/test_regressions.py`` both need to
decide *under what profile* to validate a tool (before and after running
a codemod). This module owns that policy in one place so both call sites
stay in lock-step.

See ``MEMORY.md``: ``project-corpus-check-filters`` and
``PLAN.md`` § Corpus sweep + regression retention for the rationale.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from galaxy_tool_xml.binding import parse_tool, validate_tool
from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml.profiles import available_profiles


def corpus_test_profile_for(
    declared: str | None,
    *,
    validates_at: Callable[[str], bool],
    profiles: Sequence[str],
) -> str | None:
    """Pick a corpus-test profile from the codemod-subcommand policy.

    ``profiles`` is the list of vendored profiles in oldest-to-newest
    order. ``validates_at(profile)`` reports whether the tool validates
    at the given profile.

    Returns the profile to use, or ``None`` if the tool is ineligible.
    Pure logic — no I/O — so it's straightforward to unit-test against
    synthetic ``validates_at`` callables.

    Short-circuits ``validates_at`` calls: each branch probes the
    minimum number of profiles needed to commit to an answer. For a
    typical well-authored tool (declared profile validates), that's
    exactly one probe.
    """
    if declared is not None and declared in profiles:
        if validates_at(declared):
            return declared
        declared_idx = profiles.index(declared)
        for candidate in profiles[declared_idx + 1 :]:
            if validates_at(candidate):
                return candidate
        return None
    # No usable declared anchor — find the newest validating profile by
    # scanning newest-first and stopping at the first hit.
    for candidate in reversed(profiles):
        if validates_at(candidate):
            return candidate
    return None


def corpus_test_profile(target: Path | ToolDocument, /) -> str | None:
    """Return the profile to use for a corpus-test of *target*, or ``None``.

    Accepts either a filesystem path or an already-parsed ``ToolDocument``
    (preferred when the caller has one — avoids a redundant re-parse per
    profile probe). Returns ``None`` for unparseable, non-tool, or
    otherwise ineligible inputs.
    """
    if isinstance(target, ToolDocument):
        document: ToolDocument | None = target
    else:
        document = parse_tool(target).document
    if document is None or document.root.tag != "tool":
        return None
    declared = document.root.get("profile")
    return corpus_test_profile_for(
        declared,
        validates_at=lambda profile: validate_tool(
            document, profile=profile
        ).valid,
        profiles=available_profiles(),
    )
