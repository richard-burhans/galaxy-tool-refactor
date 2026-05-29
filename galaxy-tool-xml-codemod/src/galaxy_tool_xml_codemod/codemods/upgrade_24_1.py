"""Single-step profile upgrade: 24.1 -> 24.2.

Empirically (a 24.1-stuck github+toolshed corpus sweep), the only 24.2 schema
delta real tools trip on is the ``format`` attribute gaining a pattern facet.
In 24.1 ``format`` was a free ``xs:string``; 24.2 types it:

- ``<param format>`` → ``FormatList``: ``([a-z0-9._-]+)(,([a-z0-9._-]+))*``
  (comma-separated lowercase datatype tokens, no spaces);
- ``<data format>`` → ``Format``: ``[0-9a-z._-]+`` (a single such token).

24.2 applies the same lowercase-token pattern to the ``ftype`` attribute (test
``<param>`` / ``<output>`` / collection ``<element>`` datatypes), so this
codemod normalizes both ``format`` and ``ftype``.

Tools fail with uppercase (``BAM``, ``TXT``), surrounding/embedded spaces
(``fa, fasta``, ``txt ``), or empty values. This codemod normalizes every
``format`` / ``ftype`` attribute — lowercase each comma-separated token and
strip its whitespace — which is a semantics-preserving fix (Galaxy datatype
extensions are lowercase, and whitespace was never significant). A value with
no coercible token (``format=""``, all-whitespace, or only commas) is
*dropped*: an empty datatype restriction is no restriction, and ``""`` violates
the pattern, so removing the attribute both fixes validation and preserves
behaviour. What it still cannot safely coerce is left untouched, so the tool
stays stuck and the discovery sweep reports it:

- a ``<data>`` comma-list (e.g. ``fasta,fastq``) cannot become a single
  ``Format`` token without guessing which datatype to keep, so it is left;
- a non-datatype value (``?``, ``plain text``, a Cheetah ``$var``) has no
  coercion;
- a coercible value living in an imported macro file is unreachable here (this
  codemod mutates only the tool's own tree) — see ``docs/decisions.md`` §14.

It only does structural normalization; ``UpdateProfile`` (run by the
``UpgradeToLatest`` loop) re-declares ``profile=`` afterwards. See
``docs/decisions.md`` §14.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from galaxy_tool_xml_codemod.module import Module

# Attributes 24.2 newly pattern-restricts to lowercase datatype tokens:
# ``format`` (param: FormatList, data: Format) and ``ftype`` (test
# ``<param>``/``<output>``/collection ``<element>`` datatype, same pattern).
_DATATYPE_ATTRIBUTES = ("format", "ftype")


def _normalize_format(value: str, /) -> str:
    """Lowercase and strip whitespace from each comma-separated token.

    Empty tokens are dropped, so ``"fa, fasta"`` → ``"fa,fasta"`` and ``"BAM"``
    → ``"bam"``. A value with no non-empty tokens (``""``, all-whitespace, or
    only commas) returns ``""`` — the caller drops the attribute. A ``<data>``
    comma-list round-trips unchanged (not coerced into the single-token pattern
    here).
    """
    tokens = [token.strip().lower() for token in value.split(",")]
    return ",".join(token for token in tokens if token)


class Upgrade24_1(CodemodCommand):
    """Upgrade a tool stuck at profile 24.1 toward 24.2 (normalize ``format``)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX010",
        summary="Upgrade a tool stuck at profile 24.1 toward 24.2 (normalize format).",
        since="0.0.1",
    )

    def apply(self, module: Module, /) -> None:
        for element in module.document.root.iter():
            if not isinstance(element.tag, str):
                continue  # comment / processing instruction
            cursor = Cursor(element)
            for attribute in _DATATYPE_ATTRIBUTES:
                value = element.get(attribute)
                if value is None:
                    continue
                normalized = _normalize_format(value)
                if not normalized:
                    # No coercible token (empty, all-whitespace, only commas):
                    # an empty datatype restriction is no restriction, and ""
                    # violates the 24.2 pattern — drop the attribute.
                    cursor.delete_attribute(attribute)
                elif normalized != value:
                    cursor.set_attribute(attribute, normalized)
