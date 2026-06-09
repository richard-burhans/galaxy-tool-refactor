# reStructuredText `<help>` codemods — feasibility investigation

**Question.** Can we do for `<help>` reStructuredText (RST) what the Cheetah subsystem did for
`<command>` — i.e. support **RST codemods**? Three goals were posed: **(1) auto-fix invalid RST**,
**(2) normalize/format RST**, and **(3) convert valid RST → Markdown** (so further help-codemod work
can happen in Markdown, which — unlike RST — has faithful, source-mapped parsers).

**Verdict (lead).** *Chase the auto-fix of invalid RST* — a **general, class-based repair** of the
deterministically-fixable docutils error classes, shipped as a **`GTR089.1` partition-fix** (the
fixable `.1` half; GTR089 stays the advisory `.2` residual), mirroring GTR018/019/020. It repairs
the corpus's deterministically-fixable invalid help *and any novel tool* exhibiting those classes.
**RST→Markdown** is a strong *secondary* (75 % convert with no fix; the gateway to tractable help
codemods) but is **behaviour-changing → opt-in/upgrade-style**, deferred. **Normalize is not
recommended** (no canonical RST style; changes rendering; low value).

> **SHIPPED (2026-06-09).** `RepairHelpRst` (**GTR089.1**) is live in the default `format`
> pipeline; the old `GTR089` advisory became the **GTR089.2** residual. A corpus `format` sweep
> repairs **54 tools** (`scripts.corpus_check codemod …RepairHelpRst`: 8607 idempotent, 0
> non-idempotent, 0 validity breaks). That is **below** the ~62 *raw fully-fixable* estimate
> below because the shipped **render-equivalence gate** is stricter than the raw class match — it
> vetoes any edit that changes the rendered doctree, e.g. dropping a trailing `----` transition
> (docutils renders it as an `<hr>`). Code: tier-1 `galaxy_tool_xml.rst` (§23), codemod §37,
> check D31. The "Design sketch" below is the plan that was executed.

---

## What made the Cheetah work tractable — and the RST blocker

Cheetah did **not** parse-and-reserialise. A faithful CT3-parser subclass records the exact
`[start,end)` byte span of every construct (`galaxy-tool-xml/.../cheetah_cdm.py`), so gaps + spans
reconstruct the source unchanged; mutation is **surgical character-span edits** on the original text
(`cheetah_rename._apply_edits`) under a **plan-then-apply atomic bail** (compute all sites; change
nothing on any uncertainty). The enabler was a tokenizer returning **offsets into the unchanged
source** — because Cheetah has no faithful pretty-printer.

**docutils gives a doctree but (a) no faithful RST writer** (its writers target HTML/LaTeX/XML — there
is no RST round-trip) **and (b) no reliable character offsets** on nodes (only a coarse `.line`,
`.rawsource` without position). So **parse → mutate → reserialise RST is out** — exactly the problem
the Cheetah lexer was built to avoid. Both viable paths stay *surgical*: **the fixer** edits the RST
source at the **line the docutils reporter names**; **the converter** transduces the doctree to a
*different* format (Markdown), so it never needs an RST writer.

**The Markdown target is pinned.** Galaxy renders `<help format="markdown">` client-side via
`client/src/components/ObjectStore/configurationMarkdown.ts` → `markdown-it ^14` (`client/package.json`)
with `MarkdownIt({ html: false }).render(...)` — the **"default" preset (CommonMark + GFM tables +
strikethrough)**, no plugins, and **raw HTML disabled** (so a converter must emit pure markdown-it
Markdown and must **not** fall back to raw HTML — it would render as escaped text).

---

## The data (corpus, deduped; reproduced by the standing measures)

All three are corpus-dependent (not run in CI), pinned by synthetic-fixture tests in
`galaxy-tool-xml/tests/test_measure.py`.

### `help-rst-errors` — 7,348 RST `<help>` bodies (non-macro, deduped)

- **193 invalid** (≥1 docutils message at level ≥ 2, ~GTR089); 274 info-only (sub-threshold);
  0 parse failures.
- **62 (32 % of invalid) are *fully* fixable** — every serious error is in the deterministic-fix
  class set below. (More tools are *partially* fixable — a mix of fixable + ambiguous errors.)
- **Fixable classes** (`*`; general recipe each): the *"`<block>` ends without a blank line; unexpected
  unindent"* family (block quote 24 tools, definition list 13, explicit-markup 9, line block 10,
  option list 8, bullet list 7, literal block 6) → **insert the missing blank line** at the reported
  line; *Title underline / overline too short* (16 + 5) → **extend the underline to ≥ title length**;
  *Transition at the end of the document* (14) → **drop the trailing transition line**.
