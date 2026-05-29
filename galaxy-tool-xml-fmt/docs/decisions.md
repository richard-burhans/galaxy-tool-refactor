# Decisions

This file records architectural decisions for `galaxy-tool-xml-fmt`,
mirroring the parent repository's `docs/decisions.md` conventions: each
entry cites a date and the rationale for the call.

---

## D1 (2026-05-27) — Rule framework architecture

### Decision

Internally, the formatter is organised as a registry of **rules**. Each
rule is a stateless `ABC` subclass; rules are registered at module-import
time via a `@register` decorator and listed by `all_rules()`. Each rule
implements `apply(tree) -> Iterable[Edit]`, where `Edit` is a
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

## D2 (2026-05-27) — GTX002: `<param>` attribute ordering

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

## D4 (2026-05-27) — GTX003: blank line between top-level `<tool>` children, and the `order` field on `RuleMeta`

### Decision

A new rule, **GTX003**, inserts one blank line between consecutive
top-level children of `<tool>`. Nested elements retain GTX001's
single-newline indentation. Editorial: PLAN.md says "one blank between
sibling top-level sections, no blank inside dense leaf sequences" and
no external source prescribes it more concretely (`cite=None`).

### Framework change forced by GTX003

GTX003 must run **after** GTX001 — it overwrites the tail values GTX001
sets. Until this rule, rule order was implicit (import-order, which
`ruff isort` alphabetises). GTX003 broke that: `rule_blank_line` sorts
before `rule_indent` alphabetically, so the blank-line tails were
overwritten by the subsequent indentation pass.

The fix: add `order: int = 100` to `RuleMeta`. `all_rules()` returns
rules sorted by this field (ties broken by registration order; Python's
sort is stable). Lower value runs first.

Current assignments:

| Rule | `order` |
|---|---|
| GTX001 (indentation) | 10 |
| GTX002 (param attr order) | 50 |
| GTX003 (blank line) | 90 |

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

## D5 (2026-05-27) — GTX004: empty-element shorthand

### Decision

A new rule, **GTX004**, normalises leaf elements whose only content is
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

`order=20` — runs after GTX001 (indent, 10) and before GTX002 (param
attr, 50). Position doesn't actually matter for GTX004 since no other
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

GTX004 now skips any node whose `.tag` is not a `str`. The behaviour
is covered by `test_whitespace_only_xml_comment_is_preserved` in
`tests/test_rule_empty_element.py` and by the regression fixtures
replayed under `tests/test_regressions.py`. Post-fix, the 2026-05-28
sweep reports 4,014 / 4,014 idempotent (D9).

---

## D6 (2026-05-28) — GTX005: `<tool>` attribute ordering, and the shared `attribute_ordering` helper

> **Superseded 2026-05-28 — see D10.** This rule and the
> `attribute_ordering` helper have both moved to
> `galaxy-tool-xml-codemod` (the helper to
> `codemods/_attribute_ordering.py`; the rule to
> `codemods/reorder_tool_attributes.py` as `ReorderToolAttributes`).
> The history below is retained for the Galaxy-schema-docs citation
> and the original priority-slot rationale.

### Decision

A new rule, **GTX005**, enforces canonical attribute order on the root
`<tool>` element. Order: `id`, `name`, `version`, `profile`, then
alphabetical for the rest.

### Refactor: shared `attribute_ordering` module

GTX005 has the same shape as GTX002 (priority map + sort within an
element's `attrib`). Rather than duplicate the implementation, the
shared logic moved to
`src/galaxy_tool_xml_fmt/attribute_ordering.py`:

- `canonical_order(names, priority)` — sort names by the priority map,
  falling back to alphabetical for unknowns.
- `reorder_attribute_edits(elements, priority)` — yield
  `ReorderAttributes` edits for any element whose current attribute
  order differs from the canonical.

Each per-element-kind rule (GTX002 for `<param>`, GTX005 for `<tool>`)
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

`order=55` — runs just after GTX002 (`order=50`). The two are
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

So there is no GTX rule for this. The policy is locked in by
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

So no GTX rule is needed. The policy is locked in by
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

The initial run before the GTX004 comment-skip refinement (D5) found
12 non-idempotent tools, all variants of the same bug: whitespace-only
XML comments were being clobbered by GTX004. Those fixtures are
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

### Decision

The two structural rules (former **GTX002** `<param>` attribute order
and former **GTX005** `<tool>` attribute order) have been deleted from
this package and re-implemented in `galaxy-tool-xml-codemod` as the
`ReorderParamAttributes` and `ReorderToolAttributes` codemods. They
are exposed via that package's `CANONICAL_CODEMODS` tuple.

- **`format_tool_document` is now cosmetic-only.** It no longer imports
  `galaxy-tool-xml-codemod`, runs only the three remaining cosmetic
  rules (GTX001 indent, GTX003 blank line, GTX004 empty-element
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
the GTX registry spans both tiers (GTX001–GTX012). The fmt stat page's new
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
