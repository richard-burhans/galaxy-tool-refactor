"""Shared constants and utilities used by both ``corpus_check.py`` and ``measure.py``.

Exports:
  ``PROFILE_NONE`` — sentinel string ``"(none)"`` stored in corpus rows when a
      tool has no valid vendored profile or declared no ``profile`` attribute.
  ``row_source`` — map a row's ``repo`` value to ``"github"`` / ``"toolshed"`` /
      ``None`` (``None`` when ``repo`` is not a string).
  ``unique_by_sha`` — de-duplicate corpus rows by ``sha256`` (first wins).
  ``sha256_of`` — hex sha256 of a file's bytes (the corpus dedup key).
  ``is_deprecated_path`` — True if a path lives under a deprecated directory.
  ``iter_tool_xmls`` — yield every ``*.xml`` under a root, skipping Mercurial
      metadata and deprecated directories (the single corpus-discovery filter).
  ``is_tool_document`` — True if a path parses as XML with a ``<tool>`` root
      (excludes ``macros.xml`` / non-tool XML from tool-scoped sweeps).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TypeVar

from lxml import etree

PROFILE_NONE = "(none)"

_DEPRECATED_SUBSTRING = "deprecat"

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


def sha256_of(path: Path, /) -> str:
    """Return the hex sha256 of *path*'s bytes — the corpus dedup key.

    The single content-hash helper shared by ``corpus_check`` and ``measure``;
    both dedup tools by this digest, so their unique-tool counts reconcile (see
    ``unique_by_sha``, which dedups already-computed digests on rows).
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_deprecated_path(path: Path) -> bool:
    """Return True if *path* lives under a deprecated directory.

    Matches when any *parent* directory component contains the substring
    ``"deprecat"`` (case-insensitive): ``deprecated/``, ``galru_deprecated/``,
    ``deprecated_tool/`` all qualify, as does ``deprecation/``. The filename
    itself is not inspected, so a tool merely named ``*deprecated*.xml`` under a
    live directory is kept. ``old`` / ``archive`` directories do not match — only
    ``"deprecat"`` — which avoids excluding test-data fixtures named that way.
    """
    return any(_DEPRECATED_SUBSTRING in part.casefold() for part in path.parent.parts)


def iter_tool_xmls(root: Path) -> Iterable[Path]:
    """Yield every ``*.xml`` under *root*, skipping noise and deprecated tools.

    The single corpus-discovery filter shared by ``corpus_check`` (rooted at a
    per-repo directory) and ``measure`` (rooted at the whole corpus tree). Skips
    Mercurial metadata (``.hg/``) and any file under a deprecated directory (see
    ``is_deprecated_path``). The order is ``rglob``'s; callers that need a stable
    order wrap the result in ``sorted(...)``.
    """
    for path in root.rglob("*.xml"):
        if ".hg/" in str(path):
            continue
        if is_deprecated_path(path):
            continue
        yield path


def is_tool_document(path: Path, /) -> bool:
    """Return True when *path* parses as XML with a ``<tool>`` root.

    A repository's ``*.xml`` files include ``macros.xml`` and other non-tool XML
    that a tool-scoped rule does not lint; callers (the forward gate, the bulk
    normalizer) use this to keep their denominator to actual ``<tool>`` documents.
    """
    try:
        tree = etree.parse(str(path))
    except etree.LxmlError:
        return False
    return bool(tree.getroot().tag == "tool")
