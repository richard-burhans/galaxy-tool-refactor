---
name: ship-pr
description: >
  The safe merge + branch-cleanup sequence for galaxy-tool-refactor. Use when
  merging a PR (yours or after review) and tidying up the branch. Encodes the
  hard-won corpus-safety rules — the `.local` corpus has been wiped twice by a
  careless merge checkout, each costing a multi-thousand-repo refetch — so the
  guardrails are followed, not recalled. Invoke whenever you're about to
  `gh pr merge`, or to clean up merged branches in bulk.
---

# ship-pr — merge a PR and clean up safely

The one job a hook can't do: merge a PR without wiping the local corpus, and
keep the branch list from accumulating. Two facts drive every step below.

1. **`.local/` holds the cloned corpus** (~17 GB of Toolshed clones + the Galaxy
   source clone). It is gitignored, NOT tracked. Re-fetching it takes a very long
   time (thousands of `hg clone`s). Protect it.
2. **A branch checkout that crosses a commit where `.local` was once *tracked*
   deletes the corpus.** `gh pr merge --delete-branch` triggers exactly such a
   local checkout — that is how the corpus was lost. The repo's
   `delete_branch_on_merge` setting (enabled) deletes the *remote* branch
   server-side with **no** local checkout, so it is safe; the `--delete-branch`
   *flag* is not. **Never pass `--delete-branch`.**

## Preconditions (verify before merging)

```bash
git -C "$REPO" check-ignore .local      # MUST print ".local" (gitignored, safe)
git rev-parse --abbrev-ref HEAD         # note where you are
git fetch origin main -q && git rev-parse main origin/main   # local main synced?
GH_TOKEN=x gh pr checks <PR> | cat      # CI green BEFORE merging
GH_TOKEN=x gh pr view <PR> --json mergeable,mergeStateStatus -q '{mergeable,mergeStateStatus}'
```

- If `.local` is **not** gitignored, STOP — fix `.gitignore` first; a merge could
  stage/clobber the corpus.
- If local `main` is **behind** `origin/main`, sync it (`git checkout main &&
  git pull --ff-only`) **before** merging — a stale local main is what makes a
  post-merge checkout dangerous.
- Wait for the `qa` check to pass. Never merge red.

## Merge (no `--delete-branch`)

```bash
GH_TOKEN=x gh pr merge <PR> --squash        # squash is the house style; NO --delete-branch
GH_TOKEN=x gh pr view <PR> --json state,mergedAt -q '{state,mergedAt}'
```

`delete_branch_on_merge` removes the *remote* branch automatically, server-side —
nothing is checked out locally, so the corpus is untouched.

**Confirm `state` is `MERGED` before ANY cleanup.** A merge can be refused —
`gh pr merge` then prints "add the `--admin` flag" and the PR stays open. If you
delete the local branch on a non-merge you lose your local ref. Gate the cleanup:

```bash
[ "$(GH_TOKEN=x gh pr view <PR> --json state -q .state)" = "MERGED" ] || {
  echo "NOT merged — do not clean up"; exit 1; }
```

A `BLOCKED` merge almost always means branch protection: a required status check
is missing or the branch is behind `main` (strict mode). **Gotcha:** when a CI job
is renamed — e.g. adding a Python matrix turns `qa` into `qa (3.10)`… — the
branch-protection *required check* still names the old `qa` and is never satisfied,
so every PR is `BLOCKED`. Fix by pointing protection at the stable aggregator:
`printf '{"strict":true,"contexts":["ci"]}' | GH_TOKEN=x gh api -X PATCH
repos/<owner>/<repo>/branches/main/protection/required_status_checks --input -`.

## Post-merge: sync, clean up, verify

```bash
git checkout main -q && git pull --ff-only origin main -q     # fast-forward only
git log --oneline -1                                          # confirm the squash landed
git branch -D <branch>                                        # delete the local branch
git remote prune origin                                       # drop the stale remote-tracking ref
# CORPUS TRIPWIRE — must be unchanged from before the merge:
find .local/corpus/galaxy-toolshed -mindepth 2 -maxdepth 2 -type d | wc -l
```

If the corpus count dropped, the corpus was clobbered — re-run
`uv run python -m scripts.fetch_toolshed` (additive; it skips existing clones).

## Bulk cleanup of already-merged branches

To tidy a backlog, only delete branches whose commits are already in `main`:

```bash
# 0 unmerged-by-patch-id == safe to delete. A squash-merged branch shows its
# commits as "unmerged" (squash rewrote them) — confirm via its merged PR instead:
git cherry origin/main "$branch" | grep -c '^+'              # 0 => merged
GH_TOKEN=x gh pr list --state merged --search "head:$branch" --json number   # squash check
```

Delete local + remote per branch, then `git remote prune origin`. **Never** delete
a branch with unmerged commits, and leave unrelated in-flight branches alone.

## Never

- Never pass `gh pr merge --delete-branch` (local checkout → corpus loss).
- Never symlink `.local` into a git worktree (a worktree checkout then deletes it).
- Never merge with a stale local `main` or a red `qa` check.
- Never `gh` without the `GH_TOKEN=x` placeholder prefix (the proxy injects real
  auth; a bare `gh` reports "not logged in").
