"""``<help>`` advisory checks."""


from __future__ import annotations

import contextlib
import io
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

import docutils.core
import docutils.utils
from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation

from galaxy_tool_xml_check.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_xml.document import ToolDocument

from galaxy_tool_xml_check.checks._shared import (
    _IUC,
    _violation,
)


class _RaisingWarningStream:
    """A docutils ``warning_stream`` that raises on the first real reporter message.

    Mirrors Galaxy's ``rst_to_html`` ``FakeStream(error=True)``: any non-whitespace
    output (a warning or worse) aborts the parse, marking the RST invalid.
    """

    def write(self, message: str) -> None:
        if message and not message.isspace():
            raise ValueError(message)


def _rst_is_invalid(text: str, /) -> bool:
    """Whether *text* is invalid reStructuredText (docutils — Galaxy's ``rst_invalid``).

    Publishes through docutils with a ``warning_stream`` that raises on any reported
    message and ``halt_level`` lifted so that stream is the trigger — matching
    ``galaxy.util.rst_to_html(error=True)``. docutils exposes no LBYL validity
    predicate, so the broad ``except`` is the sanctioned third-party boundary (cf.
    ``_is_pep440``);
    stderr is redirected so a noisy role/directive can't leak past the check.
    """
    overrides = {
        "warning_stream": _RaisingWarningStream(),
        "halt_level": docutils.utils.Reporter.SEVERE_LEVEL + 1,
        "doctitle_xform": False,
        "output_encoding": "unicode",
    }
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            docutils.core.publish_string(
                text, writer="html4css1", settings_overrides=overrides
            )
    except Exception:
        return True
    return False


class HelpRstValid(CheckRule):
    """GTR089 — a ``<help>`` body should be valid reStructuredText.

    Reimplements planemo `HelpInvalidRST` (`galaxy.tool_util.linters.help`), which runs
    the help through Galaxy's ``rst_to_html`` and reports any docutils warning/error.
    Help with ``format="markdown"`` is skipped (RST is the default). A
    whole-help-via-macro tool has
    no literal ``<help>`` text and is skipped; a help body embedding a ``@…@`` token is
    still validated — the token is inert text (corpus-verified the RST errors are
    structural, not token-caused). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR089",
        summary="A <help> body should be valid reStructuredText.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        help_element = document.root.find("help")
        if help_element is None or help_element.get("format") == "markdown":
            return
        text = help_element.text
        if not text or not text.strip():
            return
        if _rst_is_invalid(text):
            yield _violation(
                document,
                help_element,
                self.meta,
                "help is not valid reStructuredText",
            )
