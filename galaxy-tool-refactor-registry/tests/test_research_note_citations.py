"""Architecture guard: every corpus count cited in ``docs/upgrade_research/*.md``
still matches its source artifact — so a regenerated stat page can't silently leave
a hand-written research note quoting a stale number.

The per-code upgrade-research notes quote "first-blocker" / "stuck" counts that come
from ``docs/upgrade_behavior_block_stats.md`` (and a few interpreter-bucket counts
from ``docs/interpreter_bucket_stats.md``). Those artifacts are regenerated from
corpus sweeps; the notes are hand-written prose. When an artifact was re-walked
(after GTX016 shipped + the ``20_09_consider_set_e`` detector was tightened) the
first-blocker counts shifted and **five notes silently kept the old numbers** —
exactly the drift the ``docs/*_stats.md`` coverage guard
(``test_stat_artifact_coverage``) does *not* catch, because it guards generated
pages, not free prose.

This is the companion guard for the prose side. A manifest maps each note to a
``(source page, lookup key)``; the expected count is read **live** from the parsed
artifact, so it can't drift from the source — when the artifact changes, the live
count is recomputed and the note that still quotes the old one fails, naming the
note, the current number, and the regen command.

**Corpus-free and deterministic** (pure file reads, no package imports) → it runs in
CI / ``qa_gate.sh`` and trips at the PR that regenerates an artifact without
refreshing the note. It guards only artifact-sourced numbers: derived figures (the
without-codemod ``1,726`` baseline) and sweep-only figures (the ``1,127`` rewritten
count, which lives in no committed artifact) are intentionally out of scope — see the
manifest comments. Sibling of ``test_stat_artifact_coverage.py``; same arch-test shape.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# The workspace root is two levels up from this test file
# (<root>/galaxy-tool-refactor-registry/tests/<this file>).
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

_BEHAVIOR_BLOCK_PAGE = "docs/upgrade_behavior_block_stats.md"
_INTERPRETER_PAGE = "docs/interpreter_bucket_stats.md"
_RESEARCH_DIR = "docs/upgrade_research"

_MUST_FIX = "must_fix"
_MUST_FIX_CONSIDER = "must_fix+consider"

# A first-blocker table row:  | <profile> | <level> | `<code>` | <count> |
_BLOCK_ROW = re.compile(
    r"\|[^|]*\|[^|]*\|\s*`(?P<code>[^`]+)`\s*\|\s*(?P<count>[\d,]+)\s*\|"
)
# An interpreter bucket row keyed by its label cell (A / A-missing).
_BUCKET_ROW = re.compile(
    r"\|\s*(?P<label>\*\*A — auto-fixable\*\*|A-missing)\s*\|\s*(?P<count>[\d,]+)\s*\|"
)


def _to_int(grouped: str, /) -> int:
    """A thousands-separated table cell (``4,956``) as an ``int``."""
    return int(grouped.replace(",", ""))


def parse_behavior_blocks(page_text: str, /) -> dict[tuple[str, str], int]:
    """Map ``(policy, code) -> first-blocker count`` from the behaviour-block page.

    ``policy`` is ``must_fix`` for the "Blocking on ``must_fix`` only" section and
    ``must_fix+consider`` for the "Blocking on ``must_fix`` + ``consider``" section;
    a code can appear in both with different counts (e.g.
    ``24_2_fix_test_case_validation``).
    """
    only_at = page_text.find("## Blocking on `must_fix` only")
    both_at = page_text.find("## Blocking on `must_fix` + `consider`")
    if only_at == -1 or both_at == -1 or both_at < only_at:
        return {}
    sections = (
        (_MUST_FIX, page_text[only_at:both_at]),
        (_MUST_FIX_CONSIDER, page_text[both_at:]),
    )
    counts: dict[tuple[str, str], int] = {}
    for policy, body in sections:
        for match in _BLOCK_ROW.finditer(body):
            counts[(policy, match["code"])] = _to_int(match["count"])
    return counts


def parse_interpreter_buckets(page_text: str, /) -> dict[str, int]:
    """Map bucket label -> count for the interpreter page, plus a synthetic
    ``A+A-missing`` total (the codemod's actual target population)."""
    buckets = {
        ("A" if match["label"].startswith("**A —") else "A-missing"): _to_int(
            match["count"]
        )
        for match in _BUCKET_ROW.finditer(page_text)
    }
    if "A" in buckets and "A-missing" in buckets:
        buckets["A+A-missing"] = buckets["A"] + buckets["A-missing"]
    return buckets


@dataclass(frozen=True)
class NoteCitation:
    """A count a research note quotes, plus how to read its *current* value live
    from the source artifact — so the expectation tracks the artifact, not a literal."""

    note: str  # filename under docs/upgrade_research/
    label: str  # human description of what the number is
    regen: str  # the measure that regenerates the source artifact
    expected: Callable[[dict[tuple[str, str], int], dict[str, int]], int]


_REGEN_BLOCKS = "uv run python -m scripts.measure upgrade-behavior-blocks"
_REGEN_BUCKETS = "uv run python -m scripts.measure interpreter-bucket-split"

# Each note's artifact-sourced numbers. Derived figures are deliberately absent:
# the interpreter note's 1,726 (= 316 + 1,410, the without-codemod baseline) and
# 1,127 (the corpus-sweep "rewritten" count, in no committed artifact) are not guarded.
NOTE_CITATIONS: tuple[NoteCitation, ...] = (
    NoteCitation(
        "16_04_fix_output_format.md",
        "first-blocker count (must_fix only)",
        _REGEN_BLOCKS,
        lambda blocks, _buckets: blocks[(_MUST_FIX, "16_04_fix_output_format")],
    ),
    NoteCitation(
        "16_04_consider_implicit_extra_file_collection.md",
        "tools-stalling count (must_fix + consider)",
        _REGEN_BLOCKS,
        lambda blocks, _b: blocks[
            (_MUST_FIX_CONSIDER, "16_04_consider_implicit_extra_file_collection")
        ],
    ),
    NoteCitation(
        "23_0_consider_optional_text.md",
        "first-blocker count (must_fix + consider)",
        _REGEN_BLOCKS,
        lambda blocks, _b: blocks[(_MUST_FIX_CONSIDER, "23_0_consider_optional_text")],
    ),
    NoteCitation(
        "24_2_fix_test_case_validation.md",
        "stuck count (must_fix only, the largest blocker)",
        _REGEN_BLOCKS,
        lambda blocks, _b: blocks[(_MUST_FIX, "24_2_fix_test_case_validation")],
    ),
    NoteCitation(
        "16_04_fix_interpreter.md",
        "current stuck count (must_fix only)",
        _REGEN_BLOCKS,
        lambda blocks, _b: blocks[(_MUST_FIX, "16_04_fix_interpreter")],
    ),
    NoteCitation(
        "16_04_fix_interpreter.md",
        "bucket-A eligible count",
        _REGEN_BUCKETS,
        lambda _blocks, buckets: buckets["A"],
    ),
    NoteCitation(
        "16_04_fix_interpreter.md",
        "A + A-missing target population",
        _REGEN_BUCKETS,
        lambda _blocks, buckets: buckets["A+A-missing"],
    ),
)


def cited_number_present(note_text: str, count: int, /) -> bool:
    """Whether *count* (thousands-formatted) appears as a standalone token in
    *note_text* — the form the notes quote (``4,956``, ``1,410``, ``316``)."""
    return re.search(rf"(?<!\d){re.escape(f'{count:,}')}(?!\d)", note_text) is not None


# --- planted-failure unit tests (the guard's own self-checks) ----------------------

_SYNTHETIC_BLOCK_PAGE = """\
## Blocking on `must_fix` only

Reaches latest behavior-preservingly: **2,567**; stuck: **5,305**.

| Profile | Level | Behavior code (first blocker) | Tools stuck |
|---|---|---|--:|
| 16.04 | must_fix | `16_04_fix_interpreter` | 316 |
| 24.2 | must_fix | `24_2_fix_test_case_validation` | 4,956 |

## Blocking on `must_fix` + `consider`

| Profile | Level | Behavior code (first blocker) | Tools stuck |
|---|---|---|--:|
| 23.0 | consider | `23_0_consider_optional_text` | 318 |
| 24.2 | must_fix | `24_2_fix_test_case_validation` | 862 |
"""

_SYNTHETIC_BUCKET_PAGE = """\
| Bucket | Tools | Share | Meaning |
|---|--:|--:|---|
| **A — auto-fixable** | 1,383 | 80.0% | ... |
| A-missing | 27 | 1.6% | ... |
"""


def test_parse_behavior_blocks_splits_by_policy() -> None:
    """Both sections parse, and a code in both keeps a per-policy count."""
    blocks = parse_behavior_blocks(_SYNTHETIC_BLOCK_PAGE)
    assert blocks[(_MUST_FIX, "16_04_fix_interpreter")] == 316
    assert blocks[(_MUST_FIX, "24_2_fix_test_case_validation")] == 4956
    assert blocks[(_MUST_FIX_CONSIDER, "24_2_fix_test_case_validation")] == 862
    assert blocks[(_MUST_FIX_CONSIDER, "23_0_consider_optional_text")] == 318


def test_parse_interpreter_buckets_totals() -> None:
    """A, A-missing, and the synthetic A+A-missing total all parse."""
    buckets = parse_interpreter_buckets(_SYNTHETIC_BUCKET_PAGE)
    assert buckets == {"A": 1383, "A-missing": 27, "A+A-missing": 1410}


def test_cited_number_present_is_token_exact() -> None:
    """Presence is standalone-token, so ``316`` doesn't match ``3,164`` and a
    thousands number matches its comma form."""
    assert cited_number_present("down to 316 now", 316)
    assert not cited_number_present("line 3164 of x", 316)
    assert cited_number_present("sizes 1,410 tools", 1410)
    assert not cited_number_present("the 18 in the header", 33)


# --- the real guard ----------------------------------------------------------------

def test_manifest_notes_exist() -> None:
    """Every cited note is a real file (a renamed/removed note is a bug)."""
    for citation in NOTE_CITATIONS:
        path = _WORKSPACE_ROOT / _RESEARCH_DIR / citation.note
        assert path.is_file(), citation.note


def test_every_cited_count_is_current() -> None:
    """Each artifact-sourced number a research note quotes still matches the live
    value parsed from its source page.

    A failure means a stat artifact was regenerated (a count changed) without the
    note being refreshed — update the note to the named current value, regenerating
    the source artifact first with the named command if it is itself stale.
    """
    blocks = parse_behavior_blocks(
        (_WORKSPACE_ROOT / _BEHAVIOR_BLOCK_PAGE).read_text(encoding="utf-8")
    )
    buckets = parse_interpreter_buckets(
        (_WORKSPACE_ROOT / _INTERPRETER_PAGE).read_text(encoding="utf-8")
    )
    assert blocks, f"could not parse {_BEHAVIOR_BLOCK_PAGE}"
    assert buckets, f"could not parse {_INTERPRETER_PAGE}"

    failures: list[str] = []
    for citation in NOTE_CITATIONS:
        path = _WORKSPACE_ROOT / _RESEARCH_DIR / citation.note
        text = path.read_text(encoding="utf-8")
        count = citation.expected(blocks, buckets)
        if not cited_number_present(text, count):
            failures.append(
                f"{_RESEARCH_DIR}/{citation.note}: {citation.label} should be "
                f"{count:,} (from the current artifact) but that number is absent — "
                f"refresh the note (regen the source first if stale:  {citation.regen})"
            )
    assert not failures, "Stale research-note citation(s):\n  " + "\n  ".join(failures)
