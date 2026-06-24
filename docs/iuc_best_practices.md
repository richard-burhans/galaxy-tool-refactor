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

The GTR rule registry (`galaxy-tool-refactor-rules`) spans the fmt and codemod
tiers; see each tier's `docs/decisions.md` for per-rule rationale.

## Bucket 1 — fmt-only (cosmetic): DONE

| IUC practice | Rule | Where |
|---|---|---|
| 4-space indentation | GTR001 | fmt `rule_indent` |
| Blank line between `<tool>` children | GTR003 | fmt `rule_blank_line` — **PARKED** pending IUC input (no external citation; 13.3% corpus adoption), `docs/iuc_conference_questions.md` §4 |
| Empty elements use self-closing shorthand | GTR004 | fmt `rule_empty_element` |
| Attribute values double-quoted | — | fmt serializer (decision D7) |
| Attributes on one line | — | fmt serializer (decision D8) |

Not followed deliberately: the IUC "`label`/`help` may wrap across lines"
exception (fmt keeps attributes on one line, D8). Cheetah indentation inside
`<command>` is **not** touched — it lives inside CDATA, which fmt must not
rewrite (fmt decisions §D3).

## Bucket 2 — codemod (structural): DONE + one new

| IUC practice | Rule | Where |
|---|---|---|
| `<param>` attribute order | GTR002 | codemod `reorder_param_attributes` |
| `<tool>` attribute order (`id, name, version, profile`) | GTR005 | codemod `reorder_tool_attributes` |
| **`<tool>` child-element order** (#52) | **GTR013** | **codemod `reorder_tool_children` (new)** |

**Why element-order is a safe codemod.** The Galaxy schema's `<tool>` content
model is **`xs:all`** (order-free), not `xs:sequence` — verified against
`galaxy-tool-source/.../schema/galaxy-26.1.xsd`. Child-element order is therefore
**not** XSD-enforced: reordering can never regress validity, and the IUC order
is a pure convention this codemod normalises toward. The codemod's only real
invariant is idempotence (proven over the corpus). It joins `CANONICAL_CODEMODS`
so the app's `format` command applies it; the cosmetic formatter re-normalises
the inter-element whitespace afterward. Combined-corpus sweep: of 8,622
validatable tools, 683 (~7.9%) have out-of-order known `<tool>` children;
idempotence holds for all, 0 post-validate failures, 0 crashes (codemod
decisions §17, §53; the count was 4,640 before §53 stopped floating opaque
`<expand>` children to the end).

**Canonical order** (IUC #52): `description, macros, edam_topics,
edam_operations, xrefs, parallelism, requirements, code, stdio, version_command,
command, environment_variables, configfiles, inputs, request_param_translation,
outputs, tests, help, citations`. Tags outside this list (notably an opaque
`<expand macro="…"/>`) are pinned to their original position, never floated to
the end; the known elements sort into the slots around them (codemod decisions
§53).

**Comment safety.** A tool whose `<tool>` root has a free-floating comment is
left untouched: `Cursor.children()` hides comment/PI nodes, so reordering
elements past a comment could silently re-associate it with the wrong element.
The `reorder_children` primitive skips (no-op) in that case rather than risk
corruption (codemod decisions §17).

## Bucket 3 — combination (structural/content): DONE (GTR018/GTR019)

| IUC practice | Code | Status |
|---|---|---|
| `<command>` started/finished with CDATA (#34) | GTR018 | **done** (`WrapCommandCdata`, GTR018.1) |
| `<help>` started/finished with CDATA (#42) | GTR019 | **done** (`WrapHelpCdata`, GTR019.1) |

CDATA-wrapping touches element **content**, not whitespace, so it was deferred at
first for content-change risk (fmt decisions §D3). It is now a **canonical
codemod** — the re-examination resolved the risk: lxml already exposes the
entity-unescaped body, so wrapping is **behaviour-preserving** (only the
serialised bytes change, not the value Galaxy runs/renders), the `set_text(…,
cdata=True)` primitive (codemod §21) does the lexical wrap, and the change is
scoped to the *pure-text* subset (no child nodes, not already wrapped, no `]]>`
terminator). A corpus sweep confirms idempotence + post-apply validity with zero
regressions (2,772 `<command>` / 3,247 `<help>` modified, 0 non-idempotent, 0
post-validate-failed). See codemod `docs/decisions.md` §29.

The advisory **GTR018.2 / GTR019.2** checks (Bucket 4 below) are retained, not
superseded: they flag *any* non-CDATA `<command>` / `<help>`, so after `format`
applies GTR018/GTR019 they continue to cover the rare mixed-content residual the
codemods deliberately skip.

## Bucket 4 — another way (~40 content/semantic practices): advisory only

These cannot be fixed by a whitespace or structural transform — they require a
content or semantic decision. Examples: tests present and meaningful;
help/description prose; PEP 440 version + `@TOOL_VERSION@`/`@VERSION_SUFFIX@`
macros; meaningful tool `id`/`name`; EDAM topics/operations + bio.tools xrefs;
pinned `<requirement>`s; single-quoted Cheetah variables (#36); `&&`-joined
commands (#39); input sanitization; python3 / PEP 8 in embedded scripts;
`detect_errors` or `<stdio>` error handling (#40); `<section>` for advanced
params.

### Advisory `check` tier — BUILT (`galaxy-tool-lint`, tier 3.5)

The mechanically-detectable subset is now a **read-only `check` (lint) that
reports, never mutates**: the `galaxy-tool-lint` package (tier 3.5). Each
check carries an `GTR` code in the shared tier-0.5 registry (parallel to GTR),
is `RuleMeta.detect_only=True`, and is an LBYL query over tier-1's
`ToolDocument`. They surface via the report-only `galaxy-tool-refactor check`
subcommand: `file:line  CODE  message`, marked `(advisory)`. Advisory findings
are **informational** — `check` exits non-zero only on *fixable* (GTR) findings;
`--strict` also fails on advisory. (See `galaxy-tool-lint/docs/decisions.md`
D1 and `galaxy-tool-refactor-cli/docs/decisions.md` D2/D3.)

| check | Code | Status |
|---|---|---|
| `<tests>` present | GTR021 | done |
| `<command>` wrapped in CDATA | GTR018.2 | done (now also fixable — GTR018.1) |
| tool `id` charset (#10–12) | GTR023 | done |
| `version` PEP 440 or `@…@` macro | GTR024 | done |
| `<requirements>` present | GTR025 | done |
| error handling (`detect_errors`/`<stdio>`) | GTR026 | done |
| EDAM topics/operations or `<xrefs>` | GTR027 | done |
| non-empty `<help>` | GTR028 | done |
| non-empty `<description>` | GTR029 | done |
| `<help>` wrapped in CDATA | GTR019.2 | done (now also fixable — GTR019.1) |
| single-quoted Cheetah variables (#36) | GTR020.2 | **done** (read-only command lexer; GTR020.1 auto-quotes the rule's **file** scope — input + output `<data>` files; the text-param half stays advisory, and other single-token kinds (selects/numbers/etc.) are deliberately left alone as out of the rule, codemod §52; see below) |
| `&&` vs a lone `&` (#39) | GTR032 | **check** (shipped — D34; quote/redirect/pipe-aware, joining-class only) |
| package `<requirement>`s pin a version | GTR033 | **done** (275 tools / 661 findings; check D7) |
| unused input `<param>` (general lint, not IUC) | GTR034 | **done** (conservative reference scan; check D11) |

> **Scope note.** The table above is the *IUC-practice* slice of the `check` tier.
> The same tier (`galaxy-tool-lint`) additionally hosts the **planemo-parity
> wave `GTR038`–`GTR102`** (detect-only checks reimplementing the
> `galaxy.tool_util.lint` linters — outputs, inputs, tests, validators, `<help>` RST,
> datatypes — plus a few command-side best-practice checks), bringing the tier to
> **75 checks** total (later additions: GTR095, 2026-06-11, the id/name/version
missing-or-empty trio — the half tier-1 XSD validation can't see; the GTR098/GTR099
datatypes pair, 2026-06-14; the GTR100/GTR101 test-validation bindings via the
`[test-validation]` extra and GTR102 boolean-gates-other-options, D37/D38).
`GTR089` is now a fix/advisory **partition**
> like GTR018/019/020: the deterministically-fixable invalid `<help>` RST is
> auto-repaired by the `GTR089.1` codemod (tier 2, in the default `format`
> pipeline), and the `GTR089.2` advisory reports the residual the repair can't
> reach. Those are a different axis (planemo coverage,
> not the IUC tool-XML practices mapped here) and are tracked in
> [`planemo_linter_parity.md`](planemo_linter_parity.md) +
> `galaxy-tool-lint/docs/decisions.md` D12–D35, not in this document.

The `<command>`-CDATA-text heuristics took different paths: GTR020.2 remains
the advisory residual of its partition, and **GTR032 shipped as a real detector
in check D34** — the D3 deferral's revisit condition (the CT3/M5 lexer) was
met, and the `lone_amp` classifier (quote/redirect/pipe-aware) flags only the
genuine joining class, retiring the false-positive concern this paragraph
recorded.

**Not promising for the human-judgment remainder.** "tests are *meaningful*",
"help is *useful* prose", "names are *descriptive*", "the requirement exists on
conda", "version tracks upstream" — a tool can't reliably judge these; better
served by documentation than an app. (The detect-only checks read the
**un-expanded** tree, so a practice met via a macro — e.g.
`<expand macro="requirements"/>` — can still be flagged; advisory status keeps
that tolerable.)
