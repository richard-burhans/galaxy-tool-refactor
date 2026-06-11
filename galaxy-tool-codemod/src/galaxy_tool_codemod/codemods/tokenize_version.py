"""Codemod: factor a literal version into @TOOL_VERSION@/@VERSION_SUFFIX@ (opt-in).

GTR094, the canonical IUC version-tokenization (ledger item A2,
``../../docs/deferred_fix_opportunities.md``): a literal
``version="<base>+galaxy<suffix>"`` whose ``<base>`` equals a package
``<requirement>`` version becomes ``@TOOL_VERSION@+galaxy@VERSION_SUFFIX@``,
the matching requirement versions become ``@TOOL_VERSION@``, and the two
``<token>`` definitions land in the tool's inline ``<macros>`` (created when
absent). Like GTR092 it belongs to **no ruleset**, a multi-element style
restructure, applied only by the dedicated opt-in ``tokenize-version`` surface.

The *decision* (``tokenization_skip_reason``), the *soundness gate*
(``expansion_equality_holds``, proof by execution), and the *tree mutation*
(``tokenize_tree``) now live in tier 1 (``galaxy_tool_source.version_tokens``),
single-sourced with the offset planner that backs the galaxy-language-server
Code Action (``tokenize_version_plan``). This codemod is the tree-rendering of
that shared decision: it adapts the tier-1 functions (which take a tier-1
``ToolDocument``) to the tier-2 ``Module`` the codemod framework hands it.

See ``docs/decisions.md`` §43 and ``galaxy-tool-source/docs/decisions.md`` §29 for
the offset-planner extraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_source import version_tokens

from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.codemods._coarse_detect import coarse_detect

if TYPE_CHECKING:
    from collections.abc import Iterator

    from galaxy_tool_codemod.change import Change
    from galaxy_tool_codemod.module import Module

_IUC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"


def tokenization_skip_reason(module: Module, /) -> str | None:
    """Why GTR094 would skip *module*, or ``None`` when tokenization applies.

    The ``Module`` adapter over ``galaxy_tool_source.version_tokens``; the facade's
    ``tokenize-version`` surface calls this to share the codemod's decision path.
    """
    return version_tokens.tokenization_skip_reason(module.document)


def expansion_equality_holds(module: Module, *, base: str, suffix: str) -> bool:
    """The proof-by-execution gate (``Module`` adapter over tier 1)."""
    return version_tokens.expansion_equality_holds(
        module.document, base=base, suffix=suffix
    )


class TokenizeVersion(CodemodCommand):
    """Factor ``version="<base>+galaxy<suffix>"`` into the IUC version tokens."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR094",
        summary=(
            'Factor a literal version="<base>+galaxy<suffix>" into '
            "@TOOL_VERSION@/@VERSION_SUFFIX@ tokens shared with the matching "
            "package requirement (opt-in tokenize-version only)."
        ),
        since="0.0.1",
        cite=_IUC,
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        if version_tokens.tokenization_skip_reason(module.document) is not None:
            return iter(())
        return coarse_detect(
            self, module, message="version would be tokenized to @TOOL_VERSION@"
        )

    def apply(self, module: Module, /) -> None:
        if version_tokens.tokenization_skip_reason(module.document) is not None:
            return
        root = module.document.root
        version = root.get("version") or ""
        match = version_tokens.GALAXY_SUFFIX_VERSION.fullmatch(version)
        if match is None:  # defensive: skip_reason already vetted this
            return
        base, suffix = match["base"], match["suffix"]
        if not version_tokens.expansion_equality_holds(
            module.document, base=base, suffix=suffix
        ):
            return  # the gate could not prove the no-op, leave untouched
        version_tokens.tokenize_tree(root, base=base, suffix=suffix)
