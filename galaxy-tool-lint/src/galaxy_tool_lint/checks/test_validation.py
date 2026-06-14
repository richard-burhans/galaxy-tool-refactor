"""GTR100 / GTR101 — Galaxy's own test-validation linters, behind an opt-in extra.

``TestsAssertionValidation`` (GTR100) and ``TestsCaseValidation`` (GTR101) validate
a tool's test output assertions / test-case parameters against Galaxy's evolving
pydantic models (``galaxy.tool_util_models``). That validation logic sits *above* the
XSD layer and is **not soundly reimplementable** — Galaxy generates its XSD *from*
those models (the reverse of our schema-as-source-of-truth pipeline; see
``docs/galaxy_reimplementations.md`` Touchpoint 5). So rather than reimplement, these
two rules **bind** Galaxy's actual linters: when the opt-in ``[test-validation]``
extra (``galaxy-tool-util``) is installed and the document has a source path, we run
the real Galaxy ``Linter`` over the tool and surface its messages as ``Violation``s.
Faithful by construction (we run planemo's own check, so there is no parity gap and
no drift as the models evolve).

Without the extra, or for an in-memory document with no source path, the rules yield
nothing — they are advisory and must never break a ``check`` run. Galaxy resolves
imported macros from the tool's directory, so a real path (not a serialized
in-memory tree) is required for faithful validation, mirroring
``DatatypesCustomConf``'s path gate.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation

from galaxy_tool_lint.checks._shared import _IUC
from galaxy_tool_lint.rules import CheckRule

if TYPE_CHECKING:
    from pathlib import Path

    from galaxy_tool_source.document import ToolDocument


def _galaxy_lint_messages(source_path: Path, linter_name: str) -> list[str]:
    """Run one Galaxy ``tests`` linter over the tool at *source_path*; its messages.

    Returns ``[]`` when the optional ``galaxy-tool-util`` extra is absent, or when
    Galaxy cannot build/lint the tool (malformed XML, an unexpandable macro). These
    rules are advisory, so a failure to evaluate is silence, never a crash — the
    Galaxy parse/lint *is* the authoritative test here (a third-party boundary), so
    a broad guard is the right shape.
    """
    try:
        from galaxy.tool_util.lint import LintContext, LintLevel
        from galaxy.tool_util.linters import tests as galaxy_tests
        from galaxy.tool_util.parser.factory import get_tool_source
    except ImportError:
        return []
    linter = getattr(galaxy_tests, linter_name)
    try:
        source = get_tool_source(str(source_path))
        lint_ctx = LintContext(level=LintLevel.ALL)
        linter.lint(source, lint_ctx)
    except Exception:  # noqa: BLE001 — third-party boundary; the lint IS the test.
        return []
    messages = (*lint_ctx.error_messages, *lint_ctx.warn_messages)
    return [message.message for message in messages]


class TestsAssertionValidation(CheckRule):
    """GTR100 — test output assertions must validate against Galaxy's models.

    Binds planemo ``TestsAssertionValidation`` (opt-in ``[test-validation]`` extra).
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR100",
        summary=(
            "Test output assertions should validate against Galaxy's "
            "assertion models."
        ),
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"TestsAssertionValidation"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        source = document.source_path
        if source is None:
            return
        line = document.root.sourceline or 0
        for message in _galaxy_lint_messages(source, "TestsAssertionValidation"):
            yield Violation(self.meta.code, line, "/tool", message)


class TestsCaseValidation(CheckRule):
    """GTR101 — test-case parameters must validate against the tool's inputs.

    Binds planemo ``TestsCaseValidation`` (opt-in ``[test-validation]`` extra): a test
    whose parameters do not validate for a modern profile will silently not run.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR101",
        summary=(
            "Test-case parameters should validate against the tool's "
            "inputs on a modern profile."
        ),
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"TestsCaseValidation"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        source = document.source_path
        if source is None:
            return
        line = document.root.sourceline or 0
        for message in _galaxy_lint_messages(source, "TestsCaseValidation"):
            yield Violation(self.meta.code, line, "/tool", message)
