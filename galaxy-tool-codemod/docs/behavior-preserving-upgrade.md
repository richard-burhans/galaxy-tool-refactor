# Behaviour-preserving profile upgrade — feasibility investigation

> **Superseded (2026-06-12).** The direction this investigated is now SHIPPED in
> a different shape: rather than pinning legacy behaviour across a full bump
> (the all-or-nothing finding below still holds), the default `upgrade` now
> **stops at the behaviour ceiling** — the newest profile reachable without
> crossing an applicable, un-auto-fixed `must_fix` change — with
> `--allow-behavior-change` as the opt-out. See `docs/decisions.md` §45, the
> gate proof (`docs/proofs/behavior-gate.md`), and the user-facing reference
> (`docs/profile_boundaries.md`). This document remains the pinnability
> inventory (which codes have a legacy-restore attribute) and the record of
> why per-boundary pinning was not the chosen mechanism.

> **Design investigation — predates any implementation.** This records what it
> would take to make `upgrade` *behaviour-preserving* (the "Alternative (rejected
> for now)" in `docs/decisions.md` §22), the evidence that bounds it, and a
> recommendation. No code follows from it yet.

**Date:** 2026-06-01.

## Context

`decisions.md` §22 established that the profile upgrade is **structurally sound
but not behaviour-preserving**: bumping `profile=` opts a tool into newer Galaxy
runtime defaults the XSD cannot verify. `docs/../profile_upgrades.md` (the ledger)
enumerates those boundaries; `profile_semantics.py` + the `upgrade` warning
(decisions §23) surface them. The open question this investigates: *can we go
further and actually preserve the old behaviour across a bump?*

## The central finding — profile is all-or-nothing by design

Galaxy's `profile` is a **bundle opt-in**: declaring profile *X* opts the tool
into *every* runtime change up to *X*. Galaxy provides **no general per-behaviour
opt-out** — that is the mechanism's whole point (a tool stays on its old profile
to keep old behaviour; it raises the profile to adopt the new behaviour
wholesale). So, for most boundaries, you **cannot** bump the profile *and* retain
the old behaviour. Preservation is possible only where:

1. Galaxy ships an **explicit compatibility knob** (rare), or
2. you **edit the tool's own command / Cheetah / dependencies** to reproduce the
   old behaviour under the new defaults — which is author-intent work, not a
   mechanically-synthesizable XML edit.

This means a fully behaviour-preserving upgrade is **not achievable by XML edits**
for the majority of boundaries. The realistic feature is *best-effort
behaviour-pinning*: handle the small pinnable subset, and be explicit that the
rest cannot be preserved.

## Per-boundary triage

Pinnable = can the *old* behaviour be restored while *declaring the new profile*?

