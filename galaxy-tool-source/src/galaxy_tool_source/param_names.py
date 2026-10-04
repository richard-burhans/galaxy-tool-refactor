"""Galaxy's resolved parameter name — the one definition the other tiers share.

⛔ A ``<param>`` may carry ``name``, ``argument``, or both. When ``name`` is absent
Galaxy derives it from ``argument``, so ``argument="--min-score"`` IS a param called
``min_score``. A caller that reads ``name`` alone does not see those params at all.

That blind spot is not hypothetical and it compounds: GTR037 is the codemod that
REMOVES a redundant ``name`` beside ``argument``, so every param it rewrites became
invisible to any reader that skipped argument-only params. Measured on one 55-wrapper
repository: applying GTR037 alone moved GTR020.2 from 87 findings to 99, because
``command_vars`` could no longer classify the params whose ``name`` had just been
dropped, and GTR034 stopped examining them entirely.

Mirrors ``galaxy.tool_util.parser.util._parse_name``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lxml import etree


def derived_param_name(argument: str, /) -> str:
    """Galaxy's name-from-argument derivation: strip leading dashes, ``-`` → ``_``."""
    return argument.lstrip("-").replace("-", "_")


def resolved_param_name(param: etree._Element, /) -> str | None:
    """*param*'s resolved name: ``name``, else derived from ``argument``.

    ``None`` when it declares neither, which is the GTR054 condition.
    """
    name = param.get("name")
    if name is not None:
        return str(name)
    argument = param.get("argument")
    if argument is None:
        return None
    return derived_param_name(str(argument))
