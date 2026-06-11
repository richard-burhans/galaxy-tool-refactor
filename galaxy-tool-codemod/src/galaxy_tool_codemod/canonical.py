"""The bundled codemod pipelines — ordered contracts consumed by the app tier.

Tier 2 (this package) and Tier 3 (``galaxy-tool-fmt``) are independent
siblings of Tier 1 (``galaxy-tool-source``); neither runs the user-facing
workflow. The orchestration — read a file, apply a pipeline, write the result
via fmt's serializer — lives in the top-level app tier
(``galaxy-tool-refactor-cli``). This module only declares *which* codemods run
and *in what order*; the app consumes these tuples.

Two pipelines, separated because profile upgrade is semantic and opt-in while
canonicalisation is safe and idempotent:

``canonical_codemods()`` — the structural canonical pipeline (the app's ``format``
command, run before fmt's cosmetic rules), derived from the codemods that declare
the ``"default"`` ruleset, ordered by ``meta.order``. Front-to-back:

1. ``FixTypos`` — repair near-miss spelling typos. A no-op unless the tool
   validates at no profile, so it only acts on broken tools; running it first
   lets the rest of the pipeline see a validatable tree.
2. ``NormalizeBooleanValues`` — canonicalize Python-style boolean attribute
   values (``True``/``Yes``/…) to ``xs:boolean`` (``true``/``false``) on
   schema-boolean attributes. Like ``FixTypos`` a no-op unless the tool validates
   nowhere; behaviour-preserving and the sibling repair ``FixTypos`` cannot reach
   (the lenient model accepts ``True``).
3. ``RepairHelpRst`` — repair the deterministically-fixable invalid ``<help>``
   reStructuredText (GTR089.1, the fixable half of the GTR089 partition) behind
   tier 1's behaviour-preserving gate. A no-op on valid or macro-bearing help;
   what it can't reach stays the ``GTR089.2`` advisory residual. See
   ``docs/decisions.md`` §37.
4. ``TrimAttributeWhitespace`` / ``ReplaceOutputElement`` /
   ``DropRedundantParamName`` — the planemo-parity fixes (GTR035–GTR037):
   value-level repairs that settle attribute *content* before the reorders tidy
   attribute *order*.
5. ``ReorderParamAttributes`` / ``ReorderToolAttributes`` — tidy attribute order
   once the tree is settled.
6. ``ReorderToolChildren`` — reorder the root ``<tool>``'s child elements to the
   IUC convention (element-level tidying after attribute-level). Validity-safe:
   the schema's ``<tool>`` content model is order-free (``xs:all``).
7. ``WrapCommandCdata`` / ``WrapHelpCdata`` — wrap a pure-text ``<command>`` /
   ``<help>`` body in ``<![CDATA[…]]>`` (IUC #34/#42). Behaviour-preserving — lxml
   exposes the entity-unescaped text, so only the serialised bytes change, not the
   value Galaxy runs/renders. Content-level tidying, so it runs after the
   structural reorders; independent of them (it never touches child order). See
   ``docs/decisions.md`` §29.
8. ``SingleQuoteCommandVars`` — single-quote the *provably*-single-valued unquoted
   Cheetah ``$var``\\ s in ``<command>`` (GTR020.1, the fixable half of the GTR020
   partition).
   Acts only on references whose value can never contain whitespace for a working
   tool (bare single-token params, ``$__…__`` path built-ins, space-free attrs),
   so it is behaviour-preserving like the CDATA wraps. It runs **after**
   ``WrapCommandCdata`` so it sees the body already in its canonical CDATA form and
   preserves it. Unlike the rest of this pipeline it changes the default ``format``
   output for tools that were never previously rewritten — a deliberate, data-backed
   reversal of the GTR020.2-stays-advisory stance (``docs/decisions.md`` §30). The
   advisory ``GTR020.2`` check still reports the non-provable residual this skips.

It deliberately does **not** change ``profile=`` or apply version migrations —
that is the upgrade pipeline's job.

``AUTO_UPGRADE_CODEMODS`` — the opt-in profile-upgrade pipeline (the app's
``upgrade`` command). Front-to-back:

1. ``FixTypos`` / ``NormalizeBooleanValues`` — repair first, so a broken-and-
   outdated tool becomes validatable and therefore upgradable in one pass.
2. ``UpgradeToLatest`` — iteratively upgrade the (now possibly repaired) tool
   toward the latest profile, re-declaring its profile between steps. This
   subsumes ``UpdateProfile`` (it runs it internally each round).

``FixTypos`` / ``NormalizeBooleanValues`` intentionally appear in both pipelines;
both are idempotent, so running them in whichever pipeline the user invokes is
harmless.
"""

from __future__ import annotations

from functools import cache

from galaxy_tool_codemod.catalog import coded_codemods
from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_codemod.codemods.normalize_boolean_values import (
    NormalizeBooleanValues,
)
from galaxy_tool_codemod.upgrades import UpgradeToLatest


@cache
def canonical_codemods() -> tuple[type[CodemodCommand], ...]:
    """The structural canonical/``format`` pipeline — **derived, not hardcoded**.

    Every codemod that declares the ``"default"`` ruleset, ordered by ``meta.order``.
    Membership and application order now live on each codemod's ``RuleMeta``
    (``rulesets`` / ``order``), so this is computed from the rules rather than being
    a second hand-maintained source of truth. The front-to-back order it yields is
    the one documented above (``FixTypos`` → … → ``SingleQuoteCommandVars``).
    """
    return tuple(
        sorted(
            (cls for cls in coded_codemods() if "default" in cls.meta.rulesets),
            key=lambda cls: cls.meta.order,
        )
    )


AUTO_UPGRADE_CODEMODS: tuple[type[CodemodCommand], ...] = (
    FixTypos,
    NormalizeBooleanValues,
    UpgradeToLatest,
)
