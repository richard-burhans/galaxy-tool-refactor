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
