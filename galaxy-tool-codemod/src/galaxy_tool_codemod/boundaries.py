"""Render the per-boundary reference block of ``docs/profile_boundaries.md``.

The reference is the user-facing "my upgrade stopped, now what" document: one
section per profile boundary, one entry per Galaxy behaviour code, each saying
what changes at runtime, what the toolchain does about it (auto-fix, stop, or
warn), Galaxy's own description, and the release-notes link. It is **derived**
from ``PROFILE_UPGRADE_CODES`` plus the auto-fix registry
(``behavior_gate.auto_fixes_by_code``), so it cannot drift from the shipped
gate. ``scripts/gen_profile_boundaries.py`` writes the rendered block between
the doc's BEGIN/END markers; a freshness test pins the committed block to this
output. The hand-written preamble (and the structural-tightening ledger, which
lives in ``docs/profile_upgrades.md``) stays prose.
"""

from __future__ import annotations

import re

from galaxy_tool_codemod.behavior_gate import auto_fixes_by_code
from galaxy_tool_codemod.profile_semantics import (
    PROFILE_UPGRADE_CODES,
    ProfileUpgradeCode,
)

# Rule summaries carry bare XML tags (e.g. "<command interpreter=I>"); in
# markdown prose those read as unknown HTML and are dropped by renderers, so
# each <…> run is backtick-quoted (the same convention as parity.py).
_TAG = re.compile(r"<[^>]+>")


def _quote_tags(text: str, /) -> str:
    """Wrap each bare ``<…>`` XML tag in *text* in backticks for markdown."""
    return _TAG.sub(lambda match: f"`{match.group(0)}`", text)

BEGIN_MARKER = (
    "<!-- BEGIN GENERATED: profile boundary reference"
    " (scripts/gen_profile_boundaries.py) -->"
)
END_MARKER = (
    "<!-- END GENERATED: profile boundary reference"
    " (scripts/gen_profile_boundaries.py) -->"
)


def _what_we_do(change: ProfileUpgradeCode, /) -> str:
    """The toolchain's handling of *change*, phrased as next steps for the user."""
    fixes = auto_fixes_by_code()
    if change.code in fixes:
        fix = fixes[change.code]
        return (
            f"**What the toolchain does:** `upgrade` fixes this automatically"
            f" when the fix is provable for your tool ({fix.meta.code}:"
            f" {_quote_tags(fix.meta.summary)}). When it cannot prove the"
            f" construct gone"
            f" (the fix is verified by re-detection), the `--modernize` walk"
            f" stops below {change.profile}; update the tool by hand and"
            f" rerun, or rerun with `--modernize --allow-behavior-change` to"
            f" upgrade anyway."
        )
    if change.level == "must_fix":
        return (
            f"**What the toolchain does:** `upgrade --modernize` stops below"
            f" {change.profile} when this applies to your tool (there is no"
            f" automatic fix yet). Update the tool following Galaxy's"
            f" description below, then rerun; or rerun with"
            f" `--modernize --allow-behavior-change` to upgrade anyway and"
            f" review the change yourself."
        )
    return (
        "**What the toolchain does:** warns when this applies to your tool;"
        " the change is advisory (`consider`), so it does not stop the"
        " `--modernize` walk. Review Galaxy's description below at your"
        " leisure."
    )


def _code_section(change: ProfileUpgradeCode, /) -> list[str]:
    """The markdown block for one behaviour code."""
    level = (
        "`must_fix` (the tool's behaviour or output changes)"
        if change.level == "must_fix"
        else "`consider` (a runtime default changes; worth reviewing)"
    )
    lines = [
        f"### `{change.code}`",
        "",
        f"Severity: {level}.",
        "",
        _what_we_do(change),
        "",
        "**Galaxy's description:**",
        "",
        "```text",
        change.message,
        "```",
    ]
    if change.url is not None:
        lines.extend(["", f"Introduced by [{change.url}]({change.url})."])
    return lines


def render_boundary_reference() -> str:
    """The full generated reference: one section per profile boundary."""
    lines: list[str] = []
    current_profile: str | None = None
    for change in PROFILE_UPGRADE_CODES:  # catalogue order: profile-ascending
        if change.profile != current_profile:
            if current_profile is not None:
                lines.append("")
            current_profile = change.profile
            must_fix = sum(
                1
                for entry in PROFILE_UPGRADE_CODES
                if entry.profile == change.profile and entry.level == "must_fix"
            )
            stop_note = (
                "`upgrade --modernize` stops below this profile when one of its"
                " `must_fix` changes applies to your tool and cannot be fixed"
                " automatically."
                if must_fix
                else "No `must_fix` change lands here; the `--modernize` walk"
                " crosses this boundary freely (with warnings where a"
                " `consider` change applies)."
            )
            lines.extend([f"## Profile {change.profile}", "", stop_note, ""])
        lines.extend(_code_section(change))
        lines.append("")
    return "\n".join(lines).rstrip()
