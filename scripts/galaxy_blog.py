#!/usr/bin/env python3
"""Scaffold and validate a Galaxy Community Hub news/blog post.

Galaxy news posts are PRs to ``galaxyproject/galaxy-hub``: a post is
``content/news/<YEAR>/<slug>/index.md`` whose directory name becomes the URL
(``galaxyproject.org/news/<slug>/``), with images alongside it. This script does
the deterministic part — scaffold a correctly-named, correctly-front-mattered
post, and lint it — so the `/galaxy-blog-post` skill (and a non-agent author via
``make blog-new`` / ``make blog-check``) share one implementation.

    uv run python -m scripts.galaxy_blog new --title "..." --author nekrut \
        --tags ai,tools --hub-dir .local/galaxy-hub
    uv run python -m scripts.galaxy_blog check .local/galaxy-hub/content/news/2026/<slug>

The authoritative frontmatter schema check is galaxy-hub's own
``scripts/validate_news.py`` (run in their CI); ``check`` runs it too when the
target is inside a galaxy-hub checkout.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

# A valid Hub slug / directory name: lowercase letters, digits, single hyphens,
# no leading/trailing/double hyphen (the CI naming lint, CONTRIBUTING.md).
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DEFAULT_SUBSITES = ("all", "global")


def slugify(title: str, /) -> str:
    """A Hub-valid slug from *title*: lowercase, non-alphanumerics → single hyphen.

    Letter/digit boundaries are preserved (``gcc2026`` stays one token), matching
    the Hub normalizer.
    """
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def slug_problem(slug: str, /) -> str | None:
    """Why *slug* is not a valid Hub directory name, or ``None`` if it is."""
    if not slug:
        return "slug is empty"
    if not _SLUG_RE.fullmatch(slug):
        return (
            f"slug {slug!r} must be lowercase letters, digits, and single hyphens "
            "(no uppercase, underscores, spaces, or leading/trailing/double hyphens)"
        )
    return None


def render_frontmatter(
    *,
    title: str,
    date: str,
    author: str,
    tags: tuple[str, ...],
    subsites: tuple[str, ...],
    tease: str,
) -> str:
    """The YAML frontmatter block (between ``---`` lines) for a news post.

    Built as text (no YAML dependency) — the schema is small and fixed. Quotes the
    free-text ``title``/``tease`` so colons in them stay valid YAML.
    """
    tag_list = ", ".join(tags)
    subsite_list = ", ".join(subsites)
    return (
        "---\n"
        f'title: "{title}"\n'
        f"date: '{date}'\n"
        f'tease: "{tease}"\n'
        f"tags: [{tag_list}]\n"
        f"subsites: [{subsite_list}]\n"
        "contributions:\n"
        "  authorship:\n"
        f"    - {author}\n"
        "---\n"
    )


def render_post(
    *,
    title: str,
    date: str,
    author: str,
    tags: tuple[str, ...],
    subsites: tuple[str, ...],
    tease: str,
) -> str:
    """A full ``index.md`` (frontmatter + a body skeleton) ready to edit."""
    frontmatter = render_frontmatter(
        title=title,
        date=date,
        author=author,
        tags=tags,
        subsites=subsites,
        tease=tease,
    )
    return (
        f"{frontmatter}\n"
        f"# {title}\n\n"
        "<!-- Write the post in GitHub-Flavored Markdown. Put images in this same\n"
        "     directory and reference them relatively: ![alt](./figure.png). Keep\n"
        "     the tone honest and experience-report, matching the Galaxy news feed. -->\n\n"
        "TODO: opening hook — what this is and why a Galaxy reader should care.\n"
    )


def frontmatter_problems(text: str, /) -> list[str]:
    """Lightweight pre-flight checks on a post's frontmatter text.

    Catches the mistakes worth catching before galaxy-hub's authoritative
    ``validate_news.py`` runs: a missing block, missing required keys, a malformed
    date. Not a full YAML parse — a line scan over the first ``---``-fenced block.
    """
    if not text.startswith("---"):
        return ["no frontmatter: the file must start with a '---' line"]
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ["frontmatter block is not closed with a second '---'"]
    block = parts[1]
    problems: list[str] = []
    keys = {
        line.split(":", 1)[0].strip()
        for line in block.splitlines()
        if ":" in line and not line.startswith(" ")
    }
    for required in ("title", "date", "tags", "subsites"):
        if required not in keys:
            problems.append(f"missing required frontmatter key: {required!r}")
    date_match = re.search(r"^date:\s*'?(?P<date>[^'\n]+)'?\s*$", block, re.MULTILINE)
    if date_match is not None and not _DATE_RE.fullmatch(date_match["date"].strip()):
        problems.append(
            f"date {date_match['date'].strip()!r} is not 'YYYY-MM-DD'"
        )
    return problems


def _hub_root(post_path: Path, /) -> Path | None:
    """The galaxy-hub checkout root *post_path* lives in, or ``None``.

    Identified by its own ``scripts/validate_news.py`` + ``content/news/`` — used
    only to point the author at the authoritative validator, which must run in
    galaxy-hub's *own* environment (it needs ``pykwalify`` etc., not in ours).
    """
    for parent in post_path.resolve().parents:
        if (parent / "scripts" / "validate_news.py").is_file() and (
            parent / "content" / "news"
        ).is_dir():
            return parent
    return None


def _cmd_new(args: argparse.Namespace, /) -> int:
    title = args.title.strip()
    if not title:
        print("ABORT: --title is empty", file=sys.stderr)
        return 1
    slug = args.slug or slugify(title)
    problem = slug_problem(slug)
    if problem is not None:
        print(f"ABORT: {problem}", file=sys.stderr)
        return 1
    date = args.date
    if not _DATE_RE.fullmatch(date):
        print(f"ABORT: --date {date!r} is not 'YYYY-MM-DD'", file=sys.stderr)
        return 1

    hub_dir = Path(args.hub_dir)
    news_root = hub_dir / "content" / "news"
    if not news_root.is_dir():
        print(
            f"ABORT: {news_root} not found — clone galaxy-hub first:\n"
            f"  git clone https://github.com/galaxyproject/galaxy-hub {hub_dir}",
            file=sys.stderr,
        )
        return 1

    year = date[:4]
    post_dir = news_root / year / slug
    index = post_dir / "index.md"
    if index.exists():
        print(f"ABORT: {index} already exists", file=sys.stderr)
        return 1

    tags = tuple(t.strip() for t in args.tags.split(",") if t.strip())
    subsites = tuple(s.strip() for s in args.subsites.split(",") if s.strip())
    tease = args.tease or f"TODO: one-line teaser for {title}"
    post_dir.mkdir(parents=True)
    index.write_text(
        render_post(
            title=title,
            date=date,
            author=args.author,
            tags=tags,
            subsites=subsites,
            tease=tease,
        ),
        encoding="utf-8",
    )
    print(f"created {index}")
    print(f"  url:  galaxyproject.org/news/{slug}/")
    print("  next: write the body, add images beside index.md, then")
    print(f"        uv run python -m scripts.galaxy_blog check {post_dir}")
    return 0


def _cmd_check(args: argparse.Namespace, /) -> int:
    target = Path(args.path)
    index = target / "index.md" if target.is_dir() else target
    if not index.is_file():
        print(f"ABORT: no index.md at {target}", file=sys.stderr)
        return 1

    problems: list[str] = []
    slug = index.parent.name
    slug_issue = slug_problem(slug)
    if slug_issue is not None:
        problems.append(slug_issue)
    problems.extend(frontmatter_problems(index.read_text(encoding="utf-8")))

    if problems:
        print(f"{index}: {len(problems)} issue(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"{index}: naming + frontmatter pre-checks pass")

    hub_root = _hub_root(index)
    where = f"cd {hub_root} && " if hub_root is not None else "in your galaxy-hub clone, "
    print(
        "note: before opening the PR, run galaxy-hub's authoritative frontmatter "
        f"schema check in its own conda env:\n  {where}make validate-metadata"
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="scaffold a new post in a galaxy-hub checkout")
    new.add_argument("--title", required=True, help="the post title")
    new.add_argument(
        "--author", required=True, help="your GitHub handle (frontmatter authorship)"
    )
    new.add_argument(
        "--date",
        default=datetime.date.today().isoformat(),
        help="publication date YYYY-MM-DD (default: today)",
    )
    new.add_argument("--tags", default="", help="comma-separated tags")
    new.add_argument(
        "--subsites",
        default=",".join(_DEFAULT_SUBSITES),
        help="comma-separated subsites (default: all,global)",
    )
    new.add_argument("--tease", default="", help="one-line listing teaser")
    new.add_argument("--slug", default="", help="override the title-derived slug")
    new.add_argument(
        "--hub-dir",
        default=".local/galaxy-hub",
        help="path to a galaxy-hub checkout (default: .local/galaxy-hub)",
    )
    new.set_defaults(func=_cmd_new)

    check = sub.add_parser("check", help="lint a drafted post (naming + frontmatter)")
    check.add_argument("path", help="the post directory or its index.md")
    check.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
