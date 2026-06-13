"""The advisory ``.2`` residual sub-rules (GTR018.2/019.2/020.2)."""


from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from galaxy_tool_source.cdata import cdata_wrappable, needs_cdata
from galaxy_tool_source.command_text import unquoted_cheetah_vars
from galaxy_tool_source.command_vars import command_var_info
from galaxy_tool_source.shell_oracle import quote_is_behavior_preserving

from galaxy_tool_lint.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_source.document import ToolDocument

from galaxy_tool_lint.checks._shared import (
    _IUC,
    _violation,
)


class CommandCdata(CheckRule):
    """GTR018.2 — the ``<command>`` body should be wrapped in CDATA (advisory residual).

    The advisory half of the GTR018 practice: the fixable sibling ``GTR018.1``
    (``WrapCommandCdata``) wraps the pure-text bodies, so this flags only the
    **residual** the fix cannot reach — a body that needs CDATA but is mixed-content
    or carries a ``]]>`` terminator (``needs_cdata and not cdata_wrappable``, the
    shared tier-1 predicate).
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR018.2",
        parent="GTR018",
        summary="<command> CDATA residual the fix can't reach (mixed-content / ]]>).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        command = document.root.find("command")
        if (
            command is not None
            and needs_cdata(command)
            and not cdata_wrappable(command)
        ):
            yield _violation(
                document, command, self.meta, "<command> is not wrapped in CDATA"
            )


class HelpCdata(CheckRule):
    """GTR019.2 — the ``<help>`` body should be wrapped in CDATA (advisory residual).

    The advisory half of GTR019: ``GTR019.1`` (``WrapHelpCdata``) wraps the pure-text
    bodies, so this flags only the mixed-content / ``]]>``-bearing residual the fix
    cannot reach (the shared tier-1 ``needs_cdata and not cdata_wrappable``).
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR019.2",
        parent="GTR019",
        summary="<help> CDATA residual the fix can't reach (mixed-content / ]]>).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        help_element = document.root.find("help")
        if (
            help_element is not None
            and needs_cdata(help_element)
            and not cdata_wrappable(help_element)
        ):
            yield _violation(
                document, help_element, self.meta, "<help> is not wrapped in CDATA"
            )


class SingleQuotedCheetah(CheckRule):
    """GTR020.2 — single-quote Cheetah variables in ``<command>`` (advisory residual).

    The advisory half of GTR020: it reports one finding per unquoted shell-line
    ``$var`` that is **not provably safe** to single-quote — a free-form ``text``
    param or ``multiple=`` splat in a word-splitting position, a dataset-label attr,
    ``$on_string``, a ``#set``/loop var, or (when the ``shell-oracle`` extra is
    present) an fd-dup target — using the shared tier-1 ``quote_is_behavior_preserving``
    predicate (value-domain ``provably_quotable``, plus the bashlex fd-dup narrowing).
    Note the fixable sibling ``GTR020.1`` was narrowed (codemod ``docs/decisions.md``
    §52) to auto-quote only the IUC rule's input/output **files**, a subset of the
    provably-safe set; the other provably-safe kinds (selects, numbers, booleans,
    metadata attrs, Galaxy built-ins) are therefore neither auto-quoted nor flagged
    here — quoting them is a safe no-op but outside the rule, so they are left alone.
    This check is unchanged by that narrowing: it still flags exactly the
    not-provably-safe residual. A mixed-content ``<command>`` (which GTR020.1 skips
    wholesale) reports all its unquoted vars. Cheetah directive lines and
    already-quoted references are excluded by the read-only ``command_text`` lexer.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR020.2",
        parent="GTR020",
        summary="Single-quote <command> Cheetah vars: the non-provable residual.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        command = document.root.find("command")
        if command is None:
            return
        base_line = command.sourceline or 0
        xpath = str(document.tree.getpath(command))
        kinds, structural = command_var_info(document.root)
        text = "".join(command.itertext())
        # GTR020.1 only rewrites a pure-text body; in a mixed-content <command> it fixes
        # nothing, so every unquoted var there is residual.
        mixed_content = len(command) > 0
        for occurrence in unquoted_cheetah_vars(text):
            fixed_by_gtr020_1 = not mixed_content and quote_is_behavior_preserving(
                text, occurrence=occurrence, kinds=kinds, structural=structural
            )
            if fixed_by_gtr020_1:
                continue  # GTR020.1 auto-fixes this one
            yield Violation(
                code=self.meta.code,
                sourceline=base_line + occurrence.line_offset if base_line else 0,
                xpath=xpath,
                message=(
                    f"unquoted Cheetah variable {occurrence.name} in <command> — "
                    f"single-quote it as '{occurrence.name}'"
                ),
            )
