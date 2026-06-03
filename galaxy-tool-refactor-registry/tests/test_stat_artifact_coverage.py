"""Architecture guard: every derived ``docs/*_stats.md`` page lists every rule it
should, so adding a rule can't silently leave a stat page stale.

The repo regenerates several stat artifacts from corpus sweeps, each owned by a
*different* ``scripts/corpus_check.py`` subcommand. Nothing forced the regen, so
pages drifted: **GTX014–GTX017 silently lagged out of the rule + format pages for
four PRs** (both stuck at the GTX013 sweep) because the maintainer had to remember
to re-run two separate slow sweeps.

This guard is the dependency-tracking the plan calls for, Phase 1: a manifest maps
each page to the regenerating command and the code-set it must cover (derived live
from the same rule registries the generators iterate, so the expectation can't
drift from the generator). The test reads each committed page and fails — naming
the page and the exact regen command — if any covered code is missing. It is
**corpus-free and deterministic**, so it runs in CI / ``qa_gate.sh`` and trips at
the PR that adds the rule, not four PRs later.

It checks **coverage** (no rule silently absent), not the corpus-measured numbers
(those need the corpus and can't be verified in CI). Companion to
``test_serializer_allowlist.py`` — same arch-test shape. Rationale + the Phase-2
watched-input fingerprint follow-on: ``docs/decisions.md`` D6.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from galaxy_tool_xml_check.detect import all_checks
from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS
from galaxy_tool_xml_codemod.catalog import coded_codemods
from galaxy_tool_xml_fmt.format import all_rules

# The workspace root is two levels up from this test file
# (<root>/galaxy-tool-refactor-registry/tests/<this file>).
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _fmt_codes() -> frozenset[str]:
    return frozenset(rule_cls.meta.code for rule_cls in all_rules())


def _coded_codemod_codes() -> frozenset[str]:
    return frozenset(codemod_cls.meta.code for codemod_cls in coded_codemods())


def _canonical_codemod_codes() -> frozenset[str]:
    return frozenset(codemod_cls.meta.code for codemod_cls in CANONICAL_CODEMODS)


def _advisory_check_codes() -> frozenset[str]:
    return frozenset(check_cls.meta.code for check_cls in all_checks())


@dataclass(frozen=True)
class StatArtifact:
    """A derived stat page: its path, the command that regenerates it, and the
    set of rule codes it must list (derived live from the rule registries the
    page's generator iterates — so this expectation can't drift from it)."""

    path: str
    regen: str
    covered_codes: Callable[[], frozenset[str]]


# The single registration point — page -> regen command -> covered code-set.
# Mirrors what each generator in scripts/corpus_check.py iterates:
#   check  -> all_rules() + CANONICAL_CODEMODS + all_checks()  (_check_rule_registry)
#   rules  -> all_rules() + coded_codemods()                   (per-rule isolation)
#   fmt    -> all_rules() + coded_codemods()                   (the GTX glossary)
STAT_ARTIFACTS: tuple[StatArtifact, ...] = (
    StatArtifact(
        path="docs/corpus_check_stats.md",
        regen="uv run python -m scripts.corpus_check check",
        covered_codes=lambda: (
            _fmt_codes() | _canonical_codemod_codes() | _advisory_check_codes()
        ),
    ),
    StatArtifact(
        path="docs/corpus_rule_stats.md",
        regen="uv run python -m scripts.corpus_check rules",
        covered_codes=lambda: _fmt_codes() | _coded_codemod_codes(),
    ),
    StatArtifact(
        path="docs/corpus_format_stats.md",
        regen="uv run python -m scripts.corpus_check fmt",
        covered_codes=lambda: _fmt_codes() | _coded_codemod_codes(),
    ),
)


def missing_codes(page_text: str, /, *, expected: frozenset[str]) -> set[str]:
    """Return the *expected* rule codes that do not appear (word-boundary) in
    *page_text* — the codes whose row the page is missing."""
    return {
        code
        for code in expected
        if not re.search(rf"\b{re.escape(code)}\b", page_text)
    }


def test_missing_codes_flags_a_planted_gap() -> None:
    """The checker itself: a page missing a code is flagged; a present one isn't,
    and a longer code (GTX0011) does not satisfy a shorter one (GTX001)."""
    pair = frozenset({"GTX001", "GTX999"})
    assert missing_codes("only GTX001 here", expected=pair) == {"GTX999"}
    assert missing_codes("GTX001 and GTX999", expected=pair) == set()
    assert missing_codes("see GTX0011", expected=frozenset({"GTX001"})) == {"GTX001"}


def test_manifest_paths_exist() -> None:
    """Every registered stat page is a real file (a renamed/removed page is a bug)."""
    for artifact in STAT_ARTIFACTS:
        assert (_WORKSPACE_ROOT / artifact.path).is_file(), artifact.path


def test_every_covered_code_has_a_row() -> None:
    """The guard: each stat page lists every rule code it should.

    A failure means a rule was added (or a page regenerated stale) without the
    page being refreshed — regenerate it with the named command.
    """
    failures: list[str] = []
    for artifact in STAT_ARTIFACTS:
        text = (_WORKSPACE_ROOT / artifact.path).read_text(encoding="utf-8")
        missing = missing_codes(text, expected=artifact.covered_codes())
        if missing:
            failures.append(
                f"{artifact.path} is missing {sorted(missing)} — "
                f"recompute the whole page:  {artifact.regen}"
            )
    assert not failures, "Stale derived stat page(s):\n  " + "\n  ".join(failures)
