"""Codemod: repair the deterministically-fixable invalid reStructuredText in <help>.

GTR089.1 — the **fixable** half of the GTR089 partition (the advisory residual
``GTR089.2`` lives in the check tier). A no-op unless the ``<help>`` body is invalid
RST; then it applies the class-based surgical repairs from tier-1
``galaxy_tool_xml.rst``, which keep a fix only behind a **behaviour-preserving gate**
(re-parse: strictly fewer errors + no new class, AND the docutils doctree is identical
modulo the removed messages). Macro-bearing help (``@TOKEN@``) is left alone (the
unprovable-macro case). Help with no safely-fixable error is unchanged; whatever the
repair can't reach stays the ``GTR089.2`` advisory residual. See ``docs/decisions.md``
§37; the shared predicate lives in tier 1 (``galaxy-tool-xml/docs/decisions.md`` §22).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_xml.cdata import is_cdata_wrapped
from galaxy_tool_xml.rst import has_macro_token, repair_help_rst, rst_is_invalid

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods._coarse_detect import coarse_detect
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from collections.abc import Iterator

    from galaxy_tool_xml_codemod.change import Change
    from galaxy_tool_xml_codemod.module import Module

_IUC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"


class RepairHelpRst(CodemodCommand):
    """GTR089.1 — repair the deterministically-fixable invalid ``<help>`` RST."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR089.1",
        parent="GTR089",
        summary=(
            "Repair deterministically-fixable invalid <help> reStructuredText "
            "(short title underlines, missing blank lines) behind a "
            "behaviour-preserving gate."
        ),
        since="0.0.1",
        cite=_IUC,
        order=25,
        rulesets=frozenset({"default", "iuc", "strict"}),
        planemo_linters=frozenset({"HelpInvalidRST"}),
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self, module, message="invalid <help> reStructuredText would be repaired"
        )

    def apply(self, module: Module, /) -> None:
        help_element = module.document.root.find("help")
        if help_element is None or help_element.get("format") == "markdown":
            return
        text = help_element.text
        if not text or not text.strip() or has_macro_token(text):
            return
        if not rst_is_invalid(text):
            return
        repaired = repair_help_rst(text)
        if repaired is None:
            return
        Cursor(help_element).set_text(repaired, cdata=is_cdata_wrapped(help_element))
