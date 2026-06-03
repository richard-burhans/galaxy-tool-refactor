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

### Advisory `check` tier — BUILT (`galaxy-tool-xml-check`, tier 3.5)

The mechanically-detectable subset is now a **read-only `check` (lint) that
reports, never mutates**: the `galaxy-tool-xml-check` package (tier 3.5). Each
check carries an `IUC` code in the shared tier-0.5 registry (parallel to GTX),
is `RuleMeta.detect_only=True`, and is an LBYL query over tier-1's
`ToolDocument`. They surface via the report-only `galaxy-tool-refactor check`
subcommand: `file:line  CODE  message`, marked `(advisory)`. Advisory findings
are **informational** — `check` exits non-zero only on *fixable* (GTX) findings;
`--strict` also fails on advisory. (See `galaxy-tool-xml-check/docs/decisions.md`
D1 and `galaxy-tool-refactor-cli/docs/decisions.md` D2/D3.)

| IUC check | Code | Status |
|---|---|---|
| `<tests>` present | IUC001 | done |
| `<command>` wrapped in CDATA | IUC002 | done |
| tool `id` charset (#10–12) | IUC003 | done |
| `version` PEP 440 or `@…@` macro | IUC004 | done |
| `<requirements>` present | IUC005 | done |
| error handling (`detect_errors`/`<stdio>`) | IUC006 | done |
| EDAM topics/operations or `<xrefs>` | IUC007 | done |
| non-empty `<help>` | IUC008 | done |
| non-empty `<description>` | IUC009 | done |
| `<help>` wrapped in CDATA | IUC010 | done |
| single-quoted Cheetah variables (#36) | IUC011 | **placeholder** (deferred — has signal, see below) |
| `&&` vs a lone `&` (#39) | IUC012 | **placeholder** (deferred — data-backed, ~dead) |

The two `<command>`-CDATA-text heuristics (IUC011/IUC012) are **reserved
placeholders** — registered codes, no-op `detect` — pending tuning to avoid
noise (distinguishing an unquoted Cheetah `$var` or a command-joining `&` from
legitimate shell text inside CDATA is heuristic). For IUC012 this is now settled
with data (`galaxy-tool-xml-check/docs/decisions.md` D3, `scripts.measure
command-lone-amp`): of the 431 tools the crude lone-`&` heuristic flags, the
genuine `cmd1 & cmd2` anti-pattern appears in **1** — the rest are redirections
(`2>&1`), quoted `&` literals (sed/awk), and `|&` pipes. A precise check needs
the M5 shell lexer, not a regex, and would flag ~1 tool, so IUC012 stays
deferred. **IUC011 is the opposite** (`docs/decisions.md` D4, `scripts.measure
command-unquoted-var`): excluding Cheetah directive lines and tracking shell
quotes, a genuinely-unquoted `$var` still fires on **73.2%** of tools (50,380
occurrences) — real signal, on par with shipped advisories (IUC005 57.3%, IUC007
89.6%). IUC011 is worth building; it waits only on a read-only lexer that handles
multi-line quotes and a reporting-shape decision (per-occurrence vs per-tool), not
on "is there signal". For *why* the command text is shell at all (Cheetah →
whitespace-flatten → `#!/bin/sh` + `set -e`), which grounds both heuristics, see
[`galaxy_processing_model.md`](galaxy_processing_model.md). "Profile recency" is
omitted: it overlaps GTX007 / the `upgrade` command.

**Not promising for the human-judgment remainder.** "tests are *meaningful*",
"help is *useful* prose", "names are *descriptive*", "the requirement exists on
conda", "version tracks upstream" — a tool can't reliably judge these; better
served by documentation than an app. (The detect-only checks read the
**un-expanded** tree, so a practice met via a macro — e.g.
`<expand macro="requirements"/>` — can still be flagged; advisory status keeps
that tolerable.)
