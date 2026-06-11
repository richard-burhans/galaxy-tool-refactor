"""``CodemodCommand`` base class and the detect-dispatch harness.

A structural codemod subclasses ``CodemodCommand`` and defines one or more
``detect_<TagPascalCase>`` methods. ``detect(module)`` walks the lxml tree in
document order; for each element it looks up ``detect_<TagPascalCase>`` and, if
present, yields the ``Change``s it returns — **without mutating the tree**. The
yielded change list *is* the lint report. ``apply(module)`` is derived: it
materialises ``detect(module)`` and runs each change's ``mutate`` thunk, so the
change a codemod reports is exactly the change it applies. Comment and
ProcessingInstruction nodes are skipped by ``Cursor.children()`` so detectors
only see real elements.

Validation-driven codemods (``FixTypos``, ``UpgradeToLatest`` and the per-step
upgrades) cannot pre-compute a static change list — they branch on
re-validation — so they override ``apply`` with bespoke logic and supply a
**coarse** ``detect`` (see ``codemods._coarse_detect``).

Dispatch is by **tag name** (``<param>`` → ``detect_Param``,
``<change_format>`` → ``detect_ChangeFormat``). The architecture targets
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

from galaxy_tool_codemod.change import Change, apply_changes
from galaxy_tool_codemod.cursor import Cursor
from galaxy_tool_codemod.eligibility import corpus_test_profile

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from galaxy_tool_refactor_rules.meta import RuleMeta
    from galaxy_tool_source.document import ToolDocument

    from galaxy_tool_codemod.module import Module


@cache
def _detect_method_name(tag: str) -> str:
    """Convert an XML tag to its detector method name.

    ``"param"`` → ``"detect_Param"``;
    ``"change_format"`` → ``"detect_ChangeFormat"``.
    """
    parts = tag.split("_")
    pascal = "".join(part[:1].upper() + part[1:] for part in parts)
    return f"detect_{pascal}"


class CodemodCommand:
    """Base class for structural-refactor codemods.

    Every bundled codemod carries a ``meta: ClassVar[RuleMeta]`` GTR descriptor
    (shared with the formatter tier via ``galaxy-tool-refactor-rules``) so the
    two tiers expose one uniform rule registry. The enumerated set of coded
    codemods is ``catalog.coded_codemods()``.
    """

    meta: ClassVar[RuleMeta]

    def detect(self, module: Module, /) -> Iterable[Change]:
        """Yield the ``Change``s this codemod would make, without mutating.

        Walks ``module``'s lxml tree in document order, dispatching
        ``detect_<Tag>`` for each element and yielding the changes it returns.
        The default walk drives the structural (cursor-walk) codemods;
        validation-driven codemods override this with a coarse detector.
        """
        yield from self._detect_dispatch(Cursor(module.document.root))

    def _detect_dispatch(self, cursor: Cursor) -> Iterator[Change]:
        method_name = _detect_method_name(cursor.tag)
        detector = getattr(self, method_name, None)
        if detector is not None:
            yield from detector(cursor)
        for child in cursor.children():
            yield from self._detect_dispatch(child)

    def apply(self, module: Module, /) -> None:
        """Apply this codemod by running every detected change's thunk.

        Detection is materialised first (all reads complete before any
        mutation), then ``apply_changes`` runs the thunks. Mutations apply
        immediately to the underlying tree; atomicity (deep-copy snapshot) is
        the responsibility of whatever harness invokes ``apply`` — for the
        canonical-pipeline CLI that's the app tier; for sweep tooling that's
        the relevant subcommand.
        """
        apply_changes(list(self.detect(module)))

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
