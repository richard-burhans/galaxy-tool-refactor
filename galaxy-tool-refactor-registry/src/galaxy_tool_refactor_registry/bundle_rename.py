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

from galaxy_tool_fmt.cli_support import is_tool_root, make_backup
from galaxy_tool_fmt.format import (
    format_macro_document,
    format_tool_document_subset,
)
from galaxy_tool_source.binding import ToolXmlSyntaxError
from galaxy_tool_source.bundle import (
    BundleRenameOutcome,
    ToolBundle,
    load_bundle,
    rename_param_in_bundle,
)
from galaxy_tool_source.cheetah_refs import tool_cheetah_references
from galaxy_tool_source.cheetah_rename import is_identifier
from galaxy_tool_source.macros import imported_macro_paths
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


@dataclass(frozen=True)
class ConsensusRenameResult:
    """Outcome of a rename across every importer of a shared macro, in lockstep.

    ``changed`` is True only when the whole consensus group agreed and was rewritten.
    On a skip ``reason`` says why: a name-gate reason (``invalid-name`` / ``no-op``),
    ``not-found`` (no tool in the group defines the parameter), ``unparseable-macro``,
    ``macro-ownership-unprovable`` (a macro the group edits is absent from the importer
    map — the repo root does not cover it), or ``no-consensus`` (at least one importer
    cannot rename the parameter safely — see ``dissenting``).
    """

    seed: Path
    old: str
    new: str
    changed: bool
    reason: str | None = None
    edits: tuple[BundleMemberEdit, ...] = ()
    tools: tuple[Path, ...] = ()
    dissenting: tuple[tuple[Path, str], ...] = ()


def _member_renamed(outcome: BundleRenameOutcome, source_path: Path | None, /) -> int:
    """How many sites a member at *source_path* rewrote in *outcome*."""
    return next(
        (m.renamed for m in outcome.members if m.source_path == source_path), 0
    )


def rename_param_consensus(
    seed: Path,
    /,
    *,
    old: str,
    new: str,
    importers: Mapping[Path, frozenset[Path]],
    write: bool = False,
    backup: bool = False,
) -> ConsensusRenameResult:
    """Rename *old* to *new* across *seed* and every co-importer of any shared macro.

    The opt-in counterpart to ``rename_param_bundle``'s sole-owned gate: instead of
    *skipping* a shared macro, rename the parameter across **all** of its importers in
    lockstep, editing the shared macro once. The consensus group is the fixed-point
    closure of *seed* under "imports a macro this rename edits" (so a chain of shared
    macros is fully covered). The rename applies only when **every** group tool agrees —
    each either renames cleanly or simply does not use the parameter (``not-found``); a
    single importer that references it but cannot be rewritten safely makes the whole
    group ``no-consensus`` (reported in ``dissenting``), and nothing is written. Each
    file (tool or macro) is written once; *importers* must cover every edited macro.
    """
    seed = seed.resolve()
    if not is_identifier(old) or not is_identifier(new):
        return ConsensusRenameResult(
            seed, old, new, changed=False, reason="invalid-name"
        )
    if old == new:
        return ConsensusRenameResult(seed, old, new, changed=False, reason="no-op")

    group: dict[Path, tuple[ToolBundle, BundleRenameOutcome]] = {}
    dissenting: list[tuple[Path, str]] = []
    frontier: list[Path] = [seed]
    while frontier:
        tool = frontier.pop().resolve()
        if tool in group:
            continue
        try:  # third-party parse boundary: a malformed tool cannot join the group
            bundle = load_bundle(tool)
        except ToolXmlSyntaxError:
            dissenting.append((tool, "syntax-error"))
            continue
        if bundle.unparseable:
            return ConsensusRenameResult(
                seed, old, new, changed=False, reason="unparseable-macro"
            )
        outcome = rename_param_in_bundle(bundle, old=old, new=new)
        group[tool] = (bundle, outcome)
        if outcome.bailed:
            if outcome.reason != "not-found":
                dissenting.append((tool, outcome.reason or "unknown"))
            continue
        for macro in outcome.edited_macros:
            if macro not in importers:
                return ConsensusRenameResult(
                    seed, old, new, changed=False, reason="macro-ownership-unprovable"
                )
            frontier.extend(importers[macro])

    if dissenting:
        return ConsensusRenameResult(
            seed, old, new, changed=False, reason="no-consensus",
            dissenting=tuple(sorted(dissenting)),
        )

    edits_by_path: dict[Path, BundleMemberEdit] = {}
    renamed_tools: list[Path] = []
    for tool, (bundle, outcome) in group.items():
        if outcome.bailed:  # a co-importer that does not use the parameter — leave it
            continue
        # Only rewrite a tool whose OWN tree changed; a co-importer whose sole edits are
        # in a shared macro contributes that macro (deduped below), not its own file.
        tool_renamed = _member_renamed(outcome, bundle.tool.source_path)
        if tool_renamed > 0:
            renamed_tools.append(tool)
            edits_by_path[tool] = BundleMemberEdit(
                path=tool,
                kind="tool",
                renamed=tool_renamed,
                formatted=format_tool_document_subset(bundle.tool, rule_classes=()),
            )
        edited = set(outcome.edited_macros)
        for macro_doc in bundle.macros:
            path = macro_doc.source_path
            if path is not None and path in edited and path not in edits_by_path:
                edits_by_path[path] = BundleMemberEdit(
                    path=path,
                    kind="macro",
                    renamed=_member_renamed(outcome, path),
                    formatted=format_macro_document(macro_doc),
                )
    if not edits_by_path:
        return ConsensusRenameResult(seed, old, new, changed=False, reason="not-found")
    if write:
        for edit in edits_by_path.values():
            if backup:
                make_backup(edit.path)
            edit.path.write_bytes(edit.formatted)
    return ConsensusRenameResult(
        seed, old, new, changed=True,
        edits=tuple(edits_by_path.values()),
        tools=tuple(sorted(renamed_tools)),
    )
