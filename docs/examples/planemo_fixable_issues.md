# Issues planemo *reports* that we *fix*

`planemo lint` (via `galaxy.tool_util.linters`) is report-only — it tells an author a
tool has a problem, but the author fixes it by hand. This project's differentiator is
**auto-fixing** the subset where a fix is provably safe. This page shows a real
before/after for each such fix, paired with the planemo linter it covers and how many
corpus tools it touches.

> **Scope & honesty.** The candidate list comes from
> [`docs/planemo_linter_parity.md`](../planemo_linter_parity.md) (the full 146-linter
> map). Each row's "can we *safely* fix it?" is decided per-rule when it's built — the
> same behaviour-preservation discipline as everywhere else
> ([`soundness.md`](../guide/soundness.md)). Sometimes the homework says *no* and we
> keep it advisory instead of fixing — that outcome is recorded here too, because
> declining to change a tool's identity is itself the right answer.

Status legend: **✅ Shipped** (runs under `format` today) · **🔭 Planned** (a FIX
candidate not yet built) · **🛑 Advisory-by-design** (planemo flags it; we *detect* but
deliberately don't auto-fix — doing so wouldn't be behaviour-preserving).

---

## ✅ GTR035 — leading/trailing whitespace in `name` / `requirement version`

**Covers planemo:** `ToolNameWhitespace`, `RequirementVersionWhitespace`
(`galaxy.tool_util.linters.general`).

A display `name` or a conda `<requirement>` `version` accidentally padded with
whitespace. planemo warns *"…is pre/suffixed by whitespace, this may cause errors"*; we
trim it under `format`.

**Before:**
```xml
<tool id="demo" name="My Demo Tool " version="1.0">
    <requirements>
        <requirement type="package" version=" 1.20 ">samtools</requirement>
    </requirements>
```
**After `galaxy-tool-refactor format`:**
```xml
<tool id="demo" name="My Demo Tool" version="1.0">
    <requirements>
        <requirement type="package" version="1.20">samtools</requirement>
    </requirements>
```

**Why it's safe:** the `name` is display-only (surrounding whitespace renders to
nothing); a `requirement version` with whitespace can't resolve in conda, so a
*working* tool never has one — trimming only ever repairs an already-broken
requirement. **Corpus:** 26 tools carry the issue (`docs/corpus_check_stats.md`);
GTR035 fixes **20** in the codemod sweep — **0 non-idempotent, 0 post-validate-failed**
(`docs/corpus_rule_stats.md`).

## 🛑 `id` / tool `version` whitespace — detect, don't fix

**Covers planemo:** `ToolIDWhitespace`, `ToolVersionWhitespace`.

The same accidental whitespace, but on a `<tool>`'s `id` or `version`. We do **not**
auto-trim these: Galaxy uses both *raw* as the tool's identity / version key
(`tool_util/parser/xml.py` `parse_id`/`parse_version` don't strip; `Tool.id` is the
registration key), so trimming would change a *working* tool's identity — not
behaviour-preserving. This is the honest split of the planemo "whitespace" cluster:
two attributes we fix, two we (will) only flag. (Advisory rule: planned.)

---

## 🔭 `<output>` → `<data>` / `<collection>`

**Covers planemo:** `OutputsOutput` ("Avoid the use of 'output' and replace by 'data'
or 'collection'").

**Before:**
```xml
<outputs>
    <output name="out" format="txt"/>
</outputs>
```
**Planned fix (codemod):**
```xml
<outputs>
    <data name="out" format="txt"/>
</outputs>
```
A tag rename to the modern element. Homework needed: confirm `<output>` is a pure alias
for `<data>` (vs `<collection>`) so the rename is behaviour-preserving.

## 🔭 Drop a redundant `name` when `argument` implies it

**Covers planemo:** `InputsNameRedundantArgument`.

**Before:**
```xml
<param argument="--threads" name="threads" type="integer"/>
```
**Planned fix (codemod):**
```xml
<param argument="--threads" type="integer"/>
```
Galaxy derives the `name` from `argument` (`--threads` → `threads`); the explicit
`name` is redundant. Homework needed: verify Galaxy's derivation yields exactly the
declared name before dropping it.

## 🔭 Deprecated `<options>` / select attributes

**Covers planemo:** `InputsSelectDynamicOptions` (deprecated `dynamic_options=`),
`InputsSelectOptionsDeprecatedAttr`.

A `<param type="select" dynamic_options="...">` or a deprecated `<options>` attribute
rewritten to the current `<options>` form. Homework needed: per-attribute soundness —
some deprecated forms have an exact modern equivalent, some don't.

---

## How this list grows

Each FIX candidate from the parity map becomes a section here once it ships, with a real
`format` before/after and its corpus stat. The roadmap order (cleanest first):
whitespace trims (done) → `<output>`→`<data>` → redundant-`name` → deprecated
select-options. The ~78 *correctness* checks planemo runs (param/validator/conditional/
test rules) are mostly **detect-only** for us too — they need author intent, so they
grow the advisory `check` tier rather than this fixer showcase.
