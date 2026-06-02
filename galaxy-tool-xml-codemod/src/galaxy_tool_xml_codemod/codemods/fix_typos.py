"""Codemod: repair near-miss spelling typos until a tool validates.

Unlike the structural codemods, ``FixTypos`` is validation-driven: it targets a
tool that is well-formed but validates at **no** vendored profile, and rewrites
near-miss typos (misspelled attribute names, child-element tags, enumerated
attribute values) so that it validates. It iterates profiles newest-to-oldest;
for each candidate it asks tier 1's ``suggest_corrections`` what that profile's
vocabulary would correct, applies those corrections, and checks validity —
stopping at the first profile that validates.

This shape does not fit the ``detect_<Tag>`` walk, so ``apply`` is overridden
rather than implemented through ``CodemodCommand``'s dispatch (and ``detect`` is
the coarse apply-on-copy form; see ``_coarse_detect``). Two properties are
load-bearing:

- **Atomic.** A deep-copy snapshot is taken on entry; each profile attempt
  starts from it, and if no profile validates the snapshot is restored, leaving
  the document byte-identical (CDATA, comments, attribute order intact).
- **Idempotent.** The codemod only acts when ``newest_valid_profile`` is
  ``None``; after a successful repair the tool validates somewhere, so a second
  run is an immediate no-op.

``profile=`` is never written — only spellings change; the sibling
``UpdateProfile`` codemod owns the declared profile. ``FixTypos`` runs first in
``CANONICAL_CODEMODS``. See ``docs/decisions.md`` §11 (this codemod) and §13
(canonical ordering).
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_xml.binding import newest_valid_profile, validate_tool
from galaxy_tool_xml.corrections import Correction, suggest_corrections
from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml.profiles import available_profiles
from lxml import etree

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods._coarse_detect import coarse_detect
from galaxy_tool_xml_codemod.codemods._validation_repair import restore_root
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from collections.abc import Iterator

    from galaxy_tool_xml_codemod.change import Change
    from galaxy_tool_xml_codemod.module import Module

# Cascading typos (one fix exposing the next) converge in a handful of rounds;
# the cap guarantees termination even if a correction can never be applied.
_MAX_ROUNDS = 5


def _resolve(
    root: etree._Element, correction: Correction, claimed: set[int], /
) -> etree._Element | None:
    """Return the element a ``Correction`` refers to, or ``None`` if not found.

    ``Correction`` locates a typo by ``(element tag, source line, found token)``
    rather than by element reference, so the live tree is walked to recover the
    node. Resolution is defensive (LBYL): a correction that cannot be uniquely
    located is skipped rather than raised on, since difflib could in principle
    surface a token that no longer matches the tree.

    ``claimed`` holds the ``id()`` of elements already matched this round, so
    two corrections sharing a ``(tag, line, token)`` key — e.g. two same-tag
    elements minified onto one source line — resolve to *distinct* nodes
    instead of both targeting the first (which would double-apply and raise).
    """
    line = correction.line
    if correction.kind == "element":
        # ``element`` is the parent tag; ``found`` is the misspelled child tag.
        for node in root.iter():
            if id(node) in claimed:
                continue
            if not isinstance(node.tag, str) or node.tag != correction.found:
                continue
            if (node.sourceline or 0) != line:
                continue
            parent = node.getparent()
            if parent is not None and parent.tag == correction.element:
                return node
        return None
    # ``attribute`` / ``enum_value``: the element bearing the attribute.
    for node in root.iter():
        if id(node) in claimed:
            continue
        if not isinstance(node.tag, str) or node.tag != correction.element:
            continue
        if (node.sourceline or 0) != line:
            continue
        if correction.kind == "attribute" and correction.found in node.attrib:
            return node
        if (
            correction.kind == "enum_value"
            and node.get(correction.attribute or "") == correction.found
        ):
            return node
    return None


def _apply_correction(element: etree._Element, correction: Correction, /) -> None:
    """Apply one resolved correction through ``Cursor`` mutation primitives."""
    cursor = Cursor(element)
    if correction.kind == "attribute":
        cursor.rename_attribute(correction.found, correction.suggested)
    elif correction.kind == "element":
        cursor.rename_tag(correction.suggested)
    else:  # enum_value
        cursor.set_attribute(correction.attribute or "", correction.suggested)


class FixTypos(CodemodCommand):
    """Repair near-miss spelling typos so a globally-invalid tool validates."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX006",
        summary="Repair near-miss spelling typos so a globally-invalid tool validates.",
        since="0.0.1",
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self, module, message="near-miss typos would be repaired to validate"
        )

    def apply(self, module: Module, /) -> None:
        document = module.document
        if newest_valid_profile(document) is not None:
            return  # already valid somewhere — not this codemod's population
        snapshot = copy.deepcopy(document.root)
        for version in reversed(available_profiles()):
            restore_root(document.root, snapshot)
            self._repair_for_profile(document, version)
            if validate_tool(document, profile=version).valid:
                return
        restore_root(document.root, snapshot)

    def _repair_for_profile(self, document: ToolDocument, version: str, /) -> None:
        """Apply this profile's suggested corrections until stable (bounded)."""
        for _ in range(_MAX_ROUNDS):
            corrections = suggest_corrections(document, profile=version)
            if not corrections:
                return
            # Resolve every correction to an element against the current tree
            # before mutating, so a tag/attribute rename can't invalidate a
            # later lookup keyed on the pre-mutation spelling. ``claimed`` keeps
            # two corrections from resolving to the same node (see _resolve).
            claimed: set[int] = set()
            resolved: list[tuple[etree._Element, Correction]] = []
            for correction in corrections:
                element = _resolve(document.root, correction, claimed)
                if element is not None:
                    claimed.add(id(element))
                    resolved.append((element, correction))
            if not resolved:
                return  # nothing applicable — avoid spinning to the round cap
            for element, correction in resolved:
                _apply_correction(element, correction)

    @classmethod
    def corpus_eligible(cls, document: ToolDocument, /) -> bool:
        """Eligible exactly for the population this codemod repairs.

        Inverts the default sweep policy: a tool is in scope only when it is
        well-formed but validates at no profile (the standard
        ``corpus_test_profile`` excludes precisely these tools).
        """
        return newest_valid_profile(document) is None

    @classmethod
    def corpus_validation_profile(cls, document: ToolDocument, /) -> str | None:
        """Profile to validate the *post-repair* document at.

        Evaluated by the sweep after ``apply``: a successful repair makes the
        tool validate at some version, which this returns; an unrepairable tool
        stays ``None`` (a legitimate no-repair outcome, not a failure).
        """
        return newest_valid_profile(document)
