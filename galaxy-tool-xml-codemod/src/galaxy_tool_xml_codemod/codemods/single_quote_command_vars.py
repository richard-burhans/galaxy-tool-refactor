"""Codemod: single-quote behaviour-preserving Cheetah vars in <command> (GTR020).

The IUC ``single-quote your Cheetah variables`` practice guards against shell
word-splitting / injection, but quoting is only *behaviour-preserving* in some
positions. This codemod is the fixer for the subset that is provably so, via the
shared tier-1 policy ``galaxy_tool_xml.shell_oracle.quote_is_behavior_preserving``:

- **value-domain** (always, no dependency): a reference whose rendered value can never
  contain whitespace — the ``{safe, attr_safe, builtin_path}`` classes
  (``command_vars``): a bare ``$param`` of a single-token type, a ``$param.ext`` / path
  attribute, or a ``$__…__`` Galaxy path built-in;
- **shell-context** (when the optional ``galaxy-tool-xml[shell-oracle]`` extra is
  installed): the bashlex classifier additionally *widens* to any reference in a
  no-word-splitting context (an assignment RHS ``THREADS=$opts`` is safe to quote even
  for a free-form ``text`` param) and *narrows* away fd-dup targets (``2>&$fd``, where
  quoting a numeric fd flips a duplication into a file redirect). Without the extra the
  policy is exactly the value-domain rule, so the default ``format`` output is unchanged
  and license-clean (bashlex is GPL v3+).

Free-form ``text`` params in a splitting position, ``multiple=`` splats, label attrs
(``$input.name``), ``$on_string`` and ``#set``/loop vars in splitting positions are
left untouched; the advisory ``GTR020.2`` check reports that residual (using the same
shared policy, so the fix/advisory partition stays exact). The ``certifier`` constructor
argument reserves the Phase-2 seam (a render-based ``EditCertifier`` override); it
defaults to the static policy. See ``docs/decisions.md`` §30–31 and
``../docs/upgrade_research/cheetah_bashlex_boundary_oracle.md``.

It rides the canonical/``format`` pipeline (``canonical.py``). The rewrite is a
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
from galaxy_tool_xml.command_vars import input_param_info
from galaxy_tool_xml.shell_oracle import quote_is_behavior_preserving

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from galaxy_tool_xml_codemod.certify import EditCertifier
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
    """Single-quote the provably behaviour-preserving Cheetah vars in <command>."""

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

    def __init__(self, *, certifier: EditCertifier | None = None) -> None:
        """*certifier*: a Phase-2 ``EditCertifier`` override; ``None`` (default) uses
        the tier-1 static policy ``quote_is_behavior_preserving`` (value-domain, plus
        bashlex shell-context when the ``shell-oracle`` extra is present)."""
        self._certifier = certifier

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
        decide = (
            self._certifier.should_quote
            if self._certifier is not None
            else quote_is_behavior_preserving
        )
        qualifying = [
            occurrence
            for occurrence in unquoted_cheetah_vars(body)
            if decide(body, occurrence=occurrence, kinds=kinds, structural=structural)
        ]
        if not qualifying:
            return
        yield Change(
            code=self.meta.code,
            sourceline=cursor.sourceline,
            xpath=cursor.xpath,
            message=(
                f"single-quoted {len(qualifying)} behaviour-preserving Cheetah "
                "variable(s) in <command>"
            ),
            mutate=_wrap_occurrences(
                body, qualifying, cursor=cursor, cdata=cursor.is_cdata_wrapped()
            ),
        )
