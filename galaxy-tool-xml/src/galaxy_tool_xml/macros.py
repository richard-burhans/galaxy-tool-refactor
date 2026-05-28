"""Galaxy macro detection, stripping, and expansion.

This is the **only** module that imports ``galaxy.util.xml_macros``, isolating
the coupling to Galaxy's internal API behind a single adapter. Every exception
raised by that internal API is caught here and converted to a ``MacroError`` —
a Galaxy exception never escapes this module.

The Galaxy tool XSD is a *post-macro-expansion* schema, so ``validate_tool``
transforms a tool through these functions into a throwaway copy before
validating. The throwaway tree's loss of comments and whitespace (Galaxy's
parser strips them) does not matter — it is used only for validation.
"""

from __future__ import annotations

import copy
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from galaxy.util.xml_macros import load_with_references
from lxml import etree

logger = logging.getLogger(__name__)


@dataclass
class MacroError:
    """A single macro-expansion failure (cycle, missing macro, bad ``<import>``)."""

    message: str
    source: str | None = None

    def __str__(self) -> str:
        message = " ".join(self.message.split())
        if self.source:
            return f"{self.source}: {message}"
        return message


def has_macros(root: etree._Element) -> bool:
    """Return whether the tree uses macros — any ``<expand>`` or a ``<macros>``."""
    if root.find("macros") is not None:
        return True
    return root.find(".//expand") is not None


def strip_macros(tree: etree._ElementTree) -> etree._ElementTree:
    """Return a deep copy with every ``<expand>`` and ``<macros>`` removed.

    The input tree is never modified.
    """
    copied = copy.deepcopy(tree)
    root = copied.getroot()
    for tag in ("expand", "macros"):
        for element in list(root.iter(tag)):
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
    return copied


def _load_with_references(
    file_path: Path, *, error_source: str | None, log_label: str
) -> tuple[etree._ElementTree | None, list[MacroError]]:
    """Call ``galaxy.util.xml_macros.load_with_references`` and catch anything.

    Both ``expand_from_path`` and ``expand_from_tree`` need the same
    "call the adapter, log a warning on failure, wrap the failure as a
    ``MacroError``" sequence; this helper carries the only sanctioned
    broad-except in the module so the caller sites stay one-liners.
    """
    # third-party API: no LBYL form — galaxy.util.xml_macros raises a wide
    # variety of internal exceptions (cycle, missing macro, malformed XML)
    # and isolating that here is the whole point of the macros.py adapter.
    try:
        expanded, _imported = load_with_references(str(file_path))
    except Exception as error:  # noqa: BLE001 — galaxy.util adapter boundary
        logger.warning("macro expansion failed for %s: %s", log_label, error)
        failure = MacroError(f"macro expansion failed: {error}", source=error_source)
        return None, [failure]
    return expanded, []


def expand_from_path(
    path: Path,
) -> tuple[etree._ElementTree | None, list[MacroError]]:
    """Expand a tool's macros, reading it and its ``<import>``s from disk.

    ``<import>``s resolve against the file's own directory. Returns the expanded
    tree (or ``None`` on failure) and any errors.
    """
    return _load_with_references(path, error_source=str(path), log_label=str(path))


def expand_from_tree(
    root: etree._Element, *, source_dir: Path | None
) -> tuple[etree._ElementTree | None, list[MacroError]]:
    """Expand the macros of an in-memory (possibly mutated) tool tree.

    The tree is serialised to a temp directory; each ``<import>``ed macro file
    is copied in beside it, resolved against ``source_dir``. With
    ``source_dir=None`` external ``<import>``s cannot be resolved — inline
    macros still expand and a ``MacroError`` records the limitation.
    """
    errors: list[MacroError] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        tool_path = tmp_dir / "tool.xml"
        tool_path.write_bytes(etree.tostring(root))
        errors.extend(_stage_imports(root, source_dir=source_dir, tmp_dir=tmp_dir))
        expanded, expand_errors = _load_with_references(
            tool_path, error_source=None, log_label="in-memory tree"
        )
        errors.extend(expand_errors)
        if expanded is None:
            return None, errors
    return expanded, errors


def _import_targets(root: etree._Element) -> list[str]:
    """Return the macro-file paths a tool or macro-file element ``<import>``s.

    A tool nests imports under ``<tool><macros>``; a macro file lists them as
    direct children of its root ``<macros>``.
    """
    elements = (
        root.findall("import")
        if root.tag == "macros"
        else root.findall("macros/import")
    )
    return [
        element.text.strip()
        for element in elements
        if element.text and element.text.strip()
    ]


def _stage_imports(
    root: etree._Element, *, source_dir: Path | None, tmp_dir: Path
) -> list[MacroError]:
    """Copy every macro file the tree imports — directly or transitively.

    Each staged macro file is itself scanned for further ``<import>``s, so a
    whole chain of macro files (a tool importing ``macros.xml`` that imports
    ``read_group_macros.xml``, say) all reach the temp directory.
    """
    errors: list[MacroError] = []
    staged: set[str] = set()
    pending = _import_targets(root)
    while pending:
        relative = pending.pop()
        if relative in staged:
            continue
        staged.add(relative)
        imported_root, stage_errors = _stage_import(
            relative, source_dir=source_dir, tmp_dir=tmp_dir
        )
        errors.extend(stage_errors)
        if imported_root is not None:
            pending.extend(_import_targets(imported_root))
    return errors


def _stage_import(
    relative: str, *, source_dir: Path | None, tmp_dir: Path
) -> tuple[etree._Element | None, list[MacroError]]:
    """Copy one ``<import>``ed macro file into the temp directory.

    Returns the staged file's parsed root — so the caller can stage that file's
    own ``<import>``s — or ``None`` when the file could not be staged or parsed.
    """
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None, [
            MacroError(
                f"cannot stage <import> {relative!r}: path escapes the tool directory"
            )
        ]
    if source_dir is None:
        return None, [
            MacroError(
                f"cannot resolve <import> {relative!r}: "
                "in-memory input has no source directory"
            )
        ]
    source = source_dir / relative_path
    if not source.exists():
        return None, [MacroError(f"imported macro file not found: {source}")]
    destination = tmp_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, destination)
    # third-party API: no LBYL form — recover=True handles most malformed
    # XML, but pathological inputs (an empty file with nothing to recover)
    # still raise; treat as un-stageable. The missing root just suppresses
    # transitive <import> staging.
    try:
        staged_root = etree.parse(
            str(destination), etree.XMLParser(recover=True)
        ).getroot()
    except etree.XMLSyntaxError:
        staged_root = None
    return staged_root, []
