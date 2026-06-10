"""``ToolBundle`` — a tool and its transitively-imported macro files as one unit.

A Galaxy tool routinely *defines* a ``<param>`` in its own ``<inputs>`` but only
*references* it (``$param``) inside an imported macro file's ``<command>`` /
``<configfile>`` fragment. A single-file rename cannot see those references, so it
silently leaves a dangling ``$old`` in the macro — a broken tool. The bundle is the
unit a cross-file rename operates over: the tool document plus every macro document
it imports (transitively, via ``imported_macro_paths``), each carrying its own
``source_path`` so edits write back to the right file ("locate-in-source").

``rename_param_in_bundle`` renames across the whole bundle **atomically**, reusing
the single-root ``cheetah_rename.rename_param`` per member (it adapts to a
``<macros>`` root on its own). Aggregation: a member that simply does not mention
``old`` reports ``not-found`` and contributes nothing (the common outcome for an
unrelated macro); **any other** member bail (``shadowed`` / ``mixed-content`` /
``lexer-bail`` / ``filter-bare-ref`` / ``cross-ref-residual``)
bails the **whole** bundle — renaming the tool's param while a macro reference to
``$old`` survives would dangle.

This module owns no I/O policy and **no shared-file gate**: it mutates the bundle's
in-memory trees and reports which members changed. Deciding whether an edited macro
is safe to write (sole-owned vs shared by other tools) and serialising the result is
the registry's job (it has the repo-wide importer map). The caller passes a bundle it
is willing to see mutated and discards it on a bail — exactly as the facade
deep-copies before calling the single-root ``rename_param``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from galaxy_tool_source.binding import (
    ToolXmlSyntaxError,
    load_macros,
    load_tool,
)
from galaxy_tool_source.cheetah_rename import is_identifier, rename_param
from galaxy_tool_source.document import MacroDocument, ToolDocument
from galaxy_tool_source.macros import imported_macro_paths


@dataclass(frozen=True)
class ToolBundle:
    """A tool document plus the macro documents it imports, transitively.

    Attributes:
        tool: The tool document (its tree is mutable, the source of truth).
        macros: The imported macro documents, in import order, each with its own
            ``source_path``. Built from ``imported_macro_paths`` so the set matches
            what Galaxy would expand.
        unparseable: Imported macro paths that exist but could not be parsed. A
            rename cannot prove it is safe when a macro it might reference ``old``
            from is unreadable, so a caller that mutates should treat a non-empty
            value conservatively (bail rather than risk a dangling reference).
    """

    tool: ToolDocument
    macros: tuple[MacroDocument, ...]
    unparseable: tuple[Path, ...] = ()


def load_bundle(source: Path, /) -> ToolBundle:
    """Load *source* and every macro file it imports, transitively.

    The tool is parsed strictly (``load_tool`` raises ``ToolXmlSyntaxError`` on a
    malformed tool, as for any single-file load). Each imported macro file that
    parses becomes a ``MacroDocument``; one that exists but is malformed is recorded
    in ``unparseable`` rather than aborting the whole load. ``source`` must be a
    filesystem path — import resolution needs a directory on disk.
    """
    tool = load_tool(source)
    macros: list[MacroDocument] = []
    unparseable: list[Path] = []
    for macro_path in imported_macro_paths(tool):
        # third-party parse boundary: a file that recovers under the lenient import
        # scan can still be too malformed for the strict macro loader. Record it and
        # keep the bundle usable rather than failing every importer of one bad file.
        try:
            macros.append(load_macros(macro_path))
        except ToolXmlSyntaxError:
            unparseable.append(macro_path)
    return ToolBundle(tool, tuple(macros), tuple(unparseable))


@dataclass(frozen=True)
class BundleMemberRename:
    """The rename outcome for one bundle member (the tool or one macro file).

    Attributes:
        source_path: The member's file path, or ``None`` for an in-memory document.
        kind: ``"tool"`` or ``"macro"``.
        renamed: How many sites were rewritten in this member (``0`` if it did not
            mention ``old`` or it bailed).
        bailed: True when this member changed nothing.
        reason: The member's bail reason (see ``cheetah_rename``), or ``None``.
    """

    source_path: Path | None
    kind: str
    renamed: int
    bailed: bool
    reason: str | None


@dataclass(frozen=True)
class BundleRenameOutcome:
    """The result of renaming a parameter across a whole bundle, atomically.

    Attributes:
        members: The per-member outcomes, the tool first then each macro in import
            order.
        renamed: Total sites rewritten across all members, or ``0`` on a bail.
        bailed: True when the bundle changed nothing (a member hard-bailed, or no
            member mentioned ``old``). On a bail the in-memory trees may be partially
            mutated — the caller discards them.
        reason: The bundle-level bail reason, or ``None`` on success.
        bail_member: The member a hard bail is attributed to, or ``None``.
    """

    members: tuple[BundleMemberRename, ...]
    renamed: int
    bailed: bool
    reason: str | None
    bail_member: Path | None

    @property
    def edited_macros(self) -> tuple[Path, ...]:
        """Macro files this rename actually rewrote (the gate's classification set)."""
        return tuple(
            member.source_path
            for member in self.members
            if member.kind == "macro"
            and member.renamed > 0
            and member.source_path is not None
        )


def _member_rename(
    document: ToolDocument | MacroDocument, kind: str, old: str, new: str, /
) -> BundleMemberRename:
    """Rename within one member's tree and project its outcome onto the bundle shape."""
    outcome = rename_param(document.root, old=old, new=new)
    return BundleMemberRename(
        source_path=document.source_path,
        kind=kind,
        renamed=outcome.renamed,
        bailed=outcome.bailed,
        reason=outcome.reason,
    )


def rename_param_in_bundle(
    bundle: ToolBundle, /, *, old: str, new: str
) -> BundleRenameOutcome:
    """Rename *old* to *new* across *bundle*'s tool and macro members, atomically.

    Mutates the bundle's member trees in place on success. The shared planner runs
    per member (``rename_param`` adapts to a ``<macros>`` root automatically), and the
    outcomes are aggregated: a member reporting ``not-found`` contributes nothing,
    **any other** member bail bails the whole bundle (attributed to that member), and
    success requires at least one member to have rewritten a site. On a bail the
    in-memory trees may be partially mutated — the caller (the registry, which gates
    and serialises) works on a disposable bundle and discards it on a bail.
    """
    if not is_identifier(old) or not is_identifier(new):
        return BundleRenameOutcome((), 0, True, "invalid-name", None)
    if old == new:
        return BundleRenameOutcome((), 0, True, "no-op", None)

    members: list[BundleMemberRename] = [
        _member_rename(bundle.tool, "tool", old, new)
    ]
    for macro in bundle.macros:
        members.append(_member_rename(macro, "macro", old, new))

    member_tuple = tuple(members)
    for member in members:
        if member.bailed and member.reason != "not-found":
            return BundleRenameOutcome(
                member_tuple, 0, True, member.reason, member.source_path
            )
    total = sum(member.renamed for member in members if not member.bailed)
    if total == 0:
        return BundleRenameOutcome(member_tuple, 0, True, "not-found", None)
    return BundleRenameOutcome(member_tuple, total, False, None, None)
