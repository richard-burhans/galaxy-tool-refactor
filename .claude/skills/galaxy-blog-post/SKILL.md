---
name: galaxy-blog-post
description: >
  Draft and publish a Galaxy Community Hub news/blog post (a PR to
  galaxyproject/galaxy-hub). Use when writing a Galaxy news post — release notes,
  an event recap, a community/best-practices piece. The mechanical scaffold +
  lint is scripts/galaxy_blog.py (also runnable by non-agent authors via
  `make blog-new` / `make blog-check`); this skill drives it and writes the prose.
---

# galaxy-blog-post — write a Galaxy news/blog post

A Galaxy news post is a **PR to `galaxyproject/galaxy-hub`** (the Astro site
behind galaxyproject.org). The deterministic part is a script; the writing is
your job.

## Scaffold + lint (the script)

```bash
# create the post in a galaxy-hub checkout (clone it first if needed, into .local/)
uv run python -m scripts.galaxy_blog new \
    --title "How we set up galaxy-tool-refactor for humans and AI agents" \
    --author <github-handle> --tags ai,best-practices,tools --hub-dir .local/galaxy-hub
# …write the body, drop images beside index.md, then:
uv run python -m scripts.galaxy_blog check .local/galaxy-hub/content/news/<year>/<slug>
```

Non-agent authors run the same thing as `make blog-new TITLE=… AUTHOR=…` and
`make blog-check POST=…`. The script derives a Hub-valid slug, writes correct
frontmatter, and lints naming + required keys. The **authoritative** frontmatter
schema check is galaxy-hub's own `make validate-metadata` (run it in galaxy-hub's
conda env — it needs `pykwalify`; ours can't), which `check` points you at.

## Format (what the script encodes, for reference)

- **Path → URL:** `content/news/<YEAR>/<slug>/index.md` →
  `galaxyproject.org/news/<slug>/`. Images sit beside `index.md`, referenced
  `![alt](./figure.png)`.
- **Naming (CI-linted):** lowercase, digits, hyphens only — no camelCase/underscores.
- **Frontmatter:** `title` · `date: 'YYYY-MM-DD'` · `tease` (listing blurb) ·
  `tags: [...]` · `subsites: [all, global]` (project-wide) ·
  `contributions.authorship: [github-handle]`.
- **Body:** GitHub-Flavored Markdown (prefer MD over raw HTML).

## Writing (the judgment a script can't do)

- **Tone:** honest, experience-report, useful — matching the Galaxy news feed
  (e.g. the 2025 "Using Claude AI for Literature Searches" post). Not salesy;
  pre-release work is framed as "lessons from building X", not "use our product".
- **Structure:** a hook (why a Galaxy reader cares) → the concrete thing → what's
  transferable → a clear close (link, call to action).
- **Grounding:** every claim should trace to something real in the repo (this
  project's honesty rule, cf. the `repo-explainer` skill and `docs/guide/`).
- Pick `tags`/`subsites` that fit; default `subsites: [all, global]` for a
  project-wide post.

## Publish

Fork `galaxyproject/galaxy-hub`, branch, add the post dir, push, open the PR. CI
runs the naming lint + frontmatter schema check; a maintainer reviews and merges.
The galaxy-hub clone is scratch — keep it under `.local/` (gitignored), never
vendor it into this repo.
