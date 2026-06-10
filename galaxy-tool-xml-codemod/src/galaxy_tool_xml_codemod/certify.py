"""The ``EditCertifier`` seam: a pluggable per-edit behaviour-preservation oracle.

GTR020.1 (``SingleQuoteCommandVars``) decides, per occurrence, whether single-quoting
a Cheetah ``$var`` in ``<command>`` preserves behaviour. By **default** it uses the
tier-1 static policy ``galaxy_tool_source.shell_oracle.quote_is_behavior_preserving``
— the
bashlex shell-context classifier composed with the value-domain rule, degrading to the
pure value-domain ``provably_quotable`` when the optional
``galaxy-tool-source[shell-oracle]`` extra is absent.

This Protocol reserves the seam (shipped consulting ``None`` = the static policy) for
the Phase-2 CT3 *render* certifier (``--certify=render``): an ``EditCertifier`` injected
into the codemod overrides the default and may only *narrow* the candidate set. The
codemod calls ``should_quote`` with the same arguments as the static policy so the two
are interchangeable. See
``../../docs/upgrade_research/cheetah_bashlex_boundary_oracle.md`` §4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from galaxy_tool_source.command_text import UnquotedVar


@runtime_checkable
class EditCertifier(Protocol):
    """Certifies whether a single-quote edit on one ``<command>`` occurrence is safe."""

    def should_quote(
        self,
        body: str,
        /,
        *,
        occurrence: UnquotedVar,
        kinds: dict[str, str],
        structural: set[str],
    ) -> bool:
        """Whether single-quoting *occurrence* in ``<command>`` *body* keeps behaviour.

        Signature-compatible with
        ``galaxy_tool_source.shell_oracle.quote_is_behavior_preserving`` so a
        certifier and
        the default static policy are drop-in interchangeable.
        """
        ...
