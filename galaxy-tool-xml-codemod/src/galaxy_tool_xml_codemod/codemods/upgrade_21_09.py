"""Single-step profile upgrade: 21.09 -> 22.01.

The 22.01 schema types ``collection_type`` for the first time: ``<param
collection_type>`` becomes ``CollectionTypeList``
(``(list|paired)([:,](list|paired))*`` — no whitespace), and the single-value
sites (output ``<collection type>``, ``<output collection_type>``, test
``<output_collection type>``) become ``CollectionType``. In 21.09 all were free
``xs:string``.

The provable fix is exactly the **comma-adjacent whitespace** on a ``<param>``'s
``collection_type``: Galaxy's runtime strips each comma-separated token itself
(``DataCollectionToolParameter.__init__``: ``[t.strip() for t in
collection_types.split(",")]`` — unconditional, not profile-gated), so
``"list, list:paired"`` and ``"list,list:paired"`` are runtime-identical and the
rewrite is a behaviour no-op that gains 22.01 validity. Two precise edges from
the same runtime line: ``collection_type=""`` is **dropped** (``if
collection_types:`` is falsy — identical to absent, and ``""`` violates the
pattern), while a whitespace-only value is **left** (it strips to a
matches-nothing restriction at runtime; dropping it would lift the restriction —
a behaviour change).

Everything else is left untouched, so the tool stays stuck and the discovery
sweep reports it:

- colon-inner whitespace (``list : paired``) — ``type_description.py`` splits
  ``:`` *without* stripping, so that whitespace is runtime-significant;
- the single-value ``CollectionType`` sites — no runtime strip exists for them;
- case (``List``) — runtime comparisons are exact.

Corpus incidence is ~1 tool (`scripts.measure collection-type-normalization`) —
this ships under the novel-tool soundness principle
(``../../docs/deferred_fix_opportunities.md`` A1), for the proof, not the count.
It only does structural normalization; ``UpdateProfile`` (run by the
``UpgradeToLatest`` loop) re-declares ``profile=`` afterwards. See
``docs/decisions.md`` §41.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods._coarse_detect import coarse_detect

if TYPE_CHECKING:
    from collections.abc import Iterator

    from galaxy_tool_xml_codemod.change import Change
    from galaxy_tool_xml_codemod.module import Module

# 22.01's CollectionTypeList facet (galaxy-22.01.xsd) — the target the stripped
# value must reach before anything is written.
_COLLECTION_TYPE_LIST = re.compile(r"(list|paired)([:,](list|paired))*")


def _normalized_collection_type(value: str, /) -> str | None:
    """The comma-token-stripped *value* when that is a provable 22.01 fix.

    ``None`` when there is nothing to write: the value is already clean, or the
    stripped form still violates the pattern (case, colon-inner whitespace,
    non-collection junk — all left for the discovery sweep to report).
    """
    candidate = ",".join(token.strip() for token in value.split(","))
    if candidate == value:
        return None
    if _COLLECTION_TYPE_LIST.fullmatch(candidate) is None:
        return None
    return candidate


class Upgrade21_09(CodemodCommand):
    """Upgrade a tool stuck at 21.09 toward 22.01 (normalize ``collection_type``)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR093",
        summary=(
            "Upgrade a tool stuck at profile 21.09 toward 22.01 (normalize"
            " collection_type)."
        ),
        since="0.0.1",
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self, module, message="tool would be upgraded one step past profile 21.09"
        )

    def apply(self, module: Module, /) -> None:
        for param in module.document.root.iter("param"):
            value = param.get("collection_type")
            if value is None:
                continue
            if value == "":
                # Falsy at runtime (DataCollectionToolParameter gates on
                # ``if collection_types:``) — identical to absent, and ""
                # violates the 22.01 pattern: drop it.
                del param.attrib["collection_type"]
                continue
            normalized = _normalized_collection_type(value)
            if normalized is not None:
                param.set("collection_type", normalized)
