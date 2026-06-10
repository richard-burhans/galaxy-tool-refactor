"""Normalize literal ``format`` / ``ftype`` in imported macro files (Phase 2a).

The macro-library analog of ``Upgrade24_1`` (GTR010). ``Upgrade24_1`` lowercases /
strips ``format`` / ``ftype`` on a tool's **own** tree, but a coercible value defined
in an *imported* macro file (e.g. ``<data format="GTiff">`` in ``gdal_macros.xml``) is
unreachable from the per-tool pipeline — so a handful of tools stay stuck below 24.2
solely because of it (``galaxy-tool-xml-codemod/docs/macro-aware-normalization.md``).

This is the deliberate, opt-in, repo-scoped "normalize macro library" pass (that
note's option D): given macro files, lowercase each **literal** ``format`` / ``ftype``
token (skipping ``@TOKEN@`` placeholders, whose value is per-importer), and reserialise
through ``format_macro_document`` (fmt stays the only serializer).

**Why no per-importer validity gate is needed.** The edit is exactly the
canonicalization ``Upgrade24_1`` already applies tool-tree-wide as semantics-preserving
— lowercase is the canonical Galaxy datatype extension at every profile, and it only
*satisfies* the 24.2 ``format`` pattern facet, never breaks it. An importer blocked at
24.2 by the uppercase
value can only improve or stay put; one already valid stays valid. So editing a *shared*
macro file is as safe for every importer as editing the tool's own tree — unlike the
``@PROFILE@`` token (``macro_profile.py``), where importers can disagree on a target and
the bump needs a consensus gate. The shared-file blast radius is surfaced (the caller
reports affected importers), not gated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from galaxy_tool_source.binding import ToolXmlSyntaxError, load_macros
from galaxy_tool_xml_codemod.datatype_format import normalize_datatype_attributes
from galaxy_tool_xml_fmt.cli_support import make_backup
from galaxy_tool_xml_fmt.format import format_macro_document

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


@dataclass(frozen=True)
class MacroDatatypeEdit:
    """A macro file whose literal ``format`` / ``ftype`` values were normalized.

    Attributes:
        macro_file: The macro file edited (or, under preview, that would be).
        elements_changed: How many elements had a ``format`` / ``ftype`` rewritten
            or dropped.
    """

    macro_file: Path
    elements_changed: int


@dataclass(frozen=True)
class MacroDatatypeResult:
    """Outcome of a macro-library datatype-normalization pass.

    ``edits`` are the files changed (or, when ``write=False``, that would be). A file
    with no coercible literal is a silent no-op and appears nowhere. ``unparseable``
    are macro files that could not be loaded (unsupported version / malformed XML);
    they are skipped, not normalized, and surfaced so a batch caller can report them.
    """

    edits: tuple[MacroDatatypeEdit, ...]
    unparseable: tuple[Path, ...]


def normalize_macro_files(
    paths: Iterable[Path], /, *, write: bool, backup: bool = False
) -> MacroDatatypeResult:
    """Lowercase literal ``format`` / ``ftype`` in each macro file; report the edits.

    Each path is loaded as a ``MacroDocument``, every element's ``format`` / ``ftype``
    normalized (``skip_tokens=True`` — placeholders are left alone), and — when *write*
    is true and something changed — the file is reserialised through
    ``format_macro_document`` and written back (copied to ``<file>.bak`` first when
    *backup*). Idempotent: a file already lowercase is a no-op. Paths are de-duplicated
    (a shared macro file is edited once). A file that fails to load (malformed /
    unsupported version) is skipped and recorded in ``unparseable`` rather than aborting
    the batch — parsing is the one boundary with no LBYL form.
    """
    edits: list[MacroDatatypeEdit] = []
    unparseable: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        try:
            document = load_macros(path)
        except ToolXmlSyntaxError:
            unparseable.append(path)
            continue
        elements_changed = sum(
            1
            for element in document.root.iter()
            if isinstance(element.tag, str)
            and normalize_datatype_attributes(element, skip_tokens=True)
        )
        if not elements_changed:
            continue
        if write:
            if backup:
                make_backup(path)
            path.write_bytes(format_macro_document(document))
        edits.append(
            MacroDatatypeEdit(macro_file=path, elements_changed=elements_changed)
        )
    return MacroDatatypeResult(edits=tuple(edits), unparseable=tuple(unparseable))
