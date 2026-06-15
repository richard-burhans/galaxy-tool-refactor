# The forward-enforcement gate (Half B)

Part of the repository-scale auto-fix system (plan:
`~/.claude/plans/tools-iuc-autofix-system.md`; conference question §7 in
[`iuc_conference_questions.md`](iuc_conference_questions.md)). **Status: a proposal
to bring to the IUC maintainers, plus a working reference implementation. It is not
enforced on any repository yet** — whether a repository adopts it, and in which
mode, is the maintainers' decision.

## Why a gate

A one-shot bulk normalization of a tool repository decays: new pull requests land
in the author's own style, so the toolchain would re-fix the same files forever.
The measured re-accumulation rate is high: across 452 recently merged, human-
reviewed `tools-iuc` PRs, 96.7% were still non-canonical in their merged state
(`docs/gate_reaccumulation_stats.md`). So the durable design is two cooperating
halves over one blessed rule set:

- **Half A — the bulk normalizer** (`scripts/bulk_normalize.py`): a one-time pass
  that clears a repository's backlog.
- **Half B — this forward gate** (`scripts/forward_gate.py`): a pre-merge check
  that runs the same rules on every incoming PR, over only the tools the PR
  changed, so the backlog cannot rebuild.

Both halves read their rule set from one classification
(`galaxy_tool_refactor_registry.gate_eligibility`), so a rule the gate enforces is
exactly one the bulk pass applies, and vice versa. See
[`gate_eligibility.md`](gate_eligibility.md).

## What it runs

Only the **gate-eligible** rules: those that are both provably behaviour-preserving
*and* have an uncontroversial canonical form. Attribute reordering (GTR002, GTR005)
is **not** in the gate — it is blocked pending an IUC canonical-order decision
(conference §3), so the gate never touches it. Advisory checks never run here.

## Two modes (the IUC choice, conference §7)

- **block-until-canonical** (implemented): the gate reports where a changed tool
  deviates and fails the check, naming the exact local fix command. The author
  keeps control of their branch. This is the conservative default.
- **auto-normalize** (not implemented here): the gate rewrites the changed tools to
  canonical and pushes the fix onto the PR branch (or posts a suggestion). Lower
  author friction, but it edits the contributor's branch. This is the maintainers'
  call, so it is intentionally left unbuilt until they choose it.

## Local use

```bash
# check specific files
make forward-gate FILES="tools/foo/foo.xml tools/bar/bar.xml"
# or check everything changed against a base ref
make forward-gate REF=origin/main
# (both call scripts/forward_gate.py)
```

Exit code: 0 when every checked tool is canonical, 1 when any is not.

## CI adoption — the published Action

The gate ships as a reusable composite **GitHub Action** at
[`.github/actions/forward-gate`](../.github/actions/forward-gate/action.yml). A tool
repository adopts it by adding one workflow — no copied shell, no vendored code:

```yaml
name: forward-gate
on:
  pull_request:
    paths: ["tools/**/*.xml"]

jobs:
  canonical-form:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # the gate diffs against the PR base
      - uses: richard-burhans/galaxy-tool-refactor/.github/actions/forward-gate@v0.3.1
        with:
          version: "0.3.1"   # pin to the release the bulk normalizer used
```

**Requires `galaxy-tool-refactor` >= 0.3.1** — the first release that includes the
forward gate (`gate_eligibility`); 0.3.0 predates it. Cut that release (the standard
`make bump VERSION=0.3.1` + tag flow) before adopting the Action, then reference it
at the matching `@v0.3.1` tag. Substitute the owner the toolchain is published under.

The Action installs the pinned `galaxy-tool-refactor` release, **derives the gate's
rule set from that release's classification at runtime** (the `gate-eligible` codes
from `gate_eligibility` — so the gate and the bulk normalizer provably agree),
diffs the PR's changed `tools/**/*.xml`, and runs the shipped `check`. `check`
exits non-zero when a gate-eligible (fixable) rule fires, failing the job; a
changed `macros.xml` or other non-tool XML is reported clean, never an error. On
failure the Action emits a GitHub `::error::` annotation naming the exact
`galaxy-tool-refactor format --select …` command to fix it locally.

`version` (default the pinned release) and `base-ref` (default the PR base SHA) are
the Action's inputs. The local `scripts/forward_gate.py` is the equivalent
maintainer runner (`make forward-gate`).

## Relationship to planemo

The gate is complementary to a `planemo lint` CI step, not a replacement: planemo
covers correctness and best-practice breadth; the gate covers *canonical form* for
the provable subset, and it can *fix* what it flags. Running both is sensible.
