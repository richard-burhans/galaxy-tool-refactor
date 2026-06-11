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

from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.codemods._coarse_detect import coarse_detect
from galaxy_tool_codemod.datatype_format import normalize_datatype_attributes

if TYPE_CHECKING:
    from collections.abc import Iterator

    from galaxy_tool_codemod.change import Change
    from galaxy_tool_codemod.module import Module


class Upgrade24_1(CodemodCommand):
    """Upgrade a tool stuck at profile 24.1 toward 24.2 (normalize ``format``)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR010",
        summary="Upgrade a tool stuck at profile 24.1 toward 24.2 (normalize format).",
        since="0.0.1",
        planemo_linters=frozenset({"ValidDatatypes"}),
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self, module, message="tool would be upgraded one step past profile 24.1"
        )

    def apply(self, module: Module, /) -> None:
        for element in module.document.root.iter():
            if not isinstance(element.tag, str):
                continue  # comment / processing instruction
            normalize_datatype_attributes(element)
