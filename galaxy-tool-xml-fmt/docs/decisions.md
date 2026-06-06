# Decisions

This file records architectural decisions for `galaxy-tool-xml-fmt`,
mirroring the parent repository's `docs/decisions.md` conventions: each
entry cites a date and the rationale for the call.

---

## D1 (2026-05-27) — Rule framework architecture

### Decision

Internally, the formatter is organised as a registry of **rules**. Each
rule is a stateless `ABC` subclass; the active rules are enumerated by
`all_rules()` — a `@cache`d, `meta.order`-sorted tuple (no import-time
registration). Each rule
implements `edits(tree) -> Iterable[Edit]` (named for what it does — it
*describes* edits; the separate `apply_edits()` mutates), where `Edit` is a
discriminated union of frozen dataclasses describing canonical-form
mutations. A single `apply_edits()` function dispatches the edits to
the lxml tree via `match/case` — the only place that mutates the tree
and the only place that needs to honour the CDATA whitespace-only guard.

### Versioning

Stability for CI consumers comes from **pinning** the formatter package
version in their lockfile (`galaxy-tool-xml-fmt==x.y.z`). The formatter
ships exactly one active rule set; there is no `--rules-version` CLI
flag and historical rules do not coexist in the source tree.

Per-rule provenance is recorded as `RuleMeta.since` and
`RuleMeta.until` — both documentary. `until` remains `None` while a
rule is active; it is stamped at retirement in the same commit that
deletes the rule class, purely for changelog purposes.

### Rationale

- **Pin-the-binary versioning** trades the ability to mix-and-match
  rule sets for a dramatically smaller test matrix and zero
  long-lived-historical-rule rot. The community pattern (`black`,
  `ruff`, `prettier`) is well understood by CI authors.
- **ABC over Protocol** for `Rule` reflects that rules are internal,
  enumerated, and tested — explicit inheritance is the right intent
  signal. (`dignified-python` prefers ABC for interface roles.)
- **`register()` stores the class**, not an instance. Rules are
  instantiated per format call. Avoids an import-time allocation and
  leaves a clean path for `__init__`-based config injection if a future
  rule needs it.
- **Instance methods on rules** match the wider Python ecosystem
  convention (pylint, flake8, LibCST, `ast.NodeVisitor`).
- **Edit-list pipeline** (rules return edits, a separate step applies
  them) is testable in isolation, enables a future `--diff` / `--check`
  cleanly, and concentrates the CDATA-safe lxml dance in exactly one
  place.

### Layout

Single package (`galaxy-tool-xml-fmt`) for now. A shared rule-engine
package will be extracted only when a second consumer materialises
(planned: `galaxy-tool-xml-migrate`).

### Reproducibility

Acceptance commands at the time of decision:

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

---

## D2 (2026-05-27) — GTR002: `<param>` attribute ordering

> **Superseded 2026-05-28 — see D10.** This rule has moved to
> `galaxy-tool-xml-codemod` as `ReorderParamAttributes` (a structural
> codemod, not a cosmetic rule). The history below is retained for
> rationale on the priority slots; the implementation now lives in
> tier 2 and is consumed via fmt's CLI when the `[canonical]` extra
> is installed.

### Decision

`<param>` elements have their attributes reordered to the canonical IUC
sequence:

```
name, argument, type, format,
min | truevalue, max | falsevalue, value | checked,
optional, label, help
```

Mutually-exclusive pairs (e.g. `min` vs `truevalue`) share a priority
slot. Any attribute not in the IUC list sorts alphabetically *after*
the known set.

### Source

- IUC Galaxy tool-XML style guide:
  https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html
- Reference implementation: `galaxyproject/galaxy-language-server`'s
  `IUCToolParamAttributeSorter`
  (`server/galaxyls/services/tools/iuc.py`).

### Mechanism

New `Edit` variant `ReorderAttributes(element, names)`. `apply_edits`
clears `element.attrib` and re-sets it in the given order. If `names`
is not a permutation of the current attribute set, the edit is a no-op
(defensive: a rule bug must never silently drop attributes).

The framework's first non-text-content `Edit` — exercises attribute-level
mutation in addition to the existing `SetText` / `SetTail`.

### Notes on related sources

- `galaxy-language-server` itself uses `lxml.etree.indent` directly for
  indentation, plus an IUC param attribute sorter separate from the
  formatter pipeline. We collapse these into one pipeline because
  pin-the-binary versioning makes a single pass sufficient.
- `planemo` has zero XML layout lint checks; it only validates against
  the Galaxy XSD and runs semantic checks (citations, conda, DOIs).

---

## D3 (2026-05-27) — Scope boundary: trivia vs. structure

### Decision

Tier 3 (this package) is responsible for **trivia only**: changes that
the XML 1.0 specification declares *non-significant*. Tier 2 (the
planned codemod) owns anything the XML spec declares *significant*.

Working classification:

| Concern | Spec-significant? | Tier |
|---|---|---|
| Whitespace between elements (indentation, blank lines) | no | **3** |
| Attribute order within an element | no (XML 1.0 §3.1) | **3** |
| Attribute quoting (single vs double) | no | **3** |
| Empty-element shorthand (`<foo/>` vs `<foo></foo>`) | no (lexical) | **3** |
| CDATA section vs escaped text | no (lexical) | **3** (edge) |
| Trailing whitespace inside whitespace-only text/tail | no | **3** |
| **Child element order** | **yes** | **2** |
| **Element name (rename, case-fix)** | **yes** | **2** |
| **Adding/removing elements** | **yes** | **2** |

