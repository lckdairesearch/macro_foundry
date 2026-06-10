# ADR 0015 — Reviewer role consolidation in the gated onboarding workflow

**Status:** Accepted

**Date:** 2026-06-10

## Context

ADR 0011 ratifies the gated onboarding graph and splits the reviewer role
into three parallel specialisations: governance, data correctness, and
selector code. The original rejection rationale for a single-reviewer
alternative was that "governance fit, data correctness, and selector
code review are different specialties with different skill sets and
different appropriate model tiers; forcing them into one prompt risks
underweighting whichever specialty did not happen to drive the prompt's
design."

That rationale was sound when 0011 landed. Since then, ADRs 0013 and 0014
have meaningfully loaded the **governance reviewer specifically** with
new responsibilities:

- 0013 added: review of harmonisation items against the four closed
  triggers, the anti-pattern list, and the per-item evidence structure;
  mutation-matrix awareness; first-in-family scrutiny.
- 0014 added: evaluation of `EnumGapProposal` items against the three
  conditions, the per-proposal evidence schema, and the
  enum-gap-specific anti-pattern list.

Data correctness and selector code review were not affected by 0013 or
0014. The post-0014 reality is therefore "governance got fatter; the
other two are unchanged."

In parallel, the operator has been explicit about cost-consciousness.
Three LLM calls per review cycle is real money, even though the selector
reviewer was already conditional (only runs when
`extraction_mode == custom_python`). The structural-simplification
question is whether collapsing some of the three roles is worth doing.

Two facts shape the decision:

1. **The structural property "reviewer cannot write" is enforced by MCP
   tool binding, not by role count.** Read-only MCP instances expose no
   write tools; any role bound to that instance cannot mutate. Collapsing
   roles does not weaken this guarantee.
2. **Within-role tiering already exists in ADR 0011.** `RoleConfig`
   includes `models_by_task` plus a `task_hint` at the call site,
   allowing different model choices for different kinds of work *inside*
   one role. That mechanism lets us escalate to a code-reviewing model
   for selector-code work without giving selector-code its own role.

The governance / data correctness split, in contrast, is structurally
defensible: they take different inputs (the proposal vs the validator's
parsed sample observations), have different external-tool needs
(governance reads the catalog via MCP; data correctness fetches the
provider's published page to cross-reference one recent observation),
and load disjoint skills. Merging governance into data correctness
would force one role to carry both tool sets and both skill stacks.

## Decision

Consolidate to **two parallel reviewer roles** in v1: `governance` and
`data_correctness`. Fold selector code review into governance as a
**conditional skill load** triggered by `extraction_mode == custom_python`.

**What changes in the role inventory.**

| Before (ADR 0011) | After (this ADR) |
|---|---|
| `governance_reviewer` | `governance_reviewer` |
| `data_correctness_reviewer` | `data_correctness_reviewer` |
| `selector_reviewer` (conditional) | (folded) |

The selector reviewer role no longer exists as its own `RoleConfig`. Its
skill `skill-ingestion-selector-conventions` is loaded onto the
`governance_reviewer` role's prompt when `extraction_mode == custom_python`.

**Within-role tiering for selector code review.** The
`governance_reviewer` role's `models_by_task` map gains a
`"selector_code_review"` task entry that can be configured to a
code-reviewing model (e.g., a model with strong code reasoning) when the
governance call is reviewing a sandboxed selector module. The router
sets `task_hint = "selector_code_review"` on the governance call when
the proposal carries a non-empty `proposed_scripts`. This preserves the
specialty via model choice without giving it a separate role.

**Graph topology.** The parallel fan-out after `draft_proposal` and
`validate_script` is now two reviewers, not three:

```
                ┌──────────────────────────┐
                │  governance_review       │  ← may load
                │  (with conditional       │     selector-code skill
                │   selector-code skill)   │     and use code-review
                └────────────┬─────────────┘     model via task_hint
                             │
draft_proposal ──→ fan-out ──┤
                             │
                ┌────────────┴─────────────┐
                │  data_correctness_review │  ← unchanged
                └──────────────────────────┘
                             │
                             ▼
                       merge findings
                             │
                             ▼
                        gate_1_wait
```

**Findings merge.** With two reviewers instead of three, the merge into
the Gate 1 review bundle is simpler. Findings are surfaced under two
specialty headings (governance, data correctness) instead of three. When
the conditional selector-code skill fires, governance findings include a
selector-code subsection.

**Review loop policy unchanged.** Soft cap of 3 cycles; cycle-3 gate
offers approve / reject / permit-further-cycle, exactly as ADR 0011
specifies.

**Cost calculus.**

| Case | Under ADR 0011 (three roles) | Under this ADR (two roles) |
|---|---|---|
| `config_only` (common) | 2 LLM calls (G + D; S skipped) | 2 LLM calls (G + D) |
| `custom_python` (rare) | 3 LLM calls (G + D + S) | 2 LLM calls (G with selector skill + D) |

The savings is one call in the rare case. The win is **structural
simplicity** (one fewer role config, one fewer parallel node, one fewer
specialty in the merge logic), not raw cost.

This ADR partially amends ADR 0011's reviewer-role decision. The rest of
ADR 0011 — process topology, graph shape, state persistence, catalog
seam, role configuration mechanism, skill loading, approval semantics,
onboarding target — stands unchanged.

## Consequences

**Positive.**

- One fewer role config to author and maintain in
  `src/macro_foundry/agent/roles.py`.
- One fewer parallel node in the review fan-out; one fewer specialty in
  the findings merge.
- Code review and schema review are not collapsed *prompt-wise*; the
  governance prompt loads the selector-code skill body only when needed
  and routes to a code-reviewing model via `task_hint`. The specialty
  separation is preserved via skill loading and model tiering.
- Operator's structural-simplification concern is addressed without
  re-introducing ADR 0011's original underweighting risk (which was
  about *one fat prompt always carrying three specialties*; the new
  design keeps the specialty *conditional* and *model-tiered*).
