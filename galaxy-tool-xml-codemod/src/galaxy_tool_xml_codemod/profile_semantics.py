"""Profile bumps that change *runtime behaviour* the XSD does not encode.

The profile-upgrade machinery is **structurally** sound — a tool that validates
at profile X needs no XML change to be a valid profile-X tool (codemod
``docs/decisions.md`` §22). It is **not** behaviour-preserving: Galaxy's
``profile`` is a runtime-compatibility contract, so some bumps silently change
runtime defaults (error detection, ``set -e``, Python version, templating of
optional values, …) that no XSD validation can see.

``SEMANTIC_PROFILE_CHANGES`` maps each such profile version to a one-line
description of the runtime behaviour it introduces, sourced from the Galaxy
schema docs' ``<tool> profile`` attribute documentation
(https://docs.galaxyproject.org/en/latest/dev/schema.html). It is the
machine-readable mirror of the *Semantic* column in ``docs/profile_upgrades.md``
— keep the two in sync. ``semantic_changes_crossed`` answers "which of these does
a given bump cross", so the ``upgrade`` path can warn (it cannot auto-preserve).

``16.04`` predates the oldest vendored XSD (``16.10``) but is the most impactful
boundary for the common case of a tool with no ``profile=`` (Galaxy runs those as
``16.01``), so it is included for the warning's benefit.
"""

from __future__ import annotations

from packaging.version import InvalidVersion, Version

# version -> the runtime behaviour that profile introduces (XSD-invisible).
SEMANTIC_PROFILE_CHANGES: dict[str, str] = {
    "16.04": (
        "a non-zero exit code (not non-empty stderr) becomes the default error"
        " condition; implicit extra-file collection, format=\"input\","
        " interpreter=, and $param_file are disabled"
    ),
    "17.09": (
        "provided_metadata_style defaults to \"default\""
        " (set \"legacy\" to restore the old behaviour)"
    ),
    "18.01": "each job runs with a separate home directory",
    "18.09": (
        "references to other inputs must be fully qualified with '|';"
        " provided-but-illegal default values are rejected"
    ),
    "19.05": "the default Python interpreter changes from 2.7 to 3.5",
    "20.05": (
        "unselected optional params template as None (not the string \"None\");"
        " multiple-select params become lists, not comma-joined strings"
    ),
    "20.09": (
        "the command runs under 'set -e' (exits on the first non-zero status);"
        " collection element order is assumed sorted"
    ),
    "21.09": (
        "leading/trailing whitespace in from_work_dir is no longer stripped;"
        " data_source tools do not use the Galaxy virtualenv"
    ),
    "23.0": (
        "optional text params with no value template as None,"
        " not the empty string"
    ),
    "24.0": (
        "data_source_async tools do not use the Galaxy virtualenv; request"
        " params not declared in <request_param_translation> are dropped"
    ),
    "24.2": "data_column params require a valid data_ref",
    "25.1": "tool credentials use the <credentials> tag, not user preferences",
}


def _version_or_none(value: str, /) -> Version | None:
    """Parse *value* as a version, or ``None`` if it is not one.

    ``packaging`` exposes no validity predicate, so the ``try``/``except`` is the
    sanctioned boundary (mirrors ``codemods/update_profile.py``).
    """
    try:
        return Version(value)
    except InvalidVersion:
        return None


def semantic_changes_crossed(
    *, from_profile: str, to_profile: str
) -> list[tuple[str, str]]:
    """Return the runtime-behaviour changes a profile bump crosses.

    A change at version ``V`` is crossed when ``from_profile < V <= to_profile``
    (declaring ``V`` opts the tool into ``V``'s behaviour). The result is sorted
    oldest-first as ``(version, description)`` pairs. Returns ``[]`` when either
    profile is unparseable (e.g. a macro token) or the bump is not upward.
    """
    low = _version_or_none(from_profile)
    high = _version_or_none(to_profile)
    if low is None or high is None:
        return []
    return [
        (version, change)
        for version, change in sorted(
            SEMANTIC_PROFILE_CHANGES.items(), key=lambda item: Version(item[0])
        )
        if low < Version(version) <= high
    ]