**Caveat — "whitespace between elements is non-significant" holds only for *element*
content, not *mixed* content** (text interspersed with child elements, e.g.
`See <b>x</b> <i>y</i>` in a `<help>` body), where inter-element whitespace is a
significant word separator. GTR001's `strip()`-guarded tail rewrite (`serializer.py`
`safe_set_tail`) does not distinguish the two, so it *would* reflow such a separator —
a documented behaviour-preservation limitation (GTR001) with **zero corpus incidence**,
left unguarded rather than fixed. See `../../docs/behavior_preservation.md`.

### Source

This mirrors the parent repo's `docs/decisions.md`:

- §3: tier 3 owns trivia preservation; tier 1 ships no serializer.
- §9: tier 2 is "LibCST-shaped structural refactors"; tier 3 is the
  `black`-like formatter.

"LibCST-shaped" is the operative phrase — tier 2 changes what the
document *says*; tier 3 changes how it is *laid out*.

### Practical consequences

- IUC's "top-level element order" SHOULD-rule belongs to tier 2, not
  here. The formatter assumes its input is already in canonical
  element order and just lays it out nicely.
- IUC's "use CDATA for `<command>`/`<help>`" sits on the edge: by the
  principled line it's tier 3 (CDATA is lexical), but it has
  content-changing risk. Deferred until corpus data shows it firing.
- Cheetah quoting and Python/Cheetah PEP8 are out of scope entirely
  — they govern the contents of CDATA, which neither tier of the
  XML toolchain touches.

---

## D4 (2026-05-27) — GTR003: blank line between top-level `<tool>` children, and the `order` field on `RuleMeta`

### Decision

A new rule, **GTR003**, inserts one blank line between consecutive
top-level children of `<tool>`. Nested elements retain GTR001's
single-newline indentation. Editorial: PLAN.md says "one blank between
sibling top-level sections, no blank inside dense leaf sequences" and
no external source prescribes it more concretely (`cite=None`).

### Framework change forced by GTR003

GTR003 must run **after** GTR001 — it overwrites the tail values GTR001
sets. Until this rule, rule order was implicit (import-order, which
`ruff isort` alphabetises). GTR003 broke that: `rule_blank_line` sorts
before `rule_indent` alphabetically, so the blank-line tails were
overwritten by the subsequent indentation pass.

The fix: add `order: int = 100` to `RuleMeta`. `all_rules()` returns
rules sorted by this field (ties broken by registration order; Python's
sort is stable). Lower value runs first.

Current assignments:

| Rule | `order` |
|---|---|
| GTR001 (indentation) | 10 |
| GTR002 (param attr order) | 50 |
| GTR003 (blank line) | 90 |

Default of `100` keeps any future not-yet-classified rule at the end.
Multiples-of-ten leave room to insert between.

### Rationale

The alternative — making the pipeline care about import order, or
pinning the import order with `# noqa: I001` — would couple the rule
ordering to the layout of one file. Explicit `order` keeps each rule
self-describing.

### TDD record

Failing test (`test_blank_line_between_top_level_children`) was written
first; it failed in red on bare `format_tool_document` output, then
again after the rule module existed (registry-order bug, revealed by
the test); passed after the `order` field was added.

---

## D5 (2026-05-27) — GTR004: empty-element shorthand

### Decision

A new rule, **GTR004**, normalises leaf elements whose only content is
whitespace (e.g. `<inputs>\n</inputs>`) to the short form `<inputs/>`.

### Scope

The rule fires only when **all** of the following hold:
- the element has no children (`len(element) == 0`),
- `element.text` is not `None`,
- `element.text` is non-empty (i.e. not `""`),
- `element.text.strip() == ""` (whitespace-only).

Empty-string text (`element.text == ""`) is deliberately **not**
touched. lxml exposes empty CDATA as an empty string on `.text` with no
distinguishing API, so clearing it would silently drop the CDATA
wrapper. The whitespace-vs-empty distinction is the only safe
discriminator.

### Source

Editorial. `cite=None`. PLAN.md says "canonical: `<foo/>` over
`<foo></foo>` when the content model permits"; no external standard
prescribes this explicitly.

### Mechanism

New `Edit` variant `ClearText(element)`. `apply_edits` checks the same
whitespace-only guard `safe_set_text` uses, then assigns
`element.text = None`. Distinct from `SetText`: `SetText("")` leaves an
empty string that lxml serialises as long form, whereas `ClearText`
drops the text entirely and lxml's default `short_empty_elements=True`
emits `<foo/>`.

### Rule order

`order=20` — runs after GTR001 (indent, 10) and before GTR002 (param
attr, 50). Position doesn't actually matter for GTR004 since no other
rule touches leaf-element text, but the slot leaves room for future
text-mutating rules.

### TDD record

Six tests written first. Five passed against bare
`format_tool_document` (lxml's default `short_empty_elements=True`
already handles parsed-empty-as-short, real-text-preserved,
has-children-not-collapsed, CDATA-preserved, and idempotence-on-mixed
input). One failed: whitespace-only-text-collapses. The rule was added
to drive that case green; all six green after.

