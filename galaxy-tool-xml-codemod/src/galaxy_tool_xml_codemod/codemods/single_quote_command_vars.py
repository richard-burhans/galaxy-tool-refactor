"""Codemod: single-quote provably-single-valued Cheetah vars in <command> (GTR020).

The IUC ``single-quote your Cheetah variables`` practice guards against shell
word-splitting / injection, but quoting is only *behaviour-preserving* for a
reference whose rendered value can never contain whitespace. This codemod is the
fixer for that provable subset: it single-quotes exactly the
``{safe, attr_safe, builtin_path}`` classes the tier-1 classifier
(``galaxy_tool_xml.command_vars``) certifies — a bare ``$param`` of a single-token
type, a ``$param.ext`` / path attribute, or a ``$__…__`` Galaxy path built-in.
Free-form ``text`` params, deliberate ``multiple=`` splats, label attrs
(``$input.name``), ``$on_string`` and ``#set``/loop vars are left untouched; the
advisory ``GTR020.2`` check remains the detector for that non-provable residual.

It promotes the detection-only ``GTR020.2`` lexer into a fix, so it rides the
canonical/``format`` pipeline (``canonical.py``; the fix is behaviour-preserving so
default ``format`` may apply it — see ``docs/decisions.md`` §30). The rewrite is a
**positional splice**: each occurrence carries absolute ``start``/``end`` offsets
(``unquoted_cheetah_vars``), so the wrap targets exactly the reference the lexer
found and is applied right-to-left to keep earlier offsets valid. The body is
re-emitted preserving its CDATA-ness; once an occurrence is wrapped the lexer sees
it single-quoted and skips it, so the codemod is idempotent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_xml.command_text import UnquotedVar, unquoted_cheetah_vars
from galaxy_tool_xml.command_vars import input_param_info, provably_quotable

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from galaxy_tool_xml_codemod.module import Module

_IUC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"


def _wrap_occurrences(
    body: str, occurrences: list[UnquotedVar], /, *, cursor: Cursor, cdata: bool
) -> Callable[[], None]:
    """Return a thunk that single-quotes each occurrence's span, right-to-left.

    Wrapping from the highest offset down keeps every not-yet-applied span valid
    (an inserted quote pair only shifts text *after* it). The body is re-emitted
    with the element's original CDATA-ness so only the inserted quotes differ.
    """
    new_body = body
    for occurrence in sorted(occurrences, key=lambda occ: occ.start, reverse=True):
        new_body = (
            f"{new_body[: occurrence.start]}"
            f"'{new_body[occurrence.start : occurrence.end]}'"
            f"{new_body[occurrence.end :]}"
        )

    def mutate() -> None:
        cursor.set_text(new_body, cdata=cdata)

    return mutate


class SingleQuoteCommandVars(CodemodCommand):
    """Single-quote the provably-single-valued unquoted Cheetah vars in <command>."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR020.1",
        parent="GTR020",
        summary=(
            "Single-quote provably-single-valued Cheetah variables in <command> "
            "(bare single-token params, $__…__ path built-ins, space-free attrs)."
        ),
        since="0.0.1",
        cite=_IUC,
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        root = module.document.root
        command = root.find("command")
        if command is None:
            return
        cursor = Cursor(command)
        if cursor.child_node_count() != 0:
            return  # mixed-content body — not a single rewritable text run
        body = command.text or ""
        if not body:
            return
        kinds, structural = input_param_info(root)
        qualifying = [
            occurrence
            for occurrence in unquoted_cheetah_vars(body)
            if provably_quotable(occurrence.name, kinds, structural)
        ]
        if not qualifying:
            return
        yield Change(
            code=self.meta.code,
            sourceline=cursor.sourceline,
            xpath=cursor.xpath,
            message=(
                f"single-quoted {len(qualifying)} provably-single-valued Cheetah "
                "variable(s) in <command>"
            ),
            mutate=_wrap_occurrences(
                body, qualifying, cursor=cursor, cdata=cursor.is_cdata_wrapped()
            ),
        )
