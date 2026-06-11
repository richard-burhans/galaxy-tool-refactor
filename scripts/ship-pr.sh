#!/usr/bin/env bash
# Safe PR merge + cleanup for galaxy-tool-refactor maintainers.
#
# Usage:
#   scripts/ship-pr.sh <PR-number>             # merge + clean up
#   scripts/ship-pr.sh --dry-run <PR-number>   # check preconditions, show the plan, merge nothing
#
# Requires an authenticated GitHub CLI (`gh auth login`). Squash-merges (the
# house style), then syncs main and deletes the merged branch.
#
# It NEVER passes `gh pr merge --delete-branch`: that flag's local checkout has
# wiped the gitignored `.local` corpus before (a multi-thousand-repo refetch).
# The repo's `delete_branch_on_merge` setting removes the *remote* branch
# server-side instead, with no local checkout. A corpus tripwire at the end
# flags any shrink.
#
# Single source of truth for the merge flow: the `/ship-pr` Claude Code skill
# calls this same script, so the human path and the agent path can't drift.
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ] || [ "${1:-}" = "-n" ]; then
    DRY_RUN=1
    shift
fi
PR="${1:?usage: scripts/ship-pr.sh [--dry-run] <PR-number>}"

cd "$(git rev-parse --show-toplevel)"

corpus_count() {
    { find .local/corpus/galaxy-toolshed -mindepth 2 -maxdepth 2 -type d 2>/dev/null \
        || true; } | wc -l | tr -d ' '
}

# --- Preconditions -----------------------------------------------------------
if [ -e .local ] && ! git check-ignore -q .local; then
    echo "ABORT: .local is not gitignored — a merge checkout could clobber the corpus." >&2
    exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
    echo "ABORT: working tree is not clean; commit or stash first." >&2
    exit 1
fi

echo "Syncing local main…"
git fetch origin --quiet
git checkout main --quiet
git pull --ff-only origin main --quiet

state="$(gh pr view "$PR" --json mergeStateStatus -q .mergeStateStatus)"
branch="$(gh pr view "$PR" --json headRefName -q .headRefName)"
echo "PR #$PR  head=$branch  mergeStateStatus=$state"
if [ "$state" != "CLEAN" ]; then
    echo "ABORT: PR is '$state', not CLEAN." >&2
    case "$state" in
        BLOCKED)
            echo "  A required check is missing/red, or the branch is behind main." >&2
            echo "  If CI jobs were renamed (e.g. a Python matrix split 'qa' into" >&2
            echo "  'qa (3.x)'), repoint branch protection at the stable check name." >&2
            ;;
        BEHIND) echo "  The branch is behind main — update it (rebase/merge main) first." >&2 ;;
        DIRTY) echo "  Merge conflicts — resolve them on the branch first." >&2 ;;
        DRAFT) echo "  The PR is a draft — mark it ready first." >&2 ;;
    esac
    exit 1
fi

before="$(corpus_count)"

if [ "$DRY_RUN" = "1" ]; then
    echo
    echo "DRY RUN — would now:"
    echo "  gh pr merge $PR --squash      # remote branch auto-deletes (delete_branch_on_merge)"
    echo "  git checkout main && git pull --ff-only"
    echo "  git branch -D $branch ; git remote prune origin"
    echo "  corpus tripwire (currently $before toolshed dirs)"
    exit 0
fi

# --- Merge (squash; NO --delete-branch) --------------------------------------
echo "Merging #$PR (squash)…"
gh pr merge "$PR" --squash

merged="$(gh pr view "$PR" --json state -q .state)"
if [ "$merged" != "MERGED" ]; then
    echo "ABORT: PR state is '$merged', not MERGED — not cleaning up." >&2
    exit 1
fi

# --- Sync, clean up, tripwire ------------------------------------------------
git fetch origin --quiet
git checkout main --quiet
git pull --ff-only origin main --quiet
git branch -D "$branch" 2>/dev/null || true
git remote prune origin >/dev/null 2>&1 || true

after="$(corpus_count)"
echo "Merged #$PR — main is now: $(git log --oneline -1)"
echo "Corpus tripwire: ${before} -> ${after} toolshed dirs."
if [ "$before" != "0" ] && [ "$after" -lt "$before" ]; then
    echo "WARNING: the corpus shrank — re-run: uv run python -m scripts.fetch_toolshed" >&2
fi
