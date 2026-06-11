"""Codemod: declare the newest profile the tool actually validates at.

``UpdateProfile`` reads ``newest_valid_profile`` — the newest vendored release
whose XSD the tool satisfies — and brings the root ``<tool>``'s ``profile=`` into
line with it:

- no declaration → add one set to that version;
- a declaration *older* than that version → bump it up to that version;
- a ``@TOKEN@`` declaration whose token is defined **inline** in the tool's own
  ``<macros>`` → rewrite that token's value (keeping ``profile="@TOKEN@"``), so
  future expansions are current. A token defined in an *imported* macro file is
  left untouched here — that cross-file edit is the bundle-aware step; a token
  that resolves to no inline definition is left alone, never clobbered with a
  literal.

It is **bump-up-only**: a declared profile that is newer than (or equal to) the
newest validating version is left alone, since the ``profile`` attribute is a
runtime-compatibility contract and lowering it would claim compatibility the
tool may not have. It is also a no-op when the tool validates at no profile
(nothing to point at — that is ``FixTypos``'s job).

Like ``FixTypos`` this is document-level and validation-driven, so it overrides
``apply`` rather than using the ``detect_<Tag>`` walk. It runs in
``canonical_codemods()`` after ``FixTypos`` (a repaired tool can then be labelled)
and before ``ReorderToolAttributes`` (which positions an added ``profile=``).
See ``docs/decisions.md`` §13.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_source.binding import newest_valid_profile
from galaxy_tool_source.profiles import is_newer_profile

from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.codemods._coarse_detect import coarse_detect
from galaxy_tool_codemod.cursor import Cursor

if TYPE_CHECKING:
    from collections.abc import Iterator

    from galaxy_tool_codemod.change import Change
    from galaxy_tool_codemod.module import Module


class UpdateProfile(CodemodCommand):
    """Set ``profile=`` to the newest profile the tool validates at (bump-up-only)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR007",
        summary=(
            "Set profile= to the newest profile the tool validates at"
            " (bump-up-only)."
        ),
        since="0.0.1",
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self,
            module,
            message="profile= would be set to the newest validating profile",
        )

    def apply(self, module: Module, /) -> None:
        document = module.document
        target = newest_valid_profile(document)
        if target is None:
            return  # validates nowhere — nothing to point profile= at
        declared = document.profile
        if declared is None:
            Cursor(document.root).set_attribute("profile", target)
            return
        if "@" in declared:
            self._upgrade_inline_profile_token(module, declared, target)
            return
        if is_newer_profile(target, declared):
            Cursor(document.root).set_attribute("profile", target)

    def _upgrade_inline_profile_token(
        self, module: Module, token_name: str, target: str
    ) -> None:
        """Rewrite an inline ``<token name=token_name>`` profile value to *target*.

        Only an **inline** token (defined in the tool's own ``<macros>``) is
        touched, and only when its current value is older than *target*. A token
        defined in an imported macro file, or no matching inline token, is left
        alone — the ``profile="@TOKEN@"`` reference is never replaced with a
        literal. Editing an imported (possibly shared) macro file is the
        bundle-aware step's job.
        """
        token = self._inline_token(module, token_name)
        if token is None:
            return
        current = token.text.strip() if token.text else ""
        if is_newer_profile(target, current):
            token.set_text(target)

    @staticmethod
    def _inline_token(module: Module, token_name: str, /) -> Cursor | None:
        """Return the cursor for the inline ``<macros><token>`` named *token_name*."""
        for child in module.cursor.children():
            if child.tag != "macros":
                continue
            for token in child.children():
                if token.tag == "token" and token.get_attribute("name") == token_name:
                    return token
        return None