### Refinement (2026-05-28) — skip non-element nodes

The first corpus sweep (D9) found 12 non-idempotent fixtures, all of
which contained whitespace-only XML comments like `<!--  -->`. lxml's
`tree.iter()` yields `Comment` and `ProcessingInstruction` nodes
alongside elements; they have callable `.tag` (not strings),
`len() == 0`, and `.text` matching the comment body. The rule was
clearing those texts to `None`, which makes lxml drop the comment node
entirely from output — the next format pass then produced different
bytes, and the comment was permanently lost.

GTR004 now skips any node whose `.tag` is not a `str`. The behaviour
is covered by `test_whitespace_only_xml_comment_is_preserved` in
`tests/test_rule_empty_element.py` and by the regression fixtures
replayed under `tests/test_regressions.py`. Post-fix, the 2026-05-28
sweep reports 4,014 / 4,014 idempotent (D9).

---

## D6 (2026-05-28) — GTR005: `<tool>` attribute ordering, and the shared `attribute_ordering` helper

> **Superseded 2026-05-28 — see D10.** This rule and the
> `attribute_ordering` helper have both moved to
> `galaxy-tool-xml-codemod` (the helper to
> `codemods/_attribute_ordering.py`; the rule to
> `codemods/reorder_tool_attributes.py` as `ReorderToolAttributes`).
> The history below is retained for the Galaxy-schema-docs citation
> and the original priority-slot rationale.

### Decision

A new rule, **GTR005**, enforces canonical attribute order on the root
`<tool>` element. Order: `id`, `name`, `version`, `profile`, then
alphabetical for the rest.

### Refactor: shared `attribute_ordering` module

