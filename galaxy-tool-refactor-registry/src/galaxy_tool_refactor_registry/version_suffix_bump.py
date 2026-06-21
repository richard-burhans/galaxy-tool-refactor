"""Suite-scoped bump of an imported ``@VERSION_SUFFIX@`` token (N2), proof-gated.

The structural twin of ``macro_profile`` (which bumps an imported ``@PROFILE@``
token): when a tool's revision suffix is the ``@VERSION_SUFFIX@`` token defined in
a *shared* macros file, the tool cannot be bumped alone — editing the file's
``<token>`` value moves every importer's published revision in lockstep. That is the
intended effect of a suite bump, but it must be *only* that effect: the proof gate
re-expands every importer before and after the bump and bails unless the sole change
is the ``+galaxy<N>`` segment of each importer's version. fmt remains the only
serializer.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from galaxy_tool_fmt.format import format_macro_document
from galaxy_tool_source.binding import load_macros, parse_tool
from galaxy_tool_source.macros import expand_from_path, imported_macro_paths
from lxml import etree

_VERSION_SUFFIX_TOKEN = "@VERSION_SUFFIX@"
# Match a ``+galaxy<N>`` revision segment so an expansion diff that touches only it
# (per importer) is recognised as the intended, controlled change.
_GALAXY_SUFFIX_LITERAL = re.compile(r"\+galaxy[0-9]+")


@dataclass(frozen=True)
class SuffixBumpPlan:
    """The planned suite bump of a shared ``@VERSION_SUFFIX@`` token.

    When ``skip_reason`` is set nothing is applied; otherwise ``macros_content`` is
    written to ``macros_path`` and ``importers`` lists every tool the bump lifts.
    """

    macros_path: Path
    macros_content: bytes | None
    importers: tuple[Path, ...]
    old_suffix: int | None
    new_suffix: int | None
    skip_reason: str | None


def _bail(macros_path: Path, reason: str) -> SuffixBumpPlan:
    return SuffixBumpPlan(
        macros_path=macros_path,
        macros_content=None,
        importers=(),
        old_suffix=None,
        new_suffix=None,
        skip_reason=reason,
    )


def _directory_importers(macros_path: Path) -> list[Path]:
    """Every ``<tool>`` in ``macros_path``'s directory that imports it (sorted)."""
    importers: list[Path] = []
    for candidate in sorted(macros_path.parent.glob("*.xml")):
        if candidate.resolve() == macros_path:
            continue
        result = parse_tool(candidate)
        if result.document is None or result.document.root.tag != "tool":
            continue
        if macros_path in {p.resolve() for p in imported_macro_paths(candidate)}:
            importers.append(candidate)
    return importers


def _stripped_expansion(path: Path) -> etree._Element | None:
    """A tool's macro expansion with ``<macros>`` stripped, or ``None`` on failure."""
    tree, errors = expand_from_path(path)
    if tree is None or errors:
        return None
    root = tree.getroot()
    for macros in root.findall("macros"):
        root.remove(macros)
    return root


def _expansion_with_override(
    src_dir: Path, *, macros_name: str, macros_content: bytes, tool_name: str
) -> etree._Element | None:
    """Expand *tool_name* in a temp copy of *src_dir*, macros file overridden."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for entry in src_dir.iterdir():
            if entry.is_file() and entry.suffix == ".xml":
                shutil.copy2(entry, tmp_dir / entry.name)
        (tmp_dir / macros_name).write_bytes(macros_content)
        return _stripped_expansion(tmp_dir / tool_name)


def _changes_only_galaxy_suffix(before: etree._Element, after: etree._Element) -> bool:
    """True when *before* and *after* differ solely in their ``+galaxy<N>`` segments.

    Both expansions are canonicalised after masking every ``+galaxy<N>`` literal to a
    fixed sentinel; equality of the masked forms proves the bump changed nothing but
    the revision suffix wherever it appears.
    """
    masked_before = _GALAXY_SUFFIX_LITERAL.sub(
        "+galaxyN", bytes(etree.tostring(before)).decode("utf-8")
    )
    masked_after = _GALAXY_SUFFIX_LITERAL.sub(
        "+galaxyN", bytes(etree.tostring(after)).decode("utf-8")
    )
    return masked_before == masked_after


def plan_suite_suffix_bump(macros_path: Path, /, *, new_suffix: int) -> SuffixBumpPlan:
    """Plan bumping the shared ``@VERSION_SUFFIX@`` token in *macros_path*.

    Resolves every importer in the directory, builds the bumped macros file, and
    proves by execution that the bump changes only each importer's ``+galaxy<N>``
    segment. Bails (``skip_reason``) when the file is malformed, defines no integer
    ``@VERSION_SUFFIX@``, or any importer's expansion would change beyond the suffix.
    """
    macros_path = macros_path.resolve()
    name = macros_path.name
    src_dir = macros_path.parent

    try:
        document = load_macros(macros_path)
    except Exception as error:  # noqa: BLE001 — malformed shared file declines the bump
        return _bail(macros_path, f"{name} is not a well-formed <macros> file: {error}")
    token = document.root.find(f'token[@name="{_VERSION_SUFFIX_TOKEN}"]')
    if token is None:
        return _bail(macros_path, f"{name} defines no {_VERSION_SUFFIX_TOKEN} token")
    current_raw = (token.text or "").strip()
    if not current_raw.isdigit():
        return _bail(
            macros_path,
            f"{name} defines {_VERSION_SUFFIX_TOKEN} as {current_raw!r}, "
            "not an integer",
        )
    old_suffix = int(current_raw)

    token.text = str(new_suffix)
    macros_content = format_macro_document(document)

    importers = _directory_importers(macros_path)
    if not importers:
        return _bail(macros_path, f"no tool in the directory imports {name}")

    for importer in importers:
        before = _stripped_expansion(importer)
        after = _expansion_with_override(
            src_dir,
            macros_name=name,
            macros_content=macros_content,
            tool_name=importer.name,
        )
        if before is None or after is None:
            return _bail(
                macros_path,
                f"could not macro-expand {importer.name} to prove the suffix bump",
            )
        if not _changes_only_galaxy_suffix(before, after):
            return _bail(
                macros_path,
                f"bumping {_VERSION_SUFFIX_TOKEN} in {name} would change more than the "
                f"+galaxy<N> segment of {importer.name}",
            )

    return SuffixBumpPlan(
        macros_path=macros_path,
        macros_content=macros_content,
        importers=tuple(importer.resolve() for importer in importers),
        old_suffix=old_suffix,
        new_suffix=new_suffix,
        skip_reason=None,
    )
