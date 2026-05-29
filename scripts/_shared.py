"""Shared constants and utilities used by both ``corpus_check.py`` and ``measure.py``.

Exports:
  ``PROFILE_NONE`` — sentinel string ``"(none)"`` stored in corpus rows when a
      tool has no valid vendored profile or declared no ``profile`` attribute.
  ``row_source`` — map a row's ``repo`` value to ``"github"`` / ``"toolshed"`` /
      ``None`` (``None`` when ``repo`` is not a string).
  ``unique_by_sha`` — de-duplicate corpus rows by ``sha256`` (first wins).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TypeVar

PROFILE_NONE = "(none)"

_RowT = TypeVar("_RowT", bound=Mapping[str, object])


def row_source(repo: object) -> str | None:
    """Map a row's ``repo`` value to ``"github"`` / ``"toolshed"`` / ``None``."""
    if not isinstance(repo, str):
        return None
    return "toolshed" if "/" in repo else "github"


def unique_by_sha(rows: Iterable[_RowT]) -> list[_RowT]:
    """Return *rows* de-duplicated by ``sha256`` — first occurrence wins.

    Rows whose ``sha256`` is missing or not a string are dropped. This is the
    single first-sha-wins dedup the corpus failure pages and the ``measure``
    queries share, so their unique-tool counts reconcile.
    """
    seen: set[str] = set()
    unique: list[_RowT] = []
    for row in rows:
        sha = row.get("sha256")
        if not isinstance(sha, str) or sha in seen:
            continue
        seen.add(sha)
        unique.append(row)
    return unique
