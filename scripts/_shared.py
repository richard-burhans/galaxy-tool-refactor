"""Shared constants and utilities used by both ``corpus_check.py`` and ``measure.py``.

Exports:
  ``PROFILE_NONE`` — sentinel string ``"(none)"`` stored in corpus rows when a
      tool has no valid vendored profile or declared no ``profile`` attribute.
  ``row_source`` — map a row's ``repo`` value to ``"github"`` / ``"toolshed"``.
"""

from __future__ import annotations

PROFILE_NONE = "(none)"


def row_source(repo: object) -> str | None:
    """Map a row's ``repo`` value to ``"github"`` / ``"toolshed"`` / ``None``."""
    if not isinstance(repo, str):
        return None
    return "toolshed" if "/" in repo else "github"
