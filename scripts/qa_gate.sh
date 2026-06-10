#!/usr/bin/env bash
# Pre-push QA gate for the galaxy-tool-refactor workspace.
#
# Runs the deterministic quality slice — ruff, mypy (strict, per package), and
# pytest for all eight packages — and exits non-zero, naming the failing step,
# if anything fails. A `git push` PreToolUse hook (.claude/settings.json) calls
# this and blocks the push on failure, so code never leaves the machine with a
# red gate. Run it manually any time:
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
    galaxy-tool-xml
    galaxy-tool-xml-codemod
    galaxy-tool-xml-fmt
    galaxy-tool-xml-check
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

echo "QA gate: mypy (strict, per package)…"
for package in "${PACKAGES[@]}"; do
    uv run mypy --config-file "$package/pyproject.toml" "$package/src" \
        || fail "mypy ($package)"
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
