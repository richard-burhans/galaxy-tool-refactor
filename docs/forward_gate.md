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

## CI adoption (template for a tool repository)

This workflow is a **template to copy into a tool repository** (e.g.
`tools-iuc/.github/workflows/forward-gate.yml`); it does not run in this repo. It
installs a pinned `galaxy-tool-refactor` release, derives the gate codes from that
release's classification at runtime (so the gate and the bulk pass can never
drift), and runs the shipped `check`. Pin the version to the same release the bulk
normalizer used (or install from a tagged commit,
`pip install "git+https://github.com/<owner>/galaxy-tool-refactor@vX"`, if that
release is not on PyPI).

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
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install the toolchain (pin to the bulk-pass release)
        run: pip install "galaxy-tool-refactor==0.3.0"
      - name: Check changed tools are in canonical form
        run: |
          set -euo pipefail
          base="${{ github.event.pull_request.base.sha }}"
          # the gate's rule set, derived from the shipped classification
          codes=$(python -c "from galaxy_tool_refactor_registry.gate_eligibility import eligibility_groups, GATE_ELIGIBLE; print(','.join(sorted(eligibility_groups()[GATE_ELIGIBLE])))")
          files=$(git diff --name-only --diff-filter=AM "$base"...HEAD -- 'tools/**/*.xml')
          if [ -z "$files" ]; then echo "no changed tool XML"; exit 0; fi
          echo "Gate rules: $codes"
          galaxy-tool-refactor check --select "$codes" $files
```

The shipped `galaxy-tool-refactor check` exits non-zero when a fixable rule fires,
which fails the job; the richer message (naming the exact `format` command) is what
`scripts/forward_gate.py` prints, and a maintainer-facing Action could call that
instead once the gate is productionized as a versioned, published Action.

## Relationship to planemo

The gate is complementary to a `planemo lint` CI step, not a replacement: planemo
covers correctness and best-practice breadth; the gate covers *canonical form* for
the provable subset, and it can *fix* what it flags. Running both is sensible.