| Boundary (profile) | Runtime change | Pinnable on the new profile? | Mechanism / why not |
|---|---|---|---|
| **17.09** | `provided_metadata_style` default → `"default"` | ✅ **yes, clean knob** | set `provided_metadata_style="legacy"` (Galaxy's documented restore) |
| **16.04** | non-zero exit (not stderr) is the error default; `set -e` on | ⚠️ **partial** | restorable via an explicit `detect_errors` / `<stdio>` block, but reproducing the exact legacy stderr-check is involved (note: most corpus tools are already ≥16.10, so 16.04 only bites the no-/sub-16.04-profile baseline) |
| **24.0** | undeclared `data_source` request params dropped | ⚠️ **partial** | declare them in `<request_param_translation>` — only for `data_source` tools, and the original param set isn't always recoverable |
| **25.1** | credentials move to `<credentials>` | ⚠️ **partial** | a structural migration, but needs knowing which credentials the tool used |
| **24.2** | `data_column` params require a valid `data_ref` | ⚠️ **needs author intent** | the *correct* `data_ref` can't be guessed (this is the validity-blocking part GTR010-adjacent work would face) |
| **18.01** per-job `$HOME` · **18.09** qualified input refs · **19.05** Python 2→3 · **20.05** JSON `None`/lists · **20.09** `set -e` (multi-command) · **21.09** `from_work_dir` whitespace / `data_source` venv · **23.0** optional-text → `None` | various runtime defaults | ❌ **no XML knob** | preserving these means editing the tool's command/Cheetah/dependencies (or not bumping at all); not mechanically or safely synthesizable |

## What supporting it would require

1. **Reframe the goal.** Not "preserve behaviour on bump" (impossible in general)
   but "*best-effort* pin the handful of boundaries Galaxy lets us, and be loud
   about the rest."
2. **Data.** Extend `SEMANTIC_PROFILE_CHANGES` (or a sibling map) to carry, per
   boundary, a `pinnable` verdict and the pinning edit (mostly `None`).
3. **An opt-in mode** — e.g. `upgrade --preserve-behaviour`. For each *pinnable*
   boundary the bump crosses, synthesise the compat knob (e.g. add
   `provided_metadata_style="legacy"` when crossing 17.09). For each *non-pinnable*
   boundary crossed, **refuse the upgrade or hard-warn** (escalate the §23 note),
   never silently change behaviour.
4. **Per-knob codemods + corpus validation.** Each pinnable knob is a small,
   single-purpose codemod that must be proven to (a) still validate at the new
   profile and (b) actually restore the old behaviour. Subject to the same
   idempotence + post-validity sweep gate as every `upgrade_vN`.
5. **Accept the limit.** For the non-pinnable majority, the only
   behaviour-preserving path is human review/testing — exactly what the §23
   warning directs. The warning is therefore the *primary* mechanism, with
   auto-pinning a narrow enhancement, not a replacement.

## Recommendation

Scope any future work to the **pinnable subset only**, starting with **17.09**
(`provided_metadata_style="legacy"`) — the one clean, documented, low-risk knob —
behind an explicit opt-in flag, with the §23 warning remaining the default for all
other boundaries. Do **not** attempt the non-pinnable boundaries: they are out of
reach by Galaxy's design, and a tool that *looks* preserved but isn't is worse
than an honest warning. Revisit 16.04 / 24.0 / 25.1 only if a concrete consumer
needs them and corpus evidence shows the pinning edit is safe.

## Galaxy-source findings (2026-06-01) — authoritative

A follow-up investigation read Galaxy's own source. Galaxy ships a **tool upgrade
advisor** at `lib/galaxy/tool_util/upgrade/` with a structured catalogue,
`upgrade_codes.json` (18 codes, each `level` = `must_fix` / `consider` / `ready`,
often with a legacy-restore recipe and the introducing PR). We now **vendor that
catalogue** as `PROFILE_UPGRADE_CODES` (codemod `decisions.md` §23) — the
authoritative source of truth. These findings **supersede the hand-built triage
above** where they differ.

### The four CLEAN pinnable knobs (confirmed against `tool_util/parser/xml.py`)

For these, a single documented attribute/element restores the old behaviour while
declaring the new profile — a `--preserve-behaviour` codemod could synthesise them:

| Galaxy code | Profile | Exact edit to restore legacy behaviour |
|---|---|---|
| `16_04_exit_code` | 16.04 | add `<stdio><regex match=".*" source="stderr" level="fatal" description="Unknown error encountered"/></stdio>` (only if no `<stdio>` exists) |
| `17_09_consider_provided_metadata_style` | 17.09 | `provided_metadata_style="legacy"` on `<outputs>` |
| `18_01_consider_home_directory` | 18.01 | `use_shared_home="true"` on `<command>` |
| `20_09_consider_set_e` | 20.09 | `strict="false"` on `<command>` |

Every other code is **NONE / PARTIAL**: it restores only via `<requirements>`
additions (the `*_python_environment` trio → `galaxy-util`), `<request_param_translation>`
authoring, qualified `structured_like`, command/Cheetah handling of `None` vs `""`,
or test reordering — author-owned content, not a profile-gated toggle. (This
corrects the earlier guess that 16.04/24.0/25.1 were "partially pinnable" knobs.)

### Making *more upgrades automatic* — the `must_fix` codes

Pivotal architectural finding: **none of Galaxy's four `must_fix` gates are
XSD-enforced** — they are runtime/semantic. Our existing `upgrade_vN` codemods are
driven by `newest_valid_profile` (a change is needed only when the next profile's
XSD blocks validation), so these gates **cannot ride the `UpgradeToLatest` loop**;
automating them needs a **detect-driven** mechanism. That mechanism now exists — the
**`RuntimeGatedFix` family** the `upgrade` path applies once a tool reaches a fix's
introduction profile (codemod `decisions.md` §24).

| Galaxy `must_fix` code | Profile | Auto? | Note |
|---|---|---|---|
| `21_09_fix_from_work_dir_whitespace` | 21.09 | **AUTO — shipped** | `FixFromWorkDirWhitespace` (GTR014): deterministic `value.strip()` on `<data from_work_dir>`, applied as a runtime-gated fix during `upgrade` |
| `16_04_fix_output_format` | 16.04 | **AUTO-with-heuristic — shipped** | `FixOutputFormatInput` (GTR015): `format="input"` → `format_source="X"` for a single top-level data input — the deduped sweep fixes 79 tools (the `output-format-input` measure sizes the raw split: 109 of ~150 are single-top-level); multi/nested/no-input cases reported |
| `16_04_fix_interpreter` | 16.04 | NEEDS-INTENT | rewriting `interpreter=` to a full `$__tool_directory__` call needs the script name/position — better as an advisory `check` |
| `24_2_fix_test_case_validation` | 24.2 | NEEDS-INTENT | a bundle of parameter-model fixes (unknown-param, select-by-value, column-int, qualify names); decompose later |

### Corpus blast radius (`scripts/measure.py semantic-upgrade-boundaries`, 2026-06-01)

Of 8,608 considered tools, **94.2% cross ≥1 Galaxy upgrade code** on upgrade-to-latest;
`24_2_fix_test_case_validation` alone hits 92.3%. Decisively: **0 tools have *every*
crossed code cleanly pinnable** — so a `--preserve-behaviour` mode could *fully*
preserve essentially no real tool (almost every upgrade also crosses a no-knob
code). This is the empirical proof of the §22 boundary and the reason the §23
warning, not auto-pinning, is the primary mechanism.

### How Galaxy detects (vs our range-based warning)

Galaxy's advisor takes a tool path, walks `ProfileMigration` steps from the tool's
declared profile to the target, and emits a code only when a per-code **detection
predicate** (structural xpath / typed-attr / for 24.2 the full test validator)
fires. Our `upgrade_codes_crossed` is **range-based** (it flags every code whose
profile is crossed, not whether the tool trips it) — coarser but dependency-free;
porting Galaxy's predicates is the precondition for precise per-tool advice.
*(Aside: three upstream codes are currently dead/buggy in Galaxy's detector —
`17_09` queries a backtick-quoted attribute name, `21_09` adds an empty code
string, `23_0` relies on a helper that ignores its xpath — so do not assume the
catalogue and the live detector agree code-for-code.)*

## Methodology / reproduce / refute

- **Behaviour deltas:** the Galaxy schema docs' `<tool> profile` attribute
  (https://docs.galaxyproject.org/en/latest/dev/schema.html); the per-tool error
  knobs are the `detect_errors` / `<stdio>` docs (same schema page). These are the
  same sources as the ledger's Semantic column.
- **Refute a "pinnable" verdict:** show that setting the proposed knob either
  fails to validate at the target profile or does not actually restore the old
  behaviour. **Refute a "no XML knob" verdict:** point to a Galaxy compatibility
  attribute/element (in the schema docs or `lib/galaxy/tool_util/`) that restores
  the old default while declaring the new profile — that boundary then moves to
  the pinnable subset.

See `docs/decisions.md` §22 (soundness boundary), §23 (the warning), and
`../../docs/profile_upgrades.md` (the per-profile ledger).
