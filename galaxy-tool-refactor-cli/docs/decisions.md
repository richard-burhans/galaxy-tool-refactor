# Decisions — galaxy-tool-refactor-cli

Each entry records a decision once it lands: a date, the decision, and the
rationale. Mirrors the conventions of the sibling packages' `docs/decisions.md`.

## D1 (2026-05-29) — A top-level app tier that separates `upgrade` from `format`

### Decision

A new tier-4 package owns the user-facing `galaxy-tool-refactor` CLI and all
cross-tier orchestration. It depends on the codemod tier (tier 2) and the fmt
tier (tier 3) and exposes two commands:

- `format` — apply `CANONICAL_CODEMODS` (typo repair + attribute order) then
  fmt's cosmetic rules. Safe, idempotent; never changes `profile=`.
- `upgrade` — apply `AUTO_UPGRADE_CODEMODS` (typo repair, then iterative profile
  upgrade) then cosmetic formatting. Opt-in and semantic; reports the profile
  steps applied and warns on stalls.

Profile upgrade was previously folded into the default canonical pipeline that
fmt's CLI ran (`UpgradeToLatest` was in `CANONICAL_CODEMODS`). It has been
pulled out into the opt-in `upgrade` command here.

### Rationale

- **Upgrade is semantic, fallible, and reports outcomes** — it changes
  `profile=`, applies lossy structural migrations, and can stall below the
  latest profile. Folding that into a silent, idempotent "format my tool" pass
  conflated two very different operations. Separate, explicit commands let users
  opt into modernization deliberately (mirrors how formatters gate semantic
  rewrites behind an explicit flag).
- **Output goes through fmt's serializer**, so the orchestrator must sit *above*
  fmt. It could not live in the codemod tier without inverting the tier order
  (fmt already consumes codemod's pipeline contracts). A dedicated app tier is
  the clean home; it also let fmt's CLI shed its codemod orchestration and
  return to cosmetic-only (see `galaxy-tool-xml-fmt/docs/decisions.md` §D12).
- **`FixTypos` runs in both pipelines.** It stays in the default `format`
  pipeline (repairing near-miss typos is safe and useful) *and* runs first in
  `upgrade` as a precondition — `UpgradeToLatest` no-ops on a tool that
  validates nowhere, so a broken-and-outdated tool must be repaired before it
  can upgrade. `FixTypos` is idempotent, so appearing in both is harmless.

### Shape

- One `click` group, `galaxy-tool-refactor`, with `format` and `upgrade`
  subcommands; both reuse fmt's `cli_support` engine for file walking,
  `--check` / `--diff` / `--quiet`, drift detection, and the summary.
- Both serialize via `format_tool_document`, so output is canonical-form XML in
  either case; the commands differ only in which codemod pipeline runs. The
  typical modernization flow is `upgrade` then `format` (the second is
  idempotent on already-formatted output).

### Reproduction

```sh
uv sync
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/
```
