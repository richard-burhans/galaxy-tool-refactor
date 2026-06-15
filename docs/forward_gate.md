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

- **block-until-canonical** (implemented, `scripts/forward_gate.py` + the published
  Action): the gate reports where a changed tool deviates and fails the check,
  naming the exact local fix command. The author keeps control of their branch.
  The conservative default.
- **suggest** (implemented, `scripts/gate_suggest.py`): instead of failing, the
  gate posts the canonical fix as GitHub **review suggestions** (the one-click
  "Commit suggestion" diffs) on the PR, with the IUC doc link. The author applies
  the edits in place. A fix that lands outside the PR's diff cannot be inlined as a
  suggestion (GitHub only comments on diff lines), so those are summarized in the
  review body with the local `format` command. Non-blocking by design (the friendly
  nudge). See "Suggest mode" below.
- **auto-normalize** (not implemented here): the gate rewrites the changed tools to
  canonical and pushes the fix onto the PR branch. Lowest author friction, but it
  edits the contributor's branch. This is the maintainers' call, so it is left
  unbuilt until they choose it.

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

The Action's inputs are `version` (the pinned release), `base-ref` (default the PR
base SHA), and `mode` (`block`, the default above, or `suggest` — see "Suggest
mode"). The local `scripts/forward_gate.py` is the equivalent maintainer runner
(`make forward-gate`).

## Suggest mode

`scripts/gate_suggest.py` posts the canonical fix as GitHub one-click review
suggestions instead of failing the check. It computes the same provable fix the
bulk normalizer applies, diffs it against the PR's version, and emits a
`suggestion` block for each changed run of lines that falls inside the PR's diff
(GitHub only accepts a comment on a diff line); anything outside the diff is
summarized in the review body with the local `format` command.

```bash
# preview the review JSON locally (no token, no posting)
make gate-suggest REF=origin/main
# post the suggestions on a PR (in CI, with a PR-write token)
uv run python -m scripts.gate_suggest --repo OWNER/REPO --pr 123 --changed-against "$BASE_SHA"
```

The published Action supports it directly via `mode: suggest` (it runs the bundled
`gate_suggest` against the PR; the caller must grant `pull-requests: write`):

```yaml
jobs:
  canonical-form:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write   # so the gate can post review suggestions
    steps:
      - uses: actions/checkout@v5
        with: { fetch-depth: 0 }
      - uses: richard-burhans/galaxy-tool-refactor/.github/actions/forward-gate@main
        with:
          version: "0.3.1"
          mode: suggest
```

(Reference the Action at `@main` until a release that includes the `mode` input is
cut, then pin to that tag.) Suggest mode is non-blocking: it posts the suggestions
and the check passes. Hardening it into a first-class shipped CLI command (instead
of the bundled runner) is the follow-on.

## Relationship to planemo

The gate is complementary to a `planemo lint` CI step, not a replacement: planemo
covers correctness and best-practice breadth; the gate covers *canonical form* for
the provable subset, and it can *fix* what it flags. Running both is sensible.
