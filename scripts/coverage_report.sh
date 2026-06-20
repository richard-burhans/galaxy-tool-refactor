#!/usr/bin/env bash
# Test-coverage report across all eight code packages.
#
# REPORTING ONLY — this is deliberately NOT part of the QA gate: there is no
# threshold and it never blocks a push. It surfaces where the suites are thin
# (e.g. the large cli.py / lint check modules covered by a few dense test files)
# so coverage gaps are visible without turning coverage into a brittle gate.
#
# Human path: `make test-coverage`. Each package's suite runs in turn, appending
# into one .coverage file (sequential — no parallel/combine). Writes a terminal
# table and htmlcov/index.html. See docs/workflows.md.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

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

rm -f .coverage
for pkg in "${PACKAGES[@]}"; do
    echo "coverage: ${pkg}"
    uv run --package "$pkg" pytest "$pkg/tests/" -q \
        --cov="$pkg/src" --cov-append --cov-report= -p no:cacheprovider
done

echo
uv run coverage report
uv run coverage html >/dev/null && echo "HTML report written to htmlcov/index.html"
