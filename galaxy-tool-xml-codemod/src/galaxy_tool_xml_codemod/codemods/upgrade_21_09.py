"""Single-step profile upgrade: 21.09 -> 22.01.

Two independent 22.01 tightenings are repaired here, each behind its own
runtime proof (see the section docstrings below): the ``collection_type``
pattern facets, and the ``<stdio>`` attribute requirements (``ExitCode.range``
+ ``Regex.match`` became required; ``RangeType`` — whose only consumer is
``ExitCode.range`` — tightened away the empty form).

**collection_type.** The 22.01 schema types ``collection_type`` for the first
time: ``<param collection_type>`` becomes ``CollectionTypeList``
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

**stdio.** Galaxy's stdio parser (``lib/galaxy/tool_util/parser/xml.py``)
proves three fixes (the G1 gap-audit item,
``../../docs/deferred_fix_opportunities.md``): ``range`` falls back to the
``value`` attribute (``:1248-1250`` — runtime aliases), so ``value=`` renames
to ``range=`` and a ``value`` alongside an existing ``range`` is dead and
dropped; an ``<exit_code>`` with *neither* attribute — or whose range strips to
empty (``re.sub(r"\s", "", …)`` then the singular ``int("")`` path) — is
logged and skipped at runtime, so the dead element is deleted; and a
``<regex>`` without ``match=`` (``:1318-1324``) is likewise logged and skipped,
so it is deleted too. Deleting a runtime-skipped element and renaming runtime
aliases are behaviour no-ops that restore 22.01 validity.

**has_size Bytes.** 22.01 also types ``AssertHasSize.value``/``delta`` as
``Bytes`` (``[1-9][0-9]*([kKMGTPE]i?)?``). The runtime parser is
``galaxy.util.bytesize.parse_bytesize`` — ``upper()``, strip a suffix from the
``Ki…Ei/K…E`` table, then ``int()`` (falling back to ``float()``) — so values it
accepts that the pattern rejects are provably normalizable: surrounding/inner
whitespace (``int`` tolerates it), wrong-case suffixes (``100MI`` ≡ ``100Mi``),
and integral float/scientific forms (``129e6`` ≡ ``129000000``). The canonical
form is the case/whitespace fix when that already round-trips, else the exact
integer byte count; a non-integral parse (``1.5``) has no runtime-identical
integer form and is left, as is anything ``parse_bytesize`` rejects (``12
cars`` was never runtime-working). The mirror of the suffix grammar lives here
(``galaxy.util`` stays confined to tier-1 ``macros.py`` by convention), pinned
by tests against the runtime semantics.

Corpus incidence is ~1 tool for collection_type
(`scripts.measure collection-type-normalization`) and **0** for every stdio
shape (corpus greps: 1,795 ``<exit_code>`` elements, none using ``value=`` or
lacking both attributes) — this ships under the novel-tool soundness principle
(``../../docs/deferred_fix_opportunities.md`` A1 + G1), for the proofs, not the
counts. It only does structural normalization; ``UpdateProfile`` (run by the
``UpgradeToLatest`` loop) re-declares ``profile=`` afterwards. See
``docs/decisions.md`` §41 (collection_type) and §42 (stdio).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods._coarse_detect import coarse_detect

if TYPE_CHECKING:
    from collections.abc import Iterator

    from lxml import etree

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


# 22.01's Bytes facet (galaxy-22.01.xsd; 22.05 additionally admits "0").
_BYTES = re.compile(r"[1-9][0-9]*([kKMGTPE]i?)?")
# parse_bytesize's suffix table, longest-first (the runtime matches Ki before K).
_BYTES_SUFFIX_FACTORS: dict[str, int] = {
    "KI": 1024, "MI": 1024**2, "GI": 1024**3,
    "TI": 1024**4, "PI": 1024**5, "EI": 1024**6,
    "K": 1000, "M": 1000**2, "G": 1000**3,
    "T": 1000**4, "P": 1000**5, "E": 1000**6,
}
_COMPACT_BYTES = re.compile(r"([0-9]+)([kKmMgGtTpPeE][iI]?)?")


def _parse_bytesize(value: str, /) -> int | float | None:
    """Mirror Galaxy's ``parse_bytesize`` (``util/bytesize.py``); ``None`` = reject."""
    upper = value.upper()
    suffix = next(
        (s for s in _BYTES_SUFFIX_FACTORS if upper.endswith(s)), None
    )
    number_text = upper[: -len(suffix)] if suffix else upper
    factor = _BYTES_SUFFIX_FACTORS[suffix] if suffix else 1
    # int() first (tolerates surrounding whitespace), float() fallback — exactly
    # the runtime's order.
    try:
        return int(number_text) * factor
    except ValueError:
        pass
    try:
        return float(number_text) * factor
    except ValueError:
        return None


