"""Profile/version registry and profile-aware XSD resolution.

A tool's ``profile`` attribute names the minimum Galaxy version it targets. The
Galaxy tool XSD has evolved across releases, so validating an old tool against
the newest schema is misleading. This module resolves a profile to one of the
vendored per-release XSDs and compiles it for validation.

All state is loaded lazily behind ``functools.cache`` accessors — importing this
module performs no I/O.
"""

from __future__ import annotations

import importlib.resources
import json
import logging
from functools import cache
from typing import Any

from lxml import etree
from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)

_ON_MISSING_MODES = frozenset({"nearest", "exact", "latest"})
_XS = "{http://www.w3.org/2001/XMLSchema}"


class UnknownProfileError(Exception):
    """Raised when a profile cannot be resolved under ``on_missing="exact"``."""


@cache
def _manifest() -> dict[str, Any]:
    """Load the vendored schema manifest (cached after first call)."""
    resource = importlib.resources.files("galaxy_tool_xml") / "schema" / "manifest.json"
    manifest: dict[str, Any] = json.loads(resource.read_text(encoding="utf-8"))
    return manifest


@cache
def _schemas() -> dict[str, dict[str, str]]:
    """Return the per-version schema registry from the manifest."""
    schemas: dict[str, dict[str, str]] = _manifest()["schemas"]
    return schemas


def available_profiles() -> list[str]:
    """Return every vendored profile version, ordered oldest to newest."""
    return sorted(_schemas(), key=Version)


def latest_profile() -> str:
    """Return the newest vendored profile version."""
    latest: str = _manifest()["latest"]
    return latest


@cache
def _ordered_versions() -> tuple[tuple[Version, str], ...]:
    """Return ``(parsed, original)`` pairs for every vendored version, sorted.

    Cached so ``_nearest_profile`` doesn't re-sort on every call —
    ``available_profiles()`` is also stable for the process lifetime.
    """
    return tuple(sorted((Version(version), version) for version in _schemas()))


def _nearest_profile(profile: str) -> str:
    """Return the newest vendored version not newer than ``profile``.

    An unparseable profile, or one newer than every vendored version, resolves
    to the latest; one older than every vendored version resolves to the oldest.
    """
    # third-party API: no LBYL form — packaging exposes no `is_valid_version`
    # predicate, so the InvalidVersion catch is the only way to detect a
    # malformed `profile` (e.g., a macro token like "@PROFILE@" that survived
    # expansion failure).
    try:
        target = Version(profile)
    except InvalidVersion:
        return latest_profile()
    ordered = _ordered_versions()
    not_newer = [original for parsed, original in ordered if parsed <= target]
    if not_newer:
        return not_newer[-1]
    return ordered[0][1]


def resolve_profile(profile: str | None, *, on_missing: str = "nearest") -> str:
    """Resolve a tool ``profile`` to an exact vendored XSD version.

    ``None`` resolves to the latest vendored version. An exact vendored match
    resolves to itself. Otherwise — including a ``profile`` that cannot be
    parsed as a version — ``on_missing`` selects the strategy: ``nearest``
    (default), ``exact`` (raise ``UnknownProfileError``), or ``latest``.
    """
    if on_missing not in _ON_MISSING_MODES:
        raise ValueError(f"on_missing must be one of {sorted(_ON_MISSING_MODES)}")
    if profile is None:
        return latest_profile()
    if profile in _schemas():
        return profile
    if on_missing == "exact":
        raise UnknownProfileError(f"profile {profile!r} is not a vendored version")
    resolved = latest_profile() if on_missing == "latest" else _nearest_profile(profile)
    logger.info(
        "profile %r is not vendored; resolved to %r via on_missing=%s",
        profile,
        resolved,
        on_missing,
    )
    return resolved


def _collapse_output_groups(schema_root: etree._Element) -> None:
    """Make the ``Output`` complex type's content model deterministic.

    Galaxy releases 19.05 through 23.0 shipped an XSD whose ``Output`` type
    sequenced two overlapping unbounded groups, violating XSD 1.0's Unique
    Particle Attribution rule — libxml2 then refuses to compile it. Galaxy fixed
    this in release 23.1 by keeping only the first group; this applies the same
    fix in memory. It is a no-op for every schema that already compiles.
    """
    for complex_type in schema_root.iter(f"{_XS}complexType"):
        if complex_type.get("name") != "Output":
            continue
        sequence = complex_type.find(f"{_XS}sequence")
        if sequence is None:
            continue
        groups = [child for child in sequence if child.tag == f"{_XS}group"]
        for redundant in groups[1:]:
            sequence.remove(redundant)


@cache
def compiled_schema(version: str) -> etree.XMLSchema:
    """Compile and cache the vendored XSD for an exact vendored ``version``.

    The XSD is compiled verbatim where possible; a schema libxml2 rejects for a
    non-deterministic content model is retried after the ``Output`` group fix.
    """
    schemas = _schemas()
    if version not in schemas:
        raise UnknownProfileError(f"no vendored schema for version {version!r}")
    resource = (
        importlib.resources.files("galaxy_tool_xml")
        / "schema"
        / schemas[version]["file"]
    )
    schema_root = etree.fromstring(resource.read_bytes())
    # third-party API: no LBYL form — libxml2 exposes no way to predict
    # the non-deterministic-content-model failure that Galaxy 19.05–23.0
    # XSDs hit; the retry-with-fix is the same workaround Galaxy itself
    # applied in release 23.1.
    try:
        return etree.XMLSchema(schema_root)
    except etree.XMLSchemaParseError:
        _collapse_output_groups(schema_root)
        logger.info(
            "schema %s has a non-deterministic content model; compiled after "
            "applying Galaxy's 23.1 Output-group fix in memory",
            version,
        )
        return etree.XMLSchema(schema_root)
