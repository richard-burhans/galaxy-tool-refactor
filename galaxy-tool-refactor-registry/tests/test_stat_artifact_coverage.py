"""Architecture guard: every derived ``docs/*_stats.md`` page lists every rule it
should, with that rule's *current* summary — so adding or rewording a rule can't
silently leave a stat page stale.

The repo regenerates several stat artifacts from corpus sweeps, each owned by a
*different* ``scripts/corpus_check.py`` subcommand. Nothing forced the regen, so
pages drifted: **GTX014–GTX017 silently lagged out of the rule + format pages for
four PRs** (both stuck at the GTX013 sweep) because the maintainer had to remember
to re-run two separate slow sweeps.

This is the dependency-tracking the plan calls for. A manifest maps each page to its
regenerating command and the rule set it must reflect (derived live from the same
registries the generators iterate, so the expectation can't drift from the
generator). Two checks, both **corpus-free and deterministic** — they run in CI /
``qa_gate.sh`` and trip at the PR that adds/edits the rule, not four PRs later:

- **Phase 1 — coverage:** every covered rule *code* appears in the page.
- **Phase 2 — summary currency:** every covered rule's *current* summary appears
  in the page (so a reworded summary forces a regen, not just a new code). The page
  renders summaries through one backtick transform (``<token>`` → `` `<token>` ``),
  applied here too so the comparison matches the rendered cell.

It checks coverage + summary text, not the corpus-measured *numbers* (those need
the corpus and can't be verified in CI). Companion to ``test_serializer_allowlist.py``
— same arch-test shape. Rationale + the deferred Phase-3 (corpus/measure-source
fingerprint) follow-on: ``docs/decisions.md`` D6.
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

# Mirrors galaxy_tool_refactor_rules.reference._backtick_xml_tokens — the canonical
# transform every stat-page generator applies to a rule summary before placing it in
# a markdown cell (``<token>`` -> `` `<token>` ``). Kept local so this guard stays a
# pure addition to the test tier (no sweep / library change); the regex is stable.
_ANGLE_TOKEN = re.compile(r"(<[^>]+>)")


def _rendered_summary(summary: str) -> str:
    """A rule summary as it appears in a stat-page markdown cell."""
    return _ANGLE_TOKEN.sub(r"`\1`", summary)


# Each helper returns the (code, summary) of the rules in one family, as the page's
# generator would enumerate them — so the expectation tracks the registries live.
def _fmt_rules() -> frozenset[tuple[str, str]]:
    return frozenset((r.meta.code, r.meta.summary) for r in all_rules())


def _coded_codemod_rules() -> frozenset[tuple[str, str]]:
    return frozenset((c.meta.code, c.meta.summary) for c in coded_codemods())


def _canonical_codemod_rules() -> frozenset[tuple[str, str]]:
    return frozenset((c.meta.code, c.meta.summary) for c in CANONICAL_CODEMODS)


def _advisory_check_rules() -> frozenset[tuple[str, str]]:
    return frozenset((c.meta.code, c.meta.summary) for c in all_checks())


@dataclass(frozen=True)
class StatArtifact:
    """A derived stat page: its path, the command that regenerates it, and the
    (code, summary) of every rule it must list — derived live from the rule
    registries the page's generator iterates, so this expectation can't drift."""

    path: str
    regen: str
    covered_rules: Callable[[], frozenset[tuple[str, str]]]


# The single registration point — page -> regen command -> covered rule set.
# Mirrors what each generator in scripts/corpus_check.py iterates:
#   check  -> all_rules() + CANONICAL_CODEMODS + all_checks()  (_check_rule_registry)
#   rules  -> all_rules() + coded_codemods()                   (per-rule isolation)
#   fmt    -> all_rules() + coded_codemods()                   (the GTX glossary)
STAT_ARTIFACTS: tuple[StatArtifact, ...] = (
    StatArtifact(
        path="docs/corpus_check_stats.md",
        regen="uv run python -m scripts.corpus_check check",
        covered_rules=lambda: (
            _fmt_rules() | _canonical_codemod_rules() | _advisory_check_rules()
        ),
    ),
    StatArtifact(
        path="docs/corpus_rule_stats.md",
        regen="uv run python -m scripts.corpus_check rules",
        covered_rules=lambda: _fmt_rules() | _coded_codemod_rules(),
    ),
    StatArtifact(
        path="docs/corpus_format_stats.md",
        regen="uv run python -m scripts.corpus_check fmt",
        covered_rules=lambda: _fmt_rules() | _coded_codemod_rules(),
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


def stale_summaries(
    page_text: str, /, *, expected: frozenset[tuple[str, str]]
) -> set[str]:
    """Return the codes whose *current* (rendered) summary is absent from
    *page_text* — the rules whose page row carries an out-of-date description."""
    return {
        code
        for code, summary in expected
        if _rendered_summary(summary) not in page_text
    }


def test_missing_codes_flags_a_planted_gap() -> None:
    """The code checker: a missing code is flagged, a present one isn't, and a
    longer code (GTX0011) does not satisfy a shorter one (GTX001)."""
    pair = frozenset({"GTX001", "GTX999"})
    assert missing_codes("only GTX001 here", expected=pair) == {"GTX999"}
    assert missing_codes("GTX001 and GTX999", expected=pair) == set()
    assert missing_codes("see GTX0011", expected=frozenset({"GTX001"})) == {"GTX001"}


def test_stale_summaries_flags_reworded_and_applies_backticks() -> None:
    """The summary checker: a summary whose text isn't in the page is flagged; an
    XML token must match its backticked rendered form, not the raw ``<tag>``."""
    page = "| GTX001 | fmt | Wrap a `<command>` body. |"
    # Current summary present (after backticking the token) -> not stale.
    assert stale_summaries(
        page, expected=frozenset({("GTX001", "Wrap a <command> body.")})
    ) == set()
    # A reworded summary is no longer in the page -> flagged.
    assert stale_summaries(
        page, expected=frozenset({("GTX001", "Reworded text.")})
    ) == {"GTX001"}
    # The raw (un-backticked) form would not match the rendered cell.
    assert _rendered_summary("Wrap a <command> body.") == "Wrap a `<command>` body."


def test_manifest_paths_exist() -> None:
    """Every registered stat page is a real file (a renamed/removed page is a bug)."""
    for artifact in STAT_ARTIFACTS:
        assert (_WORKSPACE_ROOT / artifact.path).is_file(), artifact.path


def test_every_covered_code_has_a_row() -> None:
    """Phase 1 — each stat page lists every rule code it should.

    A failure means a rule was added (or a page regenerated stale) without the
    page being refreshed — regenerate it with the named command.
    """
    failures: list[str] = []
    for artifact in STAT_ARTIFACTS:
        text = (_WORKSPACE_ROOT / artifact.path).read_text(encoding="utf-8")
        codes = frozenset(code for code, _summary in artifact.covered_rules())
        missing = missing_codes(text, expected=codes)
        if missing:
            failures.append(
                f"{artifact.path} is missing {sorted(missing)} — "
                f"recompute the whole page:  {artifact.regen}"
            )
    assert not failures, "Stale derived stat page(s):\n  " + "\n  ".join(failures)


def test_every_covered_summary_is_current() -> None:
    """Phase 2 — each stat page carries every covered rule's *current* summary.

    A failure means a rule's summary was reworded without regenerating the page,
    so the page's glossary now describes the rule with stale text.
    """
    failures: list[str] = []
    for artifact in STAT_ARTIFACTS:
        text = (_WORKSPACE_ROOT / artifact.path).read_text(encoding="utf-8")
        stale = stale_summaries(text, expected=artifact.covered_rules())
        if stale:
            failures.append(
                f"{artifact.path} has stale summaries for {sorted(stale)} — "
                f"recompute the whole page:  {artifact.regen}"
            )
    assert not failures, "Stale rule summaries in stat page(s):\n  " + "\n  ".join(
        failures
    )
