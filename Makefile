# Discoverable entrypoints for common workflows — the non-agent counterpart to
# the .claude/skills/. Every target is a thin wrapper over a script in scripts/
# (the single source of truth), so `make <thing>` and the matching skill run the
# same logic. Run `make` (or `make help`) to list everything.

.DEFAULT_GOAL := help
.PHONY: help sync hooks qa-gate ship-pr bump fetch-corpus corpus-stats parity \
        blog-new blog-check forward-gate bulk-normalize coverage

help: ## List the available workflows
	@echo "galaxy-tool-refactor — workflows (see docs/workflows.md):"
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	    | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'

sync: ## Install all packages + dev deps (uv sync)
	uv sync

hooks: ## Enable the contributor pre-push gate (one-time, per clone)
	git config core.hooksPath .githooks
	@echo "pre-push gate enabled (git push now runs scripts/qa_gate.sh; --no-verify bypasses)"

qa-gate: ## Run the full quality gate (ruff + mypy strict + pytest, all packages)
	bash scripts/qa_gate.sh

ship-pr: ## Merge a PR safely + clean up — usage: make ship-pr PR=123 [DRY_RUN=1]
	@test -n "$(PR)" || { echo "usage: make ship-pr PR=<number> [DRY_RUN=1]"; exit 1; }
	bash scripts/ship-pr.sh $(if $(DRY_RUN),--dry-run) $(PR)

bump: ## Set the lockstep version everywhere — usage: make bump VERSION=0.3.0
	@test -n "$(VERSION)" || { echo "usage: make bump VERSION=<x.y.z>"; exit 1; }
	uv run python -m scripts.bump_version $(VERSION)

fetch-corpus: ## Clone/update the Toolshed corpus (maintainer; slow, needs hg)
	uv run python -m scripts.fetch_toolshed

corpus-stats: ## Regenerate the corpus stat pages (needs a complete corpus)
	uv run python -m scripts.corpus_check check
	uv run python -m scripts.corpus_check rules
	uv run python -m scripts.corpus_check fmt

parity: ## Regenerate the planemo coverage table (docs/planemo_linter_parity.md)
	uv run python -m scripts.gen_planemo_parity

forward-gate: ## Forward gate (Half B): fail if changed tools aren't canonical — usage: make forward-gate FILES="a.xml b.xml" | REF=origin/main
	uv run python -m scripts.forward_gate $(if $(REF),--changed-against $(REF)) $(FILES)

bulk-normalize: ## Bulk normalizer (Half A): apply the blessed subset across a repo — usage: make bulk-normalize ROOT=.local/tools-iuc [WRITE=1]
	@test -n "$(ROOT)" || { echo 'usage: make bulk-normalize ROOT=<repo-dir> [WRITE=1]'; exit 1; }
	uv run python -m scripts.bulk_normalize "$(ROOT)" $(if $(WRITE),--write)

coverage: ## Coverage tracker (N6): record % canonical for a repo over time — usage: make coverage ROOT=.local/tools-iuc NAME=tools-iuc
	@test -n "$(ROOT)" && test -n "$(NAME)" || { echo 'usage: make coverage ROOT=<repo-dir> NAME=<label>'; exit 1; }
	uv run python -m scripts.coverage_tracker --repo-root "$(ROOT)" --repo-name "$(NAME)"

blog-new: ## Scaffold a Galaxy blog post — usage: make blog-new TITLE="..." AUTHOR=handle [TAGS=a,b]
	@test -n "$(TITLE)" && test -n "$(AUTHOR)" || \
	    { echo 'usage: make blog-new TITLE="..." AUTHOR=<handle> [TAGS=a,b] [HUB=path]'; exit 1; }
	uv run python -m scripts.galaxy_blog new --title "$(TITLE)" --author "$(AUTHOR)" \
	    $(if $(TAGS),--tags $(TAGS)) $(if $(HUB),--hub-dir $(HUB))

blog-check: ## Lint a drafted Galaxy blog post — usage: make blog-check POST=<post-dir>
	@test -n "$(POST)" || { echo "usage: make blog-check POST=<post-dir>"; exit 1; }
	uv run python -m scripts.galaxy_blog check "$(POST)"