GTR005 has the same shape as GTR002 (priority map + sort within an
element's `attrib`). Rather than duplicate the implementation, the
shared logic moved to
`src/galaxy_tool_xml_fmt/attribute_ordering.py`:

- `canonical_order(names, priority)` — sort names by the priority map,
  falling back to alphabetical for unknowns.
- `reorder_attribute_edits(elements, priority)` — yield
  `ReorderAttributes` edits for any element whose current attribute
  order differs from the canonical.

Each per-element-kind rule (GTR002 for `<param>`, GTR005 for `<tool>`)
defines its own priority table and calls the helper. Future
element-kind orderings plug in the same way.

### Source

The Galaxy 26.1 XSD declares these `<tool>` attributes (required first):
`id`, `name`, `version`, `hidden`, `display_interface`, `tool_type`,
`profile`, `license`, `python_template_version`, `workflow_compatible`,
`URL_method`, `require_login`. The XSD imposes no display order; the
canonical order is convention from the Galaxy schema documentation page,
which consistently shows `id`, `name`, `version`, `profile` as the lead
attributes in its examples.

Cite: `https://docs.galaxyproject.org/en/latest/dev/schema.html`. Weaker
authority than IUC, but it's the only documented source.

### Rule order

`order=55` — runs just after GTR002 (`order=50`). The two are
independent (different element kinds), so the choice is arbitrary; the
explicit slot leaves room to insert between if a future rule's ordering
matters.

### TDD record

Five tests written first. Two passed trivially before the rule existed
(idempotent input had `id` first already; non-tool root is left alone
because no rule touches it). Three failed: reorder-to-canonical,
profile-after-required, and unknown-attributes-alphabetical. All five
passed after the refactor + new rule shipped.

---

## D7 (2026-05-28) — Attribute quoting: always double quotes (policy without a rule)

### Decision

All attribute values in formatter output are double-quoted; any
embedded ``"`` is escaped as ``&quot;``. Single-quoted attributes do
not appear in the output regardless of input.

### Mechanism: no rule needed

This policy is **already enforced by lxml's ``etree.tostring`` default**
— verified 2026-05-28:

| Input attribute value | Serialised output |
|---|---|
| `simple` | `a="simple"` |
| `has "quote"` | `a="has &quot;quote&quot;"` |
| `it's fine` | `a="it's fine"` |
| `has both " and '` | `a="has both &quot; and '"` |

So there is no GTR rule for this. The policy is locked in by
``tests/test_attribute_quoting.py``, which acts as regression
coverage against any future lxml change.

### Source

- IUC tool-XML style guide: SHOULD (implicit in all examples).
- Galaxy schema docs: convention (all examples use double quotes).
- lxml ≥ 5: default behaviour matches the policy.

### Rationale for not adding a rule

A rule that emits no edits when its policy is already satisfied is
noise in the registry. The same outcome is reached by:

1. Documenting the policy here (D7).
2. Letting the serializer's default do the work.
3. Locking the behaviour in with tests.

If a future lxml release changed the default, the tests would fail and
we would write a real rule then. Today, no rule.

### TDD record

Four "characterization" tests written; all four passed on arrival.
Not strict red→green TDD (the behaviour was already correct); the
value here is regression coverage, not implementation drive.

---

## D8 (2026-05-28) — Attributes on one line (policy without a rule)

### Decision

Every element's attributes appear on a single line in formatter output,
regardless of how they were laid out in the source. The IUC SHOULD
allows `label` / `help` to wrap onto their own line "for large XML
elements"; our canonical form is stricter — **no exception, always one
line.**

### Mechanism: no rule needed

This is **already enforced by lxml's ``etree.tostring`` default** —
verified 2026-05-28:

| Input | Output |
|---|---|
| `<param\n    name="x"\n    type="text"/>` (attributes across lines) | `<param name="x" type="text"/>` |
| `<param>` with many attributes | all on one line |
| `attr` whose value contains `\n` | `attr="line1&#10;line2"` (newline becomes an entity, attribute stays on one line) |
| `attr` value with literal tab | `attr="...&#9;..."` (tab becomes `&#9;`) |

So no GTR rule is needed. The policy is locked in by
``tests/test_attribute_line_layout.py``, which includes a strong
no-newline-inside-any-start-tag assertion as a backstop against any
future serializer drift.

### Rationale for the stricter-than-IUC choice

A `black`-style formatter has one canonical output per input. IUC's
"label/help may wrap for large elements" requires a threshold ("how
large is large?") and produces two valid forms for the same content.
Picking one form (always inline) preserves canonicalisation and matches
what lxml does anyway.

### TDD record

Four "characterization" tests written; all four passed on arrival
against bare `format_tool_document`. Same shape as D7: no
implementation needed, value is regression coverage.

---

## D9 (2026-05-28) — Corpus runner, fixture retention, and the first idempotence sweep

> **Gate relaxed 2026-05-29 — see D13.** The "first sweep" cohort below
> (github-only, validated under the latest profile `26.1`: 4,095 parsed / 3,933
> validated) was deliberately bounded while the formatter was unproven. D13
> relaxed it to the combined corpus (github + toolshed) gated on any vendored
> profile; the current swept numbers (9,358 / 8,608) live in
> `../../docs/corpus_format_stats.md`, not here. The numbers below are retained
> as the original cohort.

### Decision

`scripts/corpus_check.py` is the maintainer-facing tool that gates the
formatter's two invariants against the public Galaxy tool corpus:
**no crashes**, and **`format(format(x)) == format(x)`** byte-for-byte.
It mirrors the design of `galaxy-tool-xml/scripts/corpus_check.py` so
the two scripts answer different questions on the same corpus with
familial ergonomics (`--repo`, `--limit`, `--no-stats`).

### Scope

The first sweep is restricted to tools that validate under the
**latest vendored profile** (26.1 as of 2026-05-28). Validity is
established by tier 1's `validate_tool`; non-validating tools are
skipped, not failed. Future sweeps may relax the gate, but starting
with the latest-profile cohort keeps the failure surface bounded to
the tools the formatter is intended for first.

### Mechanism

For each XML file in the cloned corpus:

1. `parse_tool(path)` (skip if recover fails or root tag ≠ `tool`).
2. `validate_tool(path, profile="26.1")` (skip if not valid).
3. Format pass 1 with per-rule edit counts collected.
4. Re-parse the pass-1 bytes; format pass 2 with per-rule edit counts.
5. If `pass1_bytes != pass2_bytes`, retain the tool plus any imported
   `<import>`-referenced macros under `tests/data/regressions/`.

The retention key is the tuple `(source_repo, repo_relative_path)`,
recorded in `tests/data/regressions/PROVENANCE.md`. A second run never
re-retains a tool that's already in PROVENANCE; a new failing tool
adds a row. This differs from the parent's signature-keyed dedup
because the formatter's failure modes are diverse enough that
"signature" undercounts the fixture diversity we want.

### Stats

`docs/corpus_format_stats.md` is regenerated by every full sweep and
shows per-repo counts, the sweep outcome table, per-rule trigger
totals for pass 1 and pass 2, and the failure-signature breakdown.
Partial sweeps (`--limit`, `--repo`) do not regenerate it.

### First sweep result (2026-05-28)

| Cohort | Count |
|---|---:|
| Documents parsed as `<tool>` | 4,190 |
| Validated under profile 26.1 | 4,014 |
| Idempotent | **4,014 (100%)** |
| Non-idempotent | 0 |
| Crashed | 0 |

The initial run before the GTR004 comment-skip refinement (D5) found
12 non-idempotent tools, all variants of the same bug: whitespace-only
XML comments were being clobbered by GTR004. Those fixtures are
retained as permanent regression coverage (`tests/test_regressions.py`)
even though they now pass — they encode the bug class so we don't
regress it.

**Refreshed 2026-05-29** (after deprecated-directory tools were
excluded from the corpus — the discovery filter is
`galaxy-tool-xml/docs/decisions.md` §6, refreshed measurements §10):
the re-sweep parses **4,095** `<tool>` documents, of which
**3,933** validate under 26.1 and are all idempotent (0 non-idempotent,
0 crashed). One of the 12 retained fixtures (`tools-galaxyp__dia_umpire`)
originated from a `deprecated/` directory and was dropped, leaving **11**
regression fixtures; the remaining 11 still pass.

### Reproducibility

Sweep commit pinned per-repo via `git rev-parse HEAD` and surfaced in
`docs/corpus_format_stats.md`. Re-running on a different corpus
snapshot will diff the per-repo `Version` column.

```sh
uv run python -m scripts.corpus_check fmt
```

### Rationale

- **Gate on validation, not parsing.** A formatter that runs over
  tools that don't validate amplifies noise; the latest-profile cohort
  is the slice we're actually shipping for. Future relaxations are
  cheap (drop the `--profile` flag's default).
- **Retain all failing tools, not one per signature.** Tier-3 bugs
  are about laying out content; the same bug class can have multiple
  surface forms (different containers, different surrounding
  whitespace), and replaying every one in `pytest` is cheap.
- **Per-rule edit stats are surface-only.** A `SetText` whose target
  value equals the existing one is still a "trigger" by edit count,
  even though the tree is unchanged. The byte comparison is the
  authoritative did-it-change signal; the per-rule counts answer
  "which rule was even invoked".



---

## D10 (2026-05-28) — Structural rules moved to tier 2; fmt becomes cosmetic-only library + canonical-by-default CLI

> **Partially superseded 2026-05-29 — see D12.** The library half stands
> (fmt's library is cosmetic-only and codemod-free). The CLI half was
> reversed: the `[canonical]` extra was removed and fmt's CLI reverted to
> cosmetic-only; cross-tier orchestration moved to the tier-4 app
> (`galaxy-tool-refactor-cli`). Read the "CLI" claims below as historical.

### Decision

The two structural rules (former **GTR002** `<param>` attribute order
and former **GTR005** `<tool>` attribute order) have been deleted from
this package and re-implemented in `galaxy-tool-xml-codemod` as the
`ReorderParamAttributes` and `ReorderToolAttributes` codemods. They
are exposed via that package's `CANONICAL_CODEMODS` tuple.

- **`format_tool_document` is now cosmetic-only.** It no longer imports
  `galaxy-tool-xml-codemod`, runs only the three remaining cosmetic
  rules (GTR001 indent, GTR003 blank line, GTR004 empty-element
  shorthand), and works with just `galaxy-tool-xml + galaxy-tool-xml-fmt`
  installed.
- **`galaxy-tool-xml-codemod` is an optional `[canonical]` extra** of
  this package, not a hard dependency. Declared as
  `[project.optional-dependencies] canonical = ["galaxy-tool-xml-codemod"]`.
- **The CLI orchestrates both layers.** `galaxy-tool-xml-fmt`'s CLI
  uses `importlib.util.find_spec` (LBYL) to detect the optional
  package and, when present, runs `CANONICAL_CODEMODS` before fmt's
  cosmetic rules. When absent, the CLI emits a one-line stderr hint
  and proceeds cosmetic-only.

### Alternative

Keep both rule classes in fmt with no tier-2 layer (the pre-2026-05-28
state). Or, hard-depend on `galaxy-tool-xml-codemod` (the
2026-05-28-morning state, since reverted).

### Rationale

The three-tier architecture in `galaxy-tool-xml/docs/decisions.md` §9
positions the three packages as **independent siblings** of tier 1,
not a linear dependency chain. A hard fmt→codemod dependency
collapsed that, forcing every fmt consumer to pull in the
structural-refactor framework even when they only wanted cosmetic
formatting. The optional-extra split honours the original three-tier
intent: each tier is consumable standalone; the project's preferred
"format my tool" workflow is the orchestration the CLI performs, not
a library contract.

See also `galaxy-tool-xml-codemod/docs/decisions.md` §9 for the
mirror entry on the codemod side, and §10 for the
`MANDATORY_CODEMODS` → `CANONICAL_CODEMODS` rename that landed at the
same time.

### TDD record

- `test_format_tool_document_does_not_import_codemod_package`
  asserts the library import path stays codemod-free (no
  `galaxy_tool_xml_codemod` modules loaded after
  `format_tool_document`).
- `test_cli_runs_canonical_codemods_when_extra_is_installed` pins
  that the CLI does run `ReorderParamAttributes` in the workspace
  install (the codemod package is always present under `uv sync`).
- `test_cli_does_not_print_cosmetic_only_hint_when_extra_is_installed`
  pins the absence of the stderr hint in the workspace dev path.

### Reproduction

```sh
uv sync
uv run --package galaxy-tool-xml-fmt pytest galaxy-tool-xml-fmt/tests/test_framework.py
uv run --package galaxy-tool-xml-fmt pytest galaxy-tool-xml-fmt/tests/test_cli.py
```

## D11 (2026-05-29) — `RuleMeta` extracted to the shared `galaxy-tool-refactor-rules` package

### Decision

The `RuleMeta` descriptor, previously defined in this package's `rules.py`, now
lives in a new dependency-free package `galaxy-tool-refactor-rules` (tier 0.5).
`rules.py` imports it; the three rule modules import it from there. The `Rule`
ABC, the `Edit` union, and `apply_edits` stay here — they are lxml/edit-specific
and not shared.

This realises §D1 §Layout's plan ("a shared rule-engine package will be
extracted only when a second consumer materialises"): the codemod tier is now
that consumer, carrying the same `meta: ClassVar[RuleMeta]` on every codemod so
the GTR registry spans both tiers (GTR001–GTR012). The fmt stat page's new
"Rule reference" table is generated from that cross-tier metadata.

### Rationale

Only the metadata is genuinely shared, and it is pure data (no lxml). Putting it
in a zero-dependency package lets both fmt and codemod depend on it without
either depending on the other — the tier independence from §D10 is preserved,
because the shared package is a primitive like tier 1, not the structural
framework. fmt gains a hard dependency on `galaxy-tool-refactor-rules`, which is
fine: it is metadata-only and does not pull in codemod.

### Reproduction

```sh
uv sync
uv run --package galaxy-tool-xml-fmt pytest galaxy-tool-xml-fmt/tests/test_framework.py
uv run --package galaxy-tool-refactor-rules pytest galaxy-tool-refactor-rules/tests/
```

## D12 (2026-05-29) — fmt CLI reverts to cosmetic-only; orchestration moves to the app tier

### Decision

This reverses the CLI half of §D10. The orchestration that ran tier-2 codemods
before fmt's cosmetic rules has moved to a new top-level app tier
(`galaxy-tool-refactor-cli`, the `galaxy-tool-refactor` CLI). Consequently:

- **`galaxy-tool-xml-fmt`'s CLI is cosmetic-only again.** `cli.py` no longer
  detects or runs `CANONICAL_CODEMODS`; it parses → `format_tool_document` →
  writes. The cosmetic-only startup hint is gone (there is nothing optional to
  hint about).
- **The `[canonical]` extra is removed**, along with fmt's `galaxy-tool-xml-codemod`
  workspace source. fmt now depends only on `galaxy-tool-refactor-rules` and
  `galaxy-tool-xml`.
- **A shared CLI engine was extracted** to `cli_support.py` (public): file
  walking, `--check` / `--diff` / `--quiet`, drift detection, per-file error
  isolation, and the summary, parameterised by a transform
  (`Callable[[ToolDocument], TransformOutcome]`) and action verbs. Both this
  package's cosmetic CLI and the app's `format`/`upgrade` commands use it, so the
  plumbing is written once.

The library (`format_tool_document`) was already codemod-free under §D10 and is
unchanged; only the CLI surface moved.

### Rationale

§D10 made fmt's CLI the canonical-by-default orchestrator via an optional extra.
Splitting `upgrade` out from `format` (see
`galaxy-tool-refactor-cli/docs/decisions.md` §D1) needed a home that could both
run codemods *and* serialize — i.e. a tier above fmt. Once that app tier exists,
it is the natural single home for *all* orchestration, so fmt returns to being a
single-purpose cosmetic formatter and the optional-extra machinery is no longer
needed. The three-tier independence §D10 protected is preserved (fmt's library
still doesn't depend on codemod); orchestration simply lives one tier up.

### TDD record

- The two §D10 CLI tests (`…runs_canonical_codemods…`,
  `…cosmetic_only_hint…`) were removed; `galaxy-tool-xml-fmt`'s CLI test now
  asserts it does *not* reorder attributes (that's the app's `format` command).
- Canonical-format and upgrade behaviour is covered by the app's
  `galaxy-tool-refactor-cli/tests/test_cli.py`.

### Reproduction

```sh
uv sync
uv run --package galaxy-tool-xml-fmt      pytest galaxy-tool-xml-fmt/tests/test_cli.py
uv run --package galaxy-tool-refactor-cli pytest galaxy-tool-refactor-cli/tests/
```

## D13 (2026-05-29) — fmt corpus sweep relaxed: any-valid gate + combined source

### Decision

The `corpus_check fmt` and `corpus_check rules` sweeps no longer restrict to the
latest-profile / github-only cohort:

- **Validity gate (`_fmt_in_scope`)**: a tool is in scope if it validates under
  **any** vendored profile (`newest_valid_profile(...) is not None`), not only
  the latest. `--profile X` still pins the old single-profile gate. Cosmetic
  rules are profile-agnostic, so excluding older-but-valid tools only narrowed
  coverage; this executes §D9's stated "future sweeps may relax the gate."
- **Source**: the `fmt` subcommand gained `--source` (github | toolshed |
  combined) and both `fmt` and `rules` now **default to `combined`** (github +
  toolshed, sha256-deduplicated) — matching the `validate` sweep's coverage. The
  fmt sweep now sha256-dedups like the others.

The gate stays validity-based (never-valid XML is still excluded — §D9's
anti-noise point); only the latest-only and github-only restrictions lifted.

### Rationale

§D9 deliberately started with the latest-profile, github cohort to "keep the
failure surface bounded" while the formatter was unproven. It is now proven
(merged, the per-rule isolation sweep found zero failures), so broadening to the
full validating corpus is the planned next step and the strongest idempotence QA
— it exercises the formatter on the older, messier toolshed tools for the first
time. `_fmt_in_scope` is shared by both fmt paths (one fmt-population policy);
this is distinct from the per-tool *profile-selection* policies that
`project-corpus-check-filters` says not to unify.

### Reproduction

```sh
uv run python -m scripts.corpus_check fmt               # combined, any-valid
uv run python -m scripts.corpus_check fmt --source github --profile 26.1  # old cohort
uv run --package galaxy-tool-xml-fmt pytest galaxy-tool-xml-fmt/tests/test_corpus_check.py
```

## D14 (2026-05-30) — Cosmetic detect (lint) phase: `detect_tool_document` (PR2)

**Date:** 2026-05-30. Reproduced-by: `uv run --package galaxy-tool-xml-fmt
pytest galaxy-tool-xml-fmt/tests/test_detect.py`; corpus gate `uv run python -m
scripts.corpus_check fmt`.

PR2 of the detect/fix rule-split effort (tier-2 framework landed in PR1 — see
`galaxy-tool-xml-codemod/docs/decisions.md` §19, `galaxy-tool-refactor-rules`
D2 for the shared `Violation` type; the effort (PR1–5) merged in #15).

- **What we chose.** A new `detect.py` exposes `detect_tool_document(document)
  -> list[Violation]`, the non-mutating counterpart to `format_tool_document`.
  It reports one `Violation` per node whose **net** cosmetic whitespace the
  pipeline would change, located on the source tree (real line numbers) and
  attributed to the owning rule's `meta.code` / `meta.summary`.
- **Why net-diff, not per-edit.** fmt rules emit *unconditional* overlapping
  rewrites — GTR001 sets every child's tail, GTR003 then overrides top-level
  `<tool>` child tails (blank line). So an individual `Edit` "changing the tree"
  does **not** mean the document is non-canonical: on an already-canonical file,
  GTR001 wants to strip GTR003's blank line (a change to the intermediate state)
  that GTR003 immediately re-adds. Mapping changing edits to violations
  therefore false-positives on canonical files (empirically: 2 phantom GTR001
  findings on a canonical 3-section tool). Detection instead formats a throwaway
  copy, records the **last** rule to touch each node's whitespace (the owner),
  and diffs the formatted copy against the original — net-zero churn is silent,
  so a canonical document reports nothing, exact parity with `format`.
- **Implementation notes.** (1) lxml hands out a fresh Python proxy per
  `.iter()`, so `id()` is unstable across calls; detect captures each node list
  once and reuses those proxies (live views over shared nodes). (2) Comment / PI
  nodes are included, not just elements: GTR001/GTR003 rewrite a comment's tail
  (a blank line after a top-level comment is a real change), so omitting them
  let detect miss changes the pipeline makes — caught by the corpus parity gate
  on bimib/cobraxy (now a regression test).
- **Corpus parity gate.** `corpus_check fmt` now asserts the invariant
  `bool(detect_tool_document(doc)) == (format changes net bytes)` per tool and
  retains any `detect-parity-mismatch` as a finding. Result over the combined
  corpus: **8,608 tools swept, 8,608 idempotent, 0 non-idempotent, 0 parity
  mismatches.**
- **Tier independence preserved.** `Violation` comes from tier 0.5; detect adds
  no dependency on the codemod tier. No CLI yet — the report-only `check`
  subcommand is PR3.

## D15 (2026-05-30) — Per-rule subset seams + `TransformOutcome.notes`

**Date:** 2026-05-30. Reproduced-by: `uv run --package galaxy-tool-xml-fmt
pytest galaxy-tool-xml-fmt/tests/test_subset.py`.

Support for the rule-selection facade (`galaxy-tool-refactor-registry`, tier 3.6
— see its `docs/decisions.md`), which lets a user pick a preset or
`--select`/`--ignore` individual rules.

- **`format_tool_document_subset(document, *, rule_classes)` and
  `detect_tool_document_subset(document, *, rule_classes)`.** The existing
  whole-pipeline `format_tool_document` / `detect_tool_document` now delegate to
  these with `all_rules()`. The subset runs the chosen rules **in `meta.order`**
  regardless of the order passed (the whitespace rules are order-sensitive: see
  D14), so the facade can hand a single rule or any subset and get deterministic
  output. The net-diff attribution logic for detect stays here (its owning tier),
  not reconstructed in the facade.
- **Coherence is the caller's job for arbitrary subsets.** The shipped presets
  always include the full GTR001/GTR003/GTR004 trio (coherent, idempotent); a
  lone-rule selection (`--select GTR001`) can leave non-canonical trivia a
  coherent subset would have cancelled. Documented, not prevented.
- **`TransformOutcome.notes: tuple[str, ...]`** replaced the old singular
  `note: str | None`. One per-file notes channel carries both the upgrade summary
  line and any advisory (report-only, `detect_only`) findings a selection included
  but that never mutate the file (decision Q3: report, don't fix). The per-file
  echo prints each `notes` line; fmt's own CLI passes none, so its behaviour is
  unchanged. Notes also surface on byte-unchanged files in plain write mode so a
  `strict`-preset advisory finding is not swallowed when nothing is reformatted.

## D16 (2026-05-30) — Formatting macro files (kind-aware rules)

**Date:** 2026-05-30. Phase 2 (first step) of the macro-aware effort.
Reproduced-by: `uv run --package galaxy-tool-xml-fmt pytest
galaxy-tool-xml-fmt/tests/test_subset.py galaxy-tool-xml-fmt/tests/test_cli.py`.

The fmt tier now formats macro-library files (`<macros>` root), not just tools.

- **Rules filter by document kind via `RuleMeta.applies_to`** (tier-0.5 D3).
  GTR001 (indent) and GTR004 (empty-element shorthand) are widened to
  `{"tool","macro"}` — generic XML cosmetics; GTR003 (blank line between `<tool>`
  sections) stays tool-only, so a macro file is *not* given tool-shaped blank
  lines. `format.rules_for_kind(kind)` returns the applicable subset;
  `format_macro_document(MacroDocument)` is the `<macros>` counterpart to
  `format_tool_document` (both now route through a private `_apply_rules` over
  the kind's rules). `format_tool_document` is unchanged in output (all current
  rules apply to tools) but is now future-proof against macro-only rules.
- **`cli_support` gained an optional `macro_transform`** and an `is_macros_root`
  byte pre-check (sibling of `is_tool_root`, both via `_root_opens`). When a
  caller passes `macro_transform`, `<macros>`-root files are loaded with
  `load_macros` and formatted; without it they are skipped — so the **app CLI is
  unchanged** (it passes no `macro_transform` and still skips macro files) while
  the **cosmetic `galaxy-tool-xml-fmt` CLI** opts in and formats both kinds. The
  app's bundle-aware macro handling (tool + its imports together, shared-skip) is
  a later step.
- **`detect_macro_document`** (added with the app-tier macro `format`/`check`
  step) is the `<macros>` counterpart to `detect_tool_document`, running the
  macro-applicable cosmetic rules net-diff; the shared net-diff core is factored
  into `_detect_over_tree`. The app `check` uses it to report macro cosmetic
  drift. The import-graph **bundle + shared-skip** remains deferred to the
  Phase-3 content-edit work (see `galaxy-tool-refactor-cli/docs/decisions.md` §D5).
- **Corpus idempotence — same evidence tools have** (2026-05-30, combined
  corpus; Reproduced-by: `uv run python -m scripts.measure
  macro-fmt-idempotence`). Of **1,177** distinct `<macros>`-root files (1
  unparseable under strict load), **1,176 (99.9%) would change** under
  `format_macro_document` — i.e. almost no macro file is currently canonical, so
  formatting them is worthwhile — and **all 1,176 are idempotent (0
  non-idempotent)**, matching the tool-file guarantee in §D9/§D13. This backs
  formatting macro files with the same corpus QA tools already have.

## D17 (2026-06-02) — `cli_support` loads each file by path, not bytes (source_path fix)

**Date:** 2026-06-02. Reproduced-by: `uv run --package galaxy-tool-refactor-cli
pytest galaxy-tool-refactor-cli/tests/test_cli.py -k imported_macros`. Surfaced by
the macro-handling audit (`../../docs/macro_handling_architecture.md` §4.3).

- **The bug.** `cli_support._transform_file` loaded the per-file document from the
  bytes it had already read (`load_tool(original)`), so the document's
  `source_path` was `None` even though the filesystem `path` was in scope. Tier-1
  macro expansion resolves `<import>` against `source_path.parent`; with no
  `source_path` it resolves against the throwaway `TemporaryDirectory` the expander
  serialises into (ARCHITECTURE.md §10) and silently falls back to the **raw**
  (un-expanded) tree. So the app CLI's `format`/`upgrade` demoted every
  imported-macro tool (**47.8%** of the corpus carry an `<import>` —
  `scripts.measure macro-topology`, "imports a file") to a raw-tree view:
  `<expand>` nodes
  left the tree XSD-invalid → `newest_valid_profile` returned `None` → `upgrade`
  found nothing to do and the run spewed "macro expansion failed: No such file"
  for every validity/detection call. (The corpus sweeps never caught it because
  `corpus_check` loads from path; only the CLI hit the bytes path.)
- **The fix.** Load from `path` (`load_tool(path)` / `load_macros(path)`), so the
  document records its `source_path` and imports resolve against the file's own
  directory. `original` still drives drift detection in `_process_file`; the
  re-read is negligible. This brings the CLI in line with the path-loaded
  behaviour the corpus sweeps already validate, rather than introducing new
  behaviour. Verified end-to-end: `galaxy-tool-refactor upgrade --check` on a real
  imported-macro tool now reports the correct `profile X→latest` bump (was: no
  change + expansion-failure spam).
- **Cosmetic-CLI safe.** fmt's own cosmetic CLI doesn't expand macros, so the only
  effect there is a harmless populated `source_path`; the 90-test fmt suite and the
  app-CLI suite are unchanged.

## D18 (2026-06-06) — GTR004: don't collapse whitespace-only content-bearing leaves

**Date:** 2026-06-06. Behavior-preservation finding GTR004
(`../../docs/behavior_preservation.md`). Reproduced-by: `uv run --package
galaxy-tool-xml-fmt pytest galaxy-tool-xml-fmt/tests/test_rule_empty_element.py`.

- **The bug.** D5's empty-element rule clears any whitespace-only leaf `.text`
  (`<inputs>\n  </inputs>` → `<inputs/>`). But for a few elements the `.text` is
  *content*, not layout: Galaxy reads a `<configfile>` body verbatim
  (`fill_template`, `strip=False`) as the template, and `<command>` / `<token>`
  bodies are likewise runtime/expansion payload. A whitespace-only such body
  (`<configfile><![CDATA[   ]]></configfile>`) was collapsed to `<configfile/>`,
  silently dropping the payload — a behaviour change the static-validity oracle
  can't see (the result stays XSD-valid). The adversarial behavior-preservation
  audit refuted the rule's "behaviour-preserving for any whitespace-only leaf" claim.
- **The fix.** The rule skips a denylist `_CONTENT_BEARING_TAGS = {command,
  configfile, token}`. `<help>` is deliberately **excluded** from the denylist:
  whitespace-only help renders empty either way, so the opinionated formatter keeps
  tidying it to `<help/>` — the guard stays surgical rather than over-preserving all
  CDATA whitespace (a measured 37 corpus `<help>` bodies would otherwise stop being
  tidied).
- **Corpus impact.** A handful of degenerate whitespace-only `<command>` / `<token>`
  bodies (≈5 in a 13k-tool scan) are now conservatively preserved instead of
  collapsed; idempotence and validity unaffected (corpus `fmt` sweep). Pinned by
  `test_whitespace_only_content_bearing_text_is_preserved` (+ the `<help>`-still-
  collapses companion).
