# Blog posts

Version-controlled source for the Galaxy Community Hub news/blog posts about
`galaxy-tool-refactor`. These are public artifacts about the project, so unlike the
local-only conference drafts they live tracked in this repo, and are published to
[`galaxyproject/galaxy-hub`](https://github.com/galaxyproject/galaxy-hub).

Each post is a dated-slug directory matching the Hub layout
(`content/news/<YEAR>/<YYYY-MM-DD>-<slug>/index.md`, with images alongside), so a
directory here drops straight into a Hub PR. Scaffold and validate with
`scripts/galaxy_blog.py` (see [`docs/workflows.md`](../workflows.md)).

Published text follows the project writing conventions: welcoming, Code-of-Conduct
tone, no em-dash, Oxford comma.

## Posts

- [`2026-06-11-a-repository-for-both-humans-and-ai-agents/`](2026-06-11-a-repository-for-both-humans-and-ai-agents/index.md)
  — **published.** How the repository is built for both humans and AI agents: one
  runnable source of truth (CI, git hooks, Makefile, and agent skills all call the same
  scripts), executable conventions, and dual on-ramps.
- _(planned)_ a second post for IUC maintainers and tool authors: what
  `galaxy-tool-refactor` does for your tools (format, behavior-preserving upgrade, the
  Planemo-parity checks, the opt-in commands), why it is safe to run, and the open
  conventions questions we are bringing to GCC.
