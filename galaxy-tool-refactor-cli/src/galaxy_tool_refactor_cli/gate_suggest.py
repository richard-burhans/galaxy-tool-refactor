"""Suggest-mode engine for the forward gate (the ``gate-suggest`` CLI command).

The block-mode gate (``check``) fails a PR whose changed tools are not canonical.
Suggest mode is the friendlier sibling (forward-gate Action ``mode: suggest``):
instead of failing, it posts the canonical fix as GitHub one-click "Commit
suggestion" review comments on the PR, with the IUC doc link, so the author accepts
the edits in place. The transform applies ``format`` over the **gate-eligible** rule
subset (``gate_codes()``) — the same set the forward gate's block mode enforces. (The
bulk normalizer applies a broader set, gate-eligible plus bulk-only; suggest mode
deliberately posts only the gate subset.)

GitHub only accepts a review comment on a line that is part of the PR's diff, so a
fix that lands outside the changed hunks cannot be inlined; those are summarized in
the review body with the local ``format`` command. This module holds the pure
suggestion-computation core plus the git/``gh`` I/O the command drives.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from galaxy_tool_fmt.cli_support import is_tool_root
from galaxy_tool_refactor_registry.facade import run as facade_run

logger = logging.getLogger("gate_suggest")

_IUC_DOC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"


@dataclass(frozen=True)
class Suggestion:
    """A GitHub one-click suggestion: replace lines [start..end] of *path*."""

    path: str
    start_line: int  # 1-based, inclusive
    end_line: int
    new_lines: list[str]  # the canonical replacement (empty = delete the lines)


def build_suggestions(
    path: str, original: str, canonical: str, /, *, eligible: set[int]
) -> tuple[list[Suggestion], int]:
    """Turn *original*→*canonical* into ``(suggestions, skipped)``.

    Each maximal replaced/deleted run of *original* lines becomes one suggestion, but
    only when **every** line of that run is in *eligible* (the RIGHT-side line numbers
    GitHub will accept a comment on, i.e. inside the PR's diff hunks). A run outside
    the diff, or a pure insertion (no original line to anchor to), is counted in
    *skipped*.
    """
    o = original.splitlines()
    c = canonical.splitlines()
    suggestions: list[Suggestion] = []
    skipped = 0
    matcher = difflib.SequenceMatcher(a=o, b=c, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i2 <= i1:
            skipped += 1  # pure insertion: no RIGHT-side line to anchor a suggestion to
            continue
        start, end = i1 + 1, i2  # 1-based inclusive original (RIGHT-side) line range
        if all(line in eligible for line in range(start, end + 1)):
            suggestions.append(Suggestion(path, start, end, c[j1:j2]))
        else:
            skipped += 1
    return suggestions, skipped


def _comment(suggestion: Suggestion, /) -> dict[str, object]:
    """Render a Suggestion as a GitHub review-comment payload (a suggestion block)."""
    body = "```suggestion\n" + "\n".join(suggestion.new_lines)
    body += "\n```" if suggestion.new_lines else "```"
    comment: dict[str, object] = {"path": suggestion.path, "line": suggestion.end_line,
                                  "side": "RIGHT", "body": body}
    if suggestion.end_line > suggestion.start_line:
        comment["start_line"] = suggestion.start_line
        comment["start_side"] = "RIGHT"
    return comment


def review_payload(
    suggestions: list[Suggestion], skipped: int, /, *, codes: frozenset[str]
) -> dict[str, object]:
    """Build the ``POST /pulls/{n}/reviews`` body from the suggestions."""
    select = ",".join(sorted(codes))
    lines = [
        "**Forward gate (suggest mode).** These are deterministic, "
        "behaviour-preserving fixes toward the IUC canonical form. Click "
        "**Commit suggestion** to apply each, or run locally:",
        "",
        f"    galaxy-tool-refactor format --select {select} <file>",
        "",
        f"Reference: {_IUC_DOC}",
    ]
    if skipped:
        lines += [
            "",
            f"_{skipped} change(s) fall outside this PR's diff and cannot be inlined "
            "as suggestions; the `format` command above applies them too._",
        ]
    return {"event": "COMMENT", "body": "\n".join(lines),
            "comments": [_comment(s) for s in suggestions]}


def _commentable_lines(root: Path, base: str, relpath: str, /) -> set[int]:
    """RIGHT-side line numbers of *relpath* inside the PR diff (commentable lines)."""
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--unified=0",
         f"{base}...HEAD", "--", relpath],
        capture_output=True, text=True, check=False,
    )
    eligible: set[int] = set()
    for line in result.stdout.splitlines():
        if line.startswith("@@"):
            plus = line.split("+", 1)[1].split(" ", 1)[0]
            start_str, _, count_str = plus.partition(",")
            start = int(start_str)
            count = int(count_str) if count_str else 1
            eligible.update(range(start, start + max(count, 1)))
    return eligible


def _changed_tool_xmls(root: Path, base: str, /) -> list[str]:
    """Added/modified tool XML paths in the PR (relative posix paths under tools/)."""
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=AM",
         f"{base}...HEAD", "--", "tools/"],
        capture_output=True, text=True, check=False,
    )
    return [p for p in result.stdout.splitlines() if PurePosixPath(p).suffix == ".xml"]


@dataclass
class SuggestResult:
    """Accumulated suggestions across the PR's changed tools."""

    suggestions: list[Suggestion] = field(default_factory=list)
    skipped: int = 0
    checked: int = 0


def collect_suggestions(
    root: Path, base: str, /, *, codes: frozenset[str]
) -> SuggestResult:
    """Compute suggestions for every non-canonical changed tool in the PR."""
    result = SuggestResult()
    for relpath in _changed_tool_xmls(root, base):
        path = root / relpath
        if not path.is_file():
            continue
        try:
            original = path.read_bytes()
            if not is_tool_root(original):
                continue  # a macros.xml / non-tool XML is not gated
            canonical = facade_run(path, codes=codes).formatted
        except Exception as error:  # noqa: BLE001 — a bad tool is skipped, not fatal
            logger.warning("skipping %s: %s", relpath, error)
            continue
        result.checked += 1
        if canonical == original:
            continue
        eligible = _commentable_lines(root, base, relpath)
        found, skipped = build_suggestions(
            relpath,
            original.decode("utf-8"),
            canonical.decode("utf-8"),
            eligible=eligible,
        )
        result.suggestions.extend(found)
        result.skipped += skipped
    return result


def dump_payload(payload: dict[str, object], /) -> str:
    """Render a review payload as pretty JSON (for ``--dry-run``)."""
    return json.dumps(payload, indent=2)


def post_review(repo: str, pr: int, payload: dict[str, object], /) -> bool:
    """POST the review via ``gh api``; return True on success."""
    token = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", "x"))
    proc = subprocess.run(
        ["gh", "api", "-X", "POST",
         f"repos/{repo}/pulls/{pr}/reviews", "--input", "-"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GH_TOKEN": token},
    )
    if proc.returncode != 0:
        logger.error("posting review failed: %s", proc.stderr.strip() or "<no stderr>")
        return False
    return True
