"""``<help>`` advisory checks."""


from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from galaxy_tool_xml.rst import has_macro_token, repair_help_rst, rst_is_invalid

from galaxy_tool_xml_check.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_xml.document import ToolDocument

from galaxy_tool_xml_check.checks._shared import (
    _IUC,
    _violation,
)


class HelpRstResidual(CheckRule):
    """GTR089.2 — a ``<help>`` body should be valid reStructuredText (the residual).

    The advisory ``.2`` half of the GTR089 partition (registry ``docs/decisions.md``
    D10). It reports the invalid RST the GTR089.1 codemod (``RepairHelpRst``) *cannot*
    safely auto-fix: non-fixable error classes (unexpected indentation, unclosed inline
    markup, …), the residual of a mixed body, and macro-bearing help (which the fix
    leaves alone). Both halves call the same tier-1 predicate
    (``galaxy_tool_xml.rst``: ``rst_is_invalid`` / ``repair_help_rst``), so the
    fix/advisory boundary can't drift. Reimplements planemo `HelpInvalidRST`
    (`galaxy.tool_util.linters.help`). Help with ``format="markdown"`` and
    whole-help-via-macro tools are skipped. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR089.2",
        parent="GTR089",
        summary=(
            "A <help> body should be valid reStructuredText (the non-fixable residual)."
        ),
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"HelpInvalidRST"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        help_element = document.root.find("help")
        if help_element is None or help_element.get("format") == "markdown":
            return
        text = help_element.text
        if not text or not text.strip():
            return
        # GTR089.1 leaves macro-bearing help alone, so it stays the residual here;
        # otherwise report only what survives the behaviour-preserving repair.
        repaired = None if has_macro_token(text) else repair_help_rst(text)
        if rst_is_invalid(repaired if repaired is not None else text):
            yield _violation(
                document,
                help_element,
                self.meta,
                "help is not valid reStructuredText (the auto-fix can't reach this)",
            )
