#!/usr/bin/env bash
# Pre-push QA gate for the galaxy-tool-refactor workspace.
#
# Runs the deterministic quality slice — ruff, mypy (strict, per package), and
# pytest for all seven packages — and exits non-zero, naming the failing step,
# if anything fails. A `git push` PreToolUse hook (.claude/settings.json) calls
# this and blocks the push on failure, so code never leaves the machine with a
# red gate. Run it manually any time:
#
#   bash scripts/qa_gate.sh
#
# This is the mechanical backstop only; it does NOT replace the full pre-PR
# code + documentation audit (see the project's standing practice).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || { echo "QA gate: cannot cd to repo root" >&2; exit 1; }

PACKAGES=(
    galaxy-tool-refactor-rules
    galaxy-tool-xml
    galaxy-tool-xml-codemod
    galaxy-tool-xml-fmt
    galaxy-tool-xml-check
    galaxy-tool-refactor-registry
    galaxy-tool-refactor-cli
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

echo "QA gate: PASSED"
