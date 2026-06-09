"""Codemod: normalize non-canonical boolean attribute values until a tool validates.

A sibling of ``FixTypos`` in the validation-driven family: it targets a tool that
is well-formed but validates at **no** vendored profile, and rewrites Python-style
boolean attribute values (``True``/``False``/``Yes``/``No``/``On``/``Off``) on
schema-boolean attributes to the canonical ``xs:boolean`` form (``true``/``false``)
so the tool validates. The Galaxy XSD types these attributes ``xs:boolean`` (which
rejects the capitalized forms), but Galaxy's runtime reads booleans
case-insensitively — so the rewrite is **behaviour-preserving**.

``FixTypos`` cannot do this: the lenient generated model lists ``"True"`` as a
legal value, so ``suggest_corrections`` never flags it. Detection here is
schema-type-aware (tier 1's ``suggest_boolean_normalizations`` only reports
attributes the model types as boolean *at the element they appear on*), so a
literal-string attribute — ``value`` on ``<option>`` — is never touched.

Like ``FixTypos`` it iterates profiles newest-to-oldest, normalizing with each
profile's vocabulary (an attribute is ``xs:boolean`` only under some profiles),
and stops at the first profile that validates; if none do, a deep-copy snapshot
is restored, leaving the document byte-identical. ``profile=`` is never written.
See ``docs/decisions.md`` §26.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_xml.binding import newest_valid_profile, validate_tool
from galaxy_tool_xml.boolean_values import (
    BooleanNormalization,
    suggest_boolean_normalizations,
)
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


def _resolve(
    root: etree._Element, normalization: BooleanNormalization, /
) -> etree._Element | None:
    """Return the element a ``BooleanNormalization`` refers to, or ``None``.

    A normalization locates its target by ``(element tag, source line, attribute,
    found value)`` rather than by element reference. Matching on the *found*
    value still being present disambiguates two same-line siblings without
    bookkeeping: once the first is rewritten its value no longer matches, so the
    next lookup finds the sibling.
    """
    for node in root.iter():
        if not isinstance(node.tag, str) or node.tag != normalization.element:
            continue
        if (node.sourceline or 0) != normalization.line:
            continue
        if node.get(normalization.attribute) == normalization.found:
            return node
    return None


class NormalizeBooleanValues(CodemodCommand):
    """Normalize non-canonical boolean values so a globally-invalid tool validates."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR017",
        summary=(
            "Normalize Python-style boolean attribute values (True/Yes/…) to "
            "canonical xs:boolean so a globally-invalid tool validates."
        ),
        since="0.0.1",
        order=20,
        rulesets=frozenset({"default", "iuc", "strict"}),
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self,
            module,
            message="non-canonical boolean values would be normalized to validate",
        )

    def apply(self, module: Module, /) -> None:
        document = module.document
        if newest_valid_profile(document) is not None:
            return  # already valid somewhere — not this codemod's population
        snapshot = copy.deepcopy(document.root)
        for version in reversed(available_profiles()):
            restore_root(document.root, snapshot)
            self._normalize_for_profile(document, version)
            if validate_tool(document, profile=version).valid:
                return
        restore_root(document.root, snapshot)

    def _normalize_for_profile(self, document: ToolDocument, version: str, /) -> None:
        """Rewrite each schema-boolean value this profile would canonicalize."""
        for normalization in suggest_boolean_normalizations(document, profile=version):
            element = _resolve(document.root, normalization)
            if element is not None:
                Cursor(element).set_attribute(
                    normalization.attribute, normalization.suggested
                )

    @classmethod
    def corpus_eligible(cls, document: ToolDocument, /) -> bool:
        """Eligible exactly for the population this codemod repairs.

        Inverts the default sweep policy: a tool is in scope only when it is
        well-formed but validates at no profile (the same population ``FixTypos``
        targets).
        """
        return newest_valid_profile(document) is None

    @classmethod
    def corpus_validation_profile(cls, document: ToolDocument, /) -> str | None:
        """Profile to validate the *post-normalization* document at.

        A successful normalization makes the tool validate at some version, which
        this returns; an unfixable tool stays ``None`` (a legitimate no-op
        outcome, not a failure).
        """
        return newest_valid_profile(document)
