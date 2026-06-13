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

**Note to self:** do not relitigate this in the #8090 thread; raise it in person.
