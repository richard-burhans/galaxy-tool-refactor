# Galaxy IUC `tool_xml` best-practices — coverage map

Cross-tier reference: how the [Galaxy IUC tool_xml best-practices][iuc] map onto
this framework's automation. Every practice falls into one of four buckets:

1. **fmt-only** — cosmetic whitespace/trivia; the formatter tier handles it.
2. **codemod** — a structural tree change; the codemod tier handles it.
3. **combination** — needs both a structural/content change and a cosmetic
   reflow.
4. **another way** — not safely automatable by a whitespace or structural
   transform; needs a content/semantic decision (human, or at most a read-only
   advisory check).

[iuc]: https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html

The GTX rule registry (`galaxy-tool-refactor-rules`) spans the fmt and codemod
tiers; see each tier's `docs/decisions.md` for per-rule rationale.

## Bucket 1 — fmt-only (cosmetic): DONE

| IUC practice | Rule | Where |
|---|---|---|
| 4-space indentation | GTX001 | fmt `rule_indent` |
| Blank line between `<tool>` children | GTX003 | fmt `rule_blank_line` |
| Empty elements use self-closing shorthand | GTX004 | fmt `rule_empty_element` |
| Attribute values double-quoted | — | fmt serializer (decision D7) |
| Attributes on one line | — | fmt serializer (decision D8) |

Not followed deliberately: the IUC "`label`/`help` may wrap across lines"
exception (fmt keeps attributes on one line, D8). Cheetah indentation inside
`<command>` is **not** touched — it lives inside CDATA, which fmt must not
rewrite (fmt decisions §D3).

## Bucket 2 — codemod (structural): DONE + one new

| IUC practice | Rule | Where |
|---|---|---|
| `<param>` attribute order | GTX002 | codemod `reorder_param_attributes` |
| `<tool>` attribute order (`id, name, version, profile`) | GTX005 | codemod `reorder_tool_attributes` |
| **`<tool>` child-element order** (#52) | **GTX013** | **codemod `reorder_tool_children` (new)** |

**Why element-order is a safe codemod.** The Galaxy schema's `<tool>` content
model is **`xs:all`** (order-free), not `xs:sequence` — verified against
`galaxy-tool-xml/.../schema/galaxy-26.1.xsd`. Child-element order is therefore
**not** XSD-enforced: reordering can never regress validity, and the IUC order
is a pure convention this codemod normalises toward. The codemod's only real
invariant is idempotence (proven over the corpus). It joins `CANONICAL_CODEMODS`
so the app's `format` command applies it; the cosmetic formatter re-normalises
the inter-element whitespace afterward. Combined-corpus sweep: of 8,607
validatable tools, 4,640 (~54%) have out-of-order `<tool>` children;
idempotence holds for all, 0 post-validate failures, 0 crashes (codemod
decisions §17).

**Canonical order** (IUC #52): `description, macros, edam_topics,
edam_operations, xrefs, parallelism, requirements, code, stdio, version_command,
command, environment_variables, configfiles, inputs, request_param_translation,
outputs, tests, help, citations`. Tags outside this list keep their relative
position after the known ones.

**Comment safety.** A tool whose `<tool>` root has a free-floating comment is
left untouched: `Cursor.children()` hides comment/PI nodes, so reordering
elements past a comment could silently re-associate it with the wrong element.
The `reorder_children` primitive skips (no-op) in that case rather than risk
corruption (codemod decisions §17).

## Bucket 3 — combination (structural/content + cosmetic reflow): not done

| IUC practice | Status |
|---|---|
| `<command>` started/finished with CDATA (#34) | Deferred |
| `<help>` started/finished with CDATA (#42) | Deferred |

CDATA-wrapping touches element **content**, not whitespace, and is deferred for
content-change risk (fmt decisions §D3). It is a true combination — a lexical
wrap (codemod-ish) plus a cosmetic reflow (fmt) — and would only ever apply to
elements not already wrapped. Declined for now by the maintainer.

## Bucket 4 — another way (~40 content/semantic practices): advisory only

These cannot be fixed by a whitespace or structural transform — they require a
content or semantic decision. Examples: tests present and meaningful;
help/description prose; PEP 440 version + `@TOOL_VERSION@`/`@VERSION_SUFFIX@`
macros; meaningful tool `id`/`name`; EDAM topics/operations + bio.tools xrefs;
pinned `<requirement>`s; single-quoted Cheetah variables (#36); `&&`-joined
commands (#39); input sanitization; python3 / PEP 8 in embedded scripts;
`detect_errors` or `<stdio>` error handling (#40); `<section>` for advanced
params.

### Could these be apps, like `galaxy-tool-refactor-cli`?

Reasoning (maintainer asked; not yet built):

- **Promising for the mechanically-*detectable* subset (~12).** A **read-only
  `check` (lint) that *reports*, never mutates** is a clean fit: presence of
  `<tests>`; `<command>`/`<help>` wrapped in CDATA; meaningful `id` charset
  (#10–12); profile recency; `&&` vs a lone `&`; single-quoted Cheetah
  (heuristic); version contains a `@TOOL_VERSION@` macro / parses as PEP 440;
  `<requirements>` present; `detect_errors`-or-`<stdio>` present; EDAM/xrefs
  present; non-empty help/description. All are LBYL tree queries reusing tier-1
  (`ToolDocument`, `newest_valid_profile`, the typed model) — exactly the
  inputs tier-1 already exposes.
- **Not promising for the human-judgment remainder.** "tests are *meaningful*",
  "help is *useful* prose", "names are *descriptive*", "the requirement exists
  on conda", "version tracks upstream" — a tool can't reliably judge these. At
  most thin, explicitly low-confidence heuristics (e.g. "help looks short");
  better served by documentation than an app.
- **Proposed architecture (if built).** Advisory checks carry their own IUC
  codes in the shared tier-0.5 `galaxy-tool-refactor-rules` registry (parallel
  to GTX), live in a small check library, and surface via a **report-only
  `check` subcommand on `galaxy-tool-refactor-cli`** (diagnostics: `file:line`,
  code, severity, message; non-zero exit on findings). It would **not** reuse
  fmt's transform/write `cli_support` engine (that path is built around
  rewrite + drift detection); a report path is a separate, smaller engine. This
  keeps the mutating tiers (codemod/fmt) cleanly separated from the advisory
  tier. Status: designed, not implemented — awaiting a decision.
