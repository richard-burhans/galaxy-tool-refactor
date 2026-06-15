# Per-rule auto-fix eligibility

> Generated table — regenerate with `uv run python -m scripts.gen_gate_eligibility`
> (a freshness test keeps it in sync). Edit the classification in
> `galaxy-tool-refactor-registry/src/galaxy_tool_refactor_registry/gate_eligibility.py`,
> not this file.

The repository-scale auto-fix system (plan:
`~/.claude/plans/tools-iuc-autofix-system.md`) has two halves that must agree on
which rules they touch: a one-shot **bulk normalizer** that clears a repository's
backlog, and a **forward-enforcement gate** (a pre-merge check — conference §7)
that keeps it clean. Both read the classification below, so a rule the gate
enforces is exactly a rule the bulk pass applies, and vice versa.

A rule is auto-applied (in either half) only when it is **both**
behaviour-preserving **and** has an uncontroversial canonical target form. The
four buckets:

- **gate-eligible** — behaviour-preserving and the canonical form is
  uncontroversial (IUC-cited, or dictated by the XSD). Runs in the bulk pass and
  the forward gate.
- **bulk-only** — behaviour-preserving but an uncited house convention. Offered
  by the bulk pass; not a hard pre-merge gate until IUC adopts it as a standard.
- **blocked-pending-iuc** — behaviour-preserving but the canonical form is
  contested upstream, so it runs in neither half until IUC decides. Today this is
  attribute reordering (param + root `<tool>`), the subject of conference §3.
- **advisory-only** — not auto-fixable (`detect_only`). Reported by `check` and
  pointed at docs; never auto-applied.

`detect_only` rules map mechanically to advisory-only. The fixable rules are each
classified deliberately (a new fixable rule with no classification is a build
error, so nothing silently becomes gate-eligible).

**Scope.** This table covers the registry's *selectable* rule set — the rules
`format` / `check` consider. The upgrade-internal codemods (GTR007–GTR016,
GTR093, driven by `upgrade`) and the opt-in-command codemods (GTR092
`convert-help`, GTR094 `tokenize-version`) are a separate axis: semantic or
opt-in transformations applied by their own commands, never part of a
format-time gate, so they are intentionally out of scope here.

<!-- BEGIN generated gate-eligibility table -->
**89 rules**: 11 gate-eligible · 1 bulk-only · 2 blocked-pending-iuc · 75 advisory-only.

## Fixable rules (the auto-fix surface)

| Bucket | Code | Summary | Rationale |
|---|---|---|---|
| gate-eligible | GTR001 | Canonical 4-space indentation; no tabs. | Canonical indentation; IUC-cited, uncontroversial whitespace. |
| gate-eligible | GTR006 | Repair near-miss spelling typos so a globally-invalid tool validates. | Typo repair that restores XSD validity; the target form is dictated by the schema, not editorial taste (uncited but uncontroversial). |
| gate-eligible | GTR013 | Reorder <tool> child elements to the IUC convention. | <tool> child element order is IUC-documented and xs:all-validity-safe; element (not attribute) reordering. Precondition: the §53 <expand>-pinning fix (verify before any mass run). |
| gate-eligible | GTR017 | Normalize Python-style boolean attribute values (True/Yes/…) to canonical xs:boolean so a globally-invalid tool validates. | Boolean-value normalization that restores XSD validity; schema-dictated form (uncited but uncontroversial). |
| gate-eligible | GTR018.1 | Wrap a pure-text <command> body in CDATA (IUC #34). | Wrap a pure-text <command> body in CDATA; behaviour-preserving, IUC #34. |
| gate-eligible | GTR019.1 | Wrap a pure-text <help> body in CDATA (IUC #42). | Wrap a pure-text <help> body in CDATA; behaviour-preserving, IUC #42. |
| gate-eligible | GTR020.1 | Single-quote provably-single-valued Cheetah variables in <command> (bare single-token params, $__…__ path built-ins, space-free attrs). | Single-quote provably-single-valued command variables; behaviour-preserving provable subset, IUC-cited. |
| gate-eligible | GTR035.1 | Trim accidental leading/trailing whitespace from a <requirement> 'version' (a whitespace-bearing value never resolved — conda gets the spec verbatim; the <tool> 'name' trim is the GTR035.2 advisory). | Trim accidental whitespace in a <requirement> version; behaviour-preserving, IUC-cited. |
| gate-eligible | GTR036 | Replace a deprecated <outputs><output type="data"> with <data>, and <output type="collection"> with <collection> via Galaxy's own attribute remap (expression / degenerate outputs are left for the advisory check). | Modernize a deprecated <output> to <data>/<collection> via Galaxy's own attribute remap; behaviour-preserving, IUC-cited. |
| gate-eligible | GTR037 | Drop a <param> 'name' that equals the name Galaxy derives from its 'argument' (redundant; argument implies the same name). | Drop a redundant <param> name equal to the argument-derived name; behaviour-preserving, IUC-cited. |
| gate-eligible | GTR089.1 | Repair deterministically-fixable invalid <help> reStructuredText (short title underlines, missing blank lines) behind a behaviour-preserving gate. | Repair deterministically-fixable invalid <help> reStructuredText behind a render-equivalence gate; IUC-cited. |
| bulk-only | GTR004 | Collapse empty-with-whitespace leaves to <foo/> form. | Empty-element shorthand is an uncited house convention (conference §6); offer in the bulk pass, do not hard-gate until IUC adopts it. |
| blocked-pending-iuc | GTR002 | Reorder every <param> element's attributes to the IUC convention. | Param attribute order is contested upstream (#8090); needs an IUC canonical-order decision (conference §3). |
| blocked-pending-iuc | GTR005 | Reorder the root <tool> element's attributes to the documented prefix. | Root <tool> attribute order — the same attribute-reordering class as GTR002; confirm in the §3 conversation. |

## Advisory-only rules (75)

Detect-only checks — reported by `check` and pointed at docs, never auto-applied in either half:

`GTR018.2`, `GTR019.2`, `GTR020.2`, `GTR021`, `GTR023`, `GTR024`, `GTR025`, `GTR026`, `GTR027`, `GTR028`, `GTR029`, `GTR032`, `GTR033`, `GTR034`, `GTR035.2`, `GTR038`, `GTR039`, `GTR040`, `GTR041`, `GTR042`, `GTR043`, `GTR044`, `GTR045`, `GTR046`, `GTR047`, `GTR048`, `GTR049`, `GTR050`, `GTR051`, `GTR052`, `GTR053`, `GTR054`, `GTR055`, `GTR056`, `GTR057`, `GTR058`, `GTR059`, `GTR060`, `GTR061`, `GTR062`, `GTR063`, `GTR064`, `GTR065`, `GTR066`, `GTR067`, `GTR068`, `GTR069`, `GTR070`, `GTR071`, `GTR072`, `GTR073`, `GTR074`, `GTR075`, `GTR076`, `GTR077`, `GTR078`, `GTR079`, `GTR080`, `GTR081`, `GTR082`, `GTR083`, `GTR084`, `GTR085`, `GTR086`, `GTR087`, `GTR088`, `GTR089.2`, `GTR090`, `GTR091`, `GTR095`, `GTR098`, `GTR099`, `GTR100`, `GTR101`, `GTR102`
<!-- END generated gate-eligibility table -->
