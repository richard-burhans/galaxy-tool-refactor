// Escalation workflow template for the /architecture-audit skill.
//
// Multi-agent re-derivation + adversarial verification of an architectural audit.
// Pass this to the Workflow tool (inline `script`, or save + use `scriptPath`).
// ADAPT the three marked blocks to the target repo, then run. Requires a baseline
// ARCHITECTURE.md and an existing single-pass docs/architecture_audit.md.
//
// Shape: Find (tier + dimension finders) -> Verify (one adversarial refuter per
// finding, pipelined so each finder's findings verify as soon as it returns) ->
// Synthesize (dedup; separate new / re-confirmed / refuted). The MAIN LOOP, not
// this workflow, integrates the synthesised report into the audit doc.

export const meta = {
  name: 'architecture-audit-escalation',
  description: 'Multi-agent re-derivation + adversarial verification of an architectural audit',
  phases: [
    { title: 'Find', detail: 'tier-scoped + dimension-scoped finders re-derive findings against the baseline' },
    { title: 'Verify', detail: 'one adversarial refuter per finding (default: refute)' },
    { title: 'Synthesize', detail: 'dedup, correct severities, separate new / re-confirmed / refuted' },
  ],
}

// ── ADAPT 1: paths ──────────────────────────────────────────────────────────
const ROOT = '/absolute/path/to/repo'
const BASELINE = `${ROOT}/ARCHITECTURE.md`
const EXISTING = `${ROOT}/docs/architecture_audit.md`

// ── ADAPT 2: the seven dimensions (usually unchanged) ───────────────────────
const DIM_ENUM = ['boundary-integrity','abstraction-consistency','naming-drift','contract-enforcement-gap','duplication-missed-reuse','dead-reserved-surface','doc-code-agreement']

// ── ADAPT 3: scouts — one tier scout per package/layer, plus the dimension scouts.
const TIER_SCOUTS = [
  { scope: 'tier0.5+1 (shared vocab + foundation)', dirs: 'PACKAGE_A, PACKAGE_B', focus: 'source-of-truth ownership; dependency-freedom of the shared tier; result-type conventions.' },
  { scope: 'tier2 (structure)', dirs: 'PACKAGE_C', focus: 'the core command/visitor abstraction; mutation primitives; pipeline contracts.' },
  // ... one entry per layer/package; keep `focus` specific to that layer's contracts.
]
const DIM_SCOUTS = [
  { scope: 'dimension: boundary-integrity', focus: 'Read every dependency manifest AND grep actual imports. Confirm no layer imports a higher one or a forbidden sibling. Flag unused declared dependencies and hidden coupling via shared mutable state.' },
  { scope: 'dimension: contract-enforcement-gap', focus: 'For each invariant asserted in prose (the baseline + the CLAUDE.md/ADR files), decide whether a TEST or lint actually guards it. List invariants with NO guard.' },
  { scope: 'dimension: duplication-missed-reuse', focus: 'Parallel implementations that should share; note where a shared helper would violate a dependency rule.' },
  { scope: 'dimension: naming-drift + doc-code-agreement', focus: 'Concepts named differently across layers; one verb meaning two things. Verify the baseline`s symbol tables and decision-section citations actually resolve; spot-check each package doc against its code.' },
]
// ────────────────────────────────────────────────────────────────────────────

const FINDINGS_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    scope: { type: 'string' },
    findings: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      properties: {
        title: { type: 'string' },
        dimension: { type: 'string', enum: DIM_ENUM },
        severity: { type: 'string', enum: ['high','medium','low'] },
        locations: { type: 'array', items: { type: 'string' }, description: 'file:line (repo-relative)' },
        invariant: { type: 'string' },
        evidence: { type: 'string', description: 'concrete proof from the code' },
        recommendation: { type: 'string' },
        status_vs_existing: { type: 'string', enum: ['new','reconfirms-existing'] },
      },
      required: ['title','dimension','severity','locations','invariant','evidence','recommendation','status_vs_existing'],
    } },
  },
  required: ['scope','findings'],
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    verdict: { type: 'string', enum: ['confirmed','partially-confirmed','refuted'] },
    corrected_severity: { type: 'string', enum: ['high','medium','low','none'] },
    reasoning: { type: 'string' },
    evidence_checked: { type: 'string', description: 'files/lines opened to adjudicate' },
  },
  required: ['verdict','corrected_severity','reasoning','evidence_checked'],
}

