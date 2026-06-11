# Package naming rename — plan

## Context

We intend to publish the `galaxy-tool-refactor` tooling to PyPI. End users will
install only the front door (`-cli` and `-mcp`), but publishing those forces
publishing **all eight** packages — the whole dependency tree (`cli`/`mcp` →
`registry` → `rules` + `source` + `codemod` + `fmt` + `check`). So every
package gets a public PyPI name, and the names should be settled *before* first
publish: renaming a published package means a tombstone + deprecation shim, so
the cheap window is now (tier-1 `galaxy-tool-source` is already published; the
other seven are not).

Today the names are inconsistent on the axis that will be most visible publicly:
three tiers carry `galaxy-tool-xml-*` while tier-1 was already cleaned to
`galaxy-tool-source` (dropping "xml"). Relative to the published tier-1, the
`xml` packages are the odd ones out.

## Decision (target scheme)

Two deliberate families, matching the ecosystem consensus (consistent prefix,
role-named; building-blocks vs product; front-door distinction via metadata, not
prefix — cf. `google-cloud-*`, `opentelemetry-*`, `pydantic` + `pydantic-core`):

- **`galaxy-tool-*`** — reusable libraries for working with Galaxy tool XML.
- **`galaxy-tool-refactor-*`** — the refactor product built on them.

| Tier | Current dist | Current import | → New dist | → New import |
|---|---|---|---|---|
| 0.5 | `galaxy-tool-refactor-rules` | `galaxy_tool_refactor_rules` | **(Q2)** | |
| 1 | `galaxy-tool-source` | `galaxy_tool_source` | *unchanged (published)* | *unchanged* |
| 2 | `galaxy-tool-xml-codemod` | `galaxy_tool_xml_codemod` | `galaxy-tool-codemod` | `galaxy_tool_codemod` |
| 3 | `galaxy-tool-xml-fmt` | `galaxy_tool_xml_fmt` | `galaxy-tool-fmt` | `galaxy_tool_fmt` |
| 3.5 | `galaxy-tool-xml-check` | `galaxy_tool_xml_check` | **(Q1)** | |
| 3.6 | `galaxy-tool-refactor-registry` | `galaxy_tool_refactor_registry` | *unchanged* | *unchanged* |
| 4 | `galaxy-tool-refactor-cli` | `galaxy_tool_refactor_cli` | *unchanged* | *unchanged* |
| 4 | `galaxy-tool-refactor-mcp` | `galaxy_tool_refactor_mcp` | *unchanged* | *unchanged* |

### Decisions (resolved 2026-06-11)

- **Q1 — `check` package name → `galaxy-tool-lint`** (import `galaxy_tool_lint`).
  "check" collides publicly with planemo's "run the tool to check it" sense;
  `lint` is unambiguous and accurately names the planemo-parity linter tier. The
  CLI verb stays `check`; only the package/import name changes.
- **Q2 — `rules` stays `galaxy-tool-refactor-rules`.** `RuleMeta`/`Violation` are
  the refactor framework's own descriptors (product-specific), so it belongs with
  the product family. No churn on this one.
- **Q3 — front-door metapackage: SHIPPED** (decisions §28) — `galaxy-tool-refactor`
  depends on the CLI with an `[mcp]` extra; pure metadata wheel, lockstep member.

Final renames this pass: tier 2 `galaxy-tool-xml-codemod` → `galaxy-tool-codemod`,
tier 3 `galaxy-tool-xml-fmt` → `galaxy-tool-fmt`, tier 3.5 `galaxy-tool-xml-check`
→ `galaxy-tool-lint` (import dirs likewise).

## Out of scope (explicit)

- `galaxy-tool-source` — already correct and published; untouched.
- `registry` / `cli` / `mcp` — stay `galaxy-tool-refactor-*` (the product family).
- The CLI `check` subcommand verb — unchanged.
- **Dated decision-journal entries** that narrate past PRs keep the old package
  names verbatim (the §26 convention for the tier-1 rename); only functional refs
  and live prose are rewritten.

## Execution (mechanical, per renamed package)

1. `git mv` the dist directory and the `src/<import>` package directory.
2. Update the package's `pyproject.toml`: `[project.name]`, hatch build
   `packages`/targets, and any intra-workspace dependency entries.
3. Update root `pyproject.toml` workspace `members` + `[tool.uv.sources]`, then
   `uv lock` to refresh `uv.lock`.
4. Global **full-token** replace across tracked files — the six tokens only
   (`galaxy-tool-xml-{codemod,fmt,check}` and `galaxy_tool_xml_{codemod,fmt,check}`)
   → the new tokens. **Never** touch bare `galaxy-tool-xml` / `galaxy_tool_xml`
   (tier-1's historical name; still referenced in dated docs). This is the §26
   sed-trap, inverted: full tokens are safe, the bare prefix is not.
5. Update the doc surface: `ARCHITECTURE.md` tier tables, every `CLAUDE.md`,
   `docs/guide/*`, `iuc_best_practices.md`, the qa-gate roster
   (`scripts/qa_gate.sh`), CI (`.github/workflows/ci.yml`), and the corpus
   scripts.
6. Record the rename as a decision (`galaxy-tool-source/docs/decisions.md` §27,
   following the §26 tier-1 precedent), with the old→new mapping table.

## Verification

- `uv sync` resolves; `bash scripts/qa_gate.sh` green (ruff + mypy strict ×8 +
  pytest ×8 — proves every import resolves under the new names).
- `test_decision_citations.py` / `test_stat_artifact_coverage.py` green (catch
  broken cross-refs / stale stat pages).
- `git grep -lE 'galaxy[-_]tool[-_]xml[-_](codemod|fmt|check)'` returns nothing
  outside dated journal entries.
- `/pre-pr-audit`, then one PR.
