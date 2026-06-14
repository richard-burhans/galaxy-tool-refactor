"""``.lint_skip`` parsing and the provable-removal coverage gate.

A Galaxy tool directory may carry a ``.lint_skip`` sidecar: one planemo
(``galaxy.tool_util.lint``) linter class name per line, telling planemo to skip
that linter for the tool(s) in the directory. Authors add them because planemo
reports a linter failure without saying which file or line is at fault, so the
whole linter gets suppressed — and the suppression then lingers.

This module backs the ``lint-skip`` convenience (cli ``docs/decisions.md`` §D19):
it applies the fixes the toolchain has and deletes a suppression line **only when
the toolchain can prove it is no longer needed**. "Prove" means two things, and
both must hold:

- **Complete coverage.** Every GTR rule carrying that planemo name is a faithful
  reimplementation of the whole linter, so "our rules are clean" implies "planemo
  would pass". The faithful set is *derived*, not hand-curated: a covering rule
  qualifies iff it is a detect-only **check**-tier rule (the planemo-parity ports,
  verified against planemo) or a **canonical codemod** (a targeted, behaviour-
  preserving fix whose detector is exactly the linter's complaint, e.g. GTR013
  element order, GTR037 redundant param name, GTR089.1 RST repair). A planemo
  name covered only *incidentally* by an upgrade-tier codemod (e.g.
  ``OutputsFormatInput`` → GTR015, the runtime-gated ``format="input"`` →
  ``format_source`` fix, which only reaches the single-top-level-data-input case
  and so does not prove the linter passes) is **not** completely covered, so its
  suppression is never removed.
- **Clean after fixing.** After applying the covering fixes, none of the covering
  rules detects on any tool the ``.lint_skip`` governs.

Anything we cannot fix, cannot prove, or do not cover is left untouched and
unmentioned: the author suppressed it deliberately, and ``check`` already reports
the full picture for anyone who wants it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from galaxy_tool_codemod.canonical import canonical_codemods

from galaxy_tool_refactor_registry.planemo import planemo_index
from galaxy_tool_refactor_registry.registry import all_handles

_LINT_SKIP_FILENAME = ".lint_skip"


@dataclass(frozen=True)
class LintSkipLine:
    """One physical line of a ``.lint_skip`` file.

    ``raw`` is the line exactly as written (no trailing newline); ``name`` is the
    planemo linter name it carries, or ``None`` for a blank or ``#``-comment line.
    Keeping every physical line lets a rewrite drop only the proven-removable
    name-lines and preserve everything else (comments, blanks, names we leave)
    byte-for-byte.
    """

    raw: str
    name: str | None


def parse_lint_skip(text: str) -> list[LintSkipLine]:
    """Parse ``.lint_skip`` *text* into ordered lines, preserving every one.

    A name-line carries its planemo linter name (an inline ``#`` comment is
    stripped, matching how planemo reads the file); a blank or comment line
    carries ``name=None``.
    """
    lines: list[LintSkipLine] = []
    for raw in text.splitlines():
        stripped = raw.split("#", 1)[0].strip()
        lines.append(LintSkipLine(raw=raw, name=stripped or None))
    return lines


def lint_skip_path(tool_path: Path, /) -> Path:
    """The ``.lint_skip`` sidecar path for *tool_path* (its directory's file).

    Pure path arithmetic — no filesystem access; the caller checks existence.
    planemo reads the ``.lint_skip`` in the linted tool's own directory.
    """
    return tool_path.parent / _LINT_SKIP_FILENAME


# Check-tier rules whose clean state does NOT prove the planemo linter passes,
# because they only evaluate when an optional extra is installed (and yield nothing
# otherwise). GTR100/GTR101 bind Galaxy's own test-validation linters behind the
# galaxy-tool-lint ``[test-validation]`` extra (checks/test_validation.py), so "our
# rule is clean" can mean "the extra is absent", not "the tool is valid".
# They stay selectable and count toward planemo parity, but must not gate suppression
# removal. (Registry ``docs/decisions.md`` D24.)
_EXTRA_GATED_CHECK_CODES = frozenset({"GTR100", "GTR101"})


@cache
def _complete_coverage_codes() -> frozenset[str]:
    """GTR codes whose clean state faithfully implies the planemo linter passes.

    Derived (registry ``docs/decisions.md`` D24): every detect-only check-tier
    rule (faithful planemo ports) plus every canonical codemod (targeted fixes).
    Profile-upgrade and runtime-gated codemods are excluded — they may cover a
    planemo name only incidentally — as are the opt-in-extra-gated bindings
    (``_EXTRA_GATED_CHECK_CODES``), whose clean state is conditional on the extra.
    """
    canonical = {codemod.meta.code for codemod in canonical_codemods()}
    checks = {
        code
        for code, handle in all_handles().items()
        if handle.family == "check" and code not in _EXTRA_GATED_CHECK_CODES
    }
    return frozenset(canonical | checks)


def covering_codes(name: str, /) -> frozenset[str]:
    """The GTR codes that cover planemo linter *name* (case-insensitive)."""
    return planemo_index().get(name.lower(), frozenset())


def is_completely_covered(name: str, /) -> bool:
    """Whether *name* is covered, and every covering code is in the faithful set.

    The coverage half of the provable-removal gate: ``True`` means a clean
    detection across the covering codes proves the planemo linter would pass.
    """
    codes = covering_codes(name)
    return bool(codes) and codes <= _complete_coverage_codes()
