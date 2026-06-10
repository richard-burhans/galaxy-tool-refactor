"""Codemod: convert an RST ``<help>`` body to Markdown (opt-in, never canonical).

GTR092 — the conversion **swaps the rendering engine** (server-side docutils →
client-side markdown-it, see tier-1 ``galaxy_tool_xml.rst_markdown``), so it is
behaviour-changing by construction and belongs to **no ruleset**: it never runs in
``format``/``upgrade`` and is applied only by the dedicated opt-in ``convert-help``
surface. Three gates keep it sound:

- **profile gate** — ``<help format="…">`` is XSD-valid only at profile >=
  ``24.2`` (the five newest vendored schemas); an older or defaulted profile is
  skipped (run ``upgrade`` first — 91.7 % of corpus tools reach the latest profile).
- **render-equivalence gate** — tier-1 ``convert_help_rst`` keeps a conversion only
  when the markdown-it rendering is semantically equal to the docutils rendering
  (invalid RST is first passed through the GTR089.1 surgical repair, itself gated).
- **dependency gate** — conversion without the equivalence gate is unsound, so a
  missing ``galaxy-tool-xml[markdown]`` extra means no-op, never a blind convert.

See ``docs/decisions.md`` §38.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_xml.cdata import is_cdata_wrapped
from galaxy_tool_xml.profiles import is_newer_profile, resolve_profile
from galaxy_tool_xml.rst import has_macro_token
from galaxy_tool_xml.rst_markdown import convert_help_rst, markdown_renderer_available

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods._coarse_detect import coarse_detect
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from collections.abc import Iterator

    from galaxy_tool_xml_codemod.change import Change
    from galaxy_tool_xml_codemod.module import Module

_IUC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"

# The first profile whose XSD allows the <help> ``format`` attribute. Pinned by
# ``test_converted_tool_validates_at_the_gate_profile`` against the vendored schemas.
_HELP_FORMAT_PROFILE = "24.2"


def conversion_skip_reason(module: Module, /) -> str | None:
    """Why GTR092 would skip *module*, or ``None`` when a conversion applies.

    The single decision path ``apply`` runs and the ``convert-help`` surface
    reports — so the user-facing skip note can never disagree with the codemod.
    """
    if not markdown_renderer_available():
        return (
            "markdown renderer unavailable — install the galaxy-tool-xml[markdown] "
            "extra (conversion without the render-equivalence gate is unsound)"
        )
    root = module.document.root
    declared = resolve_profile(root.get("profile"))
    if is_newer_profile(_HELP_FORMAT_PROFILE, declared):
        return (
            f"profile {declared} is below {_HELP_FORMAT_PROFILE} — <help format=…> "
            "is not XSD-valid there; run `upgrade` first"
        )
    help_element = root.find("help")
    if help_element is None:
        return "no <help> element"
    if help_element.get("format") is not None:
        return "the <help> already declares a format"
    text = help_element.text
    if not text or not text.strip():
        return "empty <help>"
    if has_macro_token(text):
        return "the <help> carries a macro token (@…@) — conversion is unprovable"
    if convert_help_rst(text) is None:
        return (
            "not provably render-equivalent (a non-CommonMark construct, "
            "unrepairable RST, or a render mismatch)"
        )
    return None


class ConvertHelpToMarkdown(CodemodCommand):
    """GTR092 — convert a provably-equivalent RST ``<help>`` body to Markdown."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR092",
        summary=(
            "Convert an RST <help> body to Markdown (format=\"markdown\") when the "
            "markdown-it rendering is provably equivalent to the docutils rendering "
            "(opt-in convert-help only; requires profile >= 24.2)."
        ),
        since="0.0.1",
        cite=_IUC,
        order=90,
        rulesets=frozenset(),
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self, module, message="RST <help> would be converted to Markdown"
        )

    def apply(self, module: Module, /) -> None:
        if conversion_skip_reason(module) is not None:
            return
        help_element = module.document.root.find("help")
        assert help_element is not None  # skip_reason covered absence; for mypy
        markdown = convert_help_rst(help_element.text or "")
        assert markdown is not None  # skip_reason covered unconvertibility
        cursor = Cursor(help_element)
        cursor.set_text(markdown, cdata=is_cdata_wrapped(help_element))
        cursor.set_attribute("format", "markdown")
