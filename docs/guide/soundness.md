# Soundness — what "safe" guarantees (and what it doesn't)

> **TL;DR.** `format` never changes behaviour. `upgrade` is **minimal-bump by
> default**: `profile=` moves only when strictly needed for validity, and a tool
> that validates where it sits is kept byte-untouched. `upgrade --modernize` is
> the **behavior-preserving walk**: it advances the profile only as far as it
> can prove no applicable breaking (`must_fix`) Galaxy behaviour change is
> crossed un-fixed, stops there with an actionable report, and the result is
> **structurally valid** at the profile it declares. Going further is an
> explicit choice (`--modernize --allow-behavior-change`).
> Behaviour-affecting edits are applied **only where the tool can prove them safe**;
> everything else is reported, not changed. That conservatism is the point: it's what
> makes the automation trustworthy.

## Two different promises

**Formatting is behaviour-preserving by construction.** Indentation, blank lines,
attribute/element order, empty-element shorthand, and CDATA-wrapping a pure-text body
change *bytes*, not *meaning*. `format` is safe and idempotent and never touches
`profile=`.

**Upgrading is semantic, and its guarantee is two-part.** Bumping a tool's `profile=`
can change how Galaxy interprets it. Structurally, the oracle is **XSD validity at
the target profile**: the engine only advances a tool to a profile where it still
validates. Validity is a sound oracle for **structural** changes, not a behaviour
oracle, so a second, behavioural gate caps the walk: the engine computes every
Galaxy-catalogued behaviour change the bump would cross, detects per tool which
actually apply, and **stops below the first applicable `must_fix` change it cannot
provably fix on that tool**. A fix is credited only by execution (applied, then
re-detected); the stop report names the blocking code and links to
[`docs/profile_boundaries.md`](https://github.com/richard-burhans/galaxy-tool-refactor/blob/main/docs/profile_boundaries.md), the per-boundary
what-changed-and-what-to-do reference. Advisory (`consider`) changes are warned
about, never crossed silently. The full argument is
[behavior-gate.md](proofs/behavior-gate.md), part of the published
[rule proofs](proofs/index.md).

## How we know `format` is behaviour-preserving — the audit

"Behaviour-preserving by construction" is a strong claim, so it is **adversarially
audited**, not just asserted. Every fixable rule's behaviour-preservation claim was
stress-tested by independent skeptics that try to *execute a counterexample* breaking
it; each "refuted" verdict was then **re-verified by execution on the current code and
against Galaxy's own source** before being acted on (adversarial agents over-claim).
The result is recorded, rule by rule, in
[`docs/behavior_preservation.md`](https://github.com/richard-burhans/galaxy-tool-refactor/blob/main/docs/behavior_preservation.md) — the proof ledger.

This is an honest process, and it *found real bugs* in formatting rules once assumed
safe — all now fixed, each pinned by a regression fixture so a future change can't
silently reintroduce the break:

- a whitespace-only `<configfile>`/`<command>`/`<token>` body was collapsed, dropping
  template content (**GTR004**); a carriage return was lost through a CDATA wrap
  (**GTR018.1/GTR019.1**); a multi-flag `<option value="-b -h">` `select` was
  single-quoted into one token (**GTR020.1**); a deprecated `interpreter=` rewrite
  duplicated a flag in a mixed-content `<command>` (**GTR016**).

Two of the eight refuted findings turned out to be **over-claims by the audit itself**
— confirmed harmless by reading Galaxy's source (e.g. Galaxy evaluates an output
`<filter>` via `eval(filter.text.strip())`, so a comment-tail clause is dead at runtime
either way). They were documented, not "fixed". The point: the `format` guarantee is
backed by executed evidence and a living ledger, not by assertion.

**Reference and rename operations read Cheetah faithfully.** `find-references` and
`rename-param` resolve `$param` references through a faithful CT3 Cheetah lexer (a base
dependency), so a `$var` inside a `#raw` block, a comment, or behind an escaped `\$` is
classified exactly as Galaxy would — correct for novel tool XML, not a regex
approximation tuned to the current corpus.

## How the boundary is enforced

- By default the profile moves only to the **minimum valid profile at or above
  the tool's baseline**, and only when the tool does not validate where it
  sits; a valid tool is byte-untouched and an undeclared tool stays
  undeclared. An unresolvable `@PROFILE@` baseline fails closed (no advance),
  and the profile is never lowered.
- Under `--modernize` the profile is advanced only to the **newest profile the
  tool structurally reaches**, capped by the **behaviour ceiling** (the newest
  vendored profile below the first applicable, un-fixed `must_fix` change) and
  by the **deployment ceiling** (the newest profile every major public Galaxy
  server runs, vendored from a committed server-poll snapshot; a newer
  declaration could not install everywhere yet). Only an explicit
  `--target-profile` exceeds the deployment ceiling.
- For profile bumps that carry **behaviour-affecting** Galaxy changes, the engine runs
  **per-tool detection** and only applies an automated repair where it can prove the
  change is safe for *that* tool. Where it can't, it **stops and reports** (for
  `must_fix` changes) or warns (for `consider` changes) instead of silently changing
  behaviour; `--modernize --allow-behavior-change` is the explicit opt-out.