- Easier to reason about reviewer-side spend (two roles, both tunable
  via per-role and per-task model overrides).

**Negative.**

- The `governance_reviewer` role becomes the heaviest in the system.
  It already carries the most skills post-0013 and 0014; this ADR adds
  one more conditional skill on top. The mitigation is the per-call
  skill loading — no single call carries everything; each call loads
  only what its state predicate evaluates to.
- The risk of underweighting (ADR 0011's original concern) is reduced
  but not zero. When the conditional selector-code skill loads, the
  governance call is asked to balance two specialty stacks (governance
  + selector-code). The `task_hint` routing to a code-reviewing model
  partially mitigates by aligning the model strength with the dominant
  task on that specific call; in practice, the operator should monitor
  whether `custom_python` cases produce weaker governance findings.
- If the operator later finds the merge unacceptable in practice, the
  selector reviewer can be re-introduced as a sibling role via an
  amending ADR. The state schema doesn't change either way.

**Impact on PRD #32 and issue slicing.** Issue #26 ("Add data correctness
and selector code reviewer specializations") under the original PRD #19
is now mis-scoped — selector code review is not a reviewer specialisation
in this design. The follow-on PRD #32 should slice this as "Add data
correctness reviewer specialisation and wire conditional selector-code
skill on governance reviewer."

## Alternatives considered

- **Keep three reviewer roles unchanged.** Rejected because it ignores
  the operator's structural-simplification concern and produces a third
  role config solely for a conditional, rare case. The original 0011
  rationale was about prompt underweighting; that risk can be addressed
  by conditional skill loading and model tiering without paying for a
  separate role.
- **Collapse all three into a single reviewer role.** Rejected. ADR
  0011's original rejection still applies: governance and data
  correctness take different inputs, have different external-tool needs,
  and load disjoint skills. Merging them forces one fat prompt and one
  fat tool set, exactly the failure mode 0011 wanted to avoid. The
  governance reviewer also got *heavier* post-0013/0014, making the fat
  prompt harder to balance, not easier.
- **Two roles split differently: e.g., governance+selector vs data
  correctness.** Rejected. The governance/data-correctness split is the
  one that matters structurally (different inputs, different tools,
  different external-fetch behaviour). Splitting selector off from
  governance reintroduces a reviewer role for a conditional rare case;
  splitting data correctness off from governance is what this ADR
  already does.
- **Hard cap of one LLM model across all reviewers, ignore tiering.**
  Rejected. ADR 0011 already supports per-role and within-role tiering;
  using it is the right answer for managing cost without role-count
  changes.
- **Tiered cascade: cheap classifier first, then deep review only on
  flagged specialties.** Rejected for v1 as additional complexity for
  small gain. The conditional selector skill already provides
  state-predicate-gated loading; adding a meta-classifier layer is a
  premature optimisation.
