"""``RuleHandle`` — the uniform, code-addressable adapter over any rule family.

The three rule families have different native shapes: a codemod
(``CodemodCommand``) yields ``Change``s and mutates an lxml tree via a ``Module``;
an fmt ``Rule`` yields ``Edit``s applied to a tree; an advisory ``CheckRule``
yields ``Violation``s and never fixes. A ``RuleHandle`` wraps any of them behind a
single interface so the registry, the rulesets, and the facade can treat every
baked-in rule the same way and address it by its ``RuleMeta.code``.

The handle is pure data plus closures (mirroring tier-2's ``Change.mutate``
thunk): ``detect`` always returns a materialised ``list[Violation]``; ``apply`` is
``None`` for advisory (detect-only) rules and a tree-mutating thunk otherwise.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from galaxy_tool_refactor_rules.meta import RuleMeta
    from galaxy_tool_refactor_rules.violation import Violation
    from galaxy_tool_xml.document import ToolDocument


@dataclass(frozen=True)
class RuleHandle:
    """A single baked-in rule, addressable by ``meta.code`` and family-agnostic.

    Attributes:
        meta: The rule's tier-0.5 descriptor (``code``, ``summary``, ``order``,
            ``detect_only``, …).
        family: Which tier the rule comes from — ``"codemod"`` / ``"fmt"`` /
            ``"check"``. Used for apply-phase ordering and introspection.
        fixable: Whether the rule has an automatic fix (``True`` for codemod and
            fmt rules; ``False`` for advisory ``detect_only`` checks). ``apply``
            is non-``None`` exactly when this is ``True``.
        detect: Report this rule's findings for a document, without mutating it.
        apply: Apply this rule's fix to a document **in place**, or ``None`` when
            the rule only reports.
    """

    meta: RuleMeta
    family: str
    fixable: bool
    detect: Callable[[ToolDocument], list[Violation]]
    apply: Callable[[ToolDocument], None] | None
