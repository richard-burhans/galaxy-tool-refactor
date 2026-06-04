"""The bundled codemod pipelines — ordered contracts consumed by the app tier.

Tier 2 (this package) and Tier 3 (``galaxy-tool-xml-fmt``) are independent
siblings of Tier 1 (``galaxy-tool-xml``); neither runs the user-facing
workflow. The orchestration — read a file, apply a pipeline, write the result
via fmt's serializer — lives in the top-level app tier
(``galaxy-tool-refactor-cli``). This module only declares *which* codemods run
and *in what order*; the app consumes these tuples.

Two pipelines, separated because profile upgrade is semantic and opt-in while
canonicalisation is safe and idempotent:

``CANONICAL_CODEMODS`` — the structural canonical pipeline (the app's ``format``
command, run before fmt's cosmetic rules). Front-to-back:

1. ``FixTypos`` — repair near-miss spelling typos. A no-op unless the tool
   validates at no profile, so it only acts on broken tools; running it first
   lets the rest of the pipeline see a validatable tree.
2. ``NormalizeBooleanValues`` — canonicalize Python-style boolean attribute
   values (``True``/``Yes``/…) to ``xs:boolean`` (``true``/``false``) on
   schema-boolean attributes. Like ``FixTypos`` a no-op unless the tool validates
   nowhere; behaviour-preserving and the sibling repair ``FixTypos`` cannot reach
   (the lenient model accepts ``True``).
3. ``ReorderParamAttributes`` / ``ReorderToolAttributes`` — tidy attribute order
   once the tree is settled.
4. ``ReorderToolChildren`` — reorder the root ``<tool>``'s child elements to the
   IUC convention (element-level tidying after attribute-level). Validity-safe:
   the schema's ``<tool>`` content model is order-free (``xs:all``).
5. ``WrapCommandCdata`` / ``WrapHelpCdata`` — wrap a pure-text ``<command>`` /
   ``<help>`` body in ``<![CDATA[…]]>`` (IUC #34/#42). Behaviour-preserving — lxml
   exposes the entity-unescaped text, so only the serialised bytes change, not the
   value Galaxy runs/renders. Content-level tidying, so it runs after the
   structural reorders; independent of them (it never touches child order). See
   ``docs/decisions.md`` §29.
6. ``SingleQuoteCommandVars`` — single-quote the *provably*-single-valued unquoted
   Cheetah ``$var``\\ s in ``<command>`` (GTR020, the GTR031 single-quote practice).
   Acts only on references whose value can never contain whitespace for a working
   tool (bare single-token params, ``$__…__`` path built-ins, space-free attrs),
   so it is behaviour-preserving like the CDATA wraps. It runs **after**
   ``WrapCommandCdata`` so it sees the body already in its canonical CDATA form and
   preserves it. Unlike the rest of this pipeline it changes the default ``format``
   output for tools that were never previously rewritten — a deliberate, data-backed
   reversal of the GTR031-stays-advisory stance (``docs/decisions.md`` §30). The
   advisory ``GTR031`` check still reports the non-provable residual this skips.

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

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.codemods.normalize_boolean_values import (
    NormalizeBooleanValues,
)
from galaxy_tool_xml_codemod.codemods.reorder_param_attributes import (
    ReorderParamAttributes,
)
from galaxy_tool_xml_codemod.codemods.reorder_tool_attributes import (
    ReorderToolAttributes,
)
from galaxy_tool_xml_codemod.codemods.reorder_tool_children import (
    ReorderToolChildren,
)
from galaxy_tool_xml_codemod.codemods.single_quote_command_vars import (
    SingleQuoteCommandVars,
)
from galaxy_tool_xml_codemod.codemods.wrap_command_cdata import WrapCommandCdata
from galaxy_tool_xml_codemod.codemods.wrap_help_cdata import WrapHelpCdata
from galaxy_tool_xml_codemod.upgrades import UpgradeToLatest

CANONICAL_CODEMODS: tuple[type[CodemodCommand], ...] = (
    FixTypos,
    NormalizeBooleanValues,
    ReorderParamAttributes,
    ReorderToolAttributes,
    ReorderToolChildren,
    WrapCommandCdata,
    WrapHelpCdata,
    SingleQuoteCommandVars,
)

AUTO_UPGRADE_CODEMODS: tuple[type[CodemodCommand], ...] = (
    FixTypos,
    NormalizeBooleanValues,
    UpgradeToLatest,
)
