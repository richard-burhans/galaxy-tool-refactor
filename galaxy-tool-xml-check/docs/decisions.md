# Decisions — galaxy-tool-xml-check

Each entry records a decision once it lands: a date, the decision, and the
rationale. Mirrors the conventions of the sibling packages' `docs/decisions.md`.

## D1 (2026-05-30) — A new advisory-check tier for detect-only IUC rules (PR4)

### Decision

A new tier-3.5 package, `galaxy-tool-xml-check`, hosts the **detect-only**
(advisory) IUC best-practice checks: a `CheckRule` ABC (`rules.py`), the concrete
checks (`checks.py`, `IUC001`–`IUC012`), and the registry + runner (`detect.py` —
`all_checks()` / `detect_violations()`). Each check is an LBYL query over a
tier-1 `ToolDocument` that yields the shared tier-0.5 `Violation`; each carries a
`RuleMeta` with the new `detect_only=True` flag (added to tier 0.5 in this PR).
PR4 of the detect/fix rule-split effort (see `../../docs/detect_fix_split_plan.md`).

### Rationale

- **A separate package, not the app or a mutating tier.** These checks are
  conceptual peers of the GTX rules (they carry codes in the same registry) but
  are read-only and depend only on tier 1 + tier 0.5 — never on codemod/fmt or
  the app. A dedicated package keeps them independently consumable and keeps the
  app a pure composer (it runs codemod + fmt + check detect), consistent with
  `format`/`upgrade`. This realises the architecture sketched in
  `../../docs/iuc_best_practices.md` ("a small check library").
- **Advisory, not fixable.** Unlike a GTX finding ("`format`/a codemod would
  change this"), an IUC finding is a judgment call ("consider adding tests").
  `RuleMeta.detect_only` marks them so the `check` CLI treats them as
  informational (shown, but exit stays 0 unless `--strict`) rather than a
  failing gate — a canonical tool that merely lacks EDAM xrefs should not fail
  CI.

### Scope

Implemented (10): `IUC001` tests present · `IUC002` `<command>` CDATA · `IUC003`
id charset · `IUC004` version PEP 440 / `@…@` macro · `IUC005` requirements
present · `IUC006` error handling (`detect_errors` / `<stdio>`) · `IUC007`
EDAM/xrefs present · `IUC008` non-empty `<help>` · `IUC009` non-empty
`<description>` · `IUC010` `<help>` CDATA.

Reserved placeholders (`detect()` is a no-op stub, pending tuning to avoid
noise): `IUC011` single-quote Cheetah variables, `IUC012` `&&`-vs-lone-`&`
command joining — both require parsing shell/Cheetah text inside `<command>`
CDATA and are deferred. A standalone "profile recency" check is intentionally
omitted: it overlaps `GTX007` / the `upgrade` command.

### Caveats

- CDATA detection (`IUC002`/`IUC010`) works by re-serialising the element, since
  lxml exposes CDATA as plain `.text` (the tree is parsed `strip_cdata=False`,
  so a CDATA section round-trips as `<![CDATA[…]]>`).
- The checks read the **un-expanded** tree, so a practice satisfied via a macro
  (e.g. `<expand macro="requirements"/>`) can still be flagged — the same
  macro-awareness limitation the rest of the framework carries today. Advisory
  status makes the resulting noise tolerable.

### Reproduction

```sh
uv run --package galaxy-tool-xml-check pytest galaxy-tool-xml-check/tests/
# corpus sanity (per-check hit rate over a 2,000-tool sample); none at 0%/100%:
#   IUC001 31.6% · 002 37.6% · 003 13.7% · 004 0.7% · 005 54.6% · 006 51.7%
#   IUC007 91.0% · 008 2.9% · 009 8.5% · 010 42.0% · 011/012 0% (placeholders)
```
