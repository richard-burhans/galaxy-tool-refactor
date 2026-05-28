"""Unit tests for the corpus runner's internal helpers.

``scripts/corpus_check.py`` is maintainer tooling, but the
``PROVENANCE.md`` round-trip — write entries with
``_append_provenance`` and re-discover them with
``_fmt_known_fixture_paths`` — is load-bearing for "don't re-retain
already-known fixtures". Locking it in here catches regressions
without needing a slow corpus sweep.
"""

from __future__ import annotations

from pathlib import Path

import scripts.corpus_check as corpus_check


def test_provenance_round_trip(tmp_path: Path) -> None:
    """Writing entries and re-parsing them must yield the same paths."""
    fake_regressions = tmp_path / "regressions"
    fake_regressions.mkdir()
    entries = [
        ("fixture-a", "repo-x", Path("tools/a/tool.xml"), "abc123def4567890", "sig:1"),
        ("fixture-b", "repo-y", Path("tools/b/tool.xml"), "789abcdef0123456", "sig:2"),
    ]
    corpus_check._append_provenance(entries, regressions_dir=fake_regressions)
    known = corpus_check._fmt_known_fixture_paths(regressions_dir=fake_regressions)
    assert known == {
        ("repo-x", "tools/a/tool.xml"),
        ("repo-y", "tools/b/tool.xml"),
    }


def test_provenance_handles_missing_file(tmp_path: Path) -> None:
    """A non-existent PROVENANCE.md returns the empty set, not an error."""
    fake_regressions = tmp_path / "regressions"
    fake_regressions.mkdir()
    known = corpus_check._fmt_known_fixture_paths(regressions_dir=fake_regressions)
    assert known == set()


def test_provenance_append_to_existing_does_not_duplicate(tmp_path: Path) -> None:
    """A second append after writing existing entries adds without rewriting."""
    fake_regressions = tmp_path / "regressions"
    fake_regressions.mkdir()
    corpus_check._append_provenance(
        [("fix-a", "repo-x", Path("a/t.xml"), "deadbeef0000", "sig:a")],
        regressions_dir=fake_regressions,
    )
    corpus_check._append_provenance(
        [("fix-b", "repo-x", Path("b/t.xml"), "deadbeef1111", "sig:b")],
        regressions_dir=fake_regressions,
    )
    known = corpus_check._fmt_known_fixture_paths(regressions_dir=fake_regressions)
    assert known == {("repo-x", "a/t.xml"), ("repo-x", "b/t.xml")}


def test_signature_includes_exception_type_and_deepest_frame() -> None:
    """``_signature`` must dedup crashes by exc type + deepest frame."""
    try:
        raise ValueError("boom")
    except ValueError as exc:
        signature = corpus_check._signature(exc)
    assert signature.startswith("ValueError @ ")
    assert "test_corpus_check.py" in signature