const preamble = `You are auditing the monorepo at ${ROOT}. The architectural BASELINE (what the abstractions are SUPPOSED to be) is ${BASELINE} — read it first. The EXISTING single-pass audit is ${EXISTING} — read it so you do NOT merely repeat it: hunt for NEW issues it missed AND independently re-judge whether its claims hold (mark those 'reconfirms-existing'). Read real source — open files, grep, cite file:line. Be skeptical and concrete; do not invent issues. An empty findings list is a valid, honest answer. Dimensions: ${DIM_ENUM.join(', ')}.`

phase('Find')

const finders = [
  ...TIER_SCOUTS.map(s => () => agent(
    `${preamble}\n\nYOUR SCOPE: ${s.scope}. Deep-read these dir(s): ${s.dirs}. Examine: ${s.focus}\nReport findings across ANY dimension you can evidence in this scope.`,
    { label: `find:${s.scope}`, phase: 'Find', schema: FINDINGS_SCHEMA, agentType: 'Explore' })),
  ...DIM_SCOUTS.map(s => () => agent(
    `${preamble}\n\nYOUR SCOPE is one cross-cutting DIMENSION swept across ALL packages: ${s.scope}. ${s.focus}`,
    { label: s.scope, phase: 'Find', schema: FINDINGS_SCHEMA, agentType: 'Explore' })),
]

const verifiedBatches = await pipeline(
  finders,
  thunk => thunk(),
  (result) => {
    if (!result || !result.findings || result.findings.length === 0) return []
    return parallel(result.findings.map(f => () =>
      agent(
        `You are an ADVERSARIAL verifier for an architectural audit of ${ROOT}. DEFAULT stance: skepticism — try to REFUTE the finding. 'refuted' if it is intentional-and-documented, already-handled, factually wrong, or a non-issue. 'confirmed' only after opening the cited code yourself and finding the problem real with the right severity. 'partially-confirmed' if real but mis-scoped. When uncertain, lean refuted or downgrade. Read ${BASELINE} and the cited locations; verify every claim against the source.\n\nFINDING:\n- title: ${f.title}\n- dimension: ${f.dimension}\n- claimed severity: ${f.severity}\n- locations: ${(f.locations||[]).join(', ')}\n- invariant: ${f.invariant}\n- evidence: ${f.evidence}\n- recommendation: ${f.recommendation}\n- status vs existing: ${f.status_vs_existing}`,
        { label: `verify:${(f.title||'').slice(0,40)}`, phase: 'Verify', schema: VERDICT_SCHEMA, agentType: 'Explore' }
      ).then(v => ({ finding: f, verdict: v }))
    ))
  }
)

const verified = verifiedBatches.flat().filter(Boolean).filter(x => x && x.verdict)
const survivors = verified.filter(x => x.verdict.verdict !== 'refuted' && x.verdict.corrected_severity !== 'none')
const refuted = verified.filter(x => x.verdict.verdict === 'refuted' || x.verdict.corrected_severity === 'none')
log(`Find: ${verified.length} candidates across ${finders.length} scouts. Verify: ${survivors.length} survived, ${refuted.length} refuted/none.`)

phase('Synthesize')

const SYNTH_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    report_markdown: { type: 'string', description: 'Full escalated-audit report in GitHub markdown. Group surviving findings by dimension, severity-sorted; SEPARATE new findings from independent re-confirmations of the existing audit; include a brief refuted-candidates list. Cite file:line. Use each finding\'s CORRECTED severity. Note independent corroboration (multiple scouts → higher confidence). Be honest if escalation mostly confirms the single pass.' },
    new_high: { type: 'integer' }, new_medium: { type: 'integer' }, new_low: { type: 'integer' },
    reconfirmed: { type: 'integer' }, refuted: { type: 'integer' },
    headline: { type: 'string' },
  },
  required: ['report_markdown','new_high','new_medium','new_low','reconfirmed','refuted','headline'],
}

const payload = JSON.stringify({
  survivors: survivors.map(x => ({ ...x.finding, verdict: x.verdict.verdict, corrected_severity: x.verdict.corrected_severity, verify_reasoning: x.verdict.reasoning })),
  refuted: refuted.map(x => ({ title: x.finding.title, severity: x.finding.severity, why_refuted: x.verdict.reasoning })),
})

return await agent(
  `You are the synthesis lead for an ESCALATED architectural audit of ${ROOT}. The single-pass audit is at ${EXISTING} (read it). Below is the JSON of findings that SURVIVED adversarial verification plus the refuted ones. Produce the report. Rules: dedup aggressively (collapse near-identical findings; note independent corroboration count); use CORRECTED severities; separate (1) NEW findings, (2) independent RE-CONFIRMATIONS of the existing audit, (3) a brief rejected-candidates list; be honest if little is new; cite file:line throughout; keep it scannable.\n\nFINDINGS JSON:\n${payload}`,
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA }
)
