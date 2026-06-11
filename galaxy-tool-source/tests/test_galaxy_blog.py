"""Unit tests for the Galaxy Hub blog scaffolder (scripts/galaxy_blog.py).

The pure helpers (slugify / validation / frontmatter) are covered directly; an
end-to-end ``new`` then ``check`` runs against a throwaway galaxy-hub-shaped tree.
"""

from __future__ import annotations

from pathlib import Path

import scripts.galaxy_blog as gb


def test_slugify_is_hub_valid() -> None:
    slug = gb.slugify("How we set up galaxy-tool-refactor for Humans & AI Agents!")
    assert slug == "how-we-set-up-galaxy-tool-refactor-for-humans-ai-agents"
    assert gb.slug_problem(slug) is None
    # letter/digit boundaries are preserved, like the Hub normalizer
    assert gb.slugify("GCC2026 recap") == "gcc2026-recap"


def test_slug_problem_rejects_bad_names() -> None:
    assert gb.slug_problem("Galaxy_Post") is not None  # underscore + uppercase
    assert gb.slug_problem("a--b") is not None  # double hyphen
    assert gb.slug_problem("-lead") is not None  # leading hyphen
    assert gb.slug_problem("") is not None
    assert gb.slug_problem("gcc-2026") is None  # author's choice, valid


def test_render_frontmatter_quotes_free_text() -> None:
    fm = gb.render_frontmatter(
        title="Repos: humans + agents",
        date="2026-03-01",
        author="nekrut",
        tags=("ai", "tools"),
        subsites=("all", "global"),
        tease="A: B",
    )
    assert 'title: "Repos: humans + agents"' in fm  # colon stays valid YAML
    assert "date: '2026-03-01'" in fm
    assert "tags: [ai, tools]" in fm
    assert "subsites: [all, global]" in fm
    assert "    - nekrut" in fm
    assert gb.frontmatter_problems(fm) == []


def test_frontmatter_problems_flags_missing_and_bad_date() -> None:
    assert "no frontmatter" in gb.frontmatter_problems("# just a body")[0]
    bad = "---\ntitle: x\ndate: '03-2026'\n---\n"
    problems = gb.frontmatter_problems(bad)
    assert any("date" in p for p in problems)
    assert any("subsites" in p for p in problems)  # missing required key


def _make_hub(tmp_path: Path) -> Path:
    (tmp_path / "content" / "news").mkdir(parents=True)
    return tmp_path


def test_new_then_check_roundtrip(tmp_path: Path) -> None:
    hub = _make_hub(tmp_path)
    rc = gb.main(
        [
            "new",
            "--title",
            "Humans and Agents",
            "--author",
            "richard-burhans",
            "--date",
            "2026-04-15",
            "--tags",
            "ai,best-practices",
            "--hub-dir",
            str(hub),
        ]
    )
    assert rc == 0
    index = hub / "content" / "news" / "2026" / "humans-and-agents" / "index.md"
    assert index.is_file()
    text = index.read_text(encoding="utf-8")
    assert 'title: "Humans and Agents"' in text and "tags: [ai, best-practices]" in text
    # check passes (no galaxy-hub validate_news.py in the temp tree → pre-checks only)
    assert gb.main(["check", str(index.parent)]) == 0


def test_new_rejects_existing_post(tmp_path: Path) -> None:
    hub = _make_hub(tmp_path)
    args = [
        "new", "--title", "Dup", "--author", "x", "--date", "2026-01-01",
        "--hub-dir", str(hub),
    ]
    assert gb.main(args) == 0
    assert gb.main(args) == 1  # second time: index.md already exists


def test_new_aborts_without_a_hub_checkout(tmp_path: Path) -> None:
    rc = gb.main(
        ["new", "--title", "X", "--author", "y", "--hub-dir", str(tmp_path / "nope")]
    )
    assert rc == 1
