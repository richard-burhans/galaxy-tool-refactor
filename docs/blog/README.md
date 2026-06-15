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
- [`2026-06-14-what-galaxy-tool-refactor-does-for-your-tools/`](2026-06-14-what-galaxy-tool-refactor-does-for-your-tools/index.md)
  — **submitted** ([galaxy-hub#4058](https://github.com/galaxyproject/galaxy-hub/pull/4058)).
  For IUC maintainers and tool authors, now that `pip install galaxy-tool-refactor`
  works: what the tool does for your tools (format, behavior-preserving upgrade, the
  Planemo-parity checks, the opt-in commands), why it is safe to run, and the open
  conventions questions we are bringing to GCC. Builds on the first post; published
  before GCC.
- [`2026-06-15-fixing-galaxy-tools-at-scale/`](2026-06-15-fixing-galaxy-tools-at-scale/index.md)
  — **submitted** ([galaxy-hub#4062](https://github.com/galaxyproject/galaxy-hub/pull/4062)).
  Fixing tools at the repository scale without the churn: why a one-time
  cleanup decays (the 96.7% re-accumulation finding), the bulk normalizer run end to
  end on the current `tools-iuc` (27.4% to 100% canonical, 1,972 tools, 0 reverted,
  idempotent), the forward gate and its suggest mode (one-click PR review suggestions,
  live on `galaxytools`), and the gate-adoption questions for the community. Builds on
  the second post.
