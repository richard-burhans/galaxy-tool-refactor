# Open questions for IUC maintainers (conference)

A running list of policy questions to raise with IUC folks in person. Each entry
states the question, our current provisional behavior, and any corpus data we
have to bring to the conversation. Resolve them upstream, then encode the answer
in the toolchain and delete the entry.

## 1. Version-suffix policy for a multi-tool suite that shares `macros.xml`

**Context.** A real-world formatting/normalization PR that changes an
already-published tool must bump the Galaxy revision suffix, or the toolshed
rejects it (`planemo shed_lint` `ShedVersion`: "version X is less or equal than
the latest installable revision"). The `<base>+galaxy<N>` form is a valid
**PEP 440 local version identifier** (the `+...` segment), so adding or bumping
the suffix never makes the version invalid, and it is the IUC convention.

**The question.** When several tools live in one directory and import a shared
`macros.xml` (e.g. the `vg` suite: `convert.xml`, `view.xml`, `deconstruct.xml`),
and they currently disagree on the suffix, should a change bump the suffix
**per-tool** (each tool's `+galaxy<N>` is independent; a bare `@TOOL_VERSION@`
with no suffix becomes `+galaxy0`) or **suite-wide** (all tools in the suite move
to one suffix = the highest existing suffix in the suite + 1)?

Concretely for `vg` today: `convert.xml` and `view.xml` are bare
`version="@TOOL_VERSION@"` (no suffix); `deconstruct.xml` is
`version="@TOOL_VERSION@+galaxy1"`.
- Per-tool: `convert`/`view` → `+galaxy0`, `deconstruct` → `+galaxy2` (only if
  changed).
- Suite-wide: everyone → `+galaxy2` (max existing `1` + 1), ideally via a single
  shared `@VERSION_SUFFIX@` token in `macros.xml`.

**Our provisional choice:** **suite-wide** (Richard, 2026-06-13), pending the IUC
answer. Rationale: a shared `macros.xml` is the natural place for a single
`@VERSION_SUFFIX@` token, and lockstep suffixes keep a suite's revisions legible.
But it is not obviously right (independent tools arguably deserve independent
revision counters), so confirm before baking it into a codemod.

**Live example (2026-06-15).** Running `galaxy-tool-refactor upgrade` over a real
published-tools repo (the author's `galaxytools`) makes this concrete. The upgrade's
changes were correct (canonical formatting plus the `profile=` bumps validity strictly
required, and the repo's own forward gate confirmed canonical form), but the PR could
not land: `planemo shed_lint` raised `ShedVersion` on all six changed tools, because
each is already installable on the ToolShed, so any content change needs a
`@VERSION_SUFFIX@` bump first (e.g. `1.4.22+galaxy7 → +galaxy8`). We closed that PR
rather than auto-bump, because bumping a published tool's revision (and the per-tool
vs suite-wide policy below) is a "publish a new revision" decision, not a
behavior-preserving auto-fix. This is exactly why the version-suffix codemod (N2)
stays blocked on this answer: the toolchain can canonicalize a published tool, but it
cannot land that change without the revision-bump policy you own.

**Data to bring (the measure, run 2026-06-13).** Our hypothesis was that most
tools already use `version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"` with *both*
tokens imported from a shared `macros.xml`, which would make a shared-suffix token
the path of least resistance. `scripts.measure version-suffix-shape` over the
combined corpus (9,373 unique tools; 8,903 with a `version=`) gives a qualified
yes:

```
uv run python -m scripts.measure version-suffix-shape
```

- two-token form (`@A@+galaxy@B@`): 2,248 (25.2%), of which 1,973 use the
  canonical `@TOOL_VERSION@+galaxy@VERSION_SUFFIX@` names;
- of those two-token tools, **73.9% import both tokens from a macros file**
  (1,661); 20.1% define them inline; 5.9% mixed;
- but the single most common shape across the whole corpus is still **literal,
  no galaxy suffix** (47.9%, largely older ToolShed tools); bare token 7.8%;
  token-base + literal `galaxyN` 6.2%; literal base + `galaxyN` 3.3%.

So the hypothesis holds in a qualified way: among tools that *do* tokenize the
version, importing both tokens from `macros.xml` is overwhelmingly the norm
(73.9%), which supports a single shared `@VERSION_SUFFIX@` token for a suite; but
tokenized versions are a ~25% minority overall, because the long tail of older
literal-version ToolShed tools dominates.

**Specific things to ask:**
- Per-tool vs suite-wide suffix when tools share a macros file?
- Is `+galaxy0` the right starting suffix for a first wrapper revision, or
  `+galaxy1`?
- For a suite, do you prefer one shared `@VERSION_SUFFIX@` token, or per-tool
  tokens/literals?

## 2. Should text-parameter quoting be blanket, or behavior-preserving?

**Context.** The IUC rule reads "all Cheetah variables for **text parameters,
input and output files** must be single-quoted." Input/output **file** variables
are a single, Galaxy-controlled path token, so quoting them is always
behaviour-preserving, and we auto-fix them (GTR020.1). **Text** parameters are
not: their rendered value is author/user text, and quoting some of them *changes*
the command line. We measured the text-param subset and found only **1.2%**
(`scripts.measure text-param-quotable`) are provably safe to auto-quote; the rest
have a real failure mode if quoted:
- a default value that is multiple shell words (`--flag x`) collapses into one
  argv token when quoted;
- an empty value emits a stray `''` argument;
- a space-prefixed value keeps a literal leading space.

So we auto-quote only the provable subset and leave the rest as an **advisory**
(GTR020.2) rather than rewriting them. We also read the rule's scope as **files +
text only**, we do *not* quote selects, numbers, booleans, metadata attributes,
or Galaxy built-ins (a reviewer on featureCounts PR #8090 flagged inconsistent
select quoting; we removed it).

**The question(s).**
- Does IUC intend text-param quoting to be **unconditional** (quote them all,
  accepting that some change the rendered command line), or is
  **behaviour-preservation** the priority (quote only when provably safe, advise
  otherwise)? Our current choice is the latter.
- Confirm the **scope**: is the rule really just text params + input/output
  files, and selects/numbers/booleans/built-ins are intentionally *out* of scope
  (i.e. should never be auto-quoted)?

**Our provisional choice:** auto-quote provable file/text vars only; everything
else advisory or untouched. Data to bring: `scripts.measure text-param-quotable`
and `scripts.measure command-quoting-kinds`.

## 3. Is `<param>` attribute-order normalization actually wanted?

**Context.** The IUC tool-XML standards document a `<param>` attribute order
(name/argument, then type, format, then the value-ish attributes, then label,
help). We normalize to it (GTR002, `ReorderParamAttributes`,
https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html).
On featureCounts PR #8090 a maintainer (bernt-matthias) pushed back that the
attribute reordering was unnecessary. The documentation *does* specify an order,
so the maintainer's objection runs against the written standard, which is
exactly the kind of mismatch to resolve in person rather than in a PR thread.

**The question.** Is attribute-order normalization genuinely desired (worth a
codemod that touches many lines), or is the documented order an aspirational
guideline maintainers would rather not see enforced as reordering churn on
existing tools? If desired, is the documented order the canonical one we should
normalize to?

**Our position:** we follow the documented order (GTR002) and keep the
reordering. Confirm upstream so the codemod's default is unambiguously endorsed
(or downgrade it to advisory if the community prefers not to churn attribute
order on existing tools).

**Connected to §7 (the deeper point).** For attribute-order normalization to
actually *work* — rather than churn forever — two things have to be true: IUC
must bless a single canonical order (this question), AND tools-iuc must run that
normalization automatically on every incoming tool/PR (§7's forward-enforcement
gate). A one-shot reorder of existing tools decays the moment new tools land in
the author's own order, so we would re-fix the same files forever. So §3 and §7
are really one decision: bless the canonical order, then enforce it at the point
of entry.

**Data to bring (the churn, from the committed corpus stats).** GTR002
(`ReorderParamAttributes`) over the combined corpus
(`docs/corpus_check_stats.md` / `docs/corpus_rule_stats.md`):

- **6,639 of 9,304 tools (71.4%)** have at least one `<param>` whose attribute
  order differs from the documented convention (37,462 attribute-reorder findings
  total); the per-rule sweep modifies **6,087 of 8,622** validatable tools.

So only ~29% of tools already match the documented order, and enforcing it touches
~71% — a lot of diff churn on existing tools. That is exactly the tension to
settle: the written standard prescribes an order almost no existing tool fully
follows, so is enforcement wanted, or is the documented order aspirational?

**Note to self:** do not relitigate this in the #8090 thread; raise it in person.

## 4. Is the blank line between top-level `<tool>` sections actually wanted?

**Context.** Our formatter inserts one blank line between consecutive top-level
children of `<tool>` (`<description>`, `<requirements>`, `<command>`, `<inputs>`,
…) for readability — GTR003 (`BlankLineBetweenSections`). Unlike the indentation /
empty-element rules, **this one has no external citation** (`cite=None`): it came
from our own `PLAN.md` editorial guideline ("one blank between sibling top-level
sections, no blank inside dense leaf sequences"), not from the IUC standard. A
reviewer never asked for it, and it changes the serialized bytes of essentially
every tool we format.

**The question.** Does IUC want a blank line between top-level sections as a
house convention (worth a formatter enforcing it), or is vertical spacing an
author's call that a formatter should leave alone?

**Our provisional choice (2026-06-14):** **stop emitting it** — GTR003 is parked
(removed from `all_rules()`, kept in source for a one-line re-enable, fmt
`docs/decisions.md` §D4) pending this answer. We would rather not impose an
uncited convention on every tool; if IUC wants it, re-enabling is trivial.

**Data to bring (the measure, run 2026-06-14).** `scripts.measure
blank-line-adoption` scans the *source* whitespace between top-level sections of
every unique corpus tool (a boundary "has a blank line" when its gap holds a blank
line in the author's file — independent of our formatter):

```
uv run python -m scripts.measure blank-line-adoption
```

- **9,371** tools have at least one top-level section boundary;
- only **13.3%** of all section boundaries (9,798 / 73,504) already carry a blank
  line;
- **70.0%** of tools use a blank line at **no** boundary; 25.6% at some; only
  **4.4%** at every boundary.

So the convention is **not** a community norm — the large majority of authors do
not use it. That is the core evidence for parking it: we should not be the only
thing inserting a separator 70% of authors leave out, with no IUC citation behind
it.

**Specific things to ask:**
- Do you want a blank line between top-level sections as a house style?
- If yes, every boundary, or only between "major" sections?
- If no, confirm a formatter should preserve author vertical spacing rather than
  normalize it.

## 5. Should attributes always be on one line, or may `label`/`help` wrap?

**Context.** Our formatter puts every element's attributes on a single line. The IUC
SHOULD is *stricter-than-us in one direction and looser in another*: it documents
one-line attributes but explicitly **allows `label` and `help` to wrap onto their own
line "for large XML elements."** Our canonical form has no exception, so we collapse
that wrap. This is an editorial choice on our side with no citation for the *stricter*
rule (the wrap is IUC-sanctioned; we override it).

**The question.** Should the formatter honor the IUC exception and leave a wrapped
`label`/`help` alone (or even normalize *toward* wrapping long ones), or is forcing
one line the preferred house style?

**Our provisional choice:** force one line (no exception), pending this answer.

**Data to bring (the measure, run 2026-06-14).** `scripts.measure attribute-wrapping`
scans the *source* of every unique corpus tool (CDATA/comments stripped) for open tags
that span more than one line:

```
uv run python -m scripts.measure attribute-wrapping
```

- of 9,373 tools, **20.8% (1,945)** use a multi-line attribute layout that our
  one-line rule would collapse (11,350 such tags);
- **19.6% (1,833)** specifically wrap a `label`/`help` attribute — the exact layout
  the IUC SHOULD permits.

So this is **not** a fringe layout: about one tool in five uses the multi-line wrap,
and almost all of that is the IUC-sanctioned `label`/`help` case. We are overriding a
layout the standard explicitly allows, which is worth confirming before we keep doing it.

## 6. Is empty-element shorthand normalization (`<foo></foo>` → `<foo/>`) wanted?

**Context.** We collapse an empty-with-whitespace element to self-closing shorthand
(GTR004). It is an editorial choice (no IUC citation), and near-universal in
well-formatted XML (`black`/`prettier` do the equivalent), so it is low-controversy,
but it is still our own convention.

**The question.** Is normalizing toward `<foo/>` desired as a house style, or should a
formatter leave the author's empty-element form alone?

**Our provisional choice:** keep it (it is a safe, near-universal canonicalization),
but flag that it is uncited.

**Data to bring (the committed stats).** Per `docs/corpus_check_stats.md`, GTR004 flags
**1,584 of 9,304 tools (17.0%)** — those carry at least one empty-with-whitespace
element the rule would collapse (2,790 occurrences). So most tools are already in
shorthand or have no such element; the change touches ~17%.

## 7. Would IUC adopt an automated pre-merge normalization gate?

**Context.** We are designing an auto-fix system for tools-iuc (plan:
`~/.claude/plans/tools-iuc-autofix-system.md`), modelled on Carta Engineering's
LibCST automation. The central lesson is that a one-shot bulk reformat is close to
pointless on its own: reformat every tool today, and new PRs reintroduce drift
tomorrow, so the toolchain re-fixes the same files forever — pure review churn that
never converges. The durable answer is two cooperating halves that run the *same*
blessed rule subset: a one-shot bulk normalizer (clears the backlog) AND a
**forward-enforcement gate** — an automated step that runs the blessed, behaviour-
preserving, IUC-blessed rule subset on every incoming PR, over just the changed
tools, before merge. This is what makes §3 (attribute order) and the other
canonicalization questions actually enforceable rather than aspirational.

**The question(s).**
- Would IUC adopt a required CI check / GitHub Action in tools-iuc that runs a
  blessed subset of our cosmetic, behaviour-preserving rules on every PR?
- If so, should it **auto-normalize** (the action rewrites the changed tools to
  canonical and pushes the fix onto the PR branch / posts a suggestion — lowest
  author friction) or **block-until-canonical** (the check fails with the exact
  local fix command — authors stay in control of their branch)?
- Which rules belong in such a gate on day one? Our position: only rules that are
  both provably behaviour-preserving AND have a blessed canonical form. Indentation
  qualifies immediately; attribute order (§3) cannot enter the gate until IUC
  blesses the order; uncited house conventions (§4 blank lines, §5 attr-wrapping,
  §6 shorthand) only if IUC adopts them as standards.

**Why this is an easier ask than an open-ended PR-bot.** A gate only ever touches
code the author is *already* changing — no unsolicited mass PRs — and it makes
"canonical" objective and self-service, removing the need for reviewers to nitpick
formatting by hand. It is also the only thing that lets the bulk pass run *once*
instead of forever.

**Our provisional design choice.** Ship the gate as a reusable, version-pinned
Action wrapping the same `galaxy-tool-refactor` release the bulk pass uses, so the
two halves provably agree. Bulk PRs land human-in-the-loop at a conservative
cadence; the gate keeps the result clean.

**Data to bring (the measure, run 2026-06-14).** `scripts.gate_reaccumulation`
evaluates each recently merged PR in its **merged (`head`) state** — the bytes
that actually landed — and asks whether the gate's rule subset would still flag
it. A flagged merged PR is one whose author left the tool non-canonical even
after a full human review cycle: direct evidence the backlog re-accumulates.

```
uv run python -m scripts.fetch_iuc_prs --state closed --merged-only \
    --corpus-name galaxyproject__tools-iuc__merged --limit 0
uv run python -m scripts.gate_reaccumulation
```

Over **452** merged PRs that touched a `<tool>` file (of 459 fetched before the
GitHub rate limit deferred the rest), the share whose merged result the gate would
still flag:

- **cosmetic gate** (indent + shorthand): **78.8%** (356/452);
- **full behaviour-preserving gate**: **96.7%** (437/452);
- **full, minus the contested attribute order (GTR002)**: **82.3%** (372/452).

So even freshly merged, human-reviewed tools are non-canonical ~97% of the time —
a one-shot bulk pass would start decaying immediately, which is the case for a
forward gate. The argument does **not** depend on winning the attribute-order
debate: dropping GTR002 it is still 82.3%, and a whitespace-only gate alone is
78.8%. **65** PRs (14.4%) are flagged *only* by attribute order — the exact
population an IUC canonical-order decision (§3) would unlock for the gate.

Read it honestly: "non-canonical" means "differs from our canonical form," not
"defective" — the dominant drivers are attribute order (410 PRs) and indentation
(348). But there is real substance beyond cosmetics: GTR020.1 (provable command-
variable quoting) still fires on 66 merged PRs and GTR019.1 (CDATA-wrap `<help>`)
on 25 — behaviour-preserving safety/structure fixes that landed un-applied even
after review. Full breakdown: `docs/gate_reaccumulation_stats.md`.

**Specific things to ask:**
- Appetite for a required formatting/normalization check at all?
- Auto-normalize vs. block-until-canonical?
- Which rule subset is acceptable on day one, and who owns the blessed list?
