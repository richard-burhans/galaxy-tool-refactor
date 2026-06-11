---
name: galaxy-blog-post
description: >
  Draft and publish a Galaxy Community Hub news/blog post (a PR to
  galaxyproject/galaxy-hub): release notes, an event recap, a community or
  best-practices piece. The mechanical scaffold and lint is scripts/galaxy_blog.py
  (also runnable by non-agent authors via `make blog-new` / `make blog-check`);
  this skill drives it and writes the prose.
---

# galaxy-blog-post: write a Galaxy news/blog post

A Galaxy news post is a **PR to `galaxyproject/galaxy-hub`** (the Astro site
behind galaxyproject.org). The deterministic part is a script; the writing is
your job.

## Scaffold and lint (the script)

```bash
# create the post in a galaxy-hub checkout (clone it first if needed, into .local/)
uv run python -m scripts.galaxy_blog new \
    --title "How we set up galaxy-tool-refactor for humans and AI agents" \
    --author <github-handle> --tags ai,tools,community --hub-dir .local/galaxy-hub
# write the body, drop images beside index.md, then:
uv run python -m scripts.galaxy_blog check .local/galaxy-hub/content/news/<year>/<slug>
```

Non-agent authors run the same thing as `make blog-new TITLE=… AUTHOR=…` and
`make blog-check POST=…`. The script derives a Hub-valid slug, writes correct
frontmatter, and lints naming, required keys, and (when run inside a galaxy-hub
checkout) the registry fields below. The **authoritative** schema check is
galaxy-hub's own `make validate-metadata`, which `check` points you at; run it in
galaxy-hub's conda env, since it needs `pykwalify` and ours does not.

## Format (what the script encodes, for reference)

- **Path to URL:** `content/news/<YEAR>/<YYYY-MM-DD>-<slug>/index.md` becomes
  `galaxyproject.org/news/<YYYY-MM-DD>-<slug>/`. Images sit beside `index.md`,
  referenced `![alt](./figure.png)`.
- **Naming (CI-linted):** recent posts must be **date-prefixed**,
  `YYYY-MM-DD-<slug>` (their CI fails a bare slug). The slug part is lowercase,
  digits, and hyphens only, with no camelCase or underscores. `new` builds the
  dated name and `check` enforces it.
- **Frontmatter:** `title`, `date: 'YYYY-MM-DD'`, `tease` (listing blurb),
  `tags: [...]`, `subsites: [all, global]` (project-wide), and
  `contributions.authorship: [github-handle]`.
- **Body:** GitHub-Flavored Markdown (prefer Markdown over raw HTML).
- **Diagrams:** the Hub does **not** render Mermaid. Use SVG (text-based, crisp,
  reviewable in the PR diff) or PNG, placed beside `index.md` and referenced
  relatively (`![alt](./figure.svg)`). Give each an `aria-label` and `alt`.

## Registries (galaxy-hub validates these; `check` does too)

These fields are validated against registry files, and an unregistered value
fails galaxy-hub's CI. `galaxy_blog.py check` enforces them when run inside a hub
checkout:

- **`tags`** must each appear in `content/TAGS.yaml`.
- **`subsites`** must each appear in `content/SUBSITES.yaml` (`all` and `global`
  are valid for a project-wide post).
- **`contributions.authorship`** handles must be registered in
  `content/CONTRIBUTORS.yaml`. **A first-time author must add themselves** (the
  mandatory fields are `name` and `joined: YYYY-MM`; everything else is optional).
  Add that change to the same PR.

## Code of Conduct (check every post)

A post on the Hub is **community communication**, so the
[Galaxy Code of Conduct](https://galaxyproject.org/community/coc/) applies (it
covers "all public Galaxy spaces, including GitHub and the Galaxy mailing lists").
Before submitting, read the post against the CoC's principles and revise if needed:

- **Be welcoming and inclusive:** write for a world-wide community of all
  backgrounds; don't assume one audience.
- **Be considerate:** plain, accessible language; not everyone reads English as a
  first language; explain jargon.
- **Be respectful, and careful with words:** never disparage, mock, or single out
  another person, project, or community; critique ideas, not people.
- **Give credit:** name contributors and sources fairly (`contributions.authorship`,
  inline links). Get consent before naming or picturing identifiable people.

A technical, positive post clears this bar easily; the check is to make sure a
comparison, a critique, or an image never crosses into putting someone down.

## Writing (the judgment a script can't do)

- **Tone:** honest, experience-report, and useful, matching the Galaxy news feed
  (for example the 2025 "Using Claude AI for Literature Searches" post). Not
  salesy; pre-release work is framed as "lessons from building X", not "use our
  product".
- **Structure:** a hook (why a Galaxy reader cares), then the concrete thing, then
  what is transferable, then a clear close (link, call to action).
- **Grounding:** every claim should trace to something real in the repo (this
  project's honesty rule, cf. the `repo-explainer` skill and `docs/guide/`).
- Pick `tags` and `subsites` that fit; default to `subsites: [all, global]` for a
  project-wide post.

## Publish

Fork `galaxyproject/galaxy-hub`, branch, add the post dir (and the
`CONTRIBUTORS.yaml` entry if you are a first-time author), push, and open the PR.
CI runs the naming lint and the frontmatter schema check; a maintainer reviews and
merges. The galaxy-hub clone is scratch: keep it under `.local/` (gitignored), and
never vendor it into this repo.
