"""Architecture guard: every ``decisions.md §N`` / ``DN`` citation resolves.

The docs cite decision sections constantly (``galaxy-tool-source/docs/decisions.md``
§9, fmt ``§D12``, check ``D34``, ranges like ``D1–D4``). Both audit skills used to
verify these by hand-grepping headers — which is exactly as reliable as the
greper's memory of each package's header format (a manual pass produced a false
MISSING for codemod §39–43 because its headers are ``## 39.``, not ``## §39``).
This guard mechanizes the check: it scans every tracked markdown file for
citations *anchored to a resolvable* ``decisions.md`` *path* and asserts each
cited section exists as a header in that file.

**Precision-first scope** (soundness over completeness — an unchecked citation
is fine, a false failure is not):

- Only token chains **immediately following** the path are attributed to it
  (``…decisions.md`` §D8/§D10, ``D1–D4``). Prose that wanders on to cite *other*
  packages' sections (``… §D1 (+ codemod §15, fmt §D11)``) is not chained — the
  shorthand has no adjacent path to anchor it, so it is out of scope rather
  than mis-attributed.
- A path that does not resolve (generic mentions like "each package's
  ``docs/decisions.md``") is skipped, not failed.
- Range citations check their endpoints (each endpoint is a token).

Corpus-free and deterministic (pure file reads) → runs in CI / ``qa_gate.sh``.
Sibling of ``test_stat_artifact_coverage.py`` / ``test_research_note_citations.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# The workspace root is two levels up from this test file
# (<root>/galaxy-tool-refactor-registry/tests/<this file>).
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# Directories never scanned: machine-local scratch, envs, generated corpus data.
_SKIP_PARTS = {".local", ".venv", ".git", ".sbx", "corpus_data", "node_modules"}

# A decisions.md path token: optional repo-relative prefix, e.g.
# `galaxy-tool-xml-fmt/docs/decisions.md`, `docs/decisions.md`, `decisions.md`.
_PATH = re.compile(r"[\w./-]*decisions\.md")

# One cited section token: `§9`, `§D12`, `D34`, `§20.1`. A bare number without
# the `§`/`D` sigil is never a citation (it would match dates and counts).
_TOKEN = r"(?:§\s*D?|D)\d+(?:\.\d+)?"

# The chain anchored right after the path: closing backtick/paren/quote noise,
# then the first token, then further tokens joined only by `/ , + – — -` or
# "and" — never intervening words (those start a *different* file's shorthand).
_CHAIN = re.compile(
    rf"[`\"')\]]*\s*(?P<chain>{_TOKEN}(?:(?:\s*[/,+–—-]\s*|\s+and\s+){_TOKEN})*)"
)

_TOKEN_RE = re.compile(_TOKEN)

# A decision header: `## 39.` / `### 2.1 …` (numeric style) or `## D34 …`
# (D-style). The § sigil never appears in headers.
_HEADER = re.compile(
    r"^#{2,4}\s*(?P<code>D?\d+(?:\.\d+)?)(?:[.):\s—-]|$)", re.MULTILINE
)

# A numbered register row: galaxy-tool-source's assumptions table numbers its rows
# (`| 1.5 | A missing profile …`) and prose cites them as `§1.5` — those rows
# are citable codes exactly like headers.
_TABLE_ROW = re.compile(r"^\|\s*(?P<code>D?\d+(?:\.\d+)?)\s*\|", re.MULTILINE)

# Cross-package shorthand: a qualifier word immediately before a *relative*
# path names the real target — "codemod `docs/decisions.md` §30" cites the
# codemod tier's decisions from another package's docs.
_PACKAGE_BY_QUALIFIER = {
    "codemod": "galaxy-tool-xml-codemod",
    "fmt": "galaxy-tool-xml-fmt",
    "check": "galaxy-tool-xml-check",
    "registry": "galaxy-tool-refactor-registry",
    "cli": "galaxy-tool-refactor-cli",
    "mcp": "galaxy-tool-refactor-mcp",
    "rules": "galaxy-tool-refactor-rules",
    # Tier 1 renamed galaxy-tool-xml -> galaxy-tool-source (its decisions §26):
    # dated records still say "xml §N", new prose may say "source §N" — both
    # resolve to the renamed package.
    "xml": "galaxy-tool-source",
    "source": "galaxy-tool-source",
}
# The qualifier must sit directly before the path with no intervening bracket:
# in "the GTR020.1 codemod (`docs/decisions.md` D8)" the parenthetical cites the
# *citing* package's own decisions and "codemod" merely describes the rule.
_QUALIFIER = re.compile(r"(?P<word>\w[\w-]*)(?:['’]s)?[^()\[\]\w]*$")


def _normalize(token: str, /) -> str:
    """``§D12`` → ``D12``, ``§ 9`` → ``9``, ``D34`` → ``D34``."""
    return token.replace("§", "").replace(" ", "")


def header_codes(decisions_text: str, /) -> frozenset[str]:
    """The section codes a decisions file defines (headers + numbered rows)."""
    headers = frozenset(match["code"] for match in _HEADER.finditer(decisions_text))
    rows = frozenset(match["code"] for match in _TABLE_ROW.finditer(decisions_text))
    return headers | rows


@dataclass(frozen=True)
class Citation:
    """One section citation anchored to a resolved decisions file."""

    source: Path  # the citing markdown file
    target: Path  # the resolved decisions.md
    code: str  # normalized section code, e.g. "39" or "D34"


def _resolve(
    path_token: str, *, citing_file: Path, preceding_text: str
) -> Path | None:
    """The decisions file a citation's path token refers to, or ``None``.

    A *relative* token (no package prefix) preceded by a package-qualifier word
    resolves to that package ("codemod ``docs/decisions.md`` §30"). Otherwise:
    the citing file's directory first (relative citation), then the workspace
    root (repo-rooted citation). Unresolvable tokens — generic mentions of
    "docs/decisions.md" with no file behind them — return ``None``.
    """
    if not path_token.startswith("galaxy-tool-"):
        qualifier = _QUALIFIER.search(preceding_text[-40:])
        package = (
            _PACKAGE_BY_QUALIFIER.get(qualifier["word"].lower())
            if qualifier is not None
            else None
        )
        if package is not None:
            candidate = _WORKSPACE_ROOT / package / "docs" / "decisions.md"
            if candidate.is_file():
                return candidate
    for base in (citing_file.parent, _WORKSPACE_ROOT):
        candidate = (base / path_token).resolve()
        if candidate.is_file() and _WORKSPACE_ROOT in candidate.parents:
            return candidate
    return None


def extract_citations(text: str, *, citing_file: Path) -> list[Citation]:
    """Every anchored, resolvable section citation in *text*."""
    citations: list[Citation] = []
    for path_match in _PATH.finditer(text):
        target = _resolve(
            path_match.group(),
            citing_file=citing_file,
            preceding_text=text[: path_match.start()],
        )
        if target is None:
            continue
        chain = _CHAIN.match(text, path_match.end())
        if chain is None:
            continue
        citations.extend(
            Citation(source=citing_file, target=target, code=_normalize(token))
            for token in _TOKEN_RE.findall(chain["chain"])
        )
    return citations


def _scanned_markdown_files() -> list[Path]:
    return [
        path
        for path in sorted(_WORKSPACE_ROOT.rglob("*.md"))
        if not (_SKIP_PARTS & set(path.relative_to(_WORKSPACE_ROOT).parts))
    ]


def test_every_anchored_decision_citation_resolves() -> None:
    """Each ``decisions.md §N``/``DN`` citation names a real section header."""
    codes_by_file: dict[Path, frozenset[str]] = {}
    broken: list[str] = []
    for markdown in _scanned_markdown_files():
        text = markdown.read_text(encoding="utf-8")
        for citation in extract_citations(text, citing_file=markdown):
            if citation.target not in codes_by_file:
                codes_by_file[citation.target] = header_codes(
                    citation.target.read_text(encoding="utf-8")
                )
            if citation.code not in codes_by_file[citation.target]:
                broken.append(
                    f"{markdown.relative_to(_WORKSPACE_ROOT)} cites "
                    f"{citation.target.relative_to(_WORKSPACE_ROOT)} "
                    f"§{citation.code} — no such section header"
                )
    assert not broken, "phantom decision citations:\n" + "\n".join(broken)


def test_scan_actually_covers_the_repo() -> None:
    """Tripwire: the scanner sees the cross-tier citations we know exist.

    If a refactor moved the docs or broke the resolver, the citation count
    would silently collapse and the guard above would pass vacuously.
    """
    total = sum(
        len(
            extract_citations(
                markdown.read_text(encoding="utf-8"), citing_file=markdown
            )
        )
        for markdown in _scanned_markdown_files()
    )
    assert total >= 50, f"only {total} anchored citations found — scanner broken?"


def test_scanner_catches_a_phantom_citation(tmp_path: Path) -> None:
    """Unit fixture: a citation to a nonexistent section is extracted and fails."""
    decisions = tmp_path / "docs" / "decisions.md"
    decisions.parent.mkdir()
    decisions.write_text(
        "## D1 (2026-01-01) — real\n## 7. also real\n", encoding="utf-8"
    )
    citing = tmp_path / "README.md"
    text = "See `docs/decisions.md` D1/§7 and also `docs/decisions.md` §D9."
    citations = extract_citations(text, citing_file=citing)
    # Resolution is workspace-bound, so resolve against the real tree instead:
    codes = header_codes(decisions.read_text(encoding="utf-8"))
    extracted = [citation.code for citation in citations]
    assert extracted == []  # tmp_path is outside the workspace → skipped, not failed
    assert "D1" in codes and "7" in codes and "D9" not in codes
    chain = _CHAIN.match(text, text.index("decisions.md` D1") + len("decisions.md"))
    assert chain is not None and _TOKEN_RE.findall(chain["chain"]) == ["D1", "§7"]
