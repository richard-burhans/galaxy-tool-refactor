# Soundness — what "safe" guarantees (and what it doesn't)

> **TL;DR.** `format` never changes behaviour. `upgrade` guarantees the result is
> **structurally valid** at the new profile — it does **not** guarantee behaviour is
> identical in general. Behaviour-affecting edits are applied **only where the tool can
> prove them safe**; everything else is reported, not changed. That conservatism is the
> point: it's what makes the automation trustworthy.

## Two different promises

**Formatting is behaviour-preserving by construction.** Indentation, blank lines,
attribute/element order, empty-element shorthand, and CDATA-wrapping a pure-text body
change *bytes*, not *meaning*. `format` is safe and idempotent and never touches
`profile=`.

**Upgrading is semantic, and its guarantee is bounded.** Bumping a tool's `profile=`
can change how Galaxy interprets it. The engine's oracle for an upgrade is **XSD
validity at the target profile** — it will only advance a tool to a profile where the
tool still validates. Validity is a sound oracle for **structural** changes. It is
**not** a behaviour oracle: two structurally-valid tools can behave differently.

## How the boundary is enforced

- The profile is advanced only to the **newest profile the tool structurally reaches**.
- For profile bumps that carry **behaviour-affecting** Galaxy changes, the engine runs
  **per-tool detection** and only applies an automated repair where it can prove the
  change is safe for *that* tool. Where it can't, it **reports** the issue instead of
  silently changing behaviour.
- The runtime-gated repairs are deliberately conservative:
  - **GTR016 (`interpreter=`)** rewrites only the clean "bucket A" shape (a single
    leading literal script token); other shapes are left to detect/warn.
  - **GTR015 (`format="input"`)** fixes only the single-top-level-data-input case.
  - **GTR014** guards `format_source`.
- **Imported-macro write-back** is *locate-in-source* (the construct is found in its
  defining file), not provenance-driven. Two consumers exist: the `@PROFILE@` token
  (addressed by name, only when every importer agrees on the target profile) and literal
  `format`/`ftype` normalization (the opt-in `normalize-macros`, validity-safe so no
  consensus gate). There is **no** general mechanism to edit *arbitrary* macro-defined
  content yet — sizing that residual found **0** further tools, so the provenance layer
  stays deferred (`docs/macro_handling_architecture.md`).

## You can see the verdict

`upgrade` reports a **`behavior_preserving`** flag for the bump:

- `true` — it crossed no behaviour-affecting platform change that *applies to this tool*
  (a clean pass);
- `false` — at least one applies; look before accepting;
- `null` — undetermined (e.g. the profile is expressed as a macro token).

The CLI, library, and MCP server all surface it — so automation can auto-accept the
safe case and escalate the rest, rather than trusting the bump blindly.

## What this means for you

- Trust `format` unconditionally.
- Treat `upgrade` as "advance to the newest *valid* profile, plus the repairs proven
  safe" — and read its report for anything it chose to flag rather than fix.
- Treat `check` findings as advisory: they're best-practice signals, not failures.

## Authoritative references

- `docs/profile_upgrades.md` — the per-profile upgrade map and the validity-as-oracle
  boundary.
- `galaxy-tool-xml-codemod/docs/decisions.md` — the `CANONICAL_CODEMODS` /
  `AUTO_UPGRADE_CODEMODS` split, per-tool warning detection, and the soundness limits
  of raw-tree vs macro-expanded detection.
- `docs/macro_handling_architecture.md` — why macro write-back is locate-in-source
  today (the `@PROFILE@` token + literal `format`/`ftype`), and the deferred,
  sized-to-zero provenance layer that would generalise it to arbitrary content.