- **Ambiguous residual** (stays GTR089 advisory): *Unexpected indentation* (82 tools — the dominant
  class), *Unexpected section title* (8 + 5), *unclosed inline markup* (strong 10 / emphasis 8 / …),
  *Literal block expected; none found* (12), *Inconsistent literal block quoting* (4).

### `help-rst-features` — RST node inventory

Blocking (non-CommonMark) features, by tools using them: **definition_list 800**, **line_block 520**,
**table 479**, **title_reference (the `` `x` `` default role) 358**, **field_list 254**, option_list
118. These are real RST constructs with no markdown-it-default equivalent.

### `help-rst-to-markdown` — RST→MD convertibility 2×2

| | MD-convertible shape | complex (non-CommonMark) |
|---|---|---|
| **valid RST** | **5,474 (74.5 %)** — convert today | 1,681 (22.9 %) — bail |
| **invalid RST** | 84 (1.1 %) — fix-then-convert | 109 (1.5 %) |

(`pandoc` is **not** on PATH; and pandoc's RST→MD dialect ≠ markdown-it anyway.)

---

## Per-goal verdict

### (1) Auto-fix invalid RST — **CHASE THIS (general, not corpus-overfit)**

A **`GTR089.1` partition-fix** (`RepairHelpRst`) that applies a **deterministic recipe per docutils
error class**, anchored on the reporter's **line number** (the surgical analogue of Cheetah, since
RST has no faithful writer). The recipes are **class-general** — they repair *any* tool with the
class, never enumerated corpus instances; the corpus only **sizes** the win and **retains real
failures as regression fixtures** (the project's codemod pattern). **~62 corpus tools fully repaired**
today + partial on mixed tools + every novel offender.

**Atomic-bail safety** (the Cheetah contract): apply the edit → **re-parse with docutils** → keep it
only if the targeted error is gone **and no new error appeared**; else bail (change nothing). These
fixes make implicit structure explicit (a blank line, a longer underline, a dropped end-transition)
and are behaviour-preserving — but the re-parse gate proves it per tool rather than trusting it.

### (2) Normalize RST — **not recommended**

No canonical RST style exists, it changes rendered output, and the value is cosmetic. Skip.

### (3) Convert valid RST → Markdown — **strong secondary, deferred (opt-in)**

**74.5 % convert with no fix** — the gateway that makes *future* help codemods tractable (Markdown
has source-mapped CommonMark parsers; the Cheetah-style surgical edit works there, not in RST). But it
is **behaviour-changing** (server-side RST→HTML becomes client-side markdown-it render), so it is an
**opt-in / `upgrade`-style** codemod that sets `format="markdown"`, **never canonical/auto**.
Converter = a **hand-rolled doctree → CommonMark writer** (no faithful RST writer; pandoc absent),
**bailing** on the 22.9 % complex (definition lists, tables, line blocks, field/option lists,
interpreted-text roles) and on invalid RST. A **markdown-it-py** semantic-equivalence gate
(render the MD, compare normalised HTML to docutils' RST→HTML) is the convert-time atomic bail.

*Note on the user's fix→convert→MD-codemod pipeline:* sound in spirit, but the data says the **convert
step is the value** (5,474 already convertible); fixing first adds only **+84** to the convertible pool
(1.1 %). So fixing and converting are **independent wins** to pursue on their own merits, not a strict
chain.

---

## Design sketch (the build — SHIPPED 2026-06-09; this is the plan that was executed)

- **Tier 1** — a `help_text` accessor (none today; help is `root.find("help").text`) + an
  `rst_repair` module: per-class, line-anchored surgical edits with the docutils re-validation bail.
- **Tier 2** — `RepairHelpRst` = **GTR089.1** (fixable `.1`); GTR089 becomes the advisory `.2`
  residual (the non-fixable classes). Joins the canonical/format pipeline **iff** the re-parse gate
  certifies behaviour-preservation; otherwise opt-in.
- **Later / opt-in** — the RST→Markdown converter (separate capability; markdown-it-py gate).

## Reproduced by

```sh
uv run python -m scripts.measure help-rst-errors        # R1: fixable error classes + sizing
uv run python -m scripts.measure help-rst-features      # R2: RST node / blocking-feature inventory
uv run python -m scripts.measure help-rst-to-markdown   # R3: convertibility 2x2
uv run --package galaxy-tool-xml pytest galaxy-tool-xml/tests/test_measure.py -k help_rst
```
