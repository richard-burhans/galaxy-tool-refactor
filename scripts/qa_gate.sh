#!/usr/bin/env bash
# Pre-push QA gate for the galaxy-tool-refactor workspace.
#
# Runs the deterministic quality slice — ruff, mypy (strict, per package, at the
# 3.10 support floor), and pytest for all eight packages — and exits non-zero,
# naming the failing step, if anything fails. A `git push` PreToolUse hook
# (.claude/settings.json) calls this with QA_GATE_REQUIRE_CLEAN=1 and blocks the
# push on failure (or on an uncommitted tracked tree), so code never leaves the
# machine with a red gate or a validated-tree-that-differs-from-the-push. Run it
# manually any time:
#
#   bash scripts/qa_gate.sh
#
# This is the mechanical backstop only; it does NOT replace the full pre-PR
# code + documentation audit (see the project's standing practice).
#
# Green results are cached per working-tree state (.git/qa-gate-green): a
# re-run on a byte-identical tree — e.g. the pre-push hook minutes after a
# manual run — skips instantly. Any change to tracked or untracked-unignored
# files invalidates the cache. QA_GATE_FORCE=1 bypasses it.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || { echo "QA gate: cannot cd to repo root" >&2; exit 1; }

# Pre-push only (QA_GATE_REQUIRE_CLEAN=1, set by the .claude/settings.json hook):
# the gate validates the WORKING TREE, but `git push` sends COMMITS, so an
# uncommitted tracked change means we'd validate code that isn't being pushed
# (the trap that let an uncommitted fix pass the hook yet ship broken to CI, #224).
# Refuse the push until the tree is committed. Manual runs and CI do not set this,
# so dev-with-uncommitted-changes is unaffected.
if [[ "${QA_GATE_REQUIRE_CLEAN:-}" == "1" ]] && ! git diff --quiet HEAD 2>/dev/null; then
    echo "QA gate: uncommitted tracked changes present." >&2
    echo "  The gate validates the working tree, but 'git push' sends commits, so" >&2
    echo "  they would differ. Commit (or stash) before pushing." >&2
    exit 1
fi

CACHE_FILE="$REPO_ROOT/.git/qa-gate-green"

qa_state() {
    # One hash covering HEAD's tree, staged+unstaged changes, and the content
    # of untracked-unignored files — i.e. everything the gate's verdict can
    # depend on. Failure of any probe yields a distinct (uncacheable) hash.
    {
        git rev-parse 'HEAD^{tree}'
        git diff HEAD
        git ls-files --others --exclude-standard -z | sort -z | xargs -0 -r sha256sum
    } 2>/dev/null | sha256sum | cut -d' ' -f1
}

STATE_BEFORE="$(qa_state)"
if [[ "${QA_GATE_FORCE:-}" != "1" && -f "$CACHE_FILE" ]] \
    && [[ "$(cat "$CACHE_FILE")" == "$STATE_BEFORE" ]]; then
    echo "QA gate: PASSED (cached — tree unchanged since last green run;" \
        "QA_GATE_FORCE=1 to re-run)"
    exit 0
fi

PACKAGES=(
    galaxy-tool-refactor-rules
    galaxy-tool-source
    galaxy-tool-codemod
    galaxy-tool-fmt
    galaxy-tool-lint
    galaxy-tool-refactor-registry
    galaxy-tool-refactor-cli
    galaxy-tool-refactor-mcp
)

fail() {
    echo "QA gate FAILED at: $1" >&2
    exit 1
}

echo "QA gate: ruff…"
ruff_targets=()
for package in "${PACKAGES[@]}"; do
    ruff_targets+=("$package/src" "$package/tests")
done
ruff_targets+=(scripts)
uv run ruff check "${ruff_targets[@]}" || fail "ruff"

echo "QA gate: mypy (strict, per package, at the 3.10 support floor)…"
for package in "${PACKAGES[@]}"; do
    # --python-version 3.10: the requires-python floor. mypy checks against 3.10's
    # typeshed regardless of the local interpreter, catching version-floor breakage
    # the local-interpreter run misses (e.g. a 3.11+-only API, or 3.10's stricter
    # Traversable.joinpath single-arg signature — the gap that slipped #224 to CI).
    uv run mypy --python-version 3.10 --config-file "$package/pyproject.toml" \
        "$package/src" || fail "mypy ($package)"
done

echo "QA gate: pytest…"
for package in "${PACKAGES[@]}"; do
    uv run --package "$package" pytest "$package/tests/" -q \
        || fail "pytest ($package)"
done

# Cache the green verdict only if the tree did not change while the gate ran.
if [[ "$(qa_state)" == "$STATE_BEFORE" ]]; then
    printf '%s\n' "$STATE_BEFORE" > "$CACHE_FILE"
fi
echo "QA gate: PASSED"
