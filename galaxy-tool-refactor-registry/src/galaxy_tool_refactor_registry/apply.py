"""Apply a selected code set to a document, reproducing ``format``'s ordering.

Two phases, mirroring today's app ``format`` (canonical codemods → cosmetic fmt):

1. **Structural codemods** in ``meta.order`` (``FixTypos`` → reorderers), so typo
   repair runs before the rest sees the tree.
2. **Cosmetic fmt rules** as one batch via ``format_tool_document_subset`` (which
   orders them by ``meta.order`` and serialises once).

Both phases now order by the rule's own ``meta.order`` — the codemod order no
longer rides a hardcoded pipeline tuple.

Advisory (``detect_only``) codes in the selection are ignored here — they only
report (the facade surfaces them as notes). Serialisation always goes through
fmt, preserving "fmt is the only tier that writes/serialises XML": even a
codemod-only or empty selection ends in ``format_tool_document_subset`` (with no
fmt rules it just serialises the tree).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from galaxy_tool_fmt.format import format_tool_document_subset

from galaxy_tool_refactor_registry.adapters import fmt_rule_by_code
from galaxy_tool_refactor_registry.registry import registry

if TYPE_CHECKING:
    from galaxy_tool_source.document import ToolDocument


def apply_selection(document: ToolDocument, *, codes: frozenset[str]) -> bytes:
    """Apply the fixable rules in *codes* to *document* in place; return bytes.

    Codemods run first (``meta.order``), then the selected cosmetic fmt rules.
    Advisory codes in *codes* are skipped. The document's tree is mutated in
    place; the returned bytes are the serialised result.
    """
    reg = registry()
    codemod_codes = sorted(
        (code for code in codes if reg[code].family == "codemod"),
        key=lambda code: reg[code].meta.order,
    )
    for code in codemod_codes:
        apply_fn = reg[code].apply
        # codemod rules are fixable, so apply is never None; assert for mypy.
        assert apply_fn is not None
        apply_fn(document)

    fmt_by_code = fmt_rule_by_code()
    fmt_classes = tuple(
        fmt_by_code[code] for code in codes if reg[code].family == "fmt"
    )
    return format_tool_document_subset(document, rule_classes=fmt_classes)
