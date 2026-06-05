"""Cross-file parameter rename with a sole-owned shared-macro gate (registry tier).

The tier-1 ``rename_param_in_bundle`` renames a parameter across a tool and its
imported macro files atomically, but it cannot know whether a macro it would edit is
*shared* by other tools — that is a repo-wide question. This module supplies the
gate: it builds the reverse-import map over a repo root, and applies a rename only
when every macro the rename would touch is **sole-owned** by the tool being renamed.

The policy (v1) is deliberately conservative, mirroring ``macro_profile``'s
consensus skip:

- A rename whose reference edits all land in the tool itself (no macro touched) needs
  no repo context and applies directly.
- A rename that must edit a macro **sole-owned** by this tool applies (editing it is
  as safe as editing the tool's own tree).
- A rename that must edit a macro **shared** with another tool is *skipped whole* —
  the shared macro and its other importers are reported, and the tool is **not**
  written either, so it is never left half-renamed referencing a name the macro still
  emits as ``$old``. (Renaming across all importers in lockstep — consensus — is a
  documented fast-follow; this module refuses rather than guess.)
- A rename that would edit a macro but is given **no importer map** bails
  ``macro-edit-needs-repo-root``: an under-counted importer set must never silently
  authorise a shared write, so the caller must prove ownership over an explicit root.
- A rename whose edited macro is **absent from the importer map** bails
  ``macro-ownership-unprovable`` (fail **closed**). In correct usage the tool is under
  the repo root, so it imports the macro and the macro is in the map; absence means the
  repo root does not cover this tool, so ownership cannot be proven and the edit is
  refused rather than fail-open-applied.

Ownership is "sole-owned within the repo root the map was built over"; a tool outside
that root importing the same macro is invisible (documented trust boundary).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from galaxy_tool_xml.bundle import load_bundle, rename_param_in_bundle
from galaxy_tool_xml.cheetah_refs import tool_cheetah_references
from galaxy_tool_xml.macros import imported_macro_paths
from galaxy_tool_xml_fmt.cli_support import is_tool_root, make_backup
from galaxy_tool_xml_fmt.format import (
    format_macro_document,
    format_tool_document_subset,
)
from lxml import etree

if TYPE_CHECKING:
    from collections.abc import Mapping


def build_importer_map(repo_root: Path, /) -> dict[Path, frozenset[Path]]:
    """Map each macro file to the set of tools that import it, **transitively**.

    Walks *repo_root* for tool XML files (a ``<tool>`` root; macro files and other
    XML contribute no import edges of their own — a macro reached only through a tool
    is already captured by that tool's transitive ``imported_macro_paths``) and
    inverts the import relation. The gate reads this to tell a sole-owned macro (safe
    to edit) from a shared one. Paths are resolved so they compare equal to the
    ``source_path``\\ s a loaded bundle carries.
    """
    importers: dict[Path, set[Path]] = defaultdict(set)
    for path in sorted(repo_root.rglob("*.xml")):
        # third-party read boundary: an unreadable file simply contributes no edges.
        try:
            head = path.read_bytes()
        except OSError:
            continue
        if not is_tool_root(head):
            continue
        tool_path = path.resolve()
        for macro_path in imported_macro_paths(path):
            importers[macro_path].add(tool_path)
    return {macro: frozenset(tools) for macro, tools in importers.items()}


@dataclass(frozen=True)
class BundleMemberEdit:
    """One member (the tool or a macro file) a successful rename wrote, or would write.

    Attributes:
        path: The member's file path.
        kind: ``"tool"`` or ``"macro"``.
        renamed: How many sites were rewritten in this member.
        formatted: The serialised bytes (fmt is the only serializer), for preview and
            for the MCP/library caller; written to ``path`` only when ``write=True``.
    """

    path: Path
    kind: str
    renamed: int
    formatted: bytes


@dataclass(frozen=True)
class SharedMacroSkip:
    """A macro the rename had to edit but is shared — so the whole rename was skipped.

    Attributes:
        macro_file: The shared macro file the rename would have rewritten.
        other_importers: The *other* tools importing it (the blast radius that makes
            an in-place edit unsafe), sorted, excluding the tool being renamed.
    """

    macro_file: Path
    other_importers: tuple[Path, ...]


@dataclass(frozen=True)
class BundleRenameResult:
    """Outcome of a gated cross-file rename for one tool.

    ``changed`` is True only when the rename applied across all (sole-owned) members.
    On a bail/skip ``reason`` says why: a tier-1 planner reason (``shadowed`` /
    ``mixed-content`` / ``lexer-bail`` / ``filter-bare-ref`` / ``cross-ref-residual`` /
    ``not-found`` / ``invalid-name`` / ``no-op``),
    ``unparseable-macro`` (an imported macro could not be read), ``shared-macro`` (the
    gate tripped — see ``shared``), ``macro-ownership-unprovable`` (a macro the rename
    would edit is absent from the importer map — the repo root does not cover this
    tool; see ``unprovable``), or ``macro-edit-needs-repo-root`` (a macro edit was
    required but no importer map was supplied at all).
    """

    tool: Path
    old: str
    new: str
    changed: bool
    reason: str | None = None
    edits: tuple[BundleMemberEdit, ...] = ()
    shared: tuple[SharedMacroSkip, ...] = ()
    unprovable: tuple[Path, ...] = ()


def _gate_macros(
    edited_macros: tuple[Path, ...],
    tool: Path,
    importers: Mapping[Path, frozenset[Path]],
    /,
) -> tuple[tuple[SharedMacroSkip, ...], tuple[Path, ...]]:
    """Classify each edited macro against the importer map: ``(shared, unprovable)``.

    - **shared** — present in the map and imported by a tool other than *tool* (a
      ``SharedMacroSkip`` with the other importers).
    - **unprovable** — *absent* from the map entirely. Fail **closed**: in correct
      usage the tool is under the repo root the map was built over, so it imports the
      macro and the macro is in the map (with at least *tool*). Absence means the tool
      was not seen — the repo root does not cover it — so ownership cannot be proven and
      the rename must not apply (an under-counted map could otherwise authorise a write
      that breaks an unseen importer).
    """
    shared: list[SharedMacroSkip] = []
    unprovable: list[Path] = []
    for macro in edited_macros:
        if macro not in importers:
            unprovable.append(macro)
            continue
        others = importers[macro] - {tool}
        if others:
            shared.append(SharedMacroSkip(macro, tuple(sorted(others, key=str))))
    return tuple(shared), tuple(unprovable)


def rename_param_bundle(
    tool: Path,
    /,
    *,
    old: str,
    new: str,
    importers: Mapping[Path, frozenset[Path]] | None = None,
    write: bool = False,
    backup: bool = False,
) -> BundleRenameResult:
    """Rename *old* to *new* across *tool* and its sole-owned imported macros.

    Loads the bundle, renames across it (tier-1, atomic), then applies the sole-owned
    gate before writing anything: if any macro the rename touched is shared, the whole
    rename is skipped and reported (the tool is not written). *importers* is the
    reverse-import map from ``build_importer_map`` over the repo root; it is required
    only when the rename actually edits a macro. Files are written only when *write*;
    when *backup* each written member is copied to ``<file>.bak`` first.
    """
    tool = tool.resolve()
    bundle = load_bundle(tool)
    if bundle.unparseable:
        return BundleRenameResult(
            tool, old, new, changed=False, reason="unparseable-macro"
        )

    outcome = rename_param_in_bundle(bundle, old=old, new=new)
    if outcome.bailed:
        return BundleRenameResult(tool, old, new, changed=False, reason=outcome.reason)

    edited_macros = outcome.edited_macros
    if edited_macros:
        if importers is None:
            return BundleRenameResult(
                tool, old, new, changed=False, reason="macro-edit-needs-repo-root"
            )
        shared, unprovable = _gate_macros(edited_macros, tool, importers)
        if shared:
            return BundleRenameResult(
                tool, old, new, changed=False, reason="shared-macro", shared=shared
            )
        if unprovable:
            return BundleRenameResult(
                tool,
                old,
                new,
                changed=False,
                reason="macro-ownership-unprovable",
                unprovable=unprovable,
            )

    renamed_by_path = {
        member.source_path: member.renamed for member in outcome.members
    }
    edits: list[BundleMemberEdit] = [
        BundleMemberEdit(
            path=tool,
            kind="tool",
            renamed=renamed_by_path.get(bundle.tool.source_path, 0),
            formatted=format_tool_document_subset(bundle.tool, rule_classes=()),
        )
    ]
    edited = set(edited_macros)
    for macro in bundle.macros:
        if macro.source_path in edited:
            edits.append(
                BundleMemberEdit(
                    path=macro.source_path,
                    kind="macro",
                    renamed=renamed_by_path.get(macro.source_path, 0),
                    formatted=format_macro_document(macro),
                )
            )
    if write:
        for edit in edits:
            if backup:
                make_backup(edit.path)
            edit.path.write_bytes(edit.formatted)
    return BundleRenameResult(
        tool, old, new, changed=True, edits=tuple(edits)
    )


@dataclass(frozen=True)
class BundleReference:
    """One Cheetah ``$name`` reference found in a tool or one of its macro files.

    Attributes:
        path: The file the reference lives in.
        kind: ``"tool"`` or ``"macro"``.
        section: The templated section (``"command"``, ``"configfile:script"``, …).
        sourceline: 1-based line within ``path``.
        reference: The reference as written (e.g. ``"$protein_alignment"``).
    """

    path: Path
    kind: str
    section: str
    sourceline: int
    reference: str


@dataclass(frozen=True)
class BundleFindReferencesResult:
    """Every reference to a parameter across a tool and its imported macro files."""

    tool: Path
    name: str
    references: tuple[BundleReference, ...] = ()


def find_references_in_bundle(
    tool: Path, /, *, name: str
) -> BundleFindReferencesResult:
    """Every ``$name`` reference across *tool* and each imported macro file (read-only).

    The bundle-aware sibling of ``facade.find_references``: it also scans the imported
    macro files (where a reference frequently lives), attributing each occurrence to
    its own file. No gate — it never writes.
    """
    bundle = load_bundle(tool)
    references: list[BundleReference] = []
    members: list[tuple[Path | None, str, etree._Element]] = [
        (bundle.tool.source_path, "tool", bundle.tool.root),
        *((macro.source_path, "macro", macro.root) for macro in bundle.macros),
    ]
    for source_path, kind, root in members:
        if source_path is None:
            continue
        references.extend(
            BundleReference(
                path=source_path,
                kind=kind,
                section=ref.section,
                sourceline=ref.sourceline,
                reference=ref.name,
            )
            for ref in tool_cheetah_references(root)
            if name in ref.segments
        )
    return BundleFindReferencesResult(
        tool=tool.resolve(), name=name, references=tuple(references)
    )
