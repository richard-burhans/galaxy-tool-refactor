"""``CodemodCommand`` base class and the visitor-dispatch harness.

A codemod subclasses ``CodemodCommand`` and defines one or more
``visit_<TagPascalCase>`` methods. ``apply(module)`` walks the lxml tree
in document order; for each element it looks up ``visit_<TagPascalCase>``
and, if present, calls it with the cursor. A visitor that returns
``False`` halts descent into that element's subtree. Comment and
ProcessingInstruction nodes are skipped by ``Cursor.children()`` so
visitors only see real elements.

Dispatch is by **tag name** (``<param>`` → ``visit_Param``,
``<change_format>`` → ``visit_ChangeFormat``). The architecture targets
typed-model class names long-term — these coincide with PascalCase tags
for unambiguous elements like ``<param>`` and ``<tool>``, and diverge
only for elements with multiple per-context typed classes (``<when>``).
Per-context dispatch is deferred until a codemod needs it.

**Macro-mode handling is not yet implemented.** A future milestone will
add a per-codemod declaration of how macros should be treated (expand /
strip / skip / leave as-is) and a harness that honours it. Codemods
written today operate on the source tree as-parsed; do not assume any
macro-aware behaviour.

See ``docs/architecture.md`` § Cursor-walk constraint and
``PLAN.md`` § M3 for the design notes.
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_xml_codemod.cursor import Cursor
from galaxy_tool_xml_codemod.eligibility import corpus_test_profile

if TYPE_CHECKING:
    from galaxy_tool_refactor_rules.meta import RuleMeta
    from galaxy_tool_xml.document import ToolDocument

    from galaxy_tool_xml_codemod.module import Module


@cache
def _visit_method_name(tag: str) -> str:
    """Convert an XML tag to its visitor method name.

    ``"param"`` → ``"visit_Param"``;
    ``"change_format"`` → ``"visit_ChangeFormat"``.
    """
    parts = tag.split("_")
    pascal = "".join(part[:1].upper() + part[1:] for part in parts)
    return f"visit_{pascal}"


class CodemodCommand:
    """Base class for structural-refactor codemods.

    Every bundled codemod carries a ``meta: ClassVar[RuleMeta]`` GTX descriptor
    (shared with the formatter tier via ``galaxy-tool-refactor-rules``) so the
    two tiers expose one uniform rule registry. The enumerated set of coded
    codemods is ``catalog.coded_codemods()``.
    """

    meta: ClassVar[RuleMeta]

    def apply(self, module: Module, /) -> None:
        """Walk ``module``'s lxml tree and dispatch ``visit_X`` for each element.

        Mutations performed via the cursor apply immediately to the
        underlying tree. Atomicity (deep-copy snapshot) is the
        responsibility of whatever harness invokes ``apply`` — for the
        canonical-pipeline CLI that's fmt's CLI; for sweep tooling
        that's the relevant subcommand.
        """
        self._dispatch(Cursor(module.document.root))

    def _dispatch(self, cursor: Cursor) -> None:
        method_name = _visit_method_name(cursor.tag)
        visit = getattr(self, method_name, None)
        if visit is not None and visit(cursor) is False:
            return
        for child in cursor.children():
            self._dispatch(child)

    def upgrade_steps_applied(self) -> tuple[str, ...]:
        """From-versions whose upgrade the last ``apply`` advanced the tool past.

        Empty for every codemod except an upgrade orchestrator like
        ``UpgradeToLatest``; the corpus sweep reads it to keep per-step upgrade
        statistics (how many tools each ``upgrade_vN`` codemod advanced).
        """
        return ()

    @classmethod
    def corpus_eligible(cls, document: ToolDocument, /) -> bool:
        """Whether a corpus sweep should run this codemod on *document*.

        Default: eligible iff the codemod-sweep policy can pick a test profile
        (i.e. the tool validates somewhere). A codemod that targets a different
        population — e.g. ``FixTypos``, which repairs tools that validate
        nowhere — overrides this. Evaluated on the pre-codemod document.
        """
        return corpus_test_profile(document) is not None

    @classmethod
    def corpus_validation_profile(cls, document: ToolDocument, /) -> str | None:
        """The profile to validate the post-codemod document at.

        Default mirrors the sweep policy. The sweep evaluates this *after*
        ``apply``; for the structural codemods that leave the validating-profile
        set unchanged it equals the pre-codemod choice, so behaviour is the same
        as validating at the policy profile. Codemods that change which profiles
        validate (``FixTypos``) override this to report the post-repair profile.
        """
        return corpus_test_profile(document)