def _normalized_bytes(value: str, /) -> str | None:
    """A 22.01 ``Bytes``-valid form runtime-identical to *value*, or ``None``.

    ``None`` when the value is already pattern-valid, was never runtime-working
    (``parse_bytesize`` rejects it), or parses non-integral / non-positive (no
    runtime-identical pattern-valid form exists).
    """
    if _BYTES.fullmatch(value) is not None:
        return None
    parsed = _parse_bytesize(value)
    if parsed is None:
        return None
    if isinstance(parsed, float):
        if not parsed.is_integer():
            return None
        parsed = int(parsed)
    if parsed <= 0:
        return None
    compact = re.sub(r"\s+", "", value)
    match = _COMPACT_BYTES.fullmatch(compact)
    if match is not None and match.group(2) is not None:
        candidate = match.group(1) + match.group(2)[0].upper() + "i" * (
            len(match.group(2)) == 2
        )
        if _BYTES.fullmatch(candidate) and _parse_bytesize(candidate) == parsed:
            return candidate
    return str(parsed)


def _normalize_has_size(root: etree._Element, /) -> None:
    """Normalize ``has_size`` value/delta to 22.01 Bytes forms (module docstring)."""
    for has_size in root.iter("has_size"):
        for attribute in ("value", "delta"):
            value = has_size.get(attribute)
            if value is None:
                continue
            normalized = _normalized_bytes(value)
            if normalized is not None:
                has_size.set(attribute, normalized)


def _repair_stdio(root: etree._Element, /) -> None:
    """Apply the three proven 22.01 stdio repairs (module docstring, "stdio")."""
    for stdio in root.iter("stdio"):
        for exit_code in list(stdio.iter("exit_code")):
            range_value = exit_code.get("range")
            if range_value is None:
                value = exit_code.get("value")
                if value is not None:
                    exit_code.set("range", value)  # runtime aliases
                    del exit_code.attrib["value"]
                    continue
                _remove(exit_code)  # neither attr: runtime-skipped, dead
                continue
            if not re.sub(r"\s", "", range_value):
                _remove(exit_code)  # blank range: runtime-skipped, dead
                continue
            if exit_code.get("value") is not None:
                del exit_code.attrib["value"]  # never read once range exists
        for regex in list(stdio.iter("regex")):
            if regex.get("match") is None:
                _remove(regex)  # runtime-skipped, dead


def _remove(element: etree._Element, /) -> None:
    """Detach *element*, keeping its tail's whitespace with the parent."""
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


class Upgrade21_09(CodemodCommand):
    """Upgrade a tool stuck at 21.09 toward 22.01 (normalize ``collection_type``)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR093",
        summary=(
            "Upgrade a tool stuck at profile 21.09 toward 22.01 (normalize"
            " collection_type + has_size Bytes; repair stdio exit_code/regex)."
        ),
        since="0.0.1",
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self, module, message="tool would be upgraded one step past profile 21.09"
        )

    def apply(self, module: Module, /) -> None:
        _repair_stdio(module.document.root)
        _normalize_has_size(module.document.root)
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
