# Workflows — two on-ramps, one source of truth

Every maintainer/contributor workflow here has **two front doors**:

- a **human path** — a `make` target or a script you run directly, plus a docs
  checklist where judgment is involved; and
- an **agent path** — a Claude Code skill under [`.claude/skills/`](../.claude/skills)
  for contributors who drive the repo with an agent.

They are **not** two implementations. The logic lives once, in `scripts/` (and the
guard tests), and everything else calls it — CI, the git pre-push hook, the `make`
targets, and the skills. So the two paths can't drift, and you never need an agent
to do the work: `make help` lists the same things a skill would run.

## Standing convention (when you add a workflow)

> **A new *procedural* skill must ship its non-agent path in the same change.**
> Extract the executable steps into a `scripts/*.sh`/`*.py`, have the `SKILL.md`
> *call* that script (don't re-list the steps), add a `make` target, and add a row
> to the table below. Pure *reference* skills (coding standards) and *generation*
> skills (doc authoring) need no script — just link them here. This keeps the
> agent and non-agent audiences first-class and the logic single-source.

## The map

| Workflow | Human path | Agent path |
|---|---|---|
| Quality gate (ruff + strict mypy + tests + guard checks) | `make qa-gate` (= `scripts/qa_gate.sh`) | `/pre-pr-audit` (mechanical step) |
| Pre-PR review (code + docs judgment) | the [PR template](../.github/PULL_REQUEST_TEMPLATE.md) checklist + `make qa-gate` | `/pre-pr-audit` |
| Merge a PR + clean up safely | `make ship-pr PR=123` (= `scripts/ship-pr.sh`; `DRY_RUN=1` to preview) | `/ship-pr` |
| Forward gate — Half B (fail PRs whose changed tools aren't canonical) | `make forward-gate FILES=… \| REF=origin/main` (= `scripts/forward_gate.py`); see [`forward_gate.md`](forward_gate.md) | — (CI gate) |
| Forward gate — suggest mode (post canonical fixes as PR review suggestions) | `make gate-suggest REF=origin/main [REPO=… PR=…]` (= `galaxy-tool-refactor gate-suggest`) | — (CI gate) |
| Bulk normalize — Half A (apply the blessed subset across a repo) | `make bulk-normalize ROOT=… [WRITE=1]` (= `scripts/bulk_normalize.py`) | — |
| Coverage tracker — N6 (record % canonical for a repo over time) | `make coverage ROOT=… NAME=…` (= `scripts/coverage_tracker.py`; or the monthly scheduled `coverage-tracker.yml`, which opens a PR); see [`coverage_tracker.md`](coverage_tracker.md) | — |
| Cut a release (lockstep bump + tag) | `make bump VERSION=0.3.0`, then `git tag vX && git push --tags` ([CONTRIBUTING](../CONTRIBUTING.md#releasing-maintainers)) | — |
| Enable the local pre-push gate | `make hooks` (= `git config core.hooksPath .githooks`) | — |
| Refresh corpus stats | `make fetch-corpus` then `make corpus-stats` (or the scheduled `corpus-stats.yml`) | — |
| Regenerate the planemo coverage table | `make parity` (= `scripts/gen_planemo_parity.py`; freshness-tested) | — |
| Check vendored skills for upstream updates | `make check-skills` (= `scripts/check_vendored_skills.py`; or the scheduled `vendored-skills.yml`) | — |
| Test-coverage report (informational, not a gate) | `make test-coverage` (= `scripts/coverage_report.sh`; or the `coverage.yml` artifact on main) | — |
| Add a structural codemod | read [`add-codemod`](../.claude/skills/add-codemod/SKILL.md) as a TDD how-to | `/add-codemod` |
| Add a corpus measurement | read [`corpus-measurement`](../.claude/skills/corpus-measurement/SKILL.md); helpers in `scripts/measure.py` | `/corpus-measurement` |
| Write a Galaxy blog post | `make blog-new TITLE=… AUTHOR=…` + `make blog-check POST=…` (= `scripts/galaxy_blog.py`) | `/galaxy-blog-post` |
| Coding standards | [`dignified-python`](../.claude/skills/dignified-python/SKILL.md) (governs) · [`optimized-python`](../.claude/skills/optimized-python/SKILL.md) | same (auto-applied) |
| Deep architecture audit | read [`architecture-audit`](../.claude/skills/architecture-audit/SKILL.md) + `docs/architecture_audit.md` | `/architecture-audit` |
| Regenerate the audience guide (`docs/guide/`) | read [`repo-explainer`](../.claude/skills/repo-explainer/SKILL.md) (generation skill, no script) | `/repo-explainer` |

The `add-codemod` / `corpus-measurement` / `architecture-audit` skills are
**how-to guides** — a human reads the `SKILL.md` as documentation and follows it;
the agent path just automates the same steps. Only the *procedural* workflows
(gate, ship-pr) get a dedicated script, because only those have steps worth
running with one command.
