"""Shared version-parse helper for the codemod tier.

``packaging`` exposes no validity predicate, so a ``try``/``except`` over
``Version`` is the sanctioned third-party boundary. Both the profile-semantics
catalogue (``profile_semantics``) and the runtime-gated-fix crossing gate
(``runtime_fixes``) need to place a possibly-unparseable profile string, so the
helper lives here once rather than being mirrored in each (architecture audit
2026-06-03, ``../../docs/architecture_audit.md``).
"""

from __future__ import annotations

from packaging.version import InvalidVersion, Version


def version_or_none(value: str, /) -> Version | None:
    """Parse *value* as a ``Version``, or ``None`` if it is not one."""
    try:
        return Version(value)
    except InvalidVersion:
        return None
