---
name: ship-pr
description: >
  The safe merge + branch-cleanup sequence for galaxy-tool-refactor. Use when
  merging a PR (yours or after review) and tidying up the branch. The executable
  flow lives in scripts/ship-pr.sh (the single source of truth, also runnable by
  non-agent maintainers via `make ship-pr`); this skill drives it and handles the
  judgment a script can't. Encodes the hard-won corpus-safety rules — the `.local`
  corpus has been wiped twice by a careless merge checkout. Invoke whenever you're
  about to `gh pr merge`, or to clean up merged branches in bulk.
---

# ship-pr — merge a PR and clean up safely

The merge flow is a script: **`scripts/ship-pr.sh <PR>`** (preview with
`--dry-run`). It checks preconditions, squash-merges, syncs `main`, deletes the
branch, and runs a corpus tripwire. In this sandbox `gh` needs the proxy prefix:

```bash
GH_TOKEN=x bash scripts/ship-pr.sh --dry-run <PR>   # preview
GH_TOKEN=x bash scripts/ship-pr.sh <PR>             # merge + clean up
```

A non-agent maintainer runs the same thing as `make ship-pr PR=<PR>` (no proxy
prefix needed with a normally-authenticated `gh`). Don't hand-roll the steps when
the script will do — that's how they drift.

## What the script guarantees (and why)

- **Never `gh pr merge --delete-branch`.** That flag's local checkout has wiped
  the gitignored `.local` corpus (a multi-thousand-repo refetch). The repo's
  `delete_branch_on_merge` setting deletes the *remote* branch server-side, no
  checkout — the script relies on that.
- **Syncs local `main` before merging**, confirms `state == MERGED` before any
  cleanup (a refused merge must not trigger a branch delete), and **tripwires the
  corpus** afterward.

## The judgment the script leaves to you

- **A `BLOCKED` merge** is almost always branch protection: a required check is
  missing/red, or the branch is behind `main`. The classic trap is a CI job
  rename — adding a Python matrix turns `qa` into `qa (3.x)`, so the required
  context `qa` is never satisfied. Repoint protection at the stable aggregator:
  `printf '{"strict":true,"contexts":["ci"]}' | GH_TOKEN=x gh api -X PATCH
  repos/<owner>/<repo>/branches/main/protection/required_status_checks --input -`.
- **Whether to merge at all** — CI green, review done, the right base.

## Bulk cleanup of already-merged branches

The script ships one PR. To tidy a backlog, delete only branches whose commits
are already in `main`:

```bash
git cherry origin/main "$branch" | grep -c '^+'              # 0 => merged
GH_TOKEN=x gh pr list --state merged --search "head:$branch" --json number   # squash-merge check
```

A squash-merged branch shows its commits as "unmerged" (squash rewrote them) —
confirm via its merged PR instead. Delete local + remote per branch, then
`git remote prune origin`. **Never** delete a branch with unmerged commits, and
leave unrelated in-flight branches alone. (Prune can race the server-side delete —
re-run `git remote prune origin` if a stale `origin/<branch>` ref lingers.)
