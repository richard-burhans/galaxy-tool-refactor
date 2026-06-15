# IUC conversation: canonical form, and a forward gate

Talking points for the in-person IUC conversation, drawn from
[`iuc_conference_questions.md`](iuc_conference_questions.md) §3 (attribute order)
and §7 (the forward-enforcement gate). Speak from these or adapt them; they are
prep material, not a published artifact.

## The frame (one sentence)

§3 and §7 are one decision: **bless a canonical form, then enforce it
automatically at the point of entry.** Either half alone is close to pointless.

## Open with this (sets the tone, heads off the worry)

- **Collaborative.** The goal is to take mechanical maintenance toil off your
  plate so your time goes to the judgment calls only people can make. Not to
  replace maintainers.
- **Deterministic, not agentic AI.** These are provably behavior-preserving
  codemods, each with a written proof, gated on idempotence and validity. Nothing
  is an LLM guessing and hoping it is right. (This is probably the real root of
  any past hesitation, so say it early.)
- **Honest scope.** Of 89 rules, 11 are auto-fixable today and 75 stay advisory.
  We are automating the mechanical surface, and explicitly leaving the judgment to
  humans.

## The core argument (why a gate at all)

- A one-shot reformat decays. New PRs land in the author's own style, so we would
  re-fix the same files forever. That is pure review churn that never converges.
- **The number:** across 452 recently merged, human-reviewed tools-iuc PRs,
  **96.7% are still non-canonical in their merged state.** Even after a full
  review cycle, the backlog rebuilds.
- **It does not hinge on the contested rule:** drop attribute order and it is
  still **82.3%**; whitespace alone is **78.8%**. So the case for a gate stands on
  its own.
- The durable answer is two halves sharing one blessed rule set: a one-time bulk
  pass to clear the backlog, and a pre-merge gate to keep it clean. The gate is
  what makes the bulk pass worth doing.

## §3: attribute order (the specific contested rule)

- The written IUC standard specifies a `<param>` attribute order. In the corpus,
  only ~29% of tools follow it; enforcing it touches ~71% (**6,639 of 9,302
  tools, 37,462 findings**). That is real churn, which is exactly why it deserves
  a deliberate decision rather than a PR-thread argument.
- Handle the prior pushback gracefully: one reviewer preferred not to reorder, the
  written standard does specify an order, and that mismatch is precisely what we
  would like the group to settle. (No names, no blame. Just "let us resolve the
  standard-versus-practice gap together.")
- **The two asks:**
  1. Is attribute-order normalization actually wanted, or is the documented order
     aspirational?
  2. If wanted, is the documented order the canonical one to normalize to?
- If the answer is "no": completely fine. GTR002 becomes advisory, drops out of
  the gate, and we move on. The gate still does its job via the uncontroversial
  rules.

## §7: the forward gate (the mechanism)

- **Why it is an easy yes:** the gate only ever touches code the author is already
  changing. No unsolicited mass PRs. It makes "canonical" objective and
  self-service, and it frees reviewers from hand-nitpicking formatting.
- **The three asks:**
  1. Appetite for a required formatting/normalization check at all?
  2. **Auto-normalize** (the action fixes the branch or posts a suggestion, lowest
     author friction) or **block-until-canonical** (fails with the exact local fix
     command, authors keep control of their branch)?
  3. Which rules on day one, and who owns the blessed list? Our proposal: only
     rules that are both provably behavior-preserving and have a blessed canonical
     form. Indentation qualifies immediately; attribute order only after §3; the
     uncited house conventions (blank lines, attribute wrapping, shorthand) only
     if you adopt them as standards.
- **Design note to offer:** ship it as a version-pinned GitHub Action wrapping the
  same `galaxy-tool-refactor` release the bulk pass uses, so the gate and the bulk
  pass provably agree on what "canonical" means.

## Soundbites to keep handy

- "96.7% of just-merged tools are already non-canonical, so a one-time cleanup
  decays the day after."
- "The gate only ever touches what you are already editing."
- "Deterministic codemods with proofs, not an AI guessing."
- "Eleven rules auto-fixable, seventy-five advisory: we automate the toil, you
  keep the judgment."
- "Sixty-five PRs differ only in attribute order. That is the exact thing your
  decision unlocks."
- "We ran the upgrade on a real published-tools repo: the fixes were correct and the
  gate passed, but it could not land without a version-suffix bump. That bump is your
  policy call, not something we should auto-apply."

## The decisions we want to walk away with

1. Attribute order: enforce (and confirm the canonical order), or advisory-only?
2. A pre-merge gate: yes or no?
3. If yes: auto-normalize or block, plus the day-one rule list and who owns it.
4. (If time) the §1 suffix-bump policy, since any content change to a published tool
   needs it. Live proof: a real `upgrade` of the author's `galaxytools` was correct but
   blocked by `planemo shed_lint` `ShedVersion` on all six tools — the version-suffix
   codemod (N2) stays blocked on this answer.

## Backing data (have it on a laptop, do not lead with it)

- Re-accumulation: `docs/gate_reaccumulation_stats.md` (the 452-PR run).
- Per-rule eligibility: `docs/gate_eligibility.md` (the 11 / 1 / 2 / 75 split).
- Attribute-order churn: `docs/corpus_check_stats.md` / `docs/corpus_rule_stats.md`
  (GTR002).
- Full question write-ups: `docs/iuc_conference_questions.md` §3 and §7.
