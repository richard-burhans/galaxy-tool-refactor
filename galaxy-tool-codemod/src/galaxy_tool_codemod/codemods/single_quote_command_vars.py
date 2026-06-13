"""Codemod: single-quote <command> input/output FILE vars (GTR020.1).

The IUC ``single-quote your Cheetah variables`` practice names exactly three kinds:
"text parameters, input and output files". This codemod is the auto-fixer for the
**file** half — the part that is both in the rule's scope and provably
behaviour-preserving to quote (codemod ``docs/decisions.md`` §52):

- **scope** (``command_var_info`` / ``io_file_names``): only an input/output FILE
  reference — a bare ``$data_input`` (a single ``type="data"`` param) or a bare
  ``$output`` (an ``<outputs>`` ``<data>``), including a structural drill
  ``$cond.file``. An output dataset path is the same Galaxy-controlled single token
  as an input path. Selects, numbers, booleans, metadata attrs (``$input.ext``),
  ``multiple=`` splats, and Galaxy built-ins (``$__tool_directory__``) are **not**
  quoted — quoting them is a safe no-op but outside the rule, and quoting some of
  them (a multi-flag select, an "extra options" idiom) is exactly the
  "too aggressive" inconsistency IUC reviewers flagged (tools-iuc PR #8090).
- **provability** (the shared tier-1
  ``galaxy_tool_source.shell_oracle.quote_is_behavior_preserving``, ANDed with the
  file scope): the value-domain rule, plus the optional bashlex *narrowing* of
  fd-dup targets (``2>&$fd``) when the ``galaxy-tool-source[shell-oracle]`` extra is
  installed. It never widens (the assignment-RHS widening was reverted as unsound,
  tier-1 ``docs/decisions.md`` §17).

Text parameters in the rule's scope are *not* provably safe to quote (a free-form
value can carry spaces; only 1.2% are validator-bounded, ``scripts.measure
text-param-quotable``) and stay advisory-only via ``GTR020.2``; the safe non-file
kinds (select/number/boolean/attr/built-in) are neither quoted nor advised (out of
scope). The ``certifier`` constructor argument reserves the Phase-2 seam (a
render-based ``EditCertifier`` override) and **replaces** the default file policy
whole. See ``docs/decisions.md`` §30–31 / §51 / §52 and
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
from galaxy_tool_source.command_text import UnquotedVar, unquoted_cheetah_vars
from galaxy_tool_source.command_vars import (
    command_var_info,
    io_file_names,
    is_io_file_ref,
)
from galaxy_tool_source.shell_oracle import quote_is_behavior_preserving

from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.cursor import Cursor

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from galaxy_tool_codemod.certify import EditCertifier
    from galaxy_tool_codemod.module import Module

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
        order=110,
        rulesets=frozenset({"default", "iuc", "strict"}),
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
        kinds, structural = command_var_info(root)
        io_files = io_file_names(root)
        occurrences = unquoted_cheetah_vars(body)
        # Default policy: quote only input/output FILE references (the IUC rule's
        # "input and output files") that are provably single-token (Galaxy paths).
        # Selects, numbers, booleans, metadata attrs, and built-ins are left alone —
        # quoting them is a safe no-op but outside the rule's scope (codemod docs
        # §52). An injected certifier (the Phase-2 seam) replaces this policy whole.
        if self._certifier is not None:
            qualifying = [
                occurrence
                for occurrence in occurrences
                if self._certifier.should_quote(
                    body, occurrence=occurrence, kinds=kinds, structural=structural
                )
            ]
        else:
            qualifying = [
                occurrence
                for occurrence in occurrences
                if is_io_file_ref(occurrence.name, io_files, structural)
                and quote_is_behavior_preserving(
                    body, occurrence=occurrence, kinds=kinds, structural=structural
                )
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