- The runtime-gated repairs are exactly as wide as their proofs (widened
  2026-06-10 when source archaeology extended the proofs):
  - **GTR016 (`interpreter=`)** rewrites any non-empty interpreter value — Galaxy
    interpolates it verbatim in every composition form it ever shipped — provided
    the command's first token is a literal script ("bucket A"); a Cheetah-leading
    command is left to detect/warn.
  - **GTR015 (`format="input"`)** fixes the sole-data-input case, top-level or
    conditional/section-nested (qualified `format_source`); multi-input and
    repeat-nested cases are genuinely undecidable and stay reported.
  - **GTR014** guards `format_source`.
- **Imported-macro write-back** is *locate-in-source* (the construct is found in its
  defining file), not provenance-driven. Three consumers exist: the `@PROFILE@` token
  (addressed by name, only when every importer agrees on the target profile); literal
  `format`/`ftype` normalization (the opt-in `normalize-macros`, validity-safe so no
  consensus gate); and **cross-file parameter rename** (`rename-param` rewrites a
  `$param` reference found in an imported macro, gated by sole-ownership within a
  `--repo-root`, or by importer consensus with `--across-importers`). There is **no**
  general mechanism to edit *arbitrary* macro-defined content yet — sizing that residual
  found **0** further tools, so the provenance layer stays deferred
  (`docs/macro_handling_architecture.md`).

## You can see the verdict

`upgrade` reports a **`behavior_preserving`** flag for the bump:

- `true`: it crossed no behaviour-affecting platform change that *applies to this
  tool*, or every applicable breaking change was provably fixed (each credited fix
  is named in a "fixed automatically" note);
- `false`: at least one applies un-fixed (under the modernize walk's gate this
  can only be an advisory `consider` change; breaking changes stop the walk
  instead); look before accepting;
- `null`: undetermined (the profile is a macro token that resolves to no version;
  the upgrade then changes nothing).

Alongside it: `stopped_at` (where the gate capped the walk), `blocking_codes` (the
full review list), and `auto_fixed_codes`. The CLI, library, and MCP server all
surface these, so automation can auto-accept the safe case and escalate the rest,
rather than trusting the bump blindly.

## What this means for you

- Trust `format` unconditionally.
- Treat `upgrade` as "advance to the newest *valid* profile, plus the repairs proven
  safe" — and read its report for anything it chose to flag rather than fix.
- Treat `check` findings as advisory: they're best-practice signals, not failures.

## Authoritative references

- `docs/profile_upgrades.md` — the per-profile upgrade map and the validity-as-oracle
  boundary.
- `galaxy-tool-codemod/docs/decisions.md` — the `canonical_codemods()` /
  `AUTO_UPGRADE_CODEMODS` split, per-tool warning detection, and the soundness limits
  of raw-tree vs macro-expanded detection.
- `docs/macro_handling_architecture.md` — why macro write-back is locate-in-source
  today (the `@PROFILE@` token + literal `format`/`ftype`), and the deferred,
  sized-to-zero provenance layer that would generalise it to arbitrary content.
