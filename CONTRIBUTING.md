# Contributing to galaxy-tool-refactor

Thanks for your interest! This is a uv workspace of eight packages that parse,
lint, format, and structurally upgrade Galaxy tool XML. New contributors are
welcome — this guide is the fast path from clone to merged PR.

> Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first for the map of the seven tiers
> and the cross-tier contracts. Per-package rationale lives in each package's
> `docs/decisions.md`.

## Setup

```bash
git clone https://github.com/richard-burhans/galaxy-tool-refactor
cd galaxy-tool-refactor
uv sync                                  # installs all eight packages + dev deps
git config core.hooksPath .githooks      # enable the pre-push gate (one-time)
```

`uv sync` needs [uv](https://docs.astral.sh/uv/). The `core.hooksPath` step makes
`git push` run the same quality gate CI runs, so you catch failures locally.

## The quality gate

One script is the source of truth — ruff, strict mypy per package, and pytest
across all eight packages:

```bash
bash scripts/qa_gate.sh
```

It is wired into CI (`.github/workflows/ci.yml`, across Python 3.10–3.13) and the
`.githooks/pre-push` hook, so the same checks run everywhere. Green runs are
cached per working-tree state; `QA_GATE_FORCE=1` re-runs.

## Coding standards

Hand-written code follows **dignified-python** (governs), with **optimized-python**
as a secondary reference (both vendored under `.claude/skills/`). The essentials:

- LBYL over `try/except`; exceptions only at a CLI error boundary or a third-party
  API boundary with no LBYL alternative.
- `pathlib.Path` with explicit `encoding="utf-8"` on all text I/O.
- Keyword-only arguments after the first; absolute imports; no re-exports, no `__all__`.
- No import-time side effects (`@cache` for module state).
- Type hints and docstrings throughout.
- Codemod/check-tier work is **test-first** (a failing test, then the minimum code).

## Workflow

1. Branch off `main` (`feat/…`, `fix/…`, `docs/…`).
2. Make the change; if it adds a rule or a corpus-backed number, follow the
   conventions in the relevant package's `docs/decisions.md` and the
   `.claude/skills/` workflows (e.g. `add-codemod`, `corpus-measurement`).
3. Update the docs your change implicates — tier tables, package counts, the
   `docs/guide/` capability matrix, and any `docs/*_stats.md` a rule change affects.
   Record a new decision in the owning package's `docs/decisions.md`.
4. Run `bash scripts/qa_gate.sh` until green.
5. Open a PR. CI (the `ci` check) must pass; `main` is protected and requires it.
   A maintainer reviews and merges.

`main` is protected: merges require the `ci` check to be green and the branch to
be up to date. Be ready to rebase on `main` before merge.

## Releasing (maintainers)

All eight packages are versioned **in lockstep** (one version, published as a
set — `galaxy-tool-source/docs/decisions.md` §27). To cut a release:

```bash
uv run python -m scripts.bump_version 0.3.0   # set the new version everywhere
# commit, open a PR, merge
git tag v0.3.0 && git push origin v0.3.0       # triggers .github/workflows/release.yml
```

`release.yml` verifies the tag matches every package's version, builds all eight,
and publishes to PyPI via Trusted Publishing. Each package needs a one-time
pending publisher configured on PyPI (see the `release.yml` header). Update
`CHANGELOG.md` (one changelog for the whole set) as part of the release PR.

## Questions

Open an issue or a draft PR — happy to help you find where a change belongs.
