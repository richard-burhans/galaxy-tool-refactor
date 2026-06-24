"""Sphinx configuration for the galaxy-tool-refactor guide.

The published guide is exactly the ``docs/guide/`` subtree (Markdown via MyST);
``ARCHITECTURE.md`` and the internal ``docs/*`` decision/stat artifacts are not
part of it. Mermaid fences authored for GitHub render here unchanged via
``myst_fence_as_directive``.
"""

project = "galaxy-tool-refactor"
author = "Richard Burhans"
copyright = "2026, Richard Burhans"  # noqa: A001 - Sphinx-required name

extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
]

# Markdown is the source format; "index.md" is the root document.
root_doc = "index"
source_suffix = {".md": "markdown"}

# Treat GitHub-style ```mermaid fences as the mermaid directive, so the same
# fenced blocks render on GitHub and in this Sphinx build.
myst_fence_as_directive = ["mermaid"]
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

html_theme = "sphinx_rtd_theme"
html_title = "galaxy-tool-refactor"

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


_EXAMPLES_INTRO = """# Examples

Real, runnable before/after walkthroughs. Each command block on these pages is the
actual output of the shipped `galaxy-tool-refactor` CLI, not a mock-up.
"""


def _materialize_subtree(*, source, target, intro, skip):  # noqa: ANN001, ANN202
    """Copy a docs/ subtree into the Sphinx source and write a glob-toctree index.

    The proofs and examples are authored under docs/ (their canonical home, also
    referenced from GitHub and, for proofs, pinned by test_proof_documents.py). To
    publish them in this guide without duplicating them in git, they are copied
    into a generated subtree of the Sphinx source at build time and given a synthesised
    index page (an intro plus a ``:glob:`` toctree over every page). Globbing means a
    new proof or example is published automatically, never silently dropped. The
    generated docs/guide/proofs/ and docs/guide/examples/ dirs are gitignored.
    """
    import shutil

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for page in sorted(source.glob("*.md")):
        if page.name in skip:
            continue
        shutil.copy2(page, target / page.name)
    toctree = "\n```{toctree}\n:maxdepth: 1\n:glob:\n\n*\n```\n"
    (target / "index.md").write_text(intro + toctree, encoding="utf-8")


def _sync_published_subtrees(app):  # noqa: ANN001, ANN201 - Sphinx event callback
    from pathlib import Path

    docs = Path(app.confdir).parent
    source = Path(app.srcdir)
    # Proofs: the proofs/README.md is the section intro; it is not itself a page.
    _materialize_subtree(
        source=docs / "proofs",
        target=source / "proofs",
        intro=(docs / "proofs" / "README.md").read_text(encoding="utf-8"),
        skip={"README.md"},
    )
    _materialize_subtree(
        source=docs / "examples",
        target=source / "examples",
        intro=_EXAMPLES_INTRO,
        skip=set(),
    )


def setup(app):  # noqa: ANN001, ANN201 - Sphinx extension entry point
    app.connect("builder-inited", _sync_published_subtrees)
    return {"parallel_read_safe": True, "parallel_write_safe": True}
