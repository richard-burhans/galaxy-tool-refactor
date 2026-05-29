"""Codemod: declare the newest profile the tool actually validates at.

``UpdateProfile`` reads ``newest_valid_profile`` — the newest vendored release
whose XSD the tool satisfies — and brings the root ``<tool>``'s ``profile=`` into
line with it:

- no declaration → add one set to that version;
- a declaration *older* than that version → bump it up to that version.

It is **bump-up-only**: a declared profile that is newer than (or equal to) the
newest validating version is left alone, since the ``profile`` attribute is a
runtime-compatibility contract and lowering it would claim compatibility the
tool may not have. It is also a no-op when the tool validates at no profile
(nothing to point at — that is ``FixTypos``'s job) and when the declared profile
is not a parseable version (e.g. a ``@PROFILE@`` macro placeholder).

Like ``FixTypos`` this is document-level and validation-driven, so it overrides
``apply`` rather than using the ``visit_<Tag>`` walk. It runs in
``CANONICAL_CODEMODS`` after ``FixTypos`` (a repaired tool can then be labelled)
and before ``ReorderToolAttributes`` (which positions an added ``profile=``).
See ``docs/decisions.md`` §13.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_xml.binding import newest_valid_profile
from packaging.version import InvalidVersion, Version

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from galaxy_tool_xml_codemod.module import Module


def _is_newer(target: str, declared: str, /) -> bool:
    """Whether vendored *target* is a strictly newer version than *declared*.

    Returns ``False`` when *declared* is not a parseable version (e.g. a macro
    placeholder like ``@PROFILE@``) — a profile we cannot compare is never
    rewritten. The ``try``/``except`` is the sanctioned packaging boundary:
    ``packaging`` exposes no validity predicate, mirroring ``profiles.py``.
    """
    try:
        return Version(target) > Version(declared)
    except InvalidVersion:
        return False


class UpdateProfile(CodemodCommand):
    """Set ``profile=`` to the newest profile the tool validates at (bump-up-only)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX007",
        summary=(
            "Set profile= to the newest profile the tool validates at"
            " (bump-up-only)."
        ),
        since="0.0.1",
    )

    def apply(self, module: Module, /) -> None:
        document = module.document
        target = newest_valid_profile(document)
        if target is None:
            return  # validates nowhere — nothing to point profile= at
        declared = document.profile
        if declared is None or _is_newer(target, declared):
            Cursor(document.root).set_attribute("profile", target)
