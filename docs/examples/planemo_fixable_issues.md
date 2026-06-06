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

## ✅ GTR036 — deprecated `<output type="data">` → `<data>`

**Covers planemo:** `OutputsOutput` ("Avoid the use of 'output' and replace by 'data'
or 'collection'").

**Before:**
```xml
<outputs>
    <output type="data" name="out" format="txt"/>
</outputs>
```
**After `galaxy-tool-refactor format`:**
```xml
<outputs>
    <data name="out" format="txt"/>
</outputs>
```

**Why it's safe:** Galaxy routes a `<outputs>` child by tag — an `<output type="data">`
is parsed by the *same* code path as a `<data>` (`tool_util/parser/xml.py`), so the
rename + dropping the redundant `type="data"` is a no-op for Galaxy. **Corpus:** 1
tool carries it; GTR036 fixes it — 0 non-idempotent, 0 post-validate-failed
(`docs/corpus_rule_stats.md`).

**Left advisory (not auto-fixed):** `<output type="collection">` — Galaxy remaps
`collection_type`/`collection_type_source` and fills `type_source` via `unicodify(None)`
when absent, so a literal rename isn't provably equivalent — and `<output>` with no
`type` (an *expression* output, a different kind). Same soundness discipline as the
`id`/`version` whitespace split above.

## ✅ GTR037 — drop a redundant `name` when `argument` implies it

**Covers planemo:** `InputsNameRedundantArgument`.

**Before:**
```xml
<inputs>
    <param argument="--threads" name="threads" type="integer" value="1"/>
</inputs>
```
**After `galaxy-tool-refactor format`:**
```xml
<inputs>
    <param argument="--threads" type="integer" value="1"/>
</inputs>
```

**Why it's safe:** Galaxy derives `name` from `argument` when absent
(`_parse_name(None, "--threads")` = `"--threads".lstrip("-").replace("-","_")` =
`"threads"`); we drop `name` *only* when it equals that derived value, so Galaxy
computes the identical name and every `$threads` reference still resolves. And
`param/@name` is optional in all 28 vendored XSDs that allow `argument`, so validity is
preserved for every profile — including novel tool XML. **Corpus:** 343 tools carry it
(1,846 findings); GTR037 fixes **332** — 0 non-idempotent, 0 post-validate-failed
(`docs/corpus_rule_stats.md`).

## 🛑 Deprecated `<options>` / select attributes — detect, don't fix

**Covers planemo:** `InputsSelectDynamicOptions` (deprecated `dynamic_options=`),
`InputsSelectOptionsDeprecatedAttr` (`from_file`/`from_parameter`/`transform_lines`/
`options_filter_attribute`).

On inspection these have **no mechanical modern equivalent**: `dynamic_options=` holds an
arbitrary Python expression, and the deprecated `<options>` attributes require
restructuring (e.g. defining a data table). Migrating them needs author judgment, so —
like the `id`/`version` whitespace and `<output type="collection">` cases above — they
stay **advisory** (planned `check`-tier rules), reported but not auto-fixed.

---

## How this list grows

The auto-fixable subset of planemo's linters is now **complete**: **GTR035** (whitespace
trims), **GTR036** (`<output type="data">`→`<data>`), **GTR037** (redundant `name`).
Every other candidate, on inspection, is either *identity-changing* (`id`/`version`
whitespace) or has *no mechanical modern equivalent* (`<output type="collection">`,
deprecated `dynamic_options`/`<options>` attrs) — so it's **advisory-by-design**, not a
gap. The next planemo-parity frontier is the ~80 *correctness* checks
(param/validator/conditional/test rules): mostly detect-only for us too, growing the
advisory `check` tier rather than this fixer showcase.
