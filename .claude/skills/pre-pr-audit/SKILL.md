---
name: pre-pr-audit
description: >
  The standing pre-PR review for galaxy-tool-refactor: a full code + documentation
  audit of the change set before opening ANY pull request. Reads every changed/new
  file fully and checks coding standards, simplification/dead-code, doc & comment
  accuracy, stale docs (tier tables, package counts, CI coverage), and
  stat/measurement consistency, then runs the mechanical QA gate. ALWAYS invoke this
  before `gh pr create` (and ideally before the commit). Use when about to open a PR,
  when asked to review the change set / diff before pushing, or to sanity-check that
  a branch is PR-ready. Supports an opt-in multi-agent escalation for high-stakes PRs.
---

# Pre-PR audit

The standing rule for this repo: **no PR without a full code + documentation audit
of the change set.** This skill is that audit. It is a *judgment* review — read the
code, don't just run tools — that sits on top of the mechanical gate
(`scripts/qa_gate.sh`, already enforced by a pre-push hook).

Invoke it before opening any PR. The mechanical gate guarantees the green-tests part
never slips; this skill owns the parts a hook cannot: standards, doc/code agreement,
stale-doc and stat-consistency judgment.

---

## Step 0 — Scope the change set

```bash
git fetch origin main 2>/dev/null; git diff --stat main...HEAD   # or origin/main
git diff --name-status main...HEAD
```

**Read every changed and new file fully** — not just the diff hunks. A hunk hides
the surrounding contract (the docstring that now lies, the sibling field that's now
dead). No shortcuts; this is the explicit standing ask.

---

## Step 1 — Coding standards (dignified-python governs)

dignified-python is the tiebreaker; optimized-python is secondary (both vendored at
`.claude/skills/`). Check, per changed file:

- **LBYL over `try/except`** — exceptions only at the CLI error boundary (chained
  `from e`) and third-party API boundaries with no LBYL form.
- **`pathlib.Path` + explicit `encoding="utf-8"`** on all text I/O.
- **Keyword-only arguments after the first** (`*` in the signature).
- **Absolute imports, no re-exports, no `__all__`** (the generated `models/v*/` are
  the one sanctioned re-export exception).
- **No import-time side effects** — `@cache` for module state.
- **Type hints + docstrings throughout**; ≤4-space indentation depth where sane.
- `ruff` + `mypy --strict` per package (covered by Step 6, but eyeball intent too).

## Step 2 — Simplification / consolidation

- **Dead code** — fields/params/branches no longer used. *Break, don't keep for
  back-compat* (this is a pre-1.0 internal monorepo).
- **Duplicated helpers** to consolidate; functions that could reuse an existing
  pipeline instead of re-implementing (e.g. the shared `cli_support` engine, the
  `(sourceline, code)` sort, the corpus `_shared.py` helpers).
- Does the change sit at the right tier? (orchestration belongs in the registry
  facade, serialisation in fmt, etc. — see `ARCHITECTURE.md`.)

## Step 3 — Doc / comment accuracy

Every docstring, inline comment, `README.md`, `CLAUDE.md`, `docs/decisions.md`, and
`ARCHITECTURE.md` touched-or-implicated by the change must describe what the code
**actually does now**. Specifically:

- **Cross-references resolve** — cited `§`/`D`-numbers exist (grep the decisions
  headers); `[[memory]]` / file links point at real targets.
- **Consumer claims** — "X is consumed by Y", "the facade composes Z" still true.
- A new decision lands in the owning package's `docs/decisions.md` (date + a
  `Reproduced by` command when it cites a measurement).

## Step 4 — Stale docs (the easy-to-miss tier)

Sweep for things the change silently invalidated:

- **Tier tables / package counts** — "eight packages", the tier matrix in each
  `CLAUDE.md` + `ARCHITECTURE.md`.
- **Command lists** — `corpus_check` subcommands, `measure.py` slugs, CLI commands.
- **CI coverage** — `.github/workflows/ci.yml` has drifted before (silently dropped
  the check tier); confirm every package + script path is still exercised.
- Draft/aux artifacts (e.g. a gitignored abstract draft) that quote now-stale facts.

## Step 5 — Stats / measurement consistency

- Numbers cited in docs must match the committed stat artifacts
  (`docs/*_stats.md`, `docs/corpus_data/`).
- **Never fabricate or hand-edit a measured corpus number.** If a number changed,
  it must come from re-running the standing measurement
  (`scripts/measure.py` / `scripts/corpus_check.py`), not a typed-in guess.

## Step 6 — Mechanical gate + ship

```bash
bash scripts/qa_gate.sh        # ruff + mypy strict ×7 + pytest ×7
```

Only once Steps 1–5 are clean **and** the gate is green:

1. Commit (branch first if on `main` — never commit straight to the default branch).
2. `git push` (the pre-push hook re-runs the gate).
3. Open the PR with `GH_TOKEN=x gh pr create …` (the `x` placeholder lets the proxy
   inject real auth — see the gh-token memory).
4. Watch the `qa` CI check to a pass.

---

## Output

End with a short, scannable verdict:

- **PASS** — Steps 1–5 clean, gate green → proceed to commit/PR.
- **BLOCK** — list each issue with `file:line`, the dimension, and the fix; do not
  open the PR until resolved. Apply mechanical fixes inline; surface judgment calls.

Lead with the verdict. A clean "nothing to fix, here's the green gate" is the
expected common case — don't manufacture findings.

---

## Optional — multi-agent escalation (high-stakes PRs)

For large or risky change sets, escalate (opt-in; same machinery as the
`/architecture-audit` skill — adapt
[`../architecture-audit/escalation-workflow.template.js`](../architecture-audit/escalation-workflow.template.js)
to be **diff-scoped** instead of tier-scoped):

- **Find** — one reader per changed file (or per cohesive file group) + one sweep per
  audit dimension (Steps 1–5), each given the diff and `ARCHITECTURE.md`.
- **Verify** — pipeline each finding into an adversarial refuter (default: refute
  anything intentional/already-handled/wrong).
- **Synthesize** — dedup; separate must-fix-before-PR from nice-to-have; you
  integrate, apply safe fixes, re-run the gate.

Optionally fold in `/code-review` on the diff for the correctness-bug dimension this
checklist intentionally doesn't cover (it is doc/standards-focused). Reserve
escalation for PRs where the cost of a missed regression is high; the single pass is
the default.
